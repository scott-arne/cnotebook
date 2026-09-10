import html
import logging
import re
import typing
from collections.abc import Hashable, Iterable
from copy import copy as shallow_copy
from typing import Any, Literal

import oepandas as oepd
import pandas as pd
from oepandas.pandas_extensions import OEDataFrameAccessor, OESeriesAccessor
from openeye import oechem, oedepict, oegrapheme, oegraphsim

from .align import create_aligner, fingerprint_maker
from .context import get_series_context, pass_cnotebook_context
from .core import formatters as _fmt
from .core.errors import warn
from .core.table import (
    CellTokens,
    ColumnKind,
    RowWindow,
    cell_html,
    pandas_max_rows_argument,
)
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


SMARTS_DELIMITER_RE = re.compile(r'\s*[|\r\n\t]+\s*')

log = logging.getLogger("cnotebook")


def _oepandas_types(*names: str) -> tuple[type, ...]:
    """
    Resolve optional OEPandas type names.

    :param names: Attribute names to resolve from the ``oepandas`` module.
    :returns: Tuple of available types.
    """
    return tuple(
        typ for name in names
        if isinstance((typ := getattr(oepd, name, None)), type)
    )


_DEPICTABLE_MOLECULE_DTYPES = _oepandas_types("MoleculeDtype", "QueryDtype")
_DEPICTABLE_MOLECULE_ARRAYS = _oepandas_types("MoleculeArray", "QueryArray")
_DEPICTABLE_MOLECULE_DTYPE_MESSAGE = "oepandas.MoleculeDtype or oepandas.QueryDtype"
_RENDER_OPTION_UNSET = object()


def _is_depictable_molecule_dtype(dtype: Any) -> bool:
    """
    Check whether a Pandas dtype contains OpenEye molecules CNotebook can depict.

    :param dtype: Pandas dtype to check.
    :returns: ``True`` for OEPandas molecule or query dtypes.
    """
    return isinstance(dtype, _DEPICTABLE_MOLECULE_DTYPES)


def _as_depictable_molecule_array(arr: Any) -> Any:
    """
    Validate an OEPandas array that stores depictable OpenEye molecules.

    :param arr: Array object from a Pandas Series.
    :returns: The validated array.
    :raises TypeError: If the array is not a supported OEPandas molecule array.
    """
    if not isinstance(arr, _DEPICTABLE_MOLECULE_ARRAYS):
        raise TypeError(f"Expected an OEPandas molecule or query array, got {type(arr).__name__}")
    return arr


def _collect_render_options(**options: Any) -> dict[str, Any]:
    """
    Collect render options that were explicitly provided by the caller.

    :param options: Render option names and values.
    :returns: Mapping containing only caller-provided options.
    """
    return {
        name: value for name, value in options.items()
        if value is not _RENDER_OPTION_UNSET
    }


def _apply_render_options(ctx: CNotebookContext, options: dict[str, Any]) -> None:
    """
    Apply render options to a CNotebook context.

    :param ctx: Context to modify.
    :param options: Render options to apply.
    """
    for name, value in options.items():
        setattr(ctx, name, value)


def classify_dtype(dtype: Any) -> ColumnKind:
    """
    Map a Pandas dtype to the kind of cell rendering it needs.

    :param dtype: Pandas dtype of a column.
    :returns: Column kind; ``ColumnKind.OTHER`` for every dtype Pandas renders itself.
    """
    if isinstance(dtype, _oepandas_types("MoleculeDtype")):
        return ColumnKind.MOLECULE
    if isinstance(dtype, _oepandas_types("QueryDtype")):
        return ColumnKind.QUERY
    if isinstance(dtype, _oepandas_types("DisplayDtype")):
        return ColumnKind.DISPLAY
    if isinstance(dtype, _oepandas_types("DesignUnitDtype")):
        return ColumnKind.DESIGN_UNIT
    return ColumnKind.OTHER


