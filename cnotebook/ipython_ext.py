import logging
from typing import Literal
from math import floor, ceil
from openeye import oechem, oedepict
from collections.abc import Iterable, Sequence
from .render import (
    CNotebookContext,
    pass_cnotebook_context,
    oemol_to_html,
    oedisp_to_html,
    oeimage_to_html
)
from .helpers import create_structure_highlighter

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    ipython_present = False

log = logging.getLogger("cnotebook")


@pass_cnotebook_context
def render_molecule_grid(
        mols: Sequence[oechem.OEMolBase],
        nrows: int | None = None,
        ncols: int | None = None,
        max_width: int = 1280,
        max_columns: int = 100,
        min_width: int | None = None,
        min_height: int | None = None,
        align: oechem.OEMolBase | Literal["first"] | None = None,
        smarts: str | Iterable[str] | oechem.OESubSearch | Iterable[oechem.OESubSearch] | None = None,
        color: oechem.OEColor = oechem.OEColor(oechem.OELightBlue),
        style: int = oedepict.OEHighlightStyle_Stick,
        scale: float = 1.0,
        *,
        ctx: CNotebookContext
) -> oedepict.OEImage:
    """
    Convenience function to render a molecule grid
    :param ctx: Current OpenEye rendering context
    :param mols: Iterable of OpenEye molecules
    :param nrows: Number of rows to display in the grid
    :param ncols: Number of columns to display in the grid
    :param max_width: Maximum width of the image
    :param max_columns: Maximum number of columns (if ncols is being automatically calculated)
    :param min_width: Minimum image width (prevents tiny images)
    :param min_height: Minimum image height (prevents tiny images)
    :param align: Alignment to the first molecule, or to a reference molecule
    :param smarts: SMARTS substructure highlighting
    :param color: SMARTS highlighting color
    :param style: SMARTS highlighting style
    :param scale: Image scale in the 2D grid
    :return: Image of the molecule grid
    """
    # Re-scale the images
    ctx.display_options.SetScale(ctx.display_options.GetScale() * scale)

    # ---------------------------------------------------------------
    # Input validation
    # ---------------------------------------------------------------

    # Handle single molecules
    if isinstance(mols, oechem.OEMolBase):
        mols = [mols]

    # Make a copy of the molecules (so we do not modify them)
    # We can use OEGraphMol here because we don't care about conformers
    # Filter out None values first
    mols = [oechem.OEGraphMol(mol) for mol in mols if mol is not None]

    if len(mols) == 0:
        log.warning("No molecules or display objects to render into a grid")
        # Return a minimal 1x1 image instead of 0x0 to avoid OpenEye bug
        return oedepict.OEImage(1, 1)

    # Get the subset of molecules that will actually be displayed
    valid = []

    for idx, mol in enumerate(mols):
        if mol is not None:
            if isinstance(mol, oechem.OEMolBase):
                if mol.IsValid():
                    valid.append(mol)
                else:
                    log.warning(f'Molecule at index {idx} is not valid')

            else:
                log.warning(f'Object at index is not a molecule but type {type(mol).__name__}')

    if len(valid) == 0:
        log.warning("No valid molecules or display objects to render into a grid")
        # Return a minimal 1x1 image instead of 0x0 to avoid OpenEye bug
        return oedepict.OEImage(1, 1)

    # ---------------------------------------------------------------
    # For highlighting SMARTS
    # ---------------------------------------------------------------

    highlighers = None

    if smarts is not None:
        highlighers = []
        # Case: Single pattern
        if isinstance(smarts, (str, oechem.OESubSearch)):
            highlighers.append(
                create_structure_highlighter(
                    smarts,
                    color=color,
                    style=style
                )
            )

        else:
            for pattern in smarts:
                highlighers.append(
                    create_structure_highlighter(
                        pattern,
                        color=color,
                        style=style
                    )
                )

    # ---------------------------------------------------------------
    # For substructure alignment
    # ---------------------------------------------------------------

    align_mcss = None

    if align is not None:

        # If we are doing an alignment
        if isinstance(align, bool) and align:
            align_ref = mols[0]

        elif isinstance(align, oechem.OEMolBase):
            align_ref = align

        else:
            raise TypeError(f'Cannot initialize MCSS alignment reference from type {type(align).__name__}')

        # Set up the MCSS
        align_mcss = oechem.OEMCSSearch(oechem.OEMCSType_Approximate)
        align_mcss.Init(align_ref, oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)

    # ---------------------------------------------------------------
    # Create the display objects for each molecule
    # ---------------------------------------------------------------

    displays = []
    max_disp_width = float('-inf')
    max_disp_height = float('-inf')

    for mol in valid:
        if align_mcss is not None:
            oedepict.OEPrepareAlignedDepiction(mol, align_mcss)
        else:
            oedepict.OEPrepareDepiction(mol)

        # Create the display object
        disp = ctx.create_molecule_display(mol, min_width=min_width, min_height=min_height)
        # disp = oedepict.OE2DMolDisplay(mol, ctx.display_options)

        # Highlight SMARTS patterns
        if highlighers is not None:
            for highlight in highlighers:
                highlight(disp)

        displays.append(disp)

        if disp.GetWidth() > max_disp_width:
            max_disp_width = disp.GetWidth()

        if disp.GetHeight() > max_disp_height:
            max_disp_height = disp.GetHeight()

    # ---------------------------------------------------------------
    # Figure out the geometry of the full image
    # ---------------------------------------------------------------
    # Case: We have one molecule
    if len(displays) == 1:
        ncols = 1
        nrows = 1

    # Case: We are computing based on max_width
    elif ncols is None and nrows is None:

        # Number of columns we can fit into max_width
        ncols = min(floor(max_width / max_disp_width), max_columns, len(displays))
        nrows = ceil(len(displays) / ncols)

    elif nrows is not None:
        ncols = ceil(len(displays) / nrows)

    elif ncols is not None:
        nrows = ceil(len(displays) / ncols)

    else:
        raise RuntimeError("Cannot determine number of rows and columns in molecule grid")

    # Image width and height
    width = max_disp_width * ncols
    height = max_disp_height * nrows

    image = oedepict.OEImage(width, height)
    grid = oedepict.OEImageGrid(image, nrows, ncols)

    # Render the molecules
    for disp, cell in zip(displays, grid.GetCells()):
        oedepict.OERenderMolecule(cell, disp)

    return image


########################################################################################################################
# Register iPython formatters
########################################################################################################################

if ipython_present:

    def register_ipython_formatters():
        """
        Register formatters for OpenEye types here that can be rendered. Calls to this function are idempotent.
        """
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']

            try:
                _ = html_formatter.lookup(oechem.OEMolBase)
            except KeyError:
                html_formatter.for_type(oechem.OEMolBase, oemol_to_html)

            try:
                _ = html_formatter.lookup(oedepict.OE2DMolDisplay)
            except KeyError:
                html_formatter.for_type(oedepict.OE2DMolDisplay, oedisp_to_html)

            try:
                _ = html_formatter.lookup(oedepict.OEImage)
            except KeyError:
                html_formatter.for_type(oedepict.OEImage, oeimage_to_html)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register iPython extension")

else:

    # iPython is not present, so we do not register formatters for OpenEye objects
    def register_ipython_formatters():
        pass
