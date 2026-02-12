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


def oemol_to_image(
        mol: oechem.OEMolBase,
        *,
        ctx: CNotebookContext
) -> oedepict.OEImage:
    """Convert an OpenEye molecule to an OEImage.

    Handles valid, empty, and invalid molecules. For valid molecules the
    molecule is rendered via :func:`oemol_to_disp`. Empty and invalid
    molecules produce placeholder images with descriptive text.

    :param mol: Molecule to convert.
    :param ctx: Render context.
    :returns: Rendered image.
    """
    if mol.IsValid():
        disp = oemol_to_disp(mol, ctx=ctx)
        image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
        oedepict.OERenderMolecule(image, disp)
        return image

    if mol.NumAtoms() == 0:
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
        return image

    # Invalid molecule with atoms
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
    return image


def _draw_du_label(image: oedepict.OEImageBase) -> None:
    """Draw a small semi-transparent "OEDesignUnit" label in the upper right.

    :param image: Image to draw the label on.
    """
    padding = 4
    font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial,
        oedepict.OEFontStyle_Bold,
        14,
        oedepict.OEAlignment_Right,
        oechem.OEColor(180, 180, 180, 128)
    )
    image.DrawText(
        oedepict.OE2DPoint(image.GetWidth() - padding, image.GetHeight() - padding),  # + 12
        "OEDesignUnit",
        font
    )


def oedu_to_disp(
        du: oechem.OEDesignUnit,
        *,
        ctx: CNotebookContext
) -> tuple[oedepict.OE2DMolDisplay, oechem.OEGraphMol] | None:
    """Convert an OEDesignUnit to a 2D molecule display.

    Extracts the ligand from the design unit and renders it as a 2D display.
    Returns ``None`` if the design unit has no ligand (apo structure).

    .. important::
        The returned ligand molecule **must** be kept alive as long as the
        display is in use. The ``OE2DMolDisplay`` holds an internal C++
        reference to the molecule; if the molecule is garbage-collected
        the display will crash when rendered.

    :param du: Design unit to render.
    :param ctx: Render context.
    :returns: Tuple of (display, ligand), or ``None`` if no ligand.
    """
    lig = oechem.OEGraphMol()
    du.GetLigand(lig)

    if lig.NumAtoms() == 0:
        return None

    disp = oemol_to_disp(lig, ctx=ctx)
    return disp, lig


def oedu_to_image(
        du: oechem.OEDesignUnit,
        *,
        ctx: CNotebookContext
) -> oedepict.OEImage:
    """Convert an OEDesignUnit to an OEImage.

    If the design unit has a ligand, renders the ligand with a small
    "OEDesignUnit" label. If no ligand is present (apo structure),
    renders a placeholder image with "Apo DesignUnit" text.

    :param du: Design unit to render.
    :param ctx: Render context.
    :returns: Rendered image.
    """
    result = oedu_to_disp(du, ctx=ctx)

    if result is not None:
        disp, _lig = result  # _lig must stay alive while disp is rendered
        width, height = disp.GetWidth(), disp.GetHeight()
        image = oedepict.OEImage(width, height)
        oedepict.OERenderMolecule(image, disp)
        _draw_du_label(image)
        return image

    # Apo case: no ligand
    image = oedepict.OEImage(ctx.min_width, ctx.min_height)
    _draw_du_label(image)
    image.DrawText(
        oedepict.OE2DPoint(ctx.min_width / 2, ctx.min_height / 2),
        "Apo DesignUnit",
        oedepict.OEFont(
            oedepict.OEFontFamily_Arial,
            oedepict.OEFontStyle_Bold,
            14,
            oedepict.OEAlignment_Center,
            oechem.OEDarkBlue
        )
    )
    return image


@pass_cnotebook_context
def oemol_to_html(mol: oechem.OEMolBase, *, ctx: CNotebookContext) -> str:
    """Convert an OpenEye molecule to HTML.

    :param mol: Molecule to convert.
    :param ctx: Render context.
    :returns: HTML image tag.
    """
    return oeimage_to_html(oemol_to_image(mol, ctx=ctx), ctx=ctx)


@pass_cnotebook_context
def oedu_to_html(du: oechem.OEDesignUnit, *, ctx: CNotebookContext) -> str:
    """Convert an OEDesignUnit to HTML.

    If the design unit has a ligand, renders the ligand with a small
    "OEDesignUnit" label. If no ligand is present (apo structure),
    renders a placeholder image with "Apo DesignUnit" text.

    :param du: Design unit to render.
    :param ctx: Render context.
    :returns: HTML image tag.
    """
    return oeimage_to_html(oedu_to_image(du, ctx=ctx), ctx=ctx)


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


