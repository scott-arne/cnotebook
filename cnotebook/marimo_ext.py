"""
Marimo integration for CNotebook.

This module provides MIME handlers for bare OpenEye objects and registers table
formatters for pandas and polars frames with Marimo's formatter registry. Molecule,
query, display and design-unit columns render through the shared cell formatters
with the render context stored on each column, so highlighting, alignment and
sizing survive into Marimo's built-in table component.

Neither pandas nor polars is imported at module level: the formatters and
:func:`_attach` reach for whichever of them the session has already imported.
"""
import sys
from collections.abc import Callable, Iterable
from typing import Any

from openeye import oechem, oedepict

from cnotebook.core import formatters as _fmt
from cnotebook.core.context import CNotebookContext, cnotebook_context
from cnotebook.core.errors import warn
from cnotebook.core.render import (
    make_depiction,
    oedisp_to_html,
    oedu_to_disp,
    oedu_to_html,
    oeimage_to_html,
    oemol_to_html,
)
from cnotebook.core.table import ColumnKind, FrameAdapter
from cnotebook.core.versions import at_least as _at_least

########################################################################################################################
# MIME handlers for individual OpenEye objects
########################################################################################################################

def _display_mol(self: oechem.OEMolBase):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oemol_to_html(self, ctx=ctx)

oechem.OEMolBase._mime_ = _display_mol  # pyright: ignore


def _display_display(self: oedepict.OE2DMolDisplay):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oedisp_to_html(self, ctx=ctx)

oedepict.OE2DMolDisplay._mime_ = _display_display  # pyright: ignore


def _display_du(self: oechem.OEDesignUnit):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oedu_to_html(self, ctx=ctx)

oechem.OEDesignUnit._mime_ = _display_du  # pyright: ignore


def _display_image(self: oedepict.OEImage):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oeimage_to_html(self, ctx=ctx)

oedepict.OEImage._mime_ = _display_image  # pyright: ignore


########################################################################################################################
# Context-bound image wrapper
#
# Marimo serializes a table cell by calling the cell value's ``_mime_`` method. The globally
# registered ``OEImage._mime_`` hook reads the ambient ``cnotebook_context``, which is not the
# column's context, so the per-column width, image format and device pixel ratio would be lost
# on the way out. Wrapping the image pairs it with the context that rendered it.
########################################################################################################################

# Marimo's table factory, bound by :func:`_attach` so that the module imports without marimo.
table: Any = None


class _CtxBoundImage:
    """Pair an image with the context that should drive its HTML serialisation.

    :param image: Image rendered for one cell.
    :param ctx: The column's render context.
    """

    __slots__ = ("_ctx", "_image")

    def __init__(self, image: oedepict.OEImage, ctx: CNotebookContext):
        self._image = image
        self._ctx = ctx

    def _mime_(self) -> tuple[str, str]:
        """Serialise the image for marimo.

        :returns: ``("text/html", html)``, where the HTML is the trusted depiction
            markup produced by :func:`~cnotebook.core.render.oeimage_to_html`.
        """
        # The raster may be oversampled for HiDPI, so the CSS size has to come from the
        # logical size the formatter attached rather than from the pixel dimensions.
        logical = getattr(self._image, "_cnotebook_logical_size", None)
        if logical:
            return "text/html", oeimage_to_html(
                self._image, ctx=self._ctx, logical_width=logical[0], logical_height=logical[1]
            )
        return "text/html", oeimage_to_html(self._image, ctx=self._ctx)


########################################################################################################################
# Formatter factories for the table's format_mapping
#
# Marimo escapes whatever a formatter returns unless it is a MIME object, so only the depiction
# HTML of a _CtxBoundImage is ever inserted raw: ``None`` becomes an empty cell and anything that
# is not the column's own object type falls back to its escaped text.
########################################################################################################################

def _create_molecule_formatter(ctx: CNotebookContext) -> Callable[[Any], Any]:
    """Build the cell formatter for a molecule or query column.

    :param ctx: The column's render context; its callbacks run once per cell.
    :returns: Callable turning one cell value into a ``_CtxBoundImage`` or plain text.
    """
    def formatter(mol: Any) -> Any:
        if mol is None:
            return ""
        image = _fmt.molecule_cell_image(mol, ctx)
        return _CtxBoundImage(image, ctx) if image is not None else str(mol)
    return formatter


