"""
Marimo integration for CNotebook.

This module provides MIME handlers for OpenEye objects and patches Marimo's
internal table implementation to support molecule rendering with callbacks
(highlighting, alignment, etc.) in Marimo's built-in DataFrame table component.
"""
import importlib
import logging
from typing import Any

import pandas as pd
from openeye import oechem, oedepict

# Import oepandas for dtype checking
try:
    oepd: Any = importlib.import_module("oepandas")
    oepandas_available = True
except ImportError:
    oepd = None
    oepandas_available = False

# Import oepolars for dtype checking
try:
    pl: Any = importlib.import_module("polars")
    oeplr: Any = importlib.import_module("oepolars")
    oepolars_available = True
except ImportError:
    pl = None
    oeplr = None
    oepolars_available = False

from .context import cnotebook_context, get_series_context
from .render import (
    oemol_to_html,
    oedisp_to_html,
    oedu_to_html,
    oeimage_to_html,
    oemol_to_disp,
    oemol_to_image,
    oedu_to_disp,
    oedu_to_image,
)
from .pandas_ext import _is_depictable_molecule_dtype, render_dataframe

log = logging.getLogger("cnotebook")


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
# Marimo DataFrame formatters capture per-column CNotebookContext in a closure and rasterize an
# OEImage from it. When marimo serializes the cell, it invokes the image's ``_mime_`` method.
# The globally-registered ``OEImage._mime_`` hook reads ``cnotebook_context.get()`` — losing the
# per-column ctx. Wrapping the OEImage in _CtxBoundImage preserves the captured ctx across that
# boundary so ``oeimage_to_html`` sees per-column ``width``/``height``/``image_format``.
########################################################################################################################

class _CtxBoundImage:
    """Pair an ``OEImage`` with the ``CNotebookContext`` that should drive its HTML serialization.

    :param image: The rendered image.
    :param ctx: The per-column context captured from series/array metadata.
    """

    __slots__ = ("_image", "_ctx")

    def __init__(self, image: oedepict.OEImage, ctx):
        self._image = image
        self._ctx = ctx

    def _mime_(self):
        return "text/html", oeimage_to_html(self._image, ctx=self._ctx)


########################################################################################################################
# Column-width pre-pass
#
# Marimo sizes each column from cell CSS. With fixed-scale rendering, different molecules produce
# different intrinsic canvas widths, so without a uniform wrapper each cell would report its own
# natural width to the column sizer and narrower cells would clip wider ones. Running a cheap
# pre-pass over the column (display objects only — no rasterization) lets us emit a uniform
# fixed-width wrapper around every cell so the column sizes to the widest intrinsic canvas.
########################################################################################################################

def _compute_molecule_column_width(mols, ctx) -> int:
    """Return the maximum intrinsic canvas width across a molecule column.

    Mirrors the branching in :func:`_create_molecule_formatter` so the computed
    width matches what each cell will actually render at.

    :param mols: Iterable of ``OEMolBase`` (or ``None``) for one column.
    :param ctx: The column's rendering context.
    :returns: Maximum intrinsic width in pixels.
    """
    max_width = 0
    for mol in mols:
        if mol is None or not isinstance(mol, oechem.OEMolBase):
            continue

        if not mol.IsValid() or mol.NumAtoms() == 0:
            candidate = int(ctx.min_width)
        elif (ctx.max_heavy_atoms is not None
              and oechem.OECount(mol, oechem.OEIsHeavy()) > ctx.max_heavy_atoms):
            candidate = int(ctx.min_width)
        else:
            disp = oemol_to_disp(mol, ctx=ctx)
            candidate = int(disp.GetWidth())

        if candidate > max_width:
            max_width = candidate
    return max_width


def _compute_display_column_width(displays) -> int:
    """Return the maximum intrinsic canvas width across a display column.

    :param displays: Iterable of ``OE2DMolDisplay`` (or ``None``) for one column.
    :returns: Maximum intrinsic width in pixels.
    """
    max_width = 0
    for disp in displays:
        if isinstance(disp, oedepict.OE2DMolDisplay) and disp.IsValid():
            w = int(disp.GetWidth())
            if w > max_width:
                max_width = w
    return max_width


