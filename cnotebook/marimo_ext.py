"""
Marimo integration for CNotebook.

This module provides MIME handlers for OpenEye objects and patches Marimo's
internal table implementation to support molecule rendering with callbacks
(highlighting, alignment, etc.) in Marimo's built-in DataFrame table component.
"""
import logging
import pandas as pd
from openeye import oechem, oedepict

# Import oepandas for dtype checking
try:
    # noinspection PyUnusedImports
    import oepandas as oepd
    oepandas_available = True
except ImportError:
    oepandas_available = False

# Import oepolars for dtype checking
try:
    # noinspection PyUnusedImports
    import polars as pl
    # noinspection PyUnusedImports
    import oepolars as oeplr
    oepolars_available = True
except ImportError:
    oepolars_available = False

from .context import cnotebook_context, get_series_context
from .render import (
    oemol_to_html,
    oedisp_to_html,
    oeimage_to_html,
    oemol_to_disp,
    render_empty_molecule,
    render_invalid_molecule
)
from .pandas_ext import render_dataframe

log = logging.getLogger("cnotebook")


########################################################################################################################
# MIME handlers for individual OpenEye objects
########################################################################################################################

def _display_mol(self: oechem.OEMolBase):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oemol_to_html(self, ctx=ctx)

oechem.OEMolBase._mime_ = _display_mol


def _display_display(self: oedepict.OE2DMolDisplay):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oedisp_to_html(self, ctx=ctx)

oedepict.OE2DMolDisplay._mime_ = _display_display


def _display_image(self: oedepict.OEImage):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oeimage_to_html(self, ctx=ctx)

oedepict.OEImage._mime_ = _display_image


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

        # Handle invalid molecules
        if not mol.IsValid():
            return render_invalid_molecule(ctx=ctx)

        # Handle empty molecules
        if mol.NumAtoms() == 0:
            return render_empty_molecule(ctx=ctx)

        # Create display object
        disp = oemol_to_disp(mol, ctx=ctx)

        # Apply callbacks (highlighting, etc.)
        if ctx.callbacks:
            for callback in ctx.callbacks:
                callback(disp)

        # Return display object
        return disp

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

        return disp_copy

    return formatter


########################################################################################################################
# Marimo DataFrame formatter registration
#
# This registers a custom formatter with Marimo's OPINIONATED_FORMATTERS registry
# to handle DataFrames containing molecule columns. The formatter:
# - Detects MoleculeDtype and DisplayDtype columns
# - Creates format_mapping entries that apply callbacks (highlighting, alignment, etc.)
# - Returns OE2DMolDisplay objects which Marimo renders via their _mime_() method
########################################################################################################################

try:
    import marimo as mo
    # noinspection PyProtectedMember,PyUnusedImports
    from marimo._output.formatting import OPINIONATED_FORMATTERS
    # noinspection PyProtectedMember,PyUnusedImports
    from marimo._plugins.ui._impl.table import table


    # 1. Define the custom formatting logic
    def marimo_pandas_formatter(df: pd.DataFrame):
        """
        Monkey patch the Marimo DataFrame formatter
        """
        format_mapping = {}

        # Check for MoleculeDtype / DisplayDtype (OEPandas specific)
        if oepandas_available:
            for col in df.columns:
                dtype = df[col].dtype

                if isinstance(dtype, oepd.MoleculeDtype):
                    arr = df[col].array
                    ctx = get_series_context(arr.metadata).copy()
                    format_mapping[col] = _create_molecule_formatter(ctx)

                elif isinstance(dtype, oepd.DisplayDtype):
                    arr = df[col].array
                    ctx = get_series_context(arr.metadata).copy()
                    format_mapping[col] = _create_display_formatter(ctx)

        # Return a Marimo table with our custom mapping
        # noinspection PyProtectedMember,PyTypeChecker
        return table(df, selection=None, format_mapping=format_mapping, pagination=True)._mime_()

    # 2. Inject into the Registry
    def install_marimo_pandas_formatter():
        # Check if we've already installed it to avoid duplicates
        for typ, func in OPINIONATED_FORMATTERS.formatters.items():
            if typ is pd.DataFrame and func.__name__ == "marimo_pandas_formatter":
                return  # Already installed

        OPINIONATED_FORMATTERS.formatters[pd.DataFrame] = marimo_pandas_formatter

    # Do the installation
    install_marimo_pandas_formatter()

    def marimo_polars_formatter(df: pl.DataFrame):
        """
        Marimo DataFrame formatter for Polars DataFrames with molecule columns.
        """
        format_mapping = {}

        # Check for MoleculeType / DisplayType (OEPolars specific)
        if oepolars_available:
            for col in df.columns:
                dtype = df.schema[col]

                if isinstance(dtype, oeplr.MoleculeType):
                    series = df.get_column(col)
                    metadata = series.chem.metadata if hasattr(series, 'chem') else {}
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_molecule_formatter(ctx)

                elif isinstance(dtype, oeplr.DisplayType):
                    series = df.get_column(col)
                    metadata = series.chem.metadata if hasattr(series, 'chem') else {}
                    ctx = get_series_context(metadata).copy()
                    format_mapping[col] = _create_display_formatter(ctx)

        # Return a Marimo table with our custom mapping
        # noinspection PyProtectedMember,PyTypeChecker
        return table(df, selection=None, format_mapping=format_mapping, pagination=True)._mime_()

    def install_marimo_polars_formatter():
        """Install the Polars DataFrame formatter if polars is available."""
        if not oepolars_available:
            return

        # Check if we've already installed it to avoid duplicates
        for typ, func in OPINIONATED_FORMATTERS.formatters.items():
            if typ is pl.DataFrame and func.__name__ == "marimo_polars_formatter":
                return  # Already installed

        OPINIONATED_FORMATTERS.formatters[pl.DataFrame] = marimo_polars_formatter

    if oepolars_available:
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

pd.DataFrame._mime_ = _display_dataframe

if oepolars_available:
    from .polars_ext import render_polars_dataframe

    def _display_polars_dataframe(self: pl.DataFrame):
        """
        Fallback MIME hook for Polars DataFrames in non-Marimo contexts.

        In Marimo, the internal table patch handles DataFrame display.
        This is used for static exports or other tools that check _mime_.
        """
        return "text/html", render_polars_dataframe(df=self, formatters=None, col_space=None)

    pl.DataFrame._mime_ = _display_polars_dataframe
