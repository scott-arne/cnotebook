import html as _html
import logging
import re
import typing
import uuid
import weakref
from collections import OrderedDict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from typing import Any, Literal

import oepolars as oeplr  # pyright: ignore
import polars as pl
from oepolars.namespaces.dataframe import DataFrameChemNamespace  # pyright: ignore
from oepolars.namespaces.series import SeriesChemNamespace  # pyright: ignore
from openeye import oechem, oedepict, oegrapheme, oegraphsim

from .align import fingerprint_maker
from .context import create_local_context, get_series_context, pass_cnotebook_context
from .core import formatters as _fmt
from .core.columnops import AlignmentReport
from .core.errors import warn
from .core.table import ColumnKind, RowWindow, polars_row_window, render_table
from .helpers import create_structure_highlighter
from .render import CNotebookContext, oemol_to_disp

get_ipython: Any = None

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython.core.getipython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    get_ipython = None
    ipython_present = False

if typing.TYPE_CHECKING:
    from .context import CNotebookContext
    from .grid import MolGrid

log = logging.getLogger("cnotebook")


@dataclass
class ColumnState:
    """
    Per-token column state.

    :param context: Render context for every cell of the column.
    :param alignment_report: Outcome of the last depiction alignment, when one ran.
    """

    context: CNotebookContext
    alignment_report: AlignmentReport | None = None


# Polars Series are ephemeral, so column state cannot live on the Series. It is keyed by
# the token carried on the column dtype, which survives frame operations and copies.
_STATES: "OrderedDict[str, ColumnState]" = OrderedDict()
_MAX_STATES = 10_000


def new_token() -> str:
    """
    Mint a fresh column token.

    :returns: A token that has never been handed out before.
    """
    return uuid.uuid4().hex


def store_state(token: str, state: ColumnState) -> None:
    """
    Store *state* under *token*, evicting the oldest entries beyond the cap.

    :param token: Column token minted by :func:`new_token`.
    :param state: State to associate with the token.
    """
    _STATES[token] = state
    _STATES.move_to_end(token)
    while len(_STATES) > _MAX_STATES:
        _STATES.popitem(last=False)


def state_for_token(token: str | None) -> ColumnState | None:
    """
    Return the state for *token*, or ``None`` when unknown.

    :param token: Column token, or ``None`` for an untokenized column.
    :returns: The stored state, or ``None``.
    """
    if token is None:
        return None
    state = _STATES.get(token)
    if state is not None:
        _STATES.move_to_end(token)
    return state


def context_for_token(token: str | None) -> CNotebookContext | None:
    """
    Return the render context stored for *token*.

    :param token: Column token, or ``None`` for an untokenized column.
    :returns: The stored context, or ``None`` when the token is unknown.
    """
    state = state_for_token(token)
    return state.context if state is not None else None


def clear_column_contexts() -> None:
    """
    Forget every stored column state.

    Tokens still carried on frames then resolve to fresh local contexts.
    """
    _STATES.clear()


def classify_dtype(dtype: Any) -> ColumnKind:
    """
    Map a Polars dtype to the kind of cell rendering it needs.

    :param dtype: Polars dtype of a column.
    :returns: Column kind; ``ColumnKind.OTHER`` for every dtype rendered as text.
    """
    if isinstance(dtype, oeplr.MoleculeType):
        return ColumnKind.MOLECULE
    if isinstance(dtype, oeplr.DisplayType):
        return ColumnKind.DISPLAY
    if isinstance(dtype, oeplr.DesignUnitType):
        return ColumnKind.DESIGN_UNIT
    return ColumnKind.OTHER


def _dtype_name(dtype: Any) -> str:
    """
    Name a Polars dtype the way the Polars table writer does.

    :param dtype: Polars dtype of a column.
    :returns: ``ext[<name>]`` for the OEPolars extension dtypes, whose ``str()`` would
        otherwise print the internal registry token, and ``str(dtype)`` for the rest.
    """
    if isinstance(dtype, (oeplr.MoleculeType, oeplr.DisplayType, oeplr.DesignUnitType)):
        return f"ext[{dtype.ext_name()}]"
    return str(dtype)


def configured_max_rows() -> int | None:
    """
    Report Polars' configured table row limit.

    :returns: ``POLARS_FMT_MAX_ROWS`` as an integer, or ``None`` when it is unset.
    """
    # `if_set=True` omits the key when the option was never set; some versions report it
    # with a value of None instead, and `.get()` covers both.
    value = pl.Config.state(if_set=True).get("POLARS_FMT_MAX_ROWS")
    return int(value) if value is not None else None