def _compute_du_column_width(dus, ctx) -> int:
    """Return the maximum intrinsic canvas width across a design-unit column.

    Mirrors :func:`_create_du_formatter`: apo design units render at
    ``ctx.min_width`` × ``ctx.min_height``; design units with ligands render
    at the ligand's intrinsic canvas size.

    :param dus: Iterable of ``OEDesignUnit`` (or ``None``) for one column.
    :param ctx: The column's rendering context.
    :returns: Maximum intrinsic width in pixels.
    """
    max_width = 0
    for du in dus:
        if du is None or not isinstance(du, oechem.OEDesignUnit):
            continue

        result = oedu_to_disp(du, ctx=ctx)
        if result is None:
            candidate = int(ctx.min_width)
        else:
            disp, _lig = result
            candidate = int(disp.GetWidth())

        if candidate > max_width:
            max_width = candidate
    return max_width


########################################################################################################################
# Formatter factories for mo.ui.table format_mapping
########################################################################################################################

def _create_molecule_formatter(ctx):
    """
    Create a formatter closure that renders molecules with callbacks applied.

    :param ctx: CNotebookContext with callbacks (e.g., highlighting)
    :return: Formatter function for use in mo.ui.table format_mapping
    """
    def formatter(mol):
        if mol is None:
            return ""

        if not isinstance(mol, oechem.OEMolBase):
            return str(mol)

        # Check heavy atom count for valid molecules
        if (mol.IsValid()
                and ctx.max_heavy_atoms is not None
                and oechem.OECount(mol, oechem.OEIsHeavy()) > ctx.max_heavy_atoms):
            return _CtxBoundImage(oemol_to_image(mol, ctx=ctx), ctx)

        # Valid molecules with callbacks need the intermediate display step
        if mol.IsValid() and mol.NumAtoms() > 0 and ctx.callbacks:
            disp = oemol_to_disp(mol, ctx=ctx)
            for callback in ctx.callbacks:
                callback(disp)
            image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
            oedepict.OERenderMolecule(image, disp)
            return _CtxBoundImage(image, ctx)

        # All other cases (valid without callbacks, empty, invalid)
        return _CtxBoundImage(oemol_to_image(mol, ctx=ctx), ctx)

    return formatter


def _create_display_formatter(ctx):
    """
    Create a formatter closure that renders OE2DMolDisplay objects.

    :param ctx: CNotebookContext for rendering options
    :return: Formatter function for use in mo.ui.table format_mapping
    """
    def formatter(disp):
        if disp is None:
            return ""

        if not isinstance(disp, oedepict.OE2DMolDisplay):
            return str(disp)

        if not disp.IsValid():
            return str(disp)

        # Copy the display to avoid modifying the original
        disp_copy = oedepict.OE2DMolDisplay(disp)

        # Apply callbacks if any
        if ctx.callbacks:
            for callback in ctx.callbacks:
                callback(disp_copy)

        # Render to OEImage for consistent return type
        image = oedepict.OEImage(disp_copy.GetWidth(), disp_copy.GetHeight())
        oedepict.OERenderMolecule(image, disp_copy)
        return _CtxBoundImage(image, ctx)

    return formatter


def _create_du_formatter(ctx):
    """
    Create a formatter closure that renders OEDesignUnit objects.

    :param ctx: CNotebookContext for rendering options.
    :returns: Formatter function for use in mo.ui.table format_mapping.
    """
    def formatter(du):
        if du is None:
            return ""

        if not isinstance(du, oechem.OEDesignUnit):
            return str(du)

        return _CtxBoundImage(oedu_to_image(du, ctx=ctx), ctx)

    return formatter