class PandasFrameAdapter:
    """
    Frame adapter over a Pandas DataFrame (positional column access).

    Columns are addressed by position, not by label, so that a frame with
    duplicate column labels keeps one kind and one render context per column.
    """

    def __init__(self, df: pd.DataFrame, *, ctx: CNotebookContext | None = None):
        """
        Wrap a DataFrame for rendering.

        :param df: Frame to render; never modified.
        :param ctx: Context overriding every column context, or ``None`` to use
            the context stored on each column.
        """
        self.df = df
        self._ctx = ctx
        self._labels: list[Hashable] = list(df.columns)
        self._kinds = [classify_dtype(dtype) for dtype in df.dtypes]

    def columns(self) -> list[Hashable]:
        """
        :returns: Column labels in positional order.
        """
        return list(self._labels)

    def kind(self, pos: int) -> ColumnKind:
        """
        :param pos: Column position.
        :returns: How the column's cells are rendered.
        """
        return self._kinds[pos]

    def nrows(self) -> int:
        """
        :returns: Number of rows in the frame.
        """
        return len(self.df)

    def context(self, pos: int) -> CNotebookContext:
        """
        Render context of one column.

        :param pos: Column position.
        :returns: The adapter's context when it was given one, else the context
            stored on the column, else a local context deferring to the global one.
        """
        if self._ctx is not None:
            return self._ctx
        metadata = getattr(self.df.iloc[:, pos].array, "metadata", None) or {}
        return get_series_context(metadata)

    def row_budget(self, max_rows: int | None) -> int | None:
        """
        Row budget for this frame.

        :param max_rows: Caller argument; see :func:`pandas_max_rows_argument`.
        :returns: Value to pass as ``DataFrame.to_html(max_rows=...)``.
        """
        return pandas_max_rows_argument(
            len(self.df), max_rows, pd.get_option("display.max_rows"), pd.get_option("display.min_rows")
        )

    def window(self, max_rows: int | None) -> RowWindow:
        """
        Rows a generic writer should render for *max_rows*.

        :param max_rows: Caller argument; see :func:`pandas_max_rows_argument`.
        :returns: The row window. :func:`render_dataframe` does not use it: Pandas'
            own writer splits head and tail itself.
        """
        budget = self.row_budget(max_rows)
        if budget is None or len(self.df) <= budget:
            return RowWindow(list(range(len(self.df))), [], len(self.df))
        head = -(-budget // 2)
        return RowWindow(list(range(head)), list(range(len(self.df) - (budget - head), len(self.df))), len(self.df))

    def cell(self, row: int, pos: int) -> Any:
        """
        :param row: Row position.
        :param pos: Column position.
        :returns: The cell value.
        """
        return self.df.iloc[row, pos]

    def other_cell_text(self, row: int, pos: int) -> str:
        """
        :param row: Row position.
        :param pos: Column position.
        :returns: Unescaped text of an ordinary (not depicted) cell.
        """
        return str(self.df.iloc[row, pos])

    def index_text(self, row: int) -> str | None:
        """
        :param row: Row position.
        :returns: Text of the row's index label.
        """
        return str(self.df.index[row])

    def header_extra_rows(self) -> list[list[str]]:
        """
        :returns: Extra header rows; Pandas frames have none.
        """
        return []


def create_mol_formatter(*, ctx: CNotebookContext) -> typing.Callable[[Any], str]:
    """
    Create a formatter rendering molecule cells with *ctx*.

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
    Create a formatter rendering display cells with *ctx*.

    :param callbacks: Callbacks replacing the context's own callbacks, or ``None``
        to keep them.
    :param ctx: CNotebook rendering context.
    :returns: Function that renders display objects to HTML.
    """
    if callbacks is not None:
        ctx = ctx.copy()
        ctx.reset_callbacks()
        for callback in callbacks:
            ctx.add_callback(callback)
    return lambda value: _fmt.display_cell_html(value, ctx)


def create_du_formatter(*, ctx: CNotebookContext) -> typing.Callable[[Any], str]:
    """
    Create a formatter rendering design unit cells with *ctx*.

    :param ctx: CNotebook rendering context.
    :returns: Function that renders design units to HTML.
    """
    return lambda value: _fmt.design_unit_cell_html(value, ctx)


def escape_formatter(obj: Any) -> str:
    """
    Escape a plain value for HTML.

    :param obj: Value to escape; ``None`` becomes an empty cell.
    :returns: Escaped text.
    """
    return html.escape("" if obj is None else str(obj))


def render_dataframe(
        df: pd.DataFrame,
        formatters: dict | None = None,
        col_space: dict[Hashable, str | int] | None = None,
        ctx: CNotebookContext | None = None,
        max_rows: int | None = None,
        **kwargs: Any
) -> str:
    """
    Render a DataFrame with molecule-aware cells through Pandas' own HTML writer.

    Depiction cells are rendered into per-render nonce tokens that Pandas carries
    through its writer untouched, so every other value is escaped by Pandas and
    only the depiction HTML is substituted back in raw. Cells are depicted lazily
    by the Pandas formatters, so only the rows Pandas actually renders are drawn.

    :param df: Frame to render (never modified).
    :param formatters: Extra Pandas formatters for ordinary columns (copied, never mutated).
    :param col_space: Extra Pandas ``col_space`` entries (copied, never mutated).
    :param ctx: Overrides every column context when given; ``None`` honours column contexts.
    :param max_rows: ``None`` for the Pandas display rule, ``<= 0`` for all rows, else the row budget.
    :param kwargs: Forwarded to ``DataFrame.to_html``; ``escape`` is ignored with a warning.
    :returns: HTML table.
    """
    kwargs = dict(kwargs)
    if "escape" in kwargs:
        kwargs.pop("escape")
        warn("render_dataframe always escapes ordinary cells; the escape argument is ignored")

    # to_html applies its own "columns" argument after the formatters are bound, which
    # would misalign the positional formatter list; select the columns up front instead.
    columns = kwargs.pop("columns", None)
    if columns is not None:
        df = df[columns]

    adapter = PandasFrameAdapter(df, ctx=ctx)
    tokens = CellTokens()
    labels = adapter.columns()
    caller_formatters = dict(formatters or {})
    # Pandas applies a list of formatters by position, which keeps duplicate and non-string labels distinct.
    positional_formatters: list[Any] = [caller_formatters.get(label) for label in labels]
    widths: dict[Hashable, str | int] = dict(col_space or {})

    for pos, label in enumerate(labels):
        kind = adapter.kind(pos)
        if kind is ColumnKind.OTHER:
            continue
        if positional_formatters[pos] is not None:
            warn(f"Overwriting the formatter for column {label!r} with the molecule formatter")
        column_ctx = adapter.context(pos)
        positional_formatters[pos] = (
            lambda value, _kind=kind, _ctx=column_ctx: tokens.token_for(cell_html(_kind, value, _ctx))
        )
        if column_ctx.width > 0:
            # col_space is keyed by label in Pandas, so duplicate labels share the widest image.
            previous = widths.get(label)
            widths[label] = max(int(column_ctx.width), previous) if isinstance(previous, int) else int(column_ctx.width)

    html_out = df.to_html(  # pyright: ignore[reportCallIssue]
        escape=True,
        formatters=positional_formatters if any(f is not None for f in positional_formatters) else None,
        col_space=widths or None,  # pyright: ignore[reportArgumentType]
        max_rows=adapter.row_budget(max_rows),
        **kwargs
    )
    assert html_out is not None
    return tokens.substitute(html_out)


########################################################################################################################
# Register Pandas formatters
########################################################################################################################

if ipython_present:

    def register_pandas_formatters():
        """
        Modify how the notebook is told how to display Pandas Dataframes - this actually is more flexible because it
        will still work with other custom changes to to_html().

        Note: Calls to this function are idempotent.
        """
        assert get_ipython is not None
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters[  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
                'text/html'
            ]
            try:
                formatter = html_formatter.lookup(pd.DataFrame)
                if formatter is not render_dataframe:
                    html_formatter.for_type(pd.DataFrame, render_dataframe)
            except KeyError:
                html_formatter.for_type(pd.DataFrame, render_dataframe)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register pandas extension")

else:

    # iPython is not present, so we do not register a Pandas formatter
    def register_pandas_formatters():
        pass


########################################################################################################################
# CNotebook Series accessor extensions for OEPandas .chem accessor
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
    if not _is_depictable_molecule_dtype(self._obj.dtype):
        raise TypeError(
            f"highlight only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). If this column has "
            "molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get the molecule array
    arr = _as_depictable_molecule_array(self._obj.array)

    # Get / create a series context and save it (because we are modifying it locally)
    ctx = get_series_context(arr.metadata, save=True)

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
        self._obj.chem.align_depictions(ref=ref, method=method)


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
    if not _is_depictable_molecule_dtype(self._obj.dtype):
        raise TypeError(
            "recalculate_depiction_coordinates only works on molecule columns "
            f"({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Create the depiction options
    opts = oedepict.OEPrepareDepictionOptions()
    opts.SetClearCoords(clear_coords)
    opts.SetAddDepictionHydrogens(add_depiction_hydrogens)
    opts.SetPerceiveBondStereo(perceive_bond_stereo)
    opts.SetSuppressHydrogens(suppress_explicit_hydrogens)
    opts.SetDepictOrientation(orientation)

    for mol in self._obj.array:
        if isinstance(mol, oechem.OEMolBase):
            oedepict.OEPrepareDepiction(mol, opts)


def _series_set_render_options(
        self,
        *,
        width=_RENDER_OPTION_UNSET,
        height=_RENDER_OPTION_UNSET,
        min_width=_RENDER_OPTION_UNSET,
        min_height=_RENDER_OPTION_UNSET,
        max_width=_RENDER_OPTION_UNSET,
        max_height=_RENDER_OPTION_UNSET,
        structure_scale=_RENDER_OPTION_UNSET,
        auto_scale=_RENDER_OPTION_UNSET,
        atom_label_font_scale=_RENDER_OPTION_UNSET,
        title_font_scale=_RENDER_OPTION_UNSET,
        image_format=_RENDER_OPTION_UNSET,
        bond_width_scaling=_RENDER_OPTION_UNSET,
        title=_RENDER_OPTION_UNSET,
        max_heavy_atoms=_RENDER_OPTION_UNSET,
        device_pixel_ratio=_RENDER_OPTION_UNSET,
) -> None:
    """
    Set rendering options for a molecule or query series.

    :param width: Image width in pixels. If 0, determined by structure scale.
    :param height: Image height in pixels. If 0, determined by structure scale.
    :param min_width: Minimum image width in pixels.
    :param min_height: Minimum image height in pixels.
    :param max_width: Maximum image width in pixels, or ``None`` for no limit.
    :param max_height: Maximum image height in pixels, or ``None`` for no limit.
    :param structure_scale: Scale factor applied to OpenEye's default structure
        scale. Ignored when ``auto_scale`` is ``True``.
    :param auto_scale: When ``True``, size structures to fill the image canvas
        (OpenEye AutoScale) instead of using ``structure_scale``.
    :param atom_label_font_scale: Scale factor for atom labels.
    :param title_font_scale: Scale factor for title font.
    :param image_format: Output image format, such as ``"png"`` or ``"svg"``.
    :param bond_width_scaling: Whether to scale bond widths with structure scale.
    :param title: Whether to display molecule titles.
    :param max_heavy_atoms: Maximum heavy atom count to render, or ``None`` to disable.
    :param device_pixel_ratio: Oversampling ratio for PNG output (1.0 = no oversampling, 2.0 = 2x).
    """
    if not _is_depictable_molecule_dtype(self._obj.dtype):
        raise TypeError(
            f"set_render_options only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). If this "
            "column has molecules, use series.chem.as_molecule() or series.chem.as_query() first."
        )

    options = _collect_render_options(
        width=width,
        height=height,
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
        structure_scale=structure_scale,
        auto_scale=auto_scale,
        atom_label_font_scale=atom_label_font_scale,
        title_font_scale=title_font_scale,
        image_format=image_format,
        bond_width_scaling=bond_width_scaling,
        title=title,
        max_heavy_atoms=max_heavy_atoms,
        device_pixel_ratio=device_pixel_ratio,
    )
    if not options:
        return

    arr = _as_depictable_molecule_array(self._obj.array)
    ctx = get_series_context(arr.metadata, save=True)
    _apply_render_options(ctx, options)


def _series_reset_depictions(self) -> None:
    """
    Reset depiction callbacks for a molecule series
    """
    # Check if array has metadata attribute (should be true for oepandas arrays)
    if hasattr(self._obj.array, "metadata"):
        arr = _as_depictable_molecule_array(self._obj.array)
        _ = arr.metadata.pop("cnotebook", None)


def _series_clear_formatting_rules(self) -> None:
    """
    Clear all formatting rule callbacks from a molecule series.

    This removes any callbacks applied to the molecule prior to rendering,
    such as highlighting. Unlike reset_depictions which removes the entire
    rendering context, this method only clears the callbacks while preserving
    other context settings like image dimensions and styling.
    """
    if hasattr(self._obj.array, "metadata"):
        arr = _as_depictable_molecule_array(self._obj.array)
        ctx = arr.metadata.get("cnotebook", None)
        if ctx is not None and isinstance(ctx, CNotebookContext):
            ctx.reset_callbacks()


def _series_align_depictions(
        self,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | oechem.OEQMol | Literal["first"],
        method: Literal["substructure", "ss", "mcss", "fp", "fingerprint"] | None = None,
        **kwargs
) -> None:
    """
    Align the 2D coordinates of molecules
    :param ref: Alignment reference
    :param method: Alignment method
    :param kwargs: Keyword arguments for aligner
    :return: Aligned molecule depictions
    """
    if not _is_depictable_molecule_dtype(self._obj.dtype):
        raise TypeError(
            f"align_depictions only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get the rendering context for creating the displays
    arr = _as_depictable_molecule_array(self._obj.array)

    if isinstance(ref, str) and ref == "first":
        for mol in arr:
            if mol is not None and mol.IsValid():
                ref = mol.CreateCopy()
                break
        else:
            warn("No valid molecule found in series for depiction alignment")
            return

    # Suppress alignment warnings (there are lots of needless warnings)
    level = oechem.OEThrow.GetLevel()
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Error)

    # noinspection PyBroadException
    try:
        # Create the aligner
        aligner = create_aligner(ref=ref, method=method)

        for mol in arr:
            _ = aligner(mol)

    except Exception as ex:
        log.debug("Error aligning molecules: %s", ex)

    # Restore OEThrow
    finally:
        oechem.OEThrow.SetLevel(level)


########################################################################################################################
# CNotebook DataFrame accessor extensions for OEPandas .chem accessor
########################################################################################################################

def _dataframe_set_render_options(
        self,
        molecule_columns: str | Iterable[str] | None = None,
        *,
        width=_RENDER_OPTION_UNSET,
        height=_RENDER_OPTION_UNSET,
        min_width=_RENDER_OPTION_UNSET,
        min_height=_RENDER_OPTION_UNSET,
        max_width=_RENDER_OPTION_UNSET,
        max_height=_RENDER_OPTION_UNSET,
        structure_scale=_RENDER_OPTION_UNSET,
        auto_scale=_RENDER_OPTION_UNSET,
        atom_label_font_scale=_RENDER_OPTION_UNSET,
        title_font_scale=_RENDER_OPTION_UNSET,
        image_format=_RENDER_OPTION_UNSET,
        bond_width_scaling=_RENDER_OPTION_UNSET,
        title=_RENDER_OPTION_UNSET,
        max_heavy_atoms=_RENDER_OPTION_UNSET,
        device_pixel_ratio=_RENDER_OPTION_UNSET,
) -> None:
    """
    Set rendering options for molecule or query columns in a DataFrame.

    If ``molecule_columns`` is ``None``, all MoleculeDtype and QueryDtype
    columns are updated.

    :param molecule_columns: Optional molecule/query column name or names.
    :param width: Image width in pixels. If 0, determined by structure scale.
    :param height: Image height in pixels. If 0, determined by structure scale.
    :param min_width: Minimum image width in pixels.
    :param min_height: Minimum image height in pixels.
    :param max_width: Maximum image width in pixels, or ``None`` for no limit.
    :param max_height: Maximum image height in pixels, or ``None`` for no limit.
    :param structure_scale: Scale factor applied to OpenEye's default structure
        scale. Ignored when ``auto_scale`` is ``True``.
    :param auto_scale: When ``True``, size structures to fill the image canvas
        (OpenEye AutoScale) instead of using ``structure_scale``.
    :param atom_label_font_scale: Scale factor for atom labels.
    :param title_font_scale: Scale factor for title font.
    :param image_format: Output image format, such as ``"png"`` or ``"svg"``.
    :param bond_width_scaling: Whether to scale bond widths with structure scale.
    :param title: Whether to display molecule titles.
    :param max_heavy_atoms: Maximum heavy atom count to render, or ``None`` to disable.
    :param device_pixel_ratio: Oversampling ratio for PNG output (1.0 = no oversampling, 2.0 = 2x).
    """
    if molecule_columns is None:
        columns = [
            col for col in self._obj.columns
            if _is_depictable_molecule_dtype(self._obj[col].dtype)
        ]
    elif isinstance(molecule_columns, str):
        columns = [molecule_columns]
    else:
        columns = list(molecule_columns)

    for col in columns:
        if col not in self._obj.columns:
            raise ValueError(f'Column {col} not found in DataFrame columns: ({", ".join(self._obj.columns)})')
        if not _is_depictable_molecule_dtype(self._obj[col].dtype):
            raise TypeError(
                f"set_render_options only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). "
                f"Column '{col}' has type {self._obj[col].dtype}."
            )

    options = _collect_render_options(
        width=width,
        height=height,
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
        structure_scale=structure_scale,
        auto_scale=auto_scale,
        atom_label_font_scale=atom_label_font_scale,
        title_font_scale=title_font_scale,
        image_format=image_format,
        bond_width_scaling=bond_width_scaling,
        title=title,
        max_heavy_atoms=max_heavy_atoms,
        device_pixel_ratio=device_pixel_ratio,
    )
    if not options:
        return

    for col in columns:
        self._obj[col].chem.set_render_options(**options)


def _dataframe_recalculate_depiction_coordinates(
        self,
        *,
        molecule_columns: str | Iterable[str] | None = None,
        clear_coords: bool = True,
        add_depction_hydrogens: bool = True,
        perceive_bond_stereo: bool = True,
        suppress_explicit_hydrogens: bool = True,
        orientation: int = oedepict.OEDepictOrientation_Default
) -> None:
    """
    Recalculate the depictions for a one or more molecule series in a DataFrame. If molecule_columns is None,
    which is the default, then all molecule columns will have their depictions recalculated

    See the following link for more information:
    https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

    :param molecule_columns: Optional molecule column(s) to have depictions recalculated
    :param clear_coords: Clear existing 2D coordinates
    :param add_depction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens
    :param orientation: Preferred 2D orientation
    """
    if molecule_columns is None:
        molecule_columns = set()

        for col in self._obj.columns:
            if _is_depictable_molecule_dtype(self._obj.dtypes[col]):
                molecule_columns.add(col)

    elif isinstance(molecule_columns, str):
        molecule_columns = {molecule_columns}

    else:
        molecule_columns = set(molecule_columns)

    # Recalculate the column depictions
    for col in molecule_columns:

        if col in self._obj.columns:
            if _is_depictable_molecule_dtype(self._obj.dtypes[col]):
                self._obj[col].chem.recalculate_depiction_coordinates(
                    clear_coords=clear_coords,
                    add_depction_hydrogens=add_depction_hydrogens,
                    perceive_bond_stereo=perceive_bond_stereo,
                    suppress_explicit_hydrogens=suppress_explicit_hydrogens,
                    orientation=orientation
                )

            else:
                warn(f'Column {col} does not have a MoleculeDtype or QueryDtype')

        else:
            warn(f'{col} not found in DataFrame columns: ({", ".join(self._obj.columns)})')
            molecule_columns.remove(col)


def _dataframe_reset_depictions(self, *, molecule_columns: str | Iterable[str] | None = None) -> None:
    """
    Reset depiction callbacks for one or more columns
    """
    columns = set()
    if molecule_columns is None:
        columns.update(self._obj.columns)

    elif isinstance(molecule_columns, str):
        columns.add(molecule_columns)

    else:
        columns.update(molecule_columns)

    # Filter invalid and non-molecule columns
    for col in filter(
        lambda c: c in self._obj.columns and _is_depictable_molecule_dtype(self._obj[c].dtype),
        columns
    ):
        self._obj[col].chem.reset_depictions()


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
        columns.update(self._obj.columns)

    elif isinstance(molecule_columns, str):
        columns.add(molecule_columns)

    else:
        columns.update(molecule_columns)

    # Filter invalid and non-molecule columns
    for col in filter(
        lambda c: c in self._obj.columns and _is_depictable_molecule_dtype(self._obj[c].dtype),
        columns
    ):
        self._obj[col].chem.clear_formatting_rules()


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

    Example::

        # Highlight benzene rings in the 'smiles' column
        df.chem.highlight("smiles", "c1ccccc1")

        # Highlight multiple patterns
        df.chem.highlight("smiles", ["c1ccccc1", "[OH]"])
    """
    if molecule_column not in self._obj.columns:
        raise ValueError(f'Column {molecule_column} not found in DataFrame columns: ({", ".join(self._obj.columns)})')

    if not _is_depictable_molecule_dtype(self._obj[molecule_column].dtype):
        raise TypeError(
            f"highlight only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). "
            f"Column '{molecule_column}' "
            f"has type {self._obj[molecule_column].dtype}."
        )

    # Delegate to the series-level highlight (which works in Pandas)
    self._obj[molecule_column].chem.highlight(pattern, color=color, style=style)


def _dataframe_copy_molecules(
        self,
        source_column: str,
        dest_column: str,
) -> pd.DataFrame:
    """
    Create a deep copy of molecules from one column to a new column.

    This creates independent copies of all molecules, allowing modifications
    (such as highlighting or alignment) to the new column without affecting
    the original.

    :param source_column: Name of the source molecule column.
    :param dest_column: Name of the new column to create with copied molecules.
    :returns: DataFrame with the new molecule column added.

    Example::

        # Create a copy of molecules for alignment
        df = df.chem.copy_molecules("Original", "Aligned")
        df.chem.highlight("Aligned", "c1ccccc1")
    """
    if source_column not in self._obj.columns:
        raise ValueError(f'Column {source_column} not found in DataFrame columns: ({", ".join(self._obj.columns)})')

    if not isinstance(self._obj[source_column].dtype, oepd.MoleculeDtype):
        raise TypeError(
            f"copy_molecules only works on molecule columns (oepandas.MoleculeDtype). Column '{source_column}' "
            f"has type {self._obj[source_column].dtype}."
        )

    # Use the series-level copy_molecules and assign to the new column
    self._obj[dest_column] = self._obj[source_column].chem.copy_molecules()
    return self._obj


def _dataframe_highlight_using_column(
        self,
        molecule_column: str,
        pattern_column: str,
        *,
        highlighted_column: str = "highlighted_substructures",
        color: oechem.OEColor | oechem.OEColorIter | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
        inplace: bool = False
) -> pd.DataFrame:
    """
    Highlight molecules based on the value of another column. The column produced is a DisplayArray column, so
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
    :param inplace: Modify the DataFrame in place.
    :returns: Modified DataFrame.
    """
    # Object we are operating on
    df = self._obj if inplace else self._obj.copy()

    if molecule_column not in df.columns:
        raise KeyError(f'{molecule_column} not found in DataFrame columns: ({", ".join(df.columns)}')

    if not _is_depictable_molecule_dtype(df[molecule_column].dtype):
        raise TypeError(
            f"highlight_using_column only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). "
            f"If {molecule_column}"
            " has molecules, use df.chem.as_molecule() to convert to a molecule column first."
        )

    if pattern_column not in df.columns:
        raise KeyError(f'{pattern_column} not found in DataFrame columns: ({", ".join(df.columns)}')

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

    # Create the display objects
    indexes = []
    displays = []

    # Get the rendering context for creating the displays
    arr = _as_depictable_molecule_array(df[molecule_column].array)
    ctx = get_series_context(arr.metadata)

    for idx, row in df.iterrows():
        indexes.append(idx)

        mol = row[molecule_column]
        if isinstance(mol, oechem.OEMolBase):

            # Create the display
            disp = oemol_to_disp(mol, ctx=ctx)

            # Highlight
            substructures = []
            patterns = row[pattern_column]

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

            else:
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
                    assert color is not None
                    for c in color:
                        highlight_color = c
                        break
                for ss in substructures:
                    for match in ss.Match(disp.GetMolecule(), True):
                        oedepict.OEAddHighlighting(disp, highlight_color, style, match)

            displays.append(disp)

        else:
            displays.append(None)

    df[highlighted_column] = pd.Series(displays, index=indexes, dtype=oepd.DisplayDtype())
    return df


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


# Store the fingerprint tag for fingerprint_similarity
_fingerprint_overlap_tag = oechem.OEGetTag("fingerprint_overlap")


def _dataframe_fingerprint_similarity(
        self,
        molecule_column: str,
        ref: oechem.OEMolBase | None = None,
        *,
        tanimoto_column="fingerprint_tanimoto",
        reference_similarity_column="reference_similarity",
        target_similarity_column="target_similarity",
        fptype: str = "tree",
        num_bits: int = 4096,
        min_distance: int = 0,
        max_distance: int = 4,
        atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
        bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond,
        inplace: bool = False
) -> pd.DataFrame:
    """
    Color molecules by fingerprint similarity
    :param molecule_column: Name of the molecule column
    :param ref: Reference molecule
    :param tanimoto_column: Name of the tanimoto column
    :param reference_similarity_column: Name of the reference similarity column
    :param target_similarity_column: Name of the target similarity column
    :param fptype: Fingerprint type
    :param num_bits: Number of bits in the fingerprint
    :param min_distance: Minimum distance/radius for path/circular/tree
    :param max_distance: Maximum distance/radius for path/circular/tree
    :param atom_type: Atom type string delimited by "|" OR int bitmask from the oegraphsim.OEFPAtomType_ namespace
    :param bond_type: Bond type string delimited by "|" OR int bitmask from the oegraphsim.OEFPBondType_ namespace
    :param inplace: Modify the DataFrame in place
    :return: DataFrame with similarity columns
    """
    tag = _fingerprint_overlap_tag

    # Preprocess
    df = self._obj if inplace else self._obj.copy()

    if molecule_column not in df.columns:
        raise KeyError(f'Molecule column not found in DataFrame: {molecule_column}')

    if not isinstance(df[molecule_column].dtype, oepd.MoleculeDtype):
        raise TypeError(f"Column {molecule_column} does not have dtype oepd.MoleculeDtype ({df[molecule_column].dtype!s})")

    # Get the context
    arr = self._obj[molecule_column].array
    assert isinstance(arr, oepd.MoleculeArray)
    ctx = get_series_context(arr.metadata)

    # If we're using the first molecule as our reference
    if ref is None:
        for mol in arr:
            if mol.IsValid():  # type: ignore[union-attr]
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

    # Create the display objects
    ref_displays = []
    targ_displays = []

    # FIXME: See now below regarding the fact we have to cache the reference and target molecule copies
    ref_molecules = []
    targ_molecules = []

    tanimotos = []
    index = []

    for idx, mol in df[molecule_column].items():
        index.append(idx)
        if mol is not None and mol.IsValid():

            # Copy the molecules, because we're modifying them
            targ_mol = oechem.OEMol(mol)
            ref_mol = oechem.OEMol(ref)

            # FIXME: See now below regarding the fact we have to cache the reference and target molecule copies
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
                oedepict.OEPrepareDepiction(ref_mol, False)
                oedepict.OEPrepareDepiction(targ_mol, False)

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
                ref_displays.append(None)
                targ_displays.append(None)

        # Molecule was invalid
        else:
            ref_displays.append(None)
            targ_displays.append(None)

    # Add the columns
    df[tanimoto_column] = pd.Series(
        tanimotos,
        index=index,
        dtype=float
    )

    # FIXME: Submitted to OpenEye as Case #00037423
    #        We need to keep the copies of the molecules that we made above, or they will be garbage collected
    #        and the OE2DMolDisplay objects will segfault. We'll keep those in the metadata now for the arrays.
    ref_arr = oepd.DisplayArray(ref_displays, metadata={"molecules": ref_molecules})
    targ_arr = oepd.DisplayArray(targ_displays, metadata={"molecules": targ_molecules})

    df[reference_similarity_column] = pd.Series(
        ref_arr,
        index=shallow_copy(index),
        dtype=oepd.DisplayDtype()
    )

    df[target_similarity_column] = pd.Series(
        targ_arr,
        index=shallow_copy(index),
        dtype=oepd.DisplayDtype()
    )

    return df


########################################################################################################################
# Monkey-patch CNotebook methods onto OEPandas accessors
########################################################################################################################

# Add cnotebook methods to Series accessor
OESeriesAccessor.highlight = _series_highlight  # type: ignore[attr-defined]
OESeriesAccessor.recalculate_depiction_coordinates = _series_recalculate_depiction_coordinates  # type: ignore[attr-defined]
OESeriesAccessor.set_render_options = _series_set_render_options  # type: ignore[attr-defined]
OESeriesAccessor.reset_depictions = _series_reset_depictions  # type: ignore[attr-defined]
OESeriesAccessor.clear_formatting_rules = _series_clear_formatting_rules  # type: ignore[attr-defined]
OESeriesAccessor.align_depictions = _series_align_depictions  # type: ignore[attr-defined]

# Add cnotebook methods to DataFrame accessor
OEDataFrameAccessor.set_render_options = _dataframe_set_render_options  # type: ignore[attr-defined]
OEDataFrameAccessor.recalculate_depiction_coordinates = _dataframe_recalculate_depiction_coordinates  # type: ignore[attr-defined]
OEDataFrameAccessor.reset_depictions = _dataframe_reset_depictions  # type: ignore[attr-defined]
OEDataFrameAccessor.clear_formatting_rules = _dataframe_clear_formatting_rules  # type: ignore[attr-defined]
OEDataFrameAccessor.copy_molecules = _dataframe_copy_molecules  # type: ignore[attr-defined]
OEDataFrameAccessor.highlight = _dataframe_highlight  # type: ignore[attr-defined]
OEDataFrameAccessor.highlight_using_column = _dataframe_highlight_using_column  # type: ignore[attr-defined]
OEDataFrameAccessor.fingerprint_similarity = _dataframe_fingerprint_similarity  # type: ignore[attr-defined]


########################################################################################################################
# MolGrid accessor methods for Series and DataFrame
########################################################################################################################

def _series_molgrid(
    self,
    title: bool | str | None = True,
    tooltip_fields: list | None = None,
    **kwargs
):
    """Display molecules in an interactive grid.

    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
    :param tooltip_fields: Fields for tooltip.
    :param kwargs: Additional arguments passed to MolGrid.
    :returns: MolGrid instance.
    """
    from cnotebook import MolGrid

    series = self._obj
    mols = list(series)

    # Check if series is part of a DataFrame
    df = None
    # noinspection PyProtectedMember
    if hasattr(series, '_cacher') and series._cacher is not None:
        try:
            # noinspection PyProtectedMember
            df = series._cacher[1]()
        except (TypeError, KeyError):
            pass

    return MolGrid(
        mols,
        dataframe=df,
        mol_col=series.name,
        title=title,
        tooltip_fields=tooltip_fields,
        **kwargs
    )


def _dataframe_molgrid(
    self,
    mol_col: str,
    title: bool | str | None = True,
    tooltip_fields: list | None = None,
    **kwargs
):
    """Display molecules from a column in an interactive grid.

    :param mol_col: Column containing molecules.
    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
    :param tooltip_fields: Columns for tooltip.
    :param kwargs: Additional arguments passed to MolGrid.
    :returns: MolGrid instance.
    """
    from cnotebook import MolGrid

    df = self._obj
    mols = list(df[mol_col])

    return MolGrid(
        mols,
        dataframe=df,
        mol_col=mol_col,
        title=title,
        tooltip_fields=tooltip_fields,
        **kwargs
    )


# Add molgrid methods to accessors
OESeriesAccessor.molgrid = _series_molgrid  # type: ignore[attr-defined]
OEDataFrameAccessor.molgrid = _dataframe_molgrid  # type: ignore[attr-defined]