class PolarsFrameAdapter:
    """
    Frame adapter over a Polars DataFrame (positional column access).

    Columns are addressed by position so that each column keeps one kind and one
    render context, and the underlying Series are captured once per render.
    """

    def __init__(
            self,
            df: pl.DataFrame,
            *,
            ctx: CNotebookContext | None = None,
            formatters: dict[Hashable, Any] | None = None
    ):
        """
        Wrap a DataFrame for rendering.

        :param df: Frame to render; never modified.
        :param ctx: Context overriding every column context, or ``None`` to resolve
            each column's context from its dtype token.
        :param formatters: Optional caller formatters for ordinary columns, keyed by
            column label; their output is escaped by the writer. A formatter aimed at a
            depiction column is ignored, and reported by :func:`render_polars_dataframe`.
        """
        self.df = df
        self._ctx = ctx
        self._formatters = dict(formatters or {})
        self._labels: list[Hashable] = list(df.columns)
        self._series = [df.to_series(pos) for pos in range(df.width)]
        self._kinds = [classify_dtype(s.dtype) for s in self._series]

    def columns(self) -> list[Hashable]:
        """
        Report the column labels in order.

        :returns: Column labels.
        """
        return list(self._labels)

    def kind(self, pos: int) -> ColumnKind:
        """
        Report the kind of the column at *pos*.

        :param pos: Column position.
        :returns: Column kind.
        """
        return self._kinds[pos]

    def nrows(self) -> int:
        """
        Report the frame length.

        :returns: Number of rows.
        """
        return len(self.df)

    def context(self, pos: int) -> CNotebookContext:
        """
        Resolve the render context of the column at *pos*.

        Resolution order: the context passed to the adapter, the state stored for the
        column's dtype token, the legacy id-keyed store, then a fresh local context.

        :param pos: Column position.
        :returns: Render context for every cell of the column.
        """
        if self._ctx is not None:
            return self._ctx
        token = getattr(self._series[pos].dtype, "token", None)
        ctx = context_for_token(token)
        if ctx is not None:
            return ctx
        legacy = get_dataframe_column_context(self.df, str(self._labels[pos]))  # removed in Task 17
        return legacy if legacy is not None else create_local_context()

    def window(self, max_rows: int | None) -> RowWindow:
        """
        Choose the rows to render.

        :param max_rows: ``None`` for the Polars rule, ``<= 0`` for all rows, else the row budget.
        :returns: The row window.
        """
        return polars_row_window(len(self.df), max_rows, configured_max_rows())

    def cell(self, row: int, pos: int) -> Any:
        """
        Return the raw value of one cell.

        :param row: Row position.
        :param pos: Column position.
        :returns: The cell value, or ``None`` for a missing cell.
        """
        return self._series[pos][row]

    def other_cell_text(self, row: int, pos: int) -> str:
        """
        Return the display text of one ordinary cell.

        The writer escapes the returned text, so caller formatters cannot inject markup.

        :param row: Row position.
        :param pos: Column position.
        :returns: Unescaped display text; ``"null"`` for a missing cell, the Polars convention.
        """
        value = self._series[pos][row]
        formatter = self._formatters.get(self._labels[pos])
        if formatter is not None:
            return str(formatter(value))
        return "null" if value is None else str(value)

    def index_text(self, row: int) -> str | None:
        """
        Report the index label of *row*; Polars frames have no index.

        :param row: Row position.
        :returns: Always ``None``.
        """
        return None

    def header_extra_rows(self) -> list[list[str]]:
        """
        Report the extra header rows; Polars shows the column dtypes under the labels.

        :returns: A single row of dtype names, escaped by the writer.
        """
        return [[_dtype_name(dtype) for dtype in self.df.dtypes]]


def create_mol_formatter(*, ctx: CNotebookContext) -> typing.Callable[[Any], str]:
    """
    Closure that renders a molecule cell to HTML.

    :param ctx: CNotebook rendering context.
    :returns: Function that renders molecules to HTML.
    """
    return lambda value: _fmt.molecule_cell_html(value, ctx)


@pass_cnotebook_context
def create_disp_formatter(
        *,
        callbacks: list[typing.Callable[[oedepict.OE2DMolDisplay], None]] | None = None,
        ctx: CNotebookContext
) -> typing.Callable[[Any], str]:
    """
    Closure that renders an ``OE2DMolDisplay`` cell to HTML.

    :param callbacks: Callbacks to apply to the depiction copy instead of the context's own,
        or ``None`` to keep the context's own callbacks.
    :param ctx: CNotebook rendering context.
    :returns: Function that renders display objects to HTML.
    """
    if callbacks is not None:
        # The shared formatter applies ctx.callbacks exactly once on its copy, so the
        # caller's callbacks replace the context's rather than running in addition.
        ctx = ctx.copy()
        ctx.reset_callbacks()
        for callback in callbacks:
            ctx.add_callback(callback)
    return lambda value: _fmt.display_cell_html(value, ctx)


def create_du_formatter(*, ctx: CNotebookContext) -> typing.Callable[[Any], str]:
    """
    Closure that renders an ``OEDesignUnit`` cell to HTML.

    :param ctx: CNotebook rendering context.
    :returns: Function that renders design units to HTML.
    """
    return lambda value: _fmt.design_unit_cell_html(value, ctx)


def escape_formatter(obj: typing.Any) -> str:
    """
    Render an arbitrary value as escaped HTML text.

    :param obj: Value to render; ``None`` becomes the empty string.
    :returns: HTML-escaped text.
    """
    return _html.escape("" if obj is None else str(obj))


def render_polars_dataframe(
        df: pl.DataFrame,
        formatters: dict | None = None,
        col_space: dict[str, float | int] | None = None,
        ctx: CNotebookContext | None = None,
        max_rows: int | None = None,
) -> str:
    """
    Render a Polars DataFrame with molecule-aware cells.

    :param df: Frame to render (never modified).
    :param formatters: Optional formatters for ordinary columns (output is escaped); one aimed
        at a depiction column is reported and ignored.
    :param col_space: Accepted for compatibility and ignored; depiction columns take their width
        from their column context and ordinary columns are not given a minimum width.
    :param ctx: Overrides every column context when given.
    :param max_rows: ``None`` for Polars' configured limit, ``<= 0`` for all rows, else the row budget.
    :returns: HTML table with a dtype header row.
    """
    if col_space:
        warn("render_polars_dataframe sizes depiction columns from their column context; "
             "the col_space argument is ignored")
    adapter = PolarsFrameAdapter(df, ctx=ctx, formatters=formatters)
    if formatters:
        # Depiction cells go through cell_html, so a caller formatter on such a column is
        # silently unused; say so rather than let the caller believe it took effect. The
        # check lives here, not in the adapter, so the warning blames the caller's line.
        for pos, label in enumerate(adapter.columns()):
            if adapter.kind(pos) is not ColumnKind.OTHER and label in formatters:
                warn(f"Overwriting the formatter for column {label!r} with the depiction formatter")
    return render_table(adapter, ctx=ctx, max_rows=max_rows)