########################################################################################################################
# style_cell factory for molecule columns
#
# Marimo's DataTable hardcodes ``truncate max-w-[300px]`` on every ``<td>``, which caps the cell
# width and clips overflow. Inline styles emitted through ``table(style_cell=...)`` beat those
# class rules on specificity, so we use the public ``style_cell`` API to override ``maxWidth``,
# ``minWidth``, and ``overflow`` on molecule/display/design-unit columns — letting the td expand
# to the widest intrinsic canvas in each column.
########################################################################################################################

def _make_style_cell(column_widths: dict[str, int]):
    """Return a ``style_cell`` callback that lifts the 300px cap on molecule columns.

    :param column_widths: Mapping of column name to uniform cell width (px).
    :returns: Callable ``(row_id, column_name, value) -> dict`` for
        ``mo.ui.table(style_cell=...)``.
    """
    def style_cell(_row_id, column_name, _value):
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
# Marimo DataFrame formatter registration
#
# This registers a custom formatter with Marimo's OPINIONATED_FORMATTERS registry
# to handle DataFrames containing molecule columns. The formatter:
# - Detects MoleculeDtype and DisplayDtype columns
# - Creates format_mapping entries that apply callbacks (highlighting, alignment, etc.)
# - Returns OEImage objects which Marimo renders via their _mime_() method
########################################################################################################################

try:
    # noinspection PyProtectedMember,PyUnusedImports
    from marimo._output.formatting import (  # pyright: ignore
        OPINIONATED_FORMATTERS,
    )
    # noinspection PyProtectedMember,PyUnusedImports
    from marimo._plugins.ui._impl.table import table  # pyright: ignore


    # 1. Define the custom formatting logic
    def marimo_pandas_formatter(df: pd.DataFrame):
        """
        Monkey patch the Marimo DataFrame formatter
        """
        format_mapping = {}
        column_widths: dict[str, int] = {}

        # Check for MoleculeDtype / QueryDtype / DisplayDtype (OEPandas specific)
        if oepd is not None:
            for col in df.columns:
                dtype = df[col].dtype

                if _is_depictable_molecule_dtype(dtype):
                    arr = df[col].array
                    metadata = arr.metadata  # pyright: ignore
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_molecule_formatter(ctx)
                    width = _compute_molecule_column_width(arr, ctx)
                    if width:
                        column_widths[col] = width

                elif isinstance(dtype, oepd.DisplayDtype):
                    arr = df[col].array
                    metadata = arr.metadata  # pyright: ignore
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_display_formatter(ctx)
                    width = _compute_display_column_width(arr)
                    if width:
                        column_widths[col] = width

        # Check for DesignUnitDtype (OEPandas specific)
        if oepd is not None:
            for col in df.columns:
                if col not in format_mapping:
                    dtype = df[col].dtype
                    if isinstance(dtype, oepd.DesignUnitDtype):
                        arr = df[col].array
                        metadata = arr.metadata  # pyright: ignore
                        ctx = get_series_context(metadata).copy()
                        format_mapping[col] = _create_du_formatter(ctx)
                        width = _compute_du_column_width(arr, ctx)
                        if width:
                            column_widths[col] = width

        style_cell = _make_style_cell(column_widths) if column_widths else None

        # Return a Marimo table with our custom mapping
        # noinspection PyProtectedMember,PyTypeChecker
        return table(
            df,
            selection=None,
            format_mapping=format_mapping,
            pagination=True,
            style_cell=style_cell,
        )._mime_()  # type: ignore[attr-defined]

    # 2. Inject into the Registry
    def install_marimo_pandas_formatter():
        # Check if we've already installed it to avoid duplicates
        for typ, func in OPINIONATED_FORMATTERS.formatters.items():
            if typ is pd.DataFrame and func.__name__ == "marimo_pandas_formatter":
                return  # Already installed

        OPINIONATED_FORMATTERS.formatters[pd.DataFrame] = marimo_pandas_formatter

    # Do the installation
    install_marimo_pandas_formatter()

    if pl is not None and oeplr is not None:
        marimo_polars_dataframe = pl.DataFrame  # pyright: ignore
        molecule_type = oeplr.MoleculeType  # pyright: ignore
        display_type = oeplr.DisplayType  # pyright: ignore
        design_unit_type = oeplr.DesignUnitType  # pyright: ignore

        def marimo_polars_formatter(df):
            """
            Marimo DataFrame formatter for Polars DataFrames with molecule columns.
            """
            format_mapping = {}
            column_widths: dict[str, int] = {}

            # Check for MoleculeType / DisplayType (OEPolars specific)
            for col in df.columns:
                dtype = df.schema[col]

                if isinstance(dtype, molecule_type):
                    series = df.get_column(col)
                    if hasattr(series, "chem"):
                        metadata = series.chem.metadata  # pyright: ignore
                    else:
                        metadata = {}
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_molecule_formatter(ctx)
                    width = _compute_molecule_column_width(series, ctx)
                    if width:
                        column_widths[col] = width

                elif isinstance(dtype, display_type):
                    series = df.get_column(col)
                    if hasattr(series, "chem"):
                        metadata = series.chem.metadata  # pyright: ignore
                    else:
                        metadata = {}
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_display_formatter(ctx)
                    width = _compute_display_column_width(series)
                    if width:
                        column_widths[col] = width

            # Check for DesignUnitType (OEPolars specific)
            for col in df.columns:
                if col not in format_mapping:
                    dtype = df.schema[col]
                    if isinstance(dtype, design_unit_type):
                        series = df.get_column(col)
                        if hasattr(series, "chem"):
                            metadata = series.chem.metadata  # pyright: ignore
                        else:
                            metadata = {}
                        ctx = get_series_context(metadata).copy()
                        format_mapping[col] = _create_du_formatter(ctx)
                        width = _compute_du_column_width(series, ctx)
                        if width:
                            column_widths[col] = width

            style_cell = _make_style_cell(column_widths) if column_widths else None

            # Return a Marimo table with our custom mapping
            # noinspection PyProtectedMember,PyTypeChecker
            return table(
                df,
                selection=None,
                format_mapping=format_mapping,
                pagination=True,
                style_cell=style_cell,
            )._mime_()  # type: ignore[attr-defined]

        def install_marimo_polars_formatter():
            """Install the Polars DataFrame formatter if polars is available."""
            # Check if we've already installed it to avoid duplicates
            for typ, func in OPINIONATED_FORMATTERS.formatters.items():
                if (
                    typ is marimo_polars_dataframe
                    and func.__name__ == "marimo_polars_formatter"
                ):
                    return  # Already installed

            OPINIONATED_FORMATTERS.formatters[marimo_polars_dataframe] = (
                marimo_polars_formatter
            )

        install_marimo_polars_formatter()

