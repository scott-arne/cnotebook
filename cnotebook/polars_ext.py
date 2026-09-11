import html as _html
import logging
import sys
import typing
import uuid
from collections import OrderedDict
from collections.abc import Hashable, Iterable
from dataclasses import dataclass, replace
from typing import Any, Literal

import oepolars as oeplr  # pyright: ignore
import polars as pl
from openeye import oechem, oedepict, oegraphsim

from .context import create_local_context, pass_cnotebook_context
from .core import columnops
from .core import formatters as _fmt
from .core.columnops import AlignmentReport
from .core.errors import warn
from .core.table import ColumnKind, RowWindow, polars_row_window, render_table
from .core.versions import at_least as _at_least
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

if typing.TYPE_CHECKING:
    from .context import CNotebookContext
    from .grid import MolGrid

log = logging.getLogger("cnotebook")


@dataclass
class ColumnState:
    """
    Per-token column state.

    Forks receive their own copy of the report, so a caller that writes into a report it
    read from one frame cannot change what a sibling frame reports.

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
        column's dtype token, then a fresh local context.

        :param pos: Column position.
        :returns: Render context for every cell of the column.
        """
        if self._ctx is not None:
            return self._ctx
        ctx = context_for_token(getattr(self._series[pos].dtype, "token", None))
        return ctx if ctx is not None else create_local_context()

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
# Column accessor methods (attached to the oepolars chem namespaces)
########################################################################################################################

# The accessors are registered through oepolars' public extension hooks, which only exist
# from this release on.
_MIN_OEPOLARS = (0, 4, 0)
_ATTACHED = False


def _require_molecule(
        df: pl.DataFrame,
        column: str,
        method: str,
        *,
        missing: type[Exception] = ValueError
) -> None:
    """
    Check that *column* exists in *df* and holds molecules.

    :param df: Frame to check.
    :param column: Column name.
    :param method: Accessor name, used in the messages.
    :param missing: Exception raised when the column is absent; the default keeps a
        missing column and an unusable column both reporting as bad arguments.
    :raises ValueError: When *column* is absent and *missing* is left at its default.
    :raises TypeError: When *column* does not hold molecules.
    """
    if column not in df.columns:
        raise missing(f"Column {column!r} not found in DataFrame columns ({', '.join(df.columns)})")
    if not isinstance(df.schema[column], oeplr.MoleculeType):
        raise TypeError(f"{method} only works on molecule columns (oepolars.MoleculeType). "
                        f"Column {column!r} has type {df.schema[column]}.")


class PolarsColumnAdapter:
    """
    Column adapter over one column of a Polars frame.

    Polars frames are immutable, so an operation that changes the column or its token
    produces a new frame. :attr:`frame` is the current one, and the accessor hands it
    back to the caller once the operation is done.
    """

    def __init__(self, df: pl.DataFrame, column: str):
        """
        Wrap one column of a frame.

        :param df: Frame holding the column.
        :param column: Column name.
        """
        self.frame = df
        self.column = column
        self.name = column

    @property
    def _token(self) -> str | None:
        """
        Report the token carried by the column's dtype.

        :returns: The token, or ``None`` for an untokenized column.
        """
        return getattr(self.frame.schema[self.column], "token", None)

    def molecules(self) -> list[oechem.OEMolBase | None]:
        """
        Read the column's molecules.

        :returns: One entry per row, ``None`` where the cell is empty.
        """
        return self.frame.get_column(self.column).to_list()

    def replace_molecules(self, mols: list[oechem.OEMolBase | None]) -> None:
        """
        Commit *mols* into a new frame, keeping the column's dtype and token.

        :param mols: Replacement molecules, one per row.
        """
        dtype = self.frame.schema[self.column]
        self.frame = self.frame.with_columns(
            pl.Series(self.column, mols, dtype=type(dtype)(getattr(dtype, "token", None)))
        )

    def get_context(self, *, create: bool) -> CNotebookContext | None:
        """
        Return the render context of the column.

        :param create: When the column has no state, mint a token for a fresh local
            context and carry it on :attr:`frame`.
        :returns: The column's context, or ``None`` when it has none and *create* is false.
        """
        state = state_for_token(self._token)
        if state is not None:
            return state.context
        if not create:
            return None
        state = ColumnState(create_local_context())
        self._retoken(state)
        return state.context

    def set_context(self, ctx: CNotebookContext) -> None:
        """
        Store *ctx* as the render context of the column.

        :param ctx: Context to store.
        """
        state = state_for_token(self._token)
        if state is None:
            self._retoken(ColumnState(ctx))
        else:
            state.context = ctx

    def clear_context(self) -> None:
        """
        Drop the column's token on this frame.

        The state itself stays in the registry: sibling frames may still carry the token,
        and their columns keep rendering with the context they were given.
        """
        if self._token is not None:
            self.frame = self.frame.chem.with_token(self.column, None)

    def set_alignment_report(self, report: AlignmentReport) -> None:
        """
        Record the outcome of the last depiction alignment on the column.

        :param report: Report to store.
        """
        state = state_for_token(self._token)
        if state is None:
            self._retoken(ColumnState(create_local_context(), report))
        else:
            state.alignment_report = report

    def _retoken(self, state: ColumnState) -> None:
        """
        Store *state* under a fresh token and carry that token on :attr:`frame`.

        :param state: State for the column.
        """
        token = new_token()
        store_state(token, state)
        self.frame = self.frame.chem.with_token(self.column, token)