########################################################################################################################
# Legacy id-keyed column context store (superseded by the token registry above; removed in Task 17)
########################################################################################################################

# Structure: {id(DataFrame): (weakref(DataFrame), {column_name: CNotebookContext})}
# We store a weak reference to the DataFrame to allow cleanup
_dataframe_column_contexts: dict[int, tuple[weakref.ref, dict[str, CNotebookContext]]] = {}


def _cleanup_dead_contexts() -> None:
    """Remove entries for DataFrames that have been garbage collected."""
    dead_ids = [df_id for df_id, (ref, _) in _dataframe_column_contexts.items() if ref() is None]
    for df_id in dead_ids:
        del _dataframe_column_contexts[df_id]


def get_dataframe_column_context(df: pl.DataFrame, column: str) -> CNotebookContext | None:
    """
    Get the CNotebookContext for a specific DataFrame column.

    :param df: The DataFrame.
    :param column: The column name.
    :returns: The CNotebookContext if one exists, otherwise None.
    """
    _cleanup_dead_contexts()
    df_id = id(df)
    if df_id in _dataframe_column_contexts:
        ref, col_contexts = _dataframe_column_contexts[df_id]
        # Verify the DataFrame is still the same object
        if ref() is df:
            return col_contexts.get(column)
    return None


def set_dataframe_column_context(df: pl.DataFrame, column: str, ctx: CNotebookContext) -> None:
    """
    Set the CNotebookContext for a specific DataFrame column.

    :param df: The DataFrame.
    :param column: The column name.
    :param ctx: The CNotebookContext to store.
    """
    _cleanup_dead_contexts()
    df_id = id(df)
    if df_id not in _dataframe_column_contexts:
        _dataframe_column_contexts[df_id] = (weakref.ref(df), {})
    _dataframe_column_contexts[df_id][1][column] = ctx


########################################################################################################################
# Series accessor methods (monkey-patched onto oepolars)
########################################################################################################################


def _series_highlight(
        self,
        pattern: Iterable[str] | str | oechem.OESubSearch | Iterable[oechem.OESubSearch],
        *,
        color: oechem.OEColor | oechem.OEColorIter | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | None = None,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None
) -> None:
    """
    Highlight chemical features in a structure.

    The pattern argument can be:
        - SMARTS pattern
        - oechem.OESubSearch or oechem.OEMCSSearch object
        - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

    :param pattern: Pattern(s) to highlight in the molecule.
    :param color: Highlight color(s). Can be a single oechem.OEColor or an oechem.OEColorIter
        (e.g., oechem.OEGetLightColors()). Defaults to oechem.OEGetLightColors().
    :param style: Highlight style. Can be an int (OEHighlightStyle constant) or a string
        ("overlay_default", "overlay_ball_and_stick"). Defaults to "overlay_default".
    :param ref: Optional reference for alignment.
    :param method: Optional alignment method.
    """
    # Check dtype
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "highlight only works on molecule columns (oepolars.MoleculeType). If this column has "
            "molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get / create a series context and save it (because we are modifying it locally)
    ctx = get_series_context(self.metadata, save=True)

    # ********************************************************************************
    # Highlighting
    # ********************************************************************************

    # Case: Pattern is a single SMARTS string or oechem.OESubSearch object
    if isinstance(pattern, (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)):
        ctx.add_callback(
            create_structure_highlighter(
                query=pattern,
                color=color,
                style=style
            )
        )

    # Case: Pattern is an iterable
    elif isinstance(pattern, Iterable):
        for element in pattern:

            # Element is a SMARTS string or oechem.OESubSearch object
            if isinstance(element, (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)):
                ctx.add_callback(
                    create_structure_highlighter(
                        query=element,
                        color=color,
                        style=style
                    )
                )

            # Unknown element
            else:
                raise TypeError(f'Do not know how to add molecule highlight for type {type(element).__name__}')

    # Case: Pattern is an unknown type
    else:
        raise TypeError(f'Do not know how to add molecule highlight for type {type(pattern).__name__}')

    # ********************************************************************************
    # Alignment
    # ********************************************************************************

    if ref is not None:
        # Only apply alignment if align_depictions method is available
        if hasattr(self, 'align_depictions'):
            self.align_depictions(ref=ref, method=method)
        else:
            warn("align_depictions not available; ref parameter ignored")


def _series_reset_depictions(self) -> None:
    """
    Reset depiction callbacks for a molecule series.

    This clears any highlight callbacks that have been added to the series metadata.
    """
    # Clear the cnotebook context from metadata
    _ = self.metadata.pop("cnotebook", None)


def _series_clear_formatting_rules(self) -> None:
    """
    Clear all formatting rule callbacks from a molecule series.

    This removes any callbacks applied to the molecule prior to rendering,
    such as highlighting. Unlike reset_depictions which removes the entire
    rendering context, this method only clears the callbacks while preserving
    other context settings like image dimensions and styling.
    """
    ctx = self.metadata.get("cnotebook", None)
    if ctx is not None and isinstance(ctx, CNotebookContext):
        ctx.reset_callbacks()


