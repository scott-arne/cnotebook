import html
import logging
import re
import threading
import typing
from collections.abc import Hashable
from contextlib import ExitStack
from typing import Any

import numpy as np
import oepandas as oepd
import pandas as pd
from openeye import oechem, oedepict, oegraphsim

from .context import get_series_context, pass_cnotebook_context
from .core import columnops
from .core import formatters as _fmt
from .core.columnops import AlignmentReport
from .core.errors import warn
from .core.table import (
    CellTokens,
    ColumnKind,
    RowWindow,
    cell_html,
    pandas_max_rows_argument,
)
from .render import CNotebookContext

get_ipython: Any = None

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython.core.getipython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    get_ipython = None
    ipython_present = False


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

# Stands in for a missing depiction cell: Pandas renders NA scalars as the literal text "None"
# without ever calling a column formatter, so missing cells are handed to Pandas as this object.
_MISSING_CELL = object()

# display.max_colwidth is process-global, so renders that have to change it take turns.
_MAX_COLWIDTH_LOCK = threading.Lock()


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


def _escape_attribute_options(kwargs: dict[str, Any]) -> None:
    """
    Escape the ``to_html`` options Pandas writes straight into an HTML attribute.

    Pandas interpolates ``table_id``, ``classes``, ``border`` and ``justify`` into the opening
    ``<table>`` and ``<tr>`` tags without escaping them, so a caller value could close the
    attribute and start markup of its own. (``to_html`` also rejects any ``justify`` outside its
    own fixed list, but escaping it keeps the set of attribute-valued options in one place.)

    :param kwargs: Keyword arguments destined for ``DataFrame.to_html``; escaped in place.
    """
    for name in ("table_id", "justify"):
        value = kwargs.get(name)
        if value is not None:
            kwargs[name] = html.escape(str(value), quote=True)

    classes = kwargs.get("classes")
    if isinstance(classes, str):
        kwargs["classes"] = html.escape(classes, quote=True)
    elif isinstance(classes, (list, tuple)):
        kwargs["classes"] = type(classes)(html.escape(str(item), quote=True) for item in classes)

    # Pandas types border as int | bool | None; anything else is a caller string.
    border = kwargs.get("border")
    if border is not None and not isinstance(border, int):
        kwargs["border"] = html.escape(str(border), quote=True)


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

    Cell tokens cannot survive being shortened, so ordinary cells are never truncated to
    ``display.max_colwidth`` either: Pandas' default HTML writer already renders every cell in
    full, and the notebook writer is made to do the same.

    :param df: Frame to render (never modified).
    :param formatters: Extra Pandas formatters for ordinary columns (copied, never mutated).
        Their output is escaped like any other ordinary cell.
    :param col_space: Extra Pandas ``col_space`` entries (copied, never mutated). For a depiction
        column an ``int`` entry is widened to at least the image width and a non-``int`` entry is
        replaced by the image width; non-``int`` entries are escaped before Pandas writes them
        into the ``style`` attribute.
    :param ctx: Overrides every column context when given; ``None`` honours column contexts.
    :param max_rows: ``None`` for the Pandas display rule, ``<= 0`` for all rows, else the row budget.
    :param kwargs: Forwarded to ``DataFrame.to_html``. ``escape`` and ``render_links`` are ignored
        with a warning, ``buf`` is rejected because this function returns the HTML rather than
        writing it, and the options Pandas writes into HTML attributes are escaped first.
    :returns: HTML table.
    :raises TypeError: If ``buf`` is passed.
    """
    kwargs = dict(kwargs)
    if "escape" in kwargs:
        kwargs.pop("escape")
        warn("render_dataframe always escapes ordinary cells; the escape argument is ignored")

    # Pandas writes the unescaped cell text into the href of a linkified cell.
    if kwargs.pop("render_links", False):
        warn("render_dataframe never linkifies cells; the render_links argument is ignored")

    # Tokens are only substituted in the returned string, so a buffer would receive raw tokens.
    if kwargs.pop("buf", None) is not None:
        raise TypeError("render_dataframe returns the HTML; buf is not supported")

    _escape_attribute_options(kwargs)

    # to_html applies its own "columns" argument after the formatters are bound, which
    # would misalign the positional formatter list; select the columns up front instead.
    columns = kwargs.pop("columns", None)
    if columns is not None:
        # pd.Index normalises the argument the way to_html's own ensure_index call would.
        df = df[pd.Index(columns)]

    adapter = PandasFrameAdapter(df, ctx=ctx)
    tokens = CellTokens()
    labels = adapter.columns()
    caller_formatters = dict(formatters or {})
    # Pandas applies a list of formatters by position, which keeps duplicate and non-string labels distinct.
    positional_formatters: list[Any] = [caller_formatters.get(label) for label in labels]
    # Pandas interpolates a non-int col_space raw into style="min-width: {value};", so escape it
    # here; legitimate widths such as "150px" or "10%" are unchanged by escaping.
    widths: dict[Hashable, str | int] = {
        label: value if isinstance(value, int) else html.escape(str(value), quote=True)
        for label, value in (col_space or {}).items()
    }

    depiction_positions: list[int] = []
    for pos, label in enumerate(labels):
        kind = adapter.kind(pos)
        if kind is ColumnKind.OTHER:
            continue
        depiction_positions.append(pos)
        if positional_formatters[pos] is not None:
            warn(f"Overwriting the formatter for column {label!r} with the depiction formatter")
        column_ctx = adapter.context(pos)
        positional_formatters[pos] = (
            lambda value, _kind=kind, _ctx=column_ctx: tokens.token_for(
                cell_html(_kind, None if value is _MISSING_CELL else value, _ctx)
            )
        )
        if column_ctx.width > 0:
            # col_space is keyed by label in Pandas, so duplicate labels share the widest image.
            previous = widths.get(label)
            widths[label] = max(int(column_ctx.width), previous) if isinstance(previous, int) else int(column_ctx.width)

    render_df = df
    if depiction_positions:
        # Pandas renders an NA scalar as the literal text "None" without calling the column
        # formatter, so missing depiction cells travel as a sentinel the formatter maps back.
        render_df = df.copy(deep=False)
        for pos in depiction_positions:
            column = df.iloc[:, pos]
            cells = np.array(column.array, dtype=object)  # a copy, never the caller's buffer
            cells[np.asarray(column.array.isna(), dtype=bool)] = _MISSING_CELL
            render_df.isetitem(pos, cells)

    with ExitStack() as stack:
        # A trimmed cell token cannot be substituted. Pandas' default writer lifts
        # display.max_colwidth itself, its notebook writer does not, and the option is
        # process-global, so lift it only for the notebook writer and one render at a time.
        if kwargs.get("notebook"):
            stack.enter_context(_MAX_COLWIDTH_LOCK)
            stack.enter_context(pd.option_context("display.max_colwidth", None))
        html_out = render_df.to_html(  # pyright: ignore[reportCallIssue]
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

_MIN_OEPANDAS = (3, 3, 0)
_ATTACHED = False


def _require_molecule_series(series: pd.Series, method: str) -> Any:
    if not _is_depictable_molecule_dtype(series.dtype):
        raise TypeError(
            f"{method} only works on molecule columns ({_DEPICTABLE_MOLECULE_DTYPE_MESSAGE}). If this column has "
            "molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )
    return _as_depictable_molecule_array(series.array)


class PandasColumnAdapter:
    """Column adapter over a pandas Series backed by an oepandas array."""

    def __init__(self, series: pd.Series):
        self.series = series
        self.name = str(series.name)
        self.array = _require_molecule_series(series, "column operation")

    def molecules(self) -> list[oechem.OEMolBase | None]:
        return list(self.array)

    def replace_molecules(self, mols: list[oechem.OEMolBase | None]) -> None:
        for position, mol in enumerate(mols):
            self.array[position] = mol

    def get_context(self, *, create: bool) -> CNotebookContext | None:
        ctx = self.array.metadata.get("cnotebook")
        if isinstance(ctx, CNotebookContext):
            return ctx
        if not create:
            return None
        return get_series_context(self.array.metadata, save=True)

    def set_context(self, ctx: CNotebookContext) -> None:
        self.array.metadata["cnotebook"] = ctx

    def clear_context(self) -> None:
        self.array.metadata.pop("cnotebook", None)

    def set_alignment_report(self, report: AlignmentReport) -> None:
        self.array.metadata["cnotebook_alignment_report"] = report


def _series_highlight(self, pattern, *, color=None, style="overlay_default", ref=None, method=None, **align_kwargs) -> None:
    """Highlight *pattern* in every molecule of this series; align when *ref* is given.

    :param pattern: SMARTS string, search object, or iterable of those.
    :param color: Highlight color(s).
    :param style: Highlight style name or constant.
    :param ref: Alignment reference when given.
    :param method: Alignment method.
    :param align_kwargs: Extra aligner options.
    """
    columnops.highlight(PandasColumnAdapter(self._obj), pattern, color=color, style=style, ref=ref, method=method, **align_kwargs)


def _series_align_depictions(self, ref, method=None, **kwargs) -> AlignmentReport:
    """Align copies of this series' molecules to *ref* and store them in the series.

    :param ref: Molecule, SMARTS, search object, or ``"first"``.
    :param method: Alignment method.
    :param kwargs: Extra aligner options.
    :returns: The alignment report.
    """
    return columnops.align_depictions(PandasColumnAdapter(self._obj), ref, method=method, **kwargs)


def _series_alignment_report(self) -> AlignmentReport | None:
    arr = _require_molecule_series(self._obj, "alignment_report")
    return arr.metadata.get("cnotebook_alignment_report")


def _series_set_render_options(self, **options) -> None:
    """Set render options for this molecule or query series.

    :param options: Render option names and values.
    """
    options = {k: v for k, v in options.items() if v is not _RENDER_OPTION_UNSET}
    if options:
        columnops.set_render_options(PandasColumnAdapter(self._obj), **options)


def _series_reset_depictions(self) -> None:
    if hasattr(self._obj.array, "metadata"):
        columnops.reset_depictions(PandasColumnAdapter(self._obj))


def _series_clear_formatting_rules(self) -> None:
    if hasattr(self._obj.array, "metadata"):
        columnops.clear_formatting_rules(PandasColumnAdapter(self._obj))


def _series_recalculate_depiction_coordinates(self, *, clear_coords=True, add_depiction_hydrogens=True,
                                              perceive_bond_stereo=True, suppress_explicit_hydrogens=True,
                                              orientation=oedepict.OEDepictOrientation_Default) -> None:
    """Recompute 2D coordinates on copies and commit them.

    :param clear_coords: Discard existing 2D coordinates.
    :param add_depiction_hydrogens: Add explicit depiction hydrogens.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo.
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens.
    :param orientation: Preferred 2D orientation.
    """
    columnops.recalculate_depiction_coordinates(
        PandasColumnAdapter(self._obj), clear_coords=clear_coords, add_depiction_hydrogens=add_depiction_hydrogens,
        perceive_bond_stereo=perceive_bond_stereo, suppress_explicit_hydrogens=suppress_explicit_hydrogens,
        orientation=orientation,
    )


def _molecule_columns(df: pd.DataFrame, molecule_columns, method: str) -> list[Hashable]:
    if molecule_columns is None:
        return [c for c in df.columns if _is_depictable_molecule_dtype(df[c].dtype)]
    names = [molecule_columns] if isinstance(molecule_columns, str) else list(molecule_columns)
    for name in names:
        if name not in df.columns:
            warn(f"{name!r} not found in DataFrame columns ({', '.join(map(str, df.columns))}); skipped by {method}")
        elif not _is_depictable_molecule_dtype(df[name].dtype):
            raise TypeError(f"{method} only works on molecule columns; column {name!r} has dtype {df[name].dtype}")
    return [n for n in names if n in df.columns]


def _dataframe_set_render_options(self, molecule_columns=None, **options) -> None:
    """Set render options for molecule or query columns.

    :param molecule_columns: Optional column name(s); ``None`` updates all molecule columns.
    :param options: Render option names and values.
    """
    for name in _molecule_columns(self._obj, molecule_columns, "set_render_options"):
        self._obj[name].chem.set_render_options(**options)


def _dataframe_recalculate_depiction_coordinates(self, molecule_columns=None, **options) -> None:
    """Recalculate 2D coordinates for molecule columns.

    :param molecule_columns: Optional column name(s); ``None`` updates all molecule columns.
    :param options: Depiction options.
    """
    for name in _molecule_columns(self._obj, molecule_columns, "recalculate_depiction_coordinates"):
        self._obj[name].chem.recalculate_depiction_coordinates(**options)


def _dataframe_reset_depictions(self, molecule_columns=None) -> None:
    """Remove column contexts.

    :param molecule_columns: Optional column name(s); ``None`` resets all molecule columns.
    """
    for name in _molecule_columns(self._obj, molecule_columns, "reset_depictions"):
        self._obj[name].chem.reset_depictions()


def _dataframe_clear_formatting_rules(self, molecule_columns=None) -> None:
    """Drop callbacks, keeping other context options.

    :param molecule_columns: Optional column name(s); ``None`` clears all molecule columns.
    """
    for name in _molecule_columns(self._obj, molecule_columns, "clear_formatting_rules"):
        self._obj[name].chem.clear_formatting_rules()


def _dataframe_highlight(self, molecule_column, pattern, *, color=None, style="overlay_default") -> None:
    """Highlight *pattern* in a molecule column.

    :param molecule_column: Column name.
    :param pattern: SMARTS, search object, or iterable of those.
    :param color: Highlight color(s).
    :param style: Highlight style name or constant.
    """
    if molecule_column not in self._obj.columns:
        raise ValueError(f"Column {molecule_column!r} not found in DataFrame columns")
    self._obj[molecule_column].chem.highlight(pattern, color=color, style=style)


def _dataframe_copy_molecules(self, source_column, dest_column) -> pd.DataFrame:
    """Copy molecules from one column to a new column.

    :param source_column: Source column name.
    :param dest_column: Destination column name.
    :returns: The DataFrame with the new column.
    """
    if source_column not in self._obj.columns:
        raise ValueError(f"Column {source_column!r} not found in DataFrame columns")
    if not isinstance(self._obj[source_column].dtype, oepd.MoleculeDtype):
        raise TypeError(f"copy_molecules only works on molecule columns; {source_column!r} has dtype {self._obj[source_column].dtype}")
    self._obj[dest_column] = self._obj[source_column].chem.copy_molecules()
    return self._obj


def _display_column(depictions: list, index) -> pd.Series:
    arr = oepd.DisplayArray([d.display if d is not None else None for d in depictions],
                            metadata={"cnotebook_depictions": depictions})
    return pd.Series(arr, index=index, dtype=oepd.DisplayDtype())


def _dataframe_highlight_using_column(self, molecule_column, pattern_column, *, highlighted_column="highlighted_substructures",
                                      color=None, color_column=None, style="overlay_default", inplace=False) -> pd.DataFrame:
    """Highlight molecules based on per-row patterns.

    :param molecule_column: Molecule column name.
    :param pattern_column: Pattern column name.
    :param highlighted_column: Display column name.
    :param color: Single highlight color.
    :param color_column: Column of per-row colors.
    :param style: Highlight style name or constant.
    :param inplace: Modify the DataFrame in place.
    :returns: Modified DataFrame.
    """
    df = self._obj if inplace else self._obj.copy()
    for name in (molecule_column, pattern_column) + ((color_column,) if color_column else ()):
        if name not in df.columns:
            raise KeyError(f"{name!r} not found in DataFrame columns")
    arr = _require_molecule_series(df[molecule_column], "highlight_using_column")
    ctx = get_series_context(arr.metadata)
    colors = list(df[color_column]) if color_column else ([color] * len(df) if color is not None else None)
    depictions = columnops.build_highlight_column(list(arr), list(df[pattern_column]), colors=colors, style=style, ctx=ctx)
    df[highlighted_column] = _display_column(depictions, df.index)
    return df


def _dataframe_fingerprint_similarity(self, molecule_column, ref=None, *, tanimoto_column="fingerprint_tanimoto",
                                      reference_similarity_column="reference_similarity", target_similarity_column="target_similarity",
                                      fptype="tree", num_bits=4096, min_distance=0, max_distance=4,
                                      atom_type=oegraphsim.OEFPAtomType_DefaultTreeAtom,
                                      bond_type=oegraphsim.OEFPBondType_DefaultTreeBond, inplace=False) -> pd.DataFrame:
    """Tanimoto and overlap-coloured depictions per row.

    :param molecule_column: Molecule column name.
    :param ref: Reference molecule; first valid molecule when ``None``.
    :param tanimoto_column: Tanimoto column name.
    :param reference_similarity_column: Reference display column name.
    :param target_similarity_column: Target display column name.
    :param fptype: Fingerprint type.
    :param num_bits: Number of bits.
    :param min_distance: Minimum distance/radius.
    :param max_distance: Maximum distance/radius.
    :param atom_type: Atom types.
    :param bond_type: Bond types.
    :param inplace: Modify the DataFrame in place.
    :returns: Modified DataFrame.
    """
    df = self._obj if inplace else self._obj.copy()
    if molecule_column not in df.columns:
        raise KeyError(f"Molecule column not found in DataFrame: {molecule_column}")
    if not isinstance(df[molecule_column].dtype, oepd.MoleculeDtype):
        raise TypeError(f"Column {molecule_column!r} does not have dtype oepandas.MoleculeDtype")
    arr = df[molecule_column].array
    ctx = get_series_context(arr.metadata)
    result = columnops.fingerprint_similarity(list(arr), ref, fptype=fptype, num_bits=num_bits, min_distance=min_distance,
                                              max_distance=max_distance, atom_type=atom_type, bond_type=bond_type, ctx=ctx)
    df[tanimoto_column] = pd.Series([float("nan") if t is None else t for t in result.tanimotos], index=df.index, dtype=float)
    df[reference_similarity_column] = _display_column(result.reference, df.index)
    df[target_similarity_column] = _display_column(result.target, df.index)
    return df


def _series_molgrid(self, frame=None, title=True, tooltip_fields=None, **kwargs):
    """Interactive grid of this series' molecules; pass *frame* to include its other columns.

    :param frame: Optional DataFrame to show other columns.
    :param title: Title display mode.
    :param tooltip_fields: Fields for tooltip.
    :param kwargs: Additional MolGrid arguments.
    :returns: MolGrid instance.
    """
    from cnotebook.grid import MolGrid

    return MolGrid(list(self._obj), dataframe=frame, mol_col=self._obj.name if frame is not None else None,
                   title=title, tooltip_fields=tooltip_fields, **kwargs)


def _dataframe_molgrid(self, mol_col, title=True, tooltip_fields=None, **kwargs):
    """Interactive grid from a molecule column.

    :param mol_col: Molecule column name.
    :param title: Title display mode.
    :param tooltip_fields: Columns for tooltip.
    :param kwargs: Additional MolGrid arguments.
    :returns: MolGrid instance.
    """
    from cnotebook.grid import MolGrid

    return MolGrid(list(self._obj[mol_col]), dataframe=self._obj, mol_col=mol_col, title=title,
                   tooltip_fields=tooltip_fields, **kwargs)


def _attach() -> None:
    """Attach cnotebook methods to the oepandas accessors (idempotent, version-guarded)."""
    global _ATTACHED
    if _ATTACHED:
        return
    try:
        version = tuple(int(part) for part in oepd.__version__.split(".")[:3])
        if version < _MIN_OEPANDAS:
            raise ImportError(f"oepandas {oepd.__version__} is older than {'.'.join(map(str, _MIN_OEPANDAS))}")
        from oepandas.pandas_extensions import OEDataFrameAccessor, OESeriesAccessor
    except (ImportError, AttributeError, ValueError) as exc:
        warn(f"cnotebook pandas integration disabled: {exc}")
        return
    for name, func in {
        "highlight": _series_highlight, "align_depictions": _series_align_depictions,
        "set_render_options": _series_set_render_options, "reset_depictions": _series_reset_depictions,
        "clear_formatting_rules": _series_clear_formatting_rules,
        "recalculate_depiction_coordinates": _series_recalculate_depiction_coordinates, "molgrid": _series_molgrid,
    }.items():
        setattr(OESeriesAccessor, name, func)
    OESeriesAccessor.alignment_report = property(_series_alignment_report)  # type: ignore[attr-defined]
    for name, func in {
        "set_render_options": _dataframe_set_render_options,
        "recalculate_depiction_coordinates": _dataframe_recalculate_depiction_coordinates,
        "reset_depictions": _dataframe_reset_depictions, "clear_formatting_rules": _dataframe_clear_formatting_rules,
        "highlight": _dataframe_highlight, "copy_molecules": _dataframe_copy_molecules,
        "highlight_using_column": _dataframe_highlight_using_column,
        "fingerprint_similarity": _dataframe_fingerprint_similarity, "molgrid": _dataframe_molgrid,
    }.items():
        setattr(OEDataFrameAccessor, name, func)
    _ATTACHED = True


_attach()