def _copy_report(report: AlignmentReport | None) -> AlignmentReport | None:
    """
    Copy an alignment report, including its mutable fields.

    A report handed out by ``alignment_report`` is an ordinary object the caller may write
    to, so forks cannot share one: ``failed`` is the only mutable field, and it is copied.

    :param report: Report to copy, or ``None`` when the column was never aligned.
    :returns: An equal report that shares nothing with *report*, or ``None``.
    """
    return None if report is None else replace(report, failed=list(report.failed))


def _copied_state(df: pl.DataFrame, column: str, *, keep_report: bool) -> ColumnState:
    """
    Build the state a new column inherits from *column*.

    :param df: Frame holding the source column.
    :param column: Source column name.
    :param keep_report: Carry a copy of the source's alignment report. A generated display
        column has no alignment of its own, so it starts without one.
    :returns: State copied from the source column, or a fresh one when it had none.
    """
    old = state_for_token(getattr(df.schema[column], "token", None))
    if old is None:
        return ColumnState(create_local_context())
    # clone(), not copy(): an option the column left deferred has to stay deferred in the
    # copy, so both frames keep following the global context for it.
    return ColumnState(old.context.clone(), _copy_report(old.alignment_report) if keep_report else None)


def fork_column(df: pl.DataFrame, column: str, method: str) -> PolarsColumnAdapter:
    """
    Copy-on-write: an adapter over *df* whose *column* carries a copy of its state.

    The operation that follows commits into the returned adapter's frame only. Frames
    still carrying the old token -- filters, slices and other siblings taken before the
    call -- keep the state they were made with.

    :param df: Frame to fork; never modified.
    :param column: Molecule column to fork.
    :param method: Accessor name, used in the messages.
    :returns: Adapter over a new frame whose column carries the copied state.
    :raises ValueError: When *column* is not one of the frame's columns.
    :raises TypeError: When *column* does not hold molecules.
    """
    _require_molecule(df, column, method)
    token = new_token()
    store_state(token, _copied_state(df, column, keep_report=True))
    return PolarsColumnAdapter(df.chem.with_token(column, token), column)


def _columns(df: pl.DataFrame, molecule_columns: str | Iterable[str] | None, method: str) -> list[str]:
    """
    Resolve the molecule columns an accessor should work on.

    :param df: Frame to look in.
    :param molecule_columns: Column name, iterable of names, or ``None`` for every
        molecule column of the frame.
    :param method: Accessor name, used in the warnings.
    :returns: The usable molecule column names, in the order requested. Names that are
        absent or hold something else are reported with a warning and left out.
    """
    if molecule_columns is None:
        return [name for name in df.columns if isinstance(df.schema[name], oeplr.MoleculeType)]
    names = [molecule_columns] if isinstance(molecule_columns, str) else list(molecule_columns)
    found = []
    for name in names:
        # stacklevel=3 steps over this helper and the accessor so the user's call is blamed.
        if name not in df.columns:
            warn(f"{name!r} not found in DataFrame columns ({', '.join(df.columns)}); skipped by {method}",
                 stacklevel=3)
        elif not isinstance(df.schema[name], oeplr.MoleculeType):
            warn(f"Column {name!r} does not have a MoleculeType; skipped by {method}", stacklevel=3)
        else:
            found.append(name)
    return found