def _series_recalculate_depiction_coordinates(
        self,
        *,
        clear_coords: bool = True,
        add_depiction_hydrogens: bool = True,
        perceive_bond_stereo: bool = True,
        suppress_explicit_hydrogens: bool = True,
        orientation: int = oedepict.OEDepictOrientation_Default
) -> None:
    """
    Recalculate the depictions for a molecule series.

    See the following link for more information:
    https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

    :param clear_coords: Clear existing 2D coordinates
    :param add_depiction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens
    :param orientation: Preferred 2D orientation
    """
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "recalculate_depiction_coordinates only works on molecule columns (oepolars.MoleculeType). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Create the depiction options
    opts = oedepict.OEPrepareDepictionOptions()
    opts.SetClearCoords(clear_coords)
    opts.SetAddDepictionHydrogens(add_depiction_hydrogens)
    opts.SetPerceiveBondStereo(perceive_bond_stereo)
    opts.SetSuppressHydrogens(suppress_explicit_hydrogens)
    opts.SetDepictOrientation(orientation)

    for mol in self._series.to_list():
        if isinstance(mol, oechem.OEMolBase):
            oedepict.OEPrepareDepiction(mol, opts)


def _series_align_depictions(
        self,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | oechem.OEQMol | Literal["first"],
        method: Literal["substructure", "ss", "mcss", "fp", "fingerprint"] | None = None,
        **kwargs
) -> None:
    """
    Align the 2D coordinates of molecules in a series.

    :param ref: Alignment reference (molecule, "first", or search object)
    :param method: Alignment method
    :param kwargs: Keyword arguments for aligner
    """
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "align_depictions only works on molecule columns (oepolars.MoleculeType). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get molecule list from series
    mols = self._series.to_list()

    # Handle "first" reference
    if isinstance(ref, str) and ref == "first":
        for mol in mols:
            if mol is not None and mol.IsValid():
                ref = mol.CreateCopy()
                break
        else:
            warn("No valid molecule found in series for depiction alignment")
            return

    # Make sure the reference has 2D coordinates
    oedepict.OEPrepareDepiction(ref, False)

    # Suppress alignment warnings (there are lots of needless warnings)
    level = oechem.OEThrow.GetLevel()
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Error)

    # noinspection PyBroadException
    try:
        # Create the aligner
        from .align import create_aligner
        aligner = create_aligner(ref=ref, method=method, **kwargs)

        for mol in mols:
            if mol is not None:
                _ = aligner(mol)

    except Exception:
        # We don't care if the aligners fail - it just results in unaligned structures (NBD)
        pass

    # Restore OEThrow level
    oechem.OEThrow.SetLevel(level)


# Monkey-patch onto oepolars SeriesChemNamespace
# Note: Series-level highlight is not registered because Polars Series are ephemeral and
# metadata doesn't persist across column accesses. Use df.chem.highlight() instead.
SeriesChemNamespace.reset_depictions = _series_reset_depictions  # pyright: ignore
SeriesChemNamespace.clear_formatting_rules = _series_clear_formatting_rules  # pyright: ignore
SeriesChemNamespace.recalculate_depiction_coordinates = _series_recalculate_depiction_coordinates  # pyright: ignore
SeriesChemNamespace.align_depictions = _series_align_depictions  # pyright: ignore


########################################################################################################################
# DataFrame accessor methods (monkey-patched onto oepolars)
########################################################################################################################

SMARTS_DELIMITER_RE = re.compile(r'\s*[|\r\n\t]+\s*')

# Store the fingerprint tag for fingerprint_similarity
_fingerprint_overlap_tag = oechem.OEGetTag("fingerprint_overlap")


class ColorBondByOverlapScore(oegrapheme.OEBondGlyphBase):
    """Bond glyph that colors bonds by fingerprint overlap score.

    Used internally by fingerprint similarity visualization to highlight
    bonds based on their contribution to molecular similarity.

    See: https://docs.eyesopen.com/toolkits/cookbook/python/depiction/simcalc.html
    """

    def __init__(self, cg: oechem.OELinearColorGradient, tag: int):
        """Create a bond coloring glyph.

        :param cg: Color gradient to map overlap scores to colors.
        :param tag: OEChem data tag containing overlap scores on bonds.
        """
        oegrapheme.OEBondGlyphBase.__init__(self)
        self.colorg = cg
        self.tag = tag

    # noinspection PyPep8Naming
    def RenderGlyph(self, disp, bond):

        bdisp = disp.GetBondDisplay(bond)
        if bdisp is None or not bdisp.IsVisible():
            return False

        if not bond.HasData(self.tag):
            return False

        linewidth = disp.GetScale() / 3.0
        color = self.colorg.GetColorAt(bond.GetData(self.tag))
        pen = oedepict.OEPen(color, color, oedepict.OEFill_Off, linewidth)

        adispB = disp.GetAtomDisplay(bond.GetBgn())
        adispE = disp.GetAtomDisplay(bond.GetEnd())

        layer = disp.GetLayer(oedepict.OELayerPosition_Below)
        layer.DrawLine(adispB.GetCoords(), adispE.GetCoords(), pen)

        return True

    # noinspection PyPep8Naming
    def ColorBondByOverlapScore(self):
        return ColorBondByOverlapScore(self.colorg, self.tag).__disown__()


def _dataframe_reset_depictions(self, *, molecule_columns: str | Iterable[str] | None = None) -> None:
    """
    Reset depiction callbacks for one or more molecule columns in the DataFrame.

    :param molecule_columns: Optional molecule column(s) to reset. If None, resets all molecule columns.
    """
    columns = set()
    if molecule_columns is None:
        columns.update(self._df.columns)

    elif isinstance(molecule_columns, str):
        columns.add(molecule_columns)

    else:
        columns.update(molecule_columns)

    # Filter invalid and non-molecule columns
    for col in filter(
        lambda c: c in self._df.columns and isinstance(self._df.schema[c], oeplr.MoleculeType),
        columns
    ):
        self._df.get_column(col).chem.reset_depictions()  # pyright: ignore


