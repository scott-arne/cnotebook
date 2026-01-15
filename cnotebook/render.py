import logging
import base64
from .context import CNotebookContext, pass_cnotebook_context
from openeye import oechem, oedepict
from typing import Literal
from math import floor, ceil
from collections.abc import Iterable, Sequence

log = logging.getLogger("cnotebook")


########################################################################################################################
# Renderers for specific types
########################################################################################################################

def create_img_tag(
        width: float,
        height: float,
        image_mime_type: str,
        image_bytes: bytes,
        wrap_svg: bool = True

) -> str:
    """
    Create the <img> HTML tag for rendering image bytes. This could be either plain text (in the case of SVG) or base64
    encoded (in binary format cases).
    :param width: Image width
    :param height: Image height
    :param image_mime_type: Image MIME type
    :param image_bytes: Image bytes
    :param wrap_svg: Wrap SVG in a specifically sized <div> tag for maximum control of size
    :return: Image tag
    """
    if image_mime_type == "image/svg+xml":
        if wrap_svg:
            return '<div style=\'width:{}px;max-width:{}px;height:{}px;max-height:{}px\'>\n\t{}\n</div>'.format(
                int(width),
                int(width),
                int(height),
                int(height),
                image_bytes.decode("utf-8")
            )
        else:
            return image_bytes.decode("utf-8")

    return '<img src=\'data:{};base64,{}\' style=\'width:{}px;max-width:{}px;height:{}px;max-height:{}px\' />'.format(
        image_mime_type,
        base64.b64encode(image_bytes).decode("utf-8"),
        int(width),
        int(width),
        int(height),
        int(height)
    )


@pass_cnotebook_context
def oedisp_to_html(
        disp: oedepict.OE2DMolDisplay,
        *,
        ctx: CNotebookContext
) -> str:
    """
    Convert an OpenEye 2D molecule display object to HTML
    :param ctx: Current molecule render context
    :param disp: OpenEye 2D molecule display object
    :return: HTML image tag
    """
    # Convert the display object to an <img> tag
    image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
    oedepict.OERenderMolecule(image, disp)
    image_bytes = oedepict.OEWriteImageToString(ctx.image_format, image)

    return create_img_tag(
        disp.GetWidth(),
        disp.GetHeight(),
        image_mime_type=ctx.image_mime_type,
        image_bytes=image_bytes,
        wrap_svg=ctx.structure_scale != oedepict.OEScale_AutoScale
    )


def render_empty_molecule(*, ctx: CNotebookContext) -> str:
    """
    Render an image that says Empty Molecule
    :param ctx: Render context
    :return: Image tag
    """
    image = oedepict.OEImage(ctx.min_width, ctx.min_height)
    image.DrawText(
        oedepict.OE2DPoint(ctx.min_width / 2, ctx.min_height / 2),
        "Empty Molecule",
        oedepict.OEFont(
            oedepict.OEFontFamily_Arial,
            oedepict.OEFontStyle_Normal,
            14,
            oedepict.OEAlignment_Center,
            oechem.OEDarkBlue
        )
    )

    return create_img_tag(
        ctx.min_width,
        ctx.min_height,
        image_mime_type=ctx.image_mime_type,
        image_bytes=oedepict.OEWriteImageToString(ctx.image_format, image),
        wrap_svg=ctx.structure_scale != oedepict.OEScale_AutoScale
    )


def render_invalid_molecule(*, ctx: CNotebookContext) -> str:
    """
    Render an image that says Empty Molecule
    :param ctx: Render context
    :return: Image tag
    """
    image = oedepict.OEImage(ctx.min_width, ctx.min_height)
    image.DrawText(
        oedepict.OE2DPoint(ctx.min_width / 2, ctx.min_height / 2),
        "Invalid Molecule",
        oedepict.OEFont(
            oedepict.OEFontFamily_Arial,
            oedepict.OEFontStyle_Normal,
            14,
            oedepict.OEAlignment_Center,
            oechem.OERed
        )
    )

    return create_img_tag(
        ctx.min_width,
        ctx.min_height,
        image_mime_type=ctx.image_mime_type,
        image_bytes=oedepict.OEWriteImageToString(ctx.image_format, image),
        wrap_svg=ctx.structure_scale != oedepict.OEScale_AutoScale
    )


def oemol_to_disp(
        mol: oechem.OEMolBase,
        *,
        ctx: CNotebookContext
) -> oedepict.OE2DMolDisplay:
    """
    Convert a valid OpenEye molecule object to a display object for depiction. Note that it is highly recommended to
    test that the molecule is valid first before calling this function.
    :param ctx: Render context
    :param mol: Molecule to convert
    :return: Display object for depiction
    """
    # Only recalculate coordinates if we don't have a 2D structure
    if mol.GetDimension() == 2:
        oedepict.OEPrepareDepiction(mol, False)
    else:
        oedepict.OEPrepareDepiction(mol, True)

    return ctx.create_molecule_display(mol)


@pass_cnotebook_context
def oemol_to_html(mol: oechem.OEMolBase, *, ctx: CNotebookContext) -> str:
    """
    Convert an OpenEye Molecule object to HTML
    :param ctx: Render context
    :param mol: Molecule to convert
    :return: HTML string
    """
    # Render valid molecules
    if mol.IsValid():

        # Create the display object from the context
        disp = oemol_to_disp(mol, ctx=ctx)

        # Render the display
        return oedisp_to_html(disp, ctx=ctx)

    # Render empty molecules
    elif mol.NumAtoms() == 0:
        return render_empty_molecule(ctx=ctx)

    # Render other invalid molecules
    else:
        return render_invalid_molecule(ctx=ctx)


@pass_cnotebook_context
def oeimage_to_html(image: oedepict.OEImage, *, ctx: CNotebookContext) -> str:
    """
    Convert an OEImage to HTML
    :param ctx: Render context
    :param image: Image to render
    :return: HTML string
    """
    # Convert the image to an <img> tag
    image_bytes = oedepict.OEWriteImageToString(ctx.image_format, image)
    return create_img_tag(
        image.GetWidth(),
        image.GetHeight(),
        image_mime_type=ctx.image_mime_type,
        image_bytes=image_bytes,
        wrap_svg=ctx.structure_scale != oedepict.OEScale_AutoScale
    )


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
    from .helpers import create_structure_highlighter

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