def _copied_token(df: pl.DataFrame, column: str, *, keep_report: bool = False) -> str:
    """
    Mint a token whose state copies the state of *column*.

    Columns made from another column render with the settings of the column they came
    from, but changing one of them afterwards must not change the other.

    :param df: Frame holding the source column.
    :param column: Source column name.
    :param keep_report: Carry a copy of the source's alignment report, as a copied
        molecule column does. Generated display columns leave it out.
    :returns: A fresh token, already registered.
    """
    token = new_token()
    store_state(token, _copied_state(df, column, keep_report=keep_report))
    return token


def _display_series(name: str, depictions: list[Any], token: str) -> pl.Series:
    """
    Build a display column from prepared depictions.

    :param name: Column name.
    :param depictions: One :class:`~cnotebook.core.render.Depiction` per row, or ``None``
        where no depiction could be made.
    :param token: Token to carry on the column dtype.
    :returns: A ``DisplayType`` Series. Only the display is stored, and it keeps its
        molecule alive through the owner reference the depiction set on it.
    """
    return pl.Series(name, [d.display if d is not None else None for d in depictions],
                     dtype=oeplr.DisplayType(token))


def _dataframe_highlight(
        self,
        molecule_column: str,
        pattern: Iterable[str] | str | oechem.OESubSearch | Iterable[oechem.OESubSearch],
        *,
        color: oechem.OEColor | oechem.OEColorIter | str | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | None = None,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None,
        **align_kwargs: Any
) -> pl.DataFrame:
    """
    Highlight substructures in a molecule column.

    :param molecule_column: Molecule column to highlight.
    :param pattern: SMARTS string, search object, or an iterable of either, one per row.
    :param color: Highlight colour, as an ``OEColor``, an ``OEColorIter`` or ``#RRGGBB``.
    :param style: Highlight style name, or an ``OEHighlightStyle`` constant.
    :param ref: Alignment reference; the depictions are aligned before highlighting when given.
    :param method: Alignment method used with *ref*.
    :param align_kwargs: Further options for the aligner.
    :returns: A new frame whose molecule column carries the highlighted depictions.
    :raises ValueError: When *molecule_column* is not one of the frame's columns.
    :raises TypeError: When *molecule_column* does not hold molecules, or a pattern cannot be used.
    """
    col = fork_column(self._df, molecule_column, "highlight")
    columnops.highlight(col, pattern, color=color, style=style, ref=ref, method=method, **align_kwargs)
    return col.frame


def _dataframe_set_render_options(
        self,
        molecule_columns: str | Iterable[str] | None = None,
        **options: Any
) -> pl.DataFrame:
    """
    Set render options on one or more molecule columns.

    :param molecule_columns: Column name, iterable of names, or ``None`` for every
        molecule column of the frame.
    :param options: Context options, such as ``width``, ``height`` or ``title``.
    :returns: A new frame whose named columns carry the new options.
    """
    frame = self._df
    for name in _columns(frame, molecule_columns, "set_render_options"):
        col = fork_column(frame, name, "set_render_options")
        columnops.set_render_options(col, **options)
        frame = col.frame
    return frame


def _dataframe_reset_depictions(self, molecule_columns: str | Iterable[str] | None = None) -> pl.DataFrame:
    """
    Drop the render settings of one or more molecule columns.

    :param molecule_columns: Column name, iterable of names, or ``None`` for every
        molecule column of the frame.
    :returns: A new frame whose named columns render with the global defaults again.
        Sibling frames keep the settings they were made with.
    """
    frame = self._df
    for name in _columns(frame, molecule_columns, "reset_depictions"):
        col = PolarsColumnAdapter(frame, name)
        columnops.reset_depictions(col)
        frame = col.frame
    return frame


def _dataframe_clear_formatting_rules(self, molecule_columns: str | Iterable[str] | None = None) -> pl.DataFrame:
    """
    Drop the display callbacks of one or more molecule columns, keeping their other options.

    :param molecule_columns: Column name, iterable of names, or ``None`` for every
        molecule column of the frame.
    :returns: A new frame whose named columns have no display callbacks left.
    """
    frame = self._df
    for name in _columns(frame, molecule_columns, "clear_formatting_rules"):
        col = fork_column(frame, name, "clear_formatting_rules")
        columnops.clear_formatting_rules(col)
        frame = col.frame
    return frame