def _dataframe_clear_formatting_rules(self, molecule_columns: str | Iterable[str] | None = None) -> None:
    """
    Clear all formatting rule callbacks from one or more molecule columns.

    This removes any callbacks applied to molecules prior to rendering,
    such as highlighting. Unlike reset_depictions which removes the entire
    rendering context, this method only clears the callbacks while preserving
    other context settings like image dimensions and styling.

    :param molecule_columns: Optional molecule column(s) to clear formatting rules from.
        If None, clears formatting rules from all molecule columns.

    Example::

        # Clear formatting rules from all molecule columns
        df.chem.clear_formatting_rules()

        # Clear formatting rules from a specific column
        df.chem.clear_formatting_rules("smiles")

        # Clear formatting rules from multiple columns
        df.chem.clear_formatting_rules(["mol1", "mol2"])
    """
    columns = set()
    if molecule_columns is None:
        columns.update(self._df.columns)

    elif isinstance(molecule_columns, str):
        columns.add(molecule_columns)

    else:
        columns.update(molecule_columns)

    # Filter invalid and non-molecule columns and clear their formatting rules
    for col in filter(
        lambda c: c in self._df.columns and isinstance(self._df.schema[c], oeplr.MoleculeType),
        columns
    ):
        # Clear DataFrame-level column context callbacks
        ctx = get_dataframe_column_context(self._df, col)
        if ctx is not None:
            ctx.reset_callbacks()


def _dataframe_recalculate_depiction_coordinates(
        self,
        *,
        molecule_columns: str | Iterable[str] | None = None,
        clear_coords: bool = True,
        add_depiction_hydrogens: bool = True,
        perceive_bond_stereo: bool = True,
        suppress_explicit_hydrogens: bool = True,
        orientation: int = oedepict.OEDepictOrientation_Default
) -> None:
    """
    Recalculate the depictions for one or more molecule series in a DataFrame. If molecule_columns is None,
    which is the default, then all molecule columns will have their depictions recalculated.

    See the following link for more information:
    https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

    :param molecule_columns: Optional molecule column(s) to have depictions recalculated
    :param clear_coords: Clear existing 2D coordinates
    :param add_depiction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens
    :param orientation: Preferred 2D orientation
    """
    if molecule_columns is None:
        molecule_columns = set()

        for col in self._df.columns:
            if isinstance(self._df.schema[col], oeplr.MoleculeType):
                molecule_columns.add(col)

    elif isinstance(molecule_columns, str):
        molecule_columns = {molecule_columns}

    else:
        molecule_columns = set(molecule_columns)

    # Recalculate the column depictions
    for col in molecule_columns:

        if col in self._df.columns:
            if isinstance(self._df.schema[col], oeplr.MoleculeType):
                self._df.get_column(col).chem.recalculate_depiction_coordinates(  # pyright: ignore
                    clear_coords=clear_coords,
                    add_depiction_hydrogens=add_depiction_hydrogens,
                    perceive_bond_stereo=perceive_bond_stereo,
                    suppress_explicit_hydrogens=suppress_explicit_hydrogens,
                    orientation=orientation
                )

            else:
                warn(f'Column {col} does not have a MoleculeType')

        else:
            warn(f'{col} not found in DataFrame columns: ({", ".join(self._df.columns)})')


def _dataframe_highlight(
        self,
        molecule_column: str,
        pattern: Iterable[str] | str | oechem.OESubSearch | Iterable[oechem.OESubSearch],
        *,
        color: oechem.OEColor | oechem.OEColorIter | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
) -> None:
    """
    Highlight chemical features in molecules within a specified column.

    This method stores the highlighting callbacks at the DataFrame level, ensuring they persist
    across column accesses. This is necessary because Polars Series objects are ephemeral.

    The pattern argument can be:
        - SMARTS pattern
        - oechem.OESubSearch or oechem.OEMCSSearch object
        - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

    :param molecule_column: Name of the molecule column to highlight.
    :param pattern: Pattern(s) to highlight in the molecules.
    :param color: Highlight color(s). Can be a single oechem.OEColor or an oechem.OEColorIter
        (e.g., oechem.OEGetLightColors()). Defaults to oechem.OEGetLightColors().
    :param style: Highlight style. Can be an int (OEHighlightStyle constant) or a string
        ("overlay_default", "overlay_ball_and_stick"). Defaults to "overlay_default".
    """
    # Check the column exists and is a molecule type
    if molecule_column not in self._df.columns:
        raise ValueError(f'Column {molecule_column} not found in DataFrame columns: ({", ".join(self._df.columns)})')

    if not isinstance(self._df.schema[molecule_column], oeplr.MoleculeType):
        raise TypeError(
            f"highlight only works on molecule columns (oepolars.MoleculeType). Column '{molecule_column}' "
            f"has type {self._df.schema[molecule_column]}."
        )

    # Get or create the context for this DataFrame column
    ctx = get_dataframe_column_context(self._df, molecule_column)
    if ctx is None:
        ctx = create_local_context()
        set_dataframe_column_context(self._df, molecule_column, ctx)

    # Case: Pattern is a single SMARTS string or oechem.OESubSearch object
    if isinstance(pattern, (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)):
        ctx.add_callback(create_structure_highlighter(pattern, color=color, style=style))

    # Case: Pattern is an iterable of SMARTS strings and/or oechem.OESubSearch objects
    elif isinstance(pattern, Iterable):
        for p in pattern:
            ctx.add_callback(create_structure_highlighter(p, color=color, style=style))

    else:
        raise TypeError(f'Unsupported type for pattern: {type(pattern).__name__}')