except (ImportError, AttributeError) as ex:
    # Marimo not installed or API changed - skip formatter registration
    log.debug(f'Marimo formatter registration skipped: {ex}')


########################################################################################################################
# Fallback DataFrame MIME handler for non-Marimo contexts
########################################################################################################################

def _display_dataframe(self: pd.DataFrame):
    """
    Fallback MIME hook for Pandas DataFrames in non-Marimo contexts.

    In Marimo, the internal table patch handles DataFrame display.
    This is used for static exports or other tools that check _mime_.
    """
    return "text/html", render_dataframe(df=self, formatters=None, col_space=None)

pd.DataFrame._mime_ = _display_dataframe  # type: ignore[attr-defined]  # pyright: ignore

if pl is not None and oeplr is not None:
    polars_dataframe: Any = pl.DataFrame  # pyright: ignore

    from .polars_ext import render_polars_dataframe

    def _display_polars_dataframe(self):
        """
        Fallback MIME hook for Polars DataFrames in non-Marimo contexts.

        In Marimo, the internal table patch handles DataFrame display.
        This is used for static exports or other tools that check _mime_.
        """
        return "text/html", render_polars_dataframe(df=self, formatters=None, col_space=None)

    polars_dataframe._mime_ = _display_polars_dataframe  # pyright: ignore