def _dataframe_align_depictions(
        self,
        molecule_column: str,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | str,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None,
        **kwargs: Any
) -> pl.DataFrame:
    """
    Align the depictions of a molecule column to a reference.

    :param molecule_column: Molecule column to align.
    :param ref: Reference molecule, SMARTS or search object, or ``"first"`` for the first
        valid molecule of the column.
    :param method: Alignment method; inferred from *ref* when omitted.
    :param kwargs: Further options for the aligner.
    :returns: A new frame whose molecule column carries the aligned depictions. The
        outcome is available from :func:`_dataframe_alignment_report`.
    :raises ValueError: When *molecule_column* is not one of the frame's columns.
    :raises TypeError: When *molecule_column* does not hold molecules.
    """
    col = fork_column(self._df, molecule_column, "align_depictions")
    columnops.align_depictions(col, ref, method=method, **kwargs)
    return col.frame


def _dataframe_alignment_report(self, molecule_column: str) -> AlignmentReport | None:
    """
    Report the outcome of the last depiction alignment of a molecule column.

    :param molecule_column: Molecule column to report on.
    :returns: The report, or ``None`` when the column has never been aligned.
    :raises ValueError: When *molecule_column* is not one of the frame's columns.
    :raises TypeError: When *molecule_column* does not hold molecules.
    """
    _require_molecule(self._df, molecule_column, "alignment_report")
    state = state_for_token(getattr(self._df.schema[molecule_column], "token", None))
    return state.alignment_report if state is not None else None


def _dataframe_recalculate_depiction_coordinates(
        self,
        *,
        molecule_columns: str | Iterable[str] | None = None,
        **options: Any
) -> pl.DataFrame:
    """
    Lay out 2D depiction coordinates again for one or more molecule columns.

    :param molecule_columns: Column name, iterable of names, or ``None`` for every
        molecule column of the frame.
    :param options: Further options for the depiction preparation.
    :returns: A new frame holding molecules with fresh coordinates.
    """
    frame = self._df
    for name in _columns(frame, molecule_columns, "recalculate_depiction_coordinates"):
        col = fork_column(frame, name, "recalculate_depiction_coordinates")
        columnops.recalculate_depiction_coordinates(col, **options)
        frame = col.frame
    return frame


def _dataframe_copy_molecules(self, source_column: str, dest_column: str) -> pl.DataFrame:
    """
    Copy a molecule column, so the two columns can be depicted differently.

    :param source_column: Molecule column to copy.
    :param dest_column: Name of the new column; an existing column of that name is replaced.
    :returns: A new frame with the copied column, whose render settings start as a copy
        of the source column's.
    :raises ValueError: When *source_column* is not one of the frame's columns.
    :raises TypeError: When *source_column* does not hold molecules.
    """
    _require_molecule(self._df, source_column, "copy_molecules")
    # CreateCopy() keeps the conformers of a multi-conformer molecule, which the graph
    # molecule constructor would drop.
    copies = [None if m is None else m.CreateCopy() for m in self._df.get_column(source_column).to_list()]
    # B6: the copy starts from the source's whole state, its alignment report included.
    token = _copied_token(self._df, source_column, keep_report=True)
    return self._df.with_columns(pl.Series(dest_column, copies, dtype=oeplr.MoleculeType(token)))


def _dataframe_highlight_using_column(
        self,
        molecule_column: str,
        pattern_column: str,
        *,
        highlighted_column: str = "highlighted_substructures",
        color: oechem.OEColor | oechem.OEColorIter | str | None = None,
        color_column: str | None = None,
        style: int | Literal["overlay_default", "overlay_ball_and_stick"] = "overlay_default",
        inplace: bool = False
) -> pl.DataFrame:
    """
    Highlight a per-row pattern, taken from another column, into a new display column.

    :param molecule_column: Molecule column to highlight.
    :param pattern_column: Column holding one SMARTS (or search object) per row.
    :param highlighted_column: Name of the display column to add.
    :param color: Highlight colour used for every row.
    :param color_column: Column holding one colour per row; overrides *color*.
    :param style: Highlight style name, or an ``OEHighlightStyle`` constant.
    :param inplace: Ignored, and reported: Polars frames cannot be modified in place.
    :returns: A new frame with the display column added.
    :raises KeyError: When one of the named columns is not in the frame.
    :raises TypeError: When *molecule_column* does not hold molecules.
    """
    if inplace:
        warn("highlight_using_column: polars frames are immutable; a new frame is returned")
    df = self._df
    _require_molecule(df, molecule_column, "highlight_using_column", missing=KeyError)
    # An empty column name is a usable name, so ask about presence, not truthiness.
    for name in (pattern_column,) + ((color_column,) if color_column is not None else ()):
        if name not in df.columns:
            raise KeyError(f"{name!r} not found in DataFrame columns ({', '.join(df.columns)})")
    ctx = PolarsFrameAdapter(df).context(df.columns.index(molecule_column))
    if color_column is not None:
        # Null cells stay None so columnops skips colouring those rows.
        colors = df.get_column(color_column).to_list()
    else:
        colors = [color] * len(df) if color is not None else None
    depictions = columnops.build_highlight_column(
        df.get_column(molecule_column).to_list(),
        df.get_column(pattern_column).to_list(),
        colors=colors,
        style=style,
        ctx=ctx,
    )
    return df.with_columns(_display_series(highlighted_column, depictions, _copied_token(df, molecule_column)))