def _dataframe_copy_molecules(
        self,
        source_column: str,
        dest_column: str,
) -> pl.DataFrame:
    """
    Create a deep copy of molecules from one column to a new column.

    This creates independent copies of all molecules, allowing modifications
    (such as highlighting or alignment) to the new column without affecting
    the original.

    :param source_column: Name of the source molecule column.
    :param dest_column: Name of the new column to create with copied molecules.
    :returns: New DataFrame with the molecule column added.

    Example::

        # Create a copy of molecules for alignment
        df = df.chem.copy_molecules("Original", "Aligned")
        df.chem.highlight("Aligned", "c1ccccc1")
    """
    if source_column not in self._df.columns:
        raise ValueError(f'Column {source_column} not found in DataFrame columns: ({", ".join(self._df.columns)})')

    if not isinstance(self._df.schema[source_column], oeplr.MoleculeType):
        raise TypeError(
            f"copy_molecules only works on molecule columns (oepolars.MoleculeType). Column '{source_column}' "
            f"has type {self._df.schema[source_column]}."
        )

    # Use the series-level copy_molecules (or deepcopy) and add as a new column
    copied_series = self._df.get_column(source_column).chem.copy_molecules()  # pyright: ignore
    return self._df.with_columns(copied_series.alias(dest_column))


def _dataframe_highlight_using_column(
        self,
        molecule_column: str,
        pattern_column: str,
        *,
        highlighted_column: str = "highlighted_substructures",
        color: oechem.OEColor | oechem.OEColorIter | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | None = None,
        alignment_opts: oedepict.OEAlignmentOptions | None = None,
        prepare_opts: oedepict.OEPrepareDepictionOptions | None = None,
        inplace: bool = False
) -> pl.DataFrame:
    """
    Highlight molecules based on the value of another column. The column produced is a DisplayType column, so
    the results are not suitable for other molecular calculations.

    The other column can contain:
        - Comma or whitespace delimited string of SMARTS patterns
        - oechem.OESubSearch or oechem.OEMCSSearch object
        - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

    :param molecule_column: Name of the molecule column.
    :param pattern_column: Name of the pattern column.
    :param highlighted_column: Optional name of the column with highlighted structures.
    :param color: Highlight color(s). Can be a single oechem.OEColor or an oechem.OEColorIter
        (e.g., oechem.OEGetLightColors()). Defaults to oechem.OEGetLightColors().
    :param style: Highlight style. Can be an int (OEHighlightStyle constant) or a string
        ("overlay_default", "overlay_ball_and_stick"). Defaults to "overlay_default".
    :param ref: Optional reference for aligning depictions.
    :param alignment_opts: Optional depiction alignment options (oedepict.OEAlignmentOptions).
    :param prepare_opts: Optional depiction preparation options (oedepict.OEPrepareDepictionOptions).
    :param inplace: If True, returns the modified DataFrame (note: Polars DataFrames are immutable).
    :returns: Modified DataFrame with highlighted column.
    """
    df = self._df

    if molecule_column not in df.columns:
        raise KeyError(f'{molecule_column} not found in DataFrame columns: ({", ".join(df.columns)})')

    if not isinstance(df.schema[molecule_column], oeplr.MoleculeType):
        raise TypeError(
            f"highlight_using_column only works on molecule columns (oepolars.MoleculeType). If {molecule_column}"
            " has molecules, use df.chem.as_molecule() to convert to a molecule column first."
        )

    if pattern_column not in df.columns:
        raise KeyError(f'{pattern_column} not found in DataFrame columns: ({", ".join(df.columns)})')

    # Default color
    if color is None:
        color = oechem.OEGetLightColors()

    # Determine highlighting approach based on style
    use_overlay = isinstance(style, str) and style in ("overlay_default", "overlay_ball_and_stick")

    # Check if color is compatible with overlay
    if use_overlay and isinstance(color, oechem.OEColor):
        warn("Overlay coloring is not compatible with a single oechem.OEColor. Falling back to standard highlighting")
        use_overlay = False
        style = oedepict.OEHighlightStyle_BallAndStick

    assert color is not None

    # Create the display objects
    displays = []

    # Get the rendering context for creating the displays
    series = df.get_column(molecule_column)
    metadata = series.chem.metadata if hasattr(series, 'chem') else {}  # pyright: ignore
    ctx = get_series_context(metadata)

    for row_idx in range(len(df)):
        mol = df[molecule_column][row_idx]
        patterns = df[pattern_column][row_idx]

        if isinstance(mol, oechem.OEMolBase) and mol.IsValid():

            # Create the display
            disp = oemol_to_disp(mol, ctx=ctx)

            # Highlight
            substructures = []

            # Parse different patterns
            if isinstance(patterns, str):
                for pattern in re.split(SMARTS_DELIMITER_RE, patterns):
                    ss = oechem.OESubSearch(pattern)
                    if ss.IsValid():
                        substructures.append(ss)

            elif isinstance(patterns, oechem.OESubSearch):
                if patterns.IsValid():
                    substructures.append(patterns)

            elif isinstance(patterns, Iterable):

                for p in patterns:

                    if isinstance(p, str):
                        for pattern in re.split(SMARTS_DELIMITER_RE, p):
                            ss = oechem.OESubSearch(pattern)
                            if ss.IsValid():
                                substructures.append(ss)

                    elif isinstance(p, oechem.OESubSearch):
                        if p.IsValid():
                            substructures.append(p)

                    else:
                        warn(f'Do not know how to highlight using: {type(p).__name__}')

            elif patterns is not None:
                warn(f'Do not know how to highlight using: {type(patterns).__name__}')

            # Overlay highlighting
            if use_overlay:
                highlight = oedepict.OEHighlightOverlayByBallAndStick(color)
                for ss in substructures:
                    oedepict.OEAddHighlightOverlay(disp, highlight, ss.Match(disp.GetMolecule(), True))

            else:
                # Traditional highlighting
                if isinstance(color, oechem.OEColor):
                    highlight_color = color
                else:
                    highlight_color = oechem.OELightBlue
                    for c in color:
                        highlight_color = c
                        break
                for ss in substructures:
                    for match in ss.Match(disp.GetMolecule(), True):
                        oedepict.OEAddHighlighting(disp, highlight_color, style, match)

            displays.append(disp)

        else:
            displays.append(None)

    # Create the new column with DisplayType (must instantiate the type)
    display_series = pl.Series(highlighted_column, displays, dtype=oeplr.DisplayType())

    # Add the column to the DataFrame
    result = df.with_columns(display_series)

    return result