def _create_display_formatter(ctx: CNotebookContext) -> Callable[[Any], Any]:
    """Build the cell formatter for a display column.

    :param ctx: The column's render context; its callbacks run once per cell.
    :returns: Callable turning one cell value into a ``_CtxBoundImage`` or plain text.
    """
    def formatter(disp: Any) -> Any:
        if disp is None:
            return ""
        image = _fmt.display_cell_image(disp, ctx)
        return _CtxBoundImage(image, ctx) if image is not None else str(disp)
    return formatter


def _create_du_formatter(ctx: CNotebookContext) -> Callable[[Any], Any]:
    """Build the cell formatter for a design-unit column.

    :param ctx: The column's render context; its callbacks run once per cell.
    :returns: Callable turning one cell value into a ``_CtxBoundImage`` or plain text.
    """
    def formatter(du: Any) -> Any:
        if du is None:
            return ""
        image = _fmt.design_unit_cell_image(du, ctx)
        return _CtxBoundImage(image, ctx) if image is not None else str(du)
    return formatter


_FACTORIES: dict[ColumnKind, Callable[[CNotebookContext], Callable[[Any], Any]]] = {
    ColumnKind.MOLECULE: _create_molecule_formatter,
    ColumnKind.QUERY: _create_molecule_formatter,
    ColumnKind.DISPLAY: _create_display_formatter,
    ColumnKind.DESIGN_UNIT: _create_du_formatter,
}


########################################################################################################################
# Column-width pre-pass
#
# Marimo sizes a column from cell CSS. With fixed-scale rendering every molecule reports its own
# intrinsic canvas width, so without a uniform width the narrower cells clip the wider ones. A
# cheap pre-pass over the column (sizes only, no rasterization) gives every cell in the column the
# width of its widest structure.
########################################################################################################################

_WIDTH_SAMPLE = 200


def _column_width(values: Iterable[Any], kind: ColumnKind, ctx: CNotebookContext) -> int:
    """Widest intrinsic canvas over the first ``_WIDTH_SAMPLE`` values of a column.

    :param values: The column's cell values, in row order.
    :param kind: The column's kind; other kinds contribute nothing.
    :param ctx: The column's render context.
    :returns: Width in pixels, ``0`` when nothing in the sample is depictable.
    """
    width = 0
    for value in list(values)[:_WIDTH_SAMPLE]:
        candidate = 0
        if kind in (ColumnKind.MOLECULE, ColumnKind.QUERY) and isinstance(value, oechem.OEMolBase):
            if not value.IsValid() or value.NumAtoms() == 0 or (
                ctx.max_heavy_atoms is not None and oechem.OECount(value, oechem.OEIsHeavy()) > ctx.max_heavy_atoms
            ):
                candidate = int(ctx.min_width or 200)
            else:
                # The canvas size does not depend on the annotation callbacks, and the cell
                # formatters apply them exactly once per render, so the sizing pass must not
                # run them a second time.
                candidate = int(make_depiction(value, ctx=ctx, apply_callbacks=False).display.GetWidth())
        elif kind is ColumnKind.DISPLAY and isinstance(value, oedepict.OE2DMolDisplay) and value.IsValid():
            candidate = int(value.GetWidth())
        elif kind is ColumnKind.DESIGN_UNIT and isinstance(value, oechem.OEDesignUnit):
            dep = oedu_to_disp(value, ctx=ctx, apply_callbacks=False)
            candidate = int(dep.display.GetWidth()) if dep is not None else int(ctx.min_width or 200)
        width = max(width, candidate)
    return width


########################################################################################################################
# style_cell factory for depiction columns
#
# Marimo's DataTable hardcodes ``truncate max-w-[300px]`` on every ``<td>``, which caps the cell
# width and clips overflow. Inline styles emitted through ``table(style_cell=...)`` beat those
# class rules on specificity, so the public ``style_cell`` API is what lets a depiction column
# expand to its widest intrinsic canvas.
########################################################################################################################