def _dataframe_fingerprint_similarity(
        self,
        molecule_column: str,
        ref: oechem.OEMolBase | None = None,
        *,
        tanimoto_column: str = "fingerprint_tanimoto",
        reference_similarity_column: str = "reference_similarity",
        target_similarity_column: str = "target_similarity",
        fptype: Literal["tree", "path", "circular", "maccs", "maccs166"] = "tree",
        num_bits: int = 4096,
        min_distance: int = 0,
        max_distance: int = 4,
        atom_type: int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
        bond_type: int = oegraphsim.OEFPBondType_DefaultTreeBond,
        inplace: bool = False
) -> pl.DataFrame:
    """
    Score a molecule column against a reference and depict the overlapping fingerprint bits.

    :param molecule_column: Molecule column to score.
    :param ref: Reference molecule; the first valid molecule of the column when omitted.
    :param tanimoto_column: Name of the similarity column to add.
    :param reference_similarity_column: Name of the display column showing the reference.
    :param target_similarity_column: Name of the display column showing each target.
    :param fptype: Fingerprint type.
    :param num_bits: Fingerprint size in bits.
    :param min_distance: Smallest path or tree size fingerprinted.
    :param max_distance: Largest path or tree size fingerprinted.
    :param atom_type: Atom typing used by the fingerprint.
    :param bond_type: Bond typing used by the fingerprint.
    :param inplace: Ignored, and reported: Polars frames cannot be modified in place.
    :returns: A new frame with the similarity column and the two display columns added.
    :raises KeyError: When *molecule_column* is not one of the frame's columns.
    :raises TypeError: When *molecule_column* does not hold molecules.
    """
    if inplace:
        warn("fingerprint_similarity: polars frames are immutable; a new frame is returned")
    df = self._df
    _require_molecule(df, molecule_column, "fingerprint_similarity", missing=KeyError)
    ctx = PolarsFrameAdapter(df).context(df.columns.index(molecule_column))
    result = columnops.fingerprint_similarity(
        df.get_column(molecule_column).to_list(),
        ref,
        fptype=fptype,
        num_bits=num_bits,
        min_distance=min_distance,
        max_distance=max_distance,
        atom_type=atom_type,
        bond_type=bond_type,
        ctx=ctx,
    )
    token = _copied_token(df, molecule_column)
    return df.with_columns([
        pl.Series(tanimoto_column, result.tanimotos, dtype=pl.Float64),
        _display_series(reference_similarity_column, result.reference, token),
        _display_series(target_similarity_column, result.target, token),
    ])


def _series_align_depictions(
        self,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | str,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None,
        **kwargs: Any
) -> pl.Series:
    """
    Align the depictions of a molecule Series to a reference.

    :param ref: Reference molecule, SMARTS or search object, or ``"first"`` for the first
        valid molecule of the Series.
    :param method: Alignment method; inferred from *ref* when omitted.
    :param kwargs: Further options for the aligner.
    :returns: A new Series carrying the aligned depictions.
    :raises TypeError: When the Series does not hold molecules.
    """
    series = self._series
    if not isinstance(series.dtype, oeplr.MoleculeType):
        raise TypeError("align_depictions only works on molecule columns (oepolars.MoleculeType).")
    # polars gives an unnamed Series a label of its own inside a frame, so work with the
    # frame's label and put the Series' own name back on the way out.
    frame = pl.DataFrame([series])
    label = frame.columns[0]
    col = fork_column(frame, label, "align_depictions")
    columnops.align_depictions(col, ref, method=method, **kwargs)
    return col.frame.get_column(label).rename(series.name)


