import logging
import typing
import polars as pl
import oepolars as oeplr
from openeye import oechem, oedepict
from .context import pass_cnotebook_context, get_series_context
from .helpers import escape_brackets
from .render import (
    CNotebookContext,
    oemol_to_disp,
    oedisp_to_html,
    render_invalid_molecule,
    render_empty_molecule
)

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    ipython_present = False

if typing.TYPE_CHECKING:
    from .context import CNotebookContext

log = logging.getLogger("cnotebook")


def create_mol_formatter(*, ctx: CNotebookContext) -> typing.Callable[[oechem.OEMolBase], str]:
    """
    Closure that creates a function that renders an OEMol to HTML
    :param ctx: CNotebook rendering context
    :return: Function that renders molecules to HTML
    """
    def _oemol_to_html(mol: oechem.OEMolBase):
        if isinstance(mol, oechem.OEMolBase):

            # Render valid molecules
            if mol.IsValid():
                # Create the display object
                disp = oemol_to_disp(mol, ctx=ctx)

                # Apply display callbacks
                if ctx.callbacks is not None:
                    for callback in ctx.callbacks:
                        callback(disp)

                # Render into the string stream
                return oedisp_to_html(disp)

            # Empty molecule
            elif mol.NumAtoms() == 0:
                return render_empty_molecule(ctx=ctx)

            # Invalid molecule
            else:
                return render_invalid_molecule(ctx=ctx)

        return str(mol)

    return _oemol_to_html


@pass_cnotebook_context
def create_disp_formatter(
        *,
        callbacks: list[typing.Callable[[oedepict.OE2DMolDisplay], None]] | None = None,
        ctx: CNotebookContext
) -> typing.Callable[[oedepict.OE2DMolDisplay], str]:
    """
    Closure that creates a function that renders an OE2DMolDisplay to HTML
    :param ctx: Render context
    :param callbacks: List of callbacks to modify the rendering of the molecule
    :return: Function that renders display objects to HTML
    """

    def _oedisp_to_html(disp: oedepict.OE2DMolDisplay) -> str:

        if isinstance(disp, oedepict.OE2DMolDisplay) and disp.IsValid():
            # Copy the display, as not to modify the original with callbacks
            disp_to_render = oedepict.OE2DMolDisplay(disp)

            # Apply display callbacks
            if callbacks is not None:
                for callback in callbacks:
                    callback(disp_to_render)

            return oedisp_to_html(disp_to_render, ctx=ctx)
        return str(disp)

    return _oedisp_to_html


def escape_formatter(obj: typing.Any) -> str:
    return escape_brackets(str(obj))


def render_polars_dataframe(
        df: pl.DataFrame,
        formatters: dict | None = None,
        col_space: dict[str, float | int] | None = None,
        **kwargs
) -> str:
    """
    Render a Polars DataFrame with molecules to HTML.

    This is a scaffold implementation that converts to pandas for rendering.
    Future versions will implement native Polars rendering.

    :param df: Polars DataFrame to render
    :param formatters: Custom formatters for displaying columns
    :param col_space: Custom column spacing
    :param kwargs: Additional keyword arguments
    :return: HTML of rendered DataFrame
    """
    # Defaults are empty dictionaries for these
    formatters = formatters or {}
    col_space = col_space or {}

    # Identify molecule columns from oepolars MoleculeDtype
    molecule_columns = set()

    # Capture metadata from ORIGINAL DataFrame BEFORE copying
    original_metadata_by_col = {}

    for col in df.columns:
        dtype = df.schema[col]
        if isinstance(dtype, oeplr.MoleculeDtype):
            molecule_columns.add(col)
            # Get metadata from the original series
            series = df.get_column(col)
            if hasattr(series, 'chem') and hasattr(series.chem, '_array'):
                arr = series.chem._array
                if hasattr(arr, 'metadata') and arr.metadata:
                    original_metadata_by_col[col] = arr.metadata.copy()

    # Convert to pandas for rendering (temporary scaffold implementation)
    # This preserves molecule data via oepolars' to_pandas() which converts
    # MoleculeDtype columns to oepandas MoleculeDtype
    pdf = df.to_pandas()

    # Import oepandas for type checking
    import oepandas as oepd

    # Create formatters for molecule columns
    for col in molecule_columns:
        if col in formatters:
            log.warning(f'Overwriting existing formatter for {col} with a molecule formatter')

        # Get the array from the pandas DataFrame
        if isinstance(pdf[col].dtype, oepd.MoleculeDtype):
            arr = pdf[col].array
            assert isinstance(arr, oepd.MoleculeArray)

            # Restore metadata if we captured it
            if col in original_metadata_by_col:
                arr.metadata.update(original_metadata_by_col[col])

            # Get the cnotebook options for this column
            ctx = get_series_context(arr.metadata)
            formatters[col] = create_mol_formatter(ctx=ctx)

            # Record the column width
            if col in col_space:
                log.warning(f'Column spacing for {col} already defined, overwriting with molecule image width')

            col_space[col] = float(ctx.width)

    # Handle display columns
    display_columns = set()
    for col in pdf.columns:
        if isinstance(pdf.dtypes[col], oepd.DisplayDtype):
            display_columns.add(col)

    if len(display_columns) > 0:
        log.debug(f'Detected display columns: {", ".join(display_columns)}')

    for col in display_columns:
        arr = pdf[col].array
        assert isinstance(arr, oepd.DisplayArray)

        ctx = get_series_context(arr.metadata)
        formatters[col] = create_disp_formatter(ctx=ctx)

        if len(arr) > 0:
            col_space[col] = max(disp.GetWidth() for disp in arr if isinstance(disp, oedepict.OE2DMolDisplay))
            col_space[col] = max(0, col_space[col])
        else:
            col_space[col] = 0

    # All other columns get escape formatter
    for col in pdf.columns:
        if col not in display_columns and col not in molecule_columns:
            formatters[col] = escape_formatter

    return pdf.to_html(escape=False, formatters=formatters, col_space=col_space, **kwargs)


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
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']
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