def _dataframe_fingerprint_similarity(
        self,
        molecule_column: str,
        ref: oechem.OEMolBase | None = None,
        *,
        tanimoto_column: str = "fingerprint_tanimoto",
        reference_similarity_column: str = "reference_similarity",
        target_similarity_column: str = "target_similarity",
        fptype: str = "tree",
        num_bits: int = 4096,
        min_distance: int = 0,
        max_distance: int = 4,
        atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
        bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond,
        inplace: bool = False
) -> pl.DataFrame:
    """
    Color molecules by fingerprint similarity.

    :param molecule_column: Name of the molecule column
    :param ref: Reference molecule (if None, uses first valid molecule)
    :param tanimoto_column: Name of the tanimoto score column
    :param reference_similarity_column: Name of the reference display column
    :param target_similarity_column: Name of the target display column
    :param fptype: Fingerprint type
    :param num_bits: Number of bits in the fingerprint
    :param min_distance: Minimum distance/radius for path/circular/tree
    :param max_distance: Maximum distance/radius for path/circular/tree
    :param atom_type: Atom type bitmask
    :param bond_type: Bond type bitmask
    :param inplace: Not used (Polars DataFrames are immutable), kept for API compatibility
    :return: DataFrame with similarity columns
    """
    tag = _fingerprint_overlap_tag
    df = self._df

    if molecule_column not in df.columns:
        raise KeyError(f'Molecule column not found in DataFrame: {molecule_column}')

    if not isinstance(df.schema[molecule_column], oeplr.MoleculeType):
        raise TypeError(
            f"Column {molecule_column} does not have MoleculeType ({df.schema[molecule_column]})"
        )

    # Get the context for rendering
    series = df.get_column(molecule_column)
    metadata = series.chem.metadata if hasattr(series, 'chem') else {}  # pyright: ignore
    ctx = get_series_context(metadata)

    # Get molecule list
    mols = series.to_list()

    # If we're using the first molecule as our reference
    if ref is None:
        for mol in mols:
            if mol is not None and mol.IsValid():
                ref = mol
                break
        else:
            warn(f'No valid reference molecules to use for alignment in column {molecule_column}')
            return df

    assert ref is not None

    # Check reference molecule
    if not ref.IsValid():
        warn("Reference molecule is not valid")
        return df

    # Fingerprint maker
    make_fp = fingerprint_maker(
        fptype=fptype,
        num_bits=num_bits,
        min_distance=min_distance,
        max_distance=max_distance,
        atom_type=atom_type,
        bond_type=bond_type
    )

    # Make the reference fingerprint
    ref_fp = make_fp(ref)

    if not ref_fp.IsValid():
        warn("Fingerprint from reference molecule is invalid")
        return df

    # Create the display objects and scores
    ref_displays = []
    targ_displays = []
    ref_molecules = []  # Cache to prevent GC
    targ_molecules = []  # Cache to prevent GC
    tanimotos = []

    for mol in mols:
        if mol is not None and mol.IsValid():

            # Copy the molecules, because we're modifying them
            targ_mol = oechem.OEMol(mol)
            ref_mol = oechem.OEMol(ref)

            # Cache molecules to prevent GC
            targ_molecules.append(targ_mol)
            ref_molecules.append(ref_mol)

            # Create the fingerprint
            targ_fp = make_fp(targ_mol)
            if targ_fp.IsValid():

                # Add the tanimoto
                tanimotos.append(oegraphsim.OETanimoto(ref_fp, targ_fp))

                # Calculate the similarity
                targ_bonds = [0] * targ_mol.GetMaxBondIdx()
                ref_bonds = [0] * ref_mol.GetMaxBondIdx()

                # Overlaps
                overlaps = oegraphsim.OEGetFPOverlap(ref_mol, targ_mol, ref_fp.GetFPTypeBase())

                for match in overlaps:
                    for bond in match.GetPatternBonds():
                        ref_bonds[bond.GetIdx()] += 1
                    for bond in match.GetTargetBonds():
                        targ_bonds[bond.GetIdx()] += 1

                for bond in targ_mol.GetBonds():
                    bond.SetData(tag, targ_bonds[bond.GetIdx()])

                for bond in ref_mol.GetBonds():
                    bond.SetData(tag, ref_bonds[bond.GetIdx()])

                # noinspection PyTypeChecker
                maxvalue = max((0, max(targ_bonds), max(ref_bonds)))

                # Create the color gradient
                colorg = oechem.OELinearColorGradient()
                colorg.AddStop(oechem.OEColorStop(0.0, oechem.OEPinkTint))
                colorg.AddStop(oechem.OEColorStop(1.0, oechem.OEYellow))
                colorg.AddStop(oechem.OEColorStop(maxvalue, oechem.OEDarkGreen))

                # Function that will color the bonds
                bondglyph = ColorBondByOverlapScore(colorg, tag)

                # Align the molecules
                overlaps = oegraphsim.OEGetFPOverlap(ref_mol, targ_mol, ref_fp.GetFPTypeBase())
                oedepict.OEPrepareMultiAlignedDepiction(targ_mol, ref_mol, overlaps)

                # Create the displays
                ref_disp = oemol_to_disp(ref_mol, ctx=ctx)
                targ_disp = oemol_to_disp(targ_mol, ctx=ctx)

                # Color the displays
                oegrapheme.OEAddGlyph(ref_disp, bondglyph, oechem.IsTrueBond())
                oegrapheme.OEAddGlyph(targ_disp, bondglyph, oechem.IsTrueBond())

                ref_displays.append(ref_disp)
                targ_displays.append(targ_disp)

            # Fingerprint was invalid
            else:
                tanimotos.append(None)
                ref_displays.append(None)
                targ_displays.append(None)

        # Molecule was invalid
        else:
            tanimotos.append(None)
            ref_displays.append(None)
            targ_displays.append(None)

    # Create the columns
    tanimoto_series = pl.Series(tanimoto_column, tanimotos, dtype=pl.Float64)
    ref_series = pl.Series(reference_similarity_column, ref_displays, dtype=oeplr.DisplayType())
    targ_series = pl.Series(target_similarity_column, targ_displays, dtype=oeplr.DisplayType())

    # Store molecule references in metadata to prevent GC (same as pandas version)
    ref_series.chem.metadata["molecules"] = ref_molecules  # type: ignore[attr-defined]  # pyright: ignore
    targ_series.chem.metadata["molecules"] = targ_molecules  # type: ignore[attr-defined]  # pyright: ignore

    # Add the columns to the DataFrame
    result = df.with_columns([tanimoto_series, ref_series, targ_series])

    return result