def _series_recalculate_depiction_coordinates(self, **options: Any) -> pl.Series:
    """
    Lay out the 2D depiction coordinates of a molecule Series again.

    :param options: Further options for the depiction preparation.
    :returns: A new Series holding molecules with fresh coordinates.
    :raises TypeError: When the Series does not hold molecules.
    """
    series = self._series
    if not isinstance(series.dtype, oeplr.MoleculeType):
        raise TypeError("recalculate_depiction_coordinates only works on molecule columns (oepolars.MoleculeType).")
    frame = pl.DataFrame([series])
    label = frame.columns[0]
    col = fork_column(frame, label, "recalculate_depiction_coordinates")
    columnops.recalculate_depiction_coordinates(col, **options)
    return col.frame.get_column(label).rename(series.name)


def _series_molgrid(
        self,
        title: bool | str | None = True,
        tooltip_fields: list[str] | None = None,
        **kwargs: Any
) -> "MolGrid":
    """
    Display the molecules of a Series in an interactive grid.

    :param title: ``True`` for each molecule's own title, a string to name a field, or
        ``None``/``False`` for no titles.
    :param tooltip_fields: Fields shown in the tooltip.
    :param kwargs: Further options for :class:`~cnotebook.grid.MolGrid`.
    :returns: The grid.
    """
    from cnotebook.grid import MolGrid

    return MolGrid(self._series.to_list(), title=title, tooltip_fields=tooltip_fields, **kwargs)


def _dataframe_molgrid(
        self,
        mol_col: str,
        title: bool | str | None = True,
        tooltip_fields: list[str] | None = None,
        **kwargs: Any
) -> "MolGrid":
    """
    Display the molecules of a column in an interactive grid.

    :param mol_col: Molecule column to display.
    :param title: ``True`` for each molecule's own title, a string to name a column, or
        ``None``/``False`` for no titles.
    :param tooltip_fields: Columns shown in the tooltip.
    :param kwargs: Further options for :class:`~cnotebook.grid.MolGrid`.
    :returns: The grid.
    """
    import pandas as pd

    from cnotebook.grid import MolGrid

    # MolGrid reads pandas frames, so the non-molecule columns are handed over as plain
    # Python values, which also keeps pyarrow out of the conversion.
    pdf = pd.DataFrame({col: self._df.get_column(col).to_list() for col in self._df.columns if col != mol_col})
    return MolGrid(self._df.get_column(mol_col).to_list(), dataframe=pdf, mol_col=mol_col, title=title,
                   tooltip_fields=tooltip_fields, **kwargs)


def _attach() -> None:
    """
    Register the accessor methods through oepolars' public extension hooks.

    The call is idempotent and version-guarded: an oepolars too old for the hooks, or one
    whose version cannot be read, leaves the accessors unregistered and warns rather than
    failing the import of cnotebook. Polars support becoming available is also what tells
    the marimo adapter it can register a polars table formatter.
    """
    global _ATTACHED
    if _ATTACHED:
        return
    try:
        if not _at_least(oeplr.__version__, _MIN_OEPOLARS):
            raise ImportError(f"oepolars {oeplr.__version__} is older than {'.'.join(map(str, _MIN_OEPOLARS))}")
        from oepolars import extensions
    except (ImportError, AttributeError, ValueError) as exc:
        warn(f"cnotebook polars integration disabled: {exc}")
        return
    for name, series_func in {
        "align_depictions": _series_align_depictions,
        "recalculate_depiction_coordinates": _series_recalculate_depiction_coordinates,
        "molgrid": _series_molgrid,
    }.items():
        extensions.register_series_method(name, series_func, overwrite=True)
    for name, frame_func in {
        "highlight": _dataframe_highlight,
        "set_render_options": _dataframe_set_render_options,
        "reset_depictions": _dataframe_reset_depictions,
        "clear_formatting_rules": _dataframe_clear_formatting_rules,
        "align_depictions": _dataframe_align_depictions,
        "alignment_report": _dataframe_alignment_report,
        "recalculate_depiction_coordinates": _dataframe_recalculate_depiction_coordinates,
        "copy_molecules": _dataframe_copy_molecules,
        "highlight_using_column": _dataframe_highlight_using_column,
        "fingerprint_similarity": _dataframe_fingerprint_similarity,
        "molgrid": _dataframe_molgrid,
    }.items():
        extensions.register_dataframe_method(name, frame_func, overwrite=True)
    if "marimo" in sys.modules:
        # A marimo problem must not cost the caller polars support, so the tail cannot
        # be allowed to escape before _ATTACHED is set.
        try:
            from cnotebook import marimo_ext

            marimo_ext._attach()
        except Exception as exc:  # noqa: BLE001 - reported, never fatal to polars support
            warn(f"cnotebook marimo table integration disabled: {exc}")
    _ATTACHED = True


_attach()


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
