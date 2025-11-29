import logging
import base64
from .context import CNotebookContext, pass_cnotebook_context
from openeye import oechem, oedepict

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