def _make_style_cell(column_widths: dict[str, int]) -> Callable[[str, str, Any], dict[str, Any]]:
    """Build the ``style_cell`` callback that lifts marimo's 300px cap on depiction columns.

    :param column_widths: Uniform cell width in pixels, keyed by column name.
    :returns: Callable ``(row_id, column_name, value) -> dict`` for ``table(style_cell=...)``.
    """
    def style_cell(_row_id: str, column_name: str, _value: Any) -> dict[str, Any]:
        width = column_widths.get(column_name)
        if width is None:
            return {}
        return {
            "maxWidth": "none",
            "minWidth": f"{int(width)}px",
            "width": f"{int(width)}px",
            "overflow": "visible",
        }
    return style_cell


########################################################################################################################
# Frame formatters and registration
########################################################################################################################

def _format_frame(
    adapter: FrameAdapter, df: Any, values_for: Callable[[int], Iterable[Any]]
) -> tuple[str, str]:
    """Render a frame as a marimo table with depiction cells.

    :param adapter: Frame adapter reporting each column's kind and render context.
    :param df: The frame itself, handed to marimo unchanged.
    :param values_for: Callable returning the values of the column at one position.
    :returns: The table's ``_mime_`` pair.
    """
    format_mapping: dict[Any, Any] = {}
    widths: dict[str, int] = {}
    for pos, label in enumerate(adapter.columns()):
        factory = _FACTORIES.get(adapter.kind(pos))
        if factory is None:
            continue
        # A copy, because the closure outlives this call and must not see later edits
        # to the column's stored context.
        ctx = adapter.context(pos).copy()
        format_mapping[label] = factory(ctx)
        width = _column_width(values_for(pos), adapter.kind(pos), ctx)
        if width:
            widths[str(label)] = width
    style_cell = _make_style_cell(widths) if widths else None
    return table(df, selection=None, format_mapping=format_mapping, pagination=True, style_cell=style_cell)._mime_()


def marimo_pandas_formatter(df: Any) -> tuple[str, str]:
    """Format a Pandas DataFrame as a marimo table with cnotebook depiction cells.

    :param df: Frame to render; never modified.
    :returns: The table's ``_mime_`` pair.
    """
    from cnotebook.pandas_ext import PandasFrameAdapter

    adapter = PandasFrameAdapter(df)
    return _format_frame(adapter, df, lambda pos: df.iloc[:, pos])


def marimo_polars_formatter(df: Any) -> tuple[str, str]:
    """Format a Polars DataFrame as a marimo table with cnotebook depiction cells.

    :param df: Frame to render; never modified.
    :returns: The table's ``_mime_`` pair.
    """
    from cnotebook.polars_ext import PolarsFrameAdapter

    adapter = PolarsFrameAdapter(df)
    return _format_frame(adapter, df, lambda pos: df.to_series(pos))


# The registry and the table factory this module reaches into are marimo internals, so the
# adapter refuses to patch a release older than the one it was written against.
_MIN_MARIMO = (0, 13, 0)
_WARNED = False


def _attach() -> None:
    """Register the table formatters for the DataFrame libraries the session has imported.

    Safe to call repeatedly, and called again whenever pandas or polars support attaches,
    so a frame library imported after cnotebook still gets its formatter. A marimo that is
    missing, too old, or no longer exposing the internals warns once and leaves marimo's
    own table formatting in place.
    """
    global table, _WARNED
    try:
        import marimo

        if not _at_least(marimo.__version__, _MIN_MARIMO):
            raise ImportError(f"marimo {marimo.__version__} is older than {'.'.join(map(str, _MIN_MARIMO))}")
        # Both of these are marimo internals; the version guard above is what stands
        # in for the stability guarantee they do not give.
        from marimo._output.formatting import OPINIONATED_FORMATTERS
        from marimo._plugins.ui._impl.table import table as marimo_table
    except (ImportError, AttributeError, ValueError) as exc:
        if not _WARNED:
            _WARNED = True
            warn(f"cnotebook marimo table integration disabled: {exc}")
        return
    table = marimo_table
    if "pandas" in sys.modules and "oepandas" in sys.modules:
        import pandas as pd

        OPINIONATED_FORMATTERS.formatters[pd.DataFrame] = marimo_pandas_formatter
    if "polars" in sys.modules and "oepolars" in sys.modules:
        import polars as pl

        OPINIONATED_FORMATTERS.formatters[pl.DataFrame] = marimo_polars_formatter


_attach()