DataFrameChemNamespace.reset_depictions = _dataframe_reset_depictions  # pyright: ignore
DataFrameChemNamespace.clear_formatting_rules = _dataframe_clear_formatting_rules  # pyright: ignore
DataFrameChemNamespace.recalculate_depiction_coordinates = (  # pyright: ignore
    _dataframe_recalculate_depiction_coordinates
)
DataFrameChemNamespace.highlight = _dataframe_highlight  # pyright: ignore
DataFrameChemNamespace.highlight_using_column = _dataframe_highlight_using_column  # pyright: ignore
DataFrameChemNamespace.fingerprint_similarity = _dataframe_fingerprint_similarity  # pyright: ignore
DataFrameChemNamespace.copy_molecules = _dataframe_copy_molecules  # pyright: ignore


########################################################################################################################
# MolGrid accessor methods for Series and DataFrame
########################################################################################################################


def _polars_series_molgrid(
    self,
    title: bool | str | None = True,
    tooltip_fields: list[str] | None = None,
    **kwargs
) -> "MolGrid":
    """Display molecules in an interactive grid.

    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
    :param tooltip_fields: Fields for tooltip.
    :param kwargs: Additional arguments passed to MolGrid.
    :returns: MolGrid instance.
    """
    from cnotebook import MolGrid

    series = self._series
    mols = list(series.to_list())

    return MolGrid(
        mols,
        title=title,
        tooltip_fields=tooltip_fields,
        **kwargs
    )


def _polars_dataframe_molgrid(
    self,
    mol_col: str,
    title: bool | str | None = True,
    tooltip_fields: list[str] | None = None,
    **kwargs
) -> "MolGrid":
    """Display molecules from a column in an interactive grid.

    :param mol_col: Column containing molecules.
    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
    :param tooltip_fields: Columns for tooltip.
    :param kwargs: Additional arguments passed to MolGrid.
    :returns: MolGrid instance.
    """
    import pandas as pd

    from cnotebook import MolGrid

    df = self._df
    mols = list(df[mol_col].to_list())

    # Build pandas DataFrame from non-molecule columns for MolGrid data access
    # We extract only primitive columns to avoid pyarrow dependency issues
    pdf_data = {}
    for col in df.columns:
        if col != mol_col:
            # Extract column values as Python objects
            pdf_data[col] = df[col].to_list()

    pdf = pd.DataFrame(pdf_data)

    return MolGrid(
        mols,
        dataframe=pdf,
        mol_col=mol_col,
        title=title,
        tooltip_fields=tooltip_fields,
        **kwargs
    )


# Attach molgrid methods to accessors
SeriesChemNamespace.molgrid = _polars_series_molgrid  # pyright: ignore
DataFrameChemNamespace.molgrid = _polars_dataframe_molgrid  # pyright: ignore


########################################################################################################################
# Register Polars formatters
########################################################################################################################

if ipython_present:

    def register_polars_formatters():
        """
        Register Polars DataFrame formatters for iPython/Jupyter display.

        This registers render_polars_dataframe as the HTML formatter for
        Polars DataFrames in iPython environments.

        Note: Calls to this function are idempotent.
        """
        if get_ipython is None:
            return

        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']  # pyright: ignore
            try:
                formatter = html_formatter.lookup(pl.DataFrame)
                if formatter is not render_polars_dataframe:
                    html_formatter.for_type(pl.DataFrame, render_polars_dataframe)
            except KeyError:
                html_formatter.for_type(pl.DataFrame, render_polars_dataframe)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register polars extension")

else:

    # iPython is not present, so we do not register a Polars formatter
    def register_polars_formatters():
        pass
