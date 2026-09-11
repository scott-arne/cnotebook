import base64
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openeye import oechem, oedepict

from cnotebook.core.context import (
    CNotebookContext,
    cnotebook_context,
    pass_cnotebook_context,
)
from cnotebook.core.vocabulary import IMAGE_FORMATS

log = logging.getLogger("cnotebook")

@dataclass
class Depiction:
    """A depiction-ready molecule copy and the display built from it.

    The display keeps a reference to ``mol`` through its ``_cnotebook_owner``
    attribute, so the molecule lives exactly as long as the display.
    """

    mol: oechem.OEMolBase
    display: oedepict.OE2DMolDisplay

    def __post_init__(self) -> None:
        self.display._cnotebook_owner = self.mol  # type: ignore[attr-defined]

    def render_image(self, ctx: CNotebookContext) -> oedepict.OEImage:
        """Rasterise the display into an image at the display's own size.

        :param ctx: Render context (image format decides nothing here yet; Task 4 adds oversampling).
        :returns: The rendered image.
        """
        return _render_display_image(self.display, ctx)

    def to_html(self, ctx: CNotebookContext) -> str:
        """Render the display to an HTML image tag.

        :param ctx: Render context.
        :returns: HTML fragment.
        """
        return oeimage_to_html(self.render_image(ctx), ctx=ctx, logical_width=self.display.GetWidth(), logical_height=self.display.GetHeight())


def prepare_depiction_copy(
    mol: oechem.OEMolBase, *, clear_coords: bool | None = None
) -> oechem.OEMolBase:
    """Return a copy of *mol* with 2D depiction coordinates; *mol* is never modified.

    :param mol: Source molecule (concrete or query).
    :param clear_coords: Recompute coordinates when ``True``; keep existing ones when
        ``False``; ``None`` keeps them only when the source already has 2D coordinates.
    :returns: The prepared copy.
    """
    work: oechem.OEMolBase = (
        oechem.OEQMol(mol) if isinstance(mol, oechem.OEQMolBase) else oechem.OEGraphMol(mol)
    )
    if clear_coords is None:
        clear_coords = work.GetDimension() != 2
    oedepict.OEPrepareDepiction(work, clear_coords)
    return work


def make_depiction(mol: oechem.OEMolBase, *, ctx: CNotebookContext, apply_callbacks: bool = True) -> Depiction:
    """Prepare a copy of *mol* and build its display with *ctx*.

    :param mol: Source molecule.
    :param ctx: Render context.
    :param apply_callbacks: Whether to apply context callbacks to the display. Set to ``False`` for sizing passes that measure without rendering.
    :returns: The depiction handle.
    """
    work = prepare_depiction_copy(mol)
    disp = ctx.create_molecule_display(work)

    # Apply context callbacks to the display before rendering (unless this is a sizing pass)
    if apply_callbacks:
        for callback in ctx.callbacks:
            callback(disp)

    return Depiction(work, disp)



def placeholder_size(ctx: CNotebookContext) -> tuple[int, int]:
    """Canvas size for placeholder images.

    :param ctx: Render context.
    :returns: ``(width, height)`` in pixels, each at least 1, defaulting to 200 when the
        context has no minimum.
    """
    width = int(ctx.min_width) if ctx.min_width else 200
    height = int(ctx.min_height) if ctx.min_height else 200
    return max(1, width), max(1, height)


def _render_display_image(disp: oedepict.OE2DMolDisplay, ctx: CNotebookContext) -> oedepict.OEImage:
    """Rasterise *disp*, oversampling PNG output by the context's device pixel ratio."""
    scale = ctx.device_pixel_ratio if ctx.image_format == "png" else 1.0
    logical_width = disp.GetWidth()
    logical_height = disp.GetHeight()
    image = oedepict.OEImage(
        max(1, int(logical_width * scale)), max(1, int(logical_height * scale))
    )
    oedepict.OERenderMolecule(image, disp)
    # Attach logical size for callers that don't explicitly pass it
    image._cnotebook_logical_size = (logical_width, logical_height)  # type: ignore[attr-defined]
    return image


########################################################################################################################
# Renderers for specific types
########################################################################################################################

def create_img_tag(
        width: float,
        height: float,
        image_mime_type: str,
        image_bytes: bytes,
        wrap_svg: bool = True,
        explicit_height: bool = False

) -> str:
    """
    Create the <img> HTML tag for rendering image bytes. This could be either plain text (in the case of SVG) or base64
    encoded (in binary format cases).
    :param width: Image width
    :param height: Image height
    :param image_mime_type: Image MIME type
    :param image_bytes: Image bytes
    :param wrap_svg: Wrap SVG in a specifically sized <div> tag for maximum control of size
    :param explicit_height: Emit explicit height in CSS (for clamped output); otherwise use height:auto
    :return: Image tag
    """
    if image_mime_type == "image/svg+xml":
        # Keep wrapper when explicit dimensions are needed (clamping or explicit sizing)
        if wrap_svg or explicit_height:
            if explicit_height:
                return '<div style=\'width:{w}px;height:{h}px;max-width:none\'>\n\t{svg}\n</div>'.format(
                    w=int(width),
                    h=int(height),
                    svg=image_bytes.decode("utf-8")
                )
            else:
                return '<div style=\'width:{w}px;height:auto;max-width:none\'>\n\t{svg}\n</div>'.format(
                    w=int(width),
                    svg=image_bytes.decode("utf-8")
                )
        else:
            return image_bytes.decode("utf-8")

    if explicit_height:
        return '<img src=\'data:{mime};base64,{data}\' style=\'width:{w}px;height:{h}px;max-width:none\' />'.format(
            mime=image_mime_type,
            data=base64.b64encode(image_bytes).decode("utf-8"),
            w=int(width),
            h=int(height)
        )
    else:
        return '<img src=\'data:{mime};base64,{data}\' style=\'width:{w}px;height:auto;max-width:none\' />'.format(
            mime=image_mime_type,
            data=base64.b64encode(image_bytes).decode("utf-8"),
            w=int(width)
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
    return oeimage_to_html(_render_display_image(disp, ctx), ctx=ctx, logical_width=disp.GetWidth(), logical_height=disp.GetHeight())


def render_empty_molecule(*, ctx: CNotebookContext) -> str:
    """
    Render an image that says Empty Molecule
    :param ctx: Render context
    :return: Image tag
    """
    min_width, min_height = placeholder_size(ctx)

    image = oedepict.OEImage(min_width, min_height)
    image.DrawText(
        oedepict.OE2DPoint(min_width / 2, min_height / 2),
        "Empty Molecule",
        oedepict.OEFont(
            oedepict.OEFontFamily_Arial,
            oedepict.OEFontStyle_Normal,
            14,
            oedepict.OEAlignment_Center,
            oechem.OEDarkBlue
        )
    )

    return oeimage_to_html(image, ctx=ctx, logical_width=min_width, logical_height=min_height)


def render_invalid_molecule(*, ctx: CNotebookContext) -> str:
    """
    Render an image that says Empty Molecule
    :param ctx: Render context
    :return: Image tag
    """
    min_width, min_height = placeholder_size(ctx)

    image = oedepict.OEImage(min_width, min_height)
    image.DrawText(
        oedepict.OE2DPoint(min_width / 2, min_height / 2),
        "Invalid Molecule",
        oedepict.OEFont(
            oedepict.OEFontFamily_Arial,
            oedepict.OEFontStyle_Normal,
            14,
            oedepict.OEAlignment_Center,
            oechem.OERed
        )
    )

    return oeimage_to_html(image, ctx=ctx, logical_width=min_width, logical_height=min_height)


def _create_exceeds_heavy_atoms_image(
        mol: oechem.OEMolBase,
        *,
        ctx: CNotebookContext
) -> oedepict.OEImage:
    """Create a placeholder OEImage for molecules that exceed the heavy atom limit.

    Draws "Exceeds Max Heavy Atoms" and "for Rendering" centered on two lines,
    and optionally the molecule title below if ``ctx.title`` is enabled.

    :param mol: Molecule (used to retrieve the title).
    :param ctx: Render context.
    :returns: Placeholder image.
    """
    min_width, min_height = placeholder_size(ctx)

    image = oedepict.OEImage(min_width, min_height)

    center_x = min_width / 2
    center_y = min_height / 2

    font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial,
        oedepict.OEFontStyle_Normal,
        14,
        oedepict.OEAlignment_Center,
        oechem.OEDarkBlue
    )

    image.DrawText(
        oedepict.OE2DPoint(center_x, center_y - 10),
        "Exceeds Max Heavy Atoms",
        font
    )
    image.DrawText(
        oedepict.OE2DPoint(center_x, center_y + 10),
        "for Rendering",
        font
    )

    if ctx.title:
        mol_title = mol.GetTitle()
        if mol_title:
            title_font = oedepict.OEFont(
                oedepict.OEFontFamily_Arial,
                oedepict.OEFontStyle_Normal,
                14,
                oedepict.OEAlignment_Center,
                oechem.OEBlack
            )
            image.DrawText(
                oedepict.OE2DPoint(center_x, center_y + 35),
                mol_title,
                title_font
            )

    return image


def render_exceeds_max_heavy_atoms(
        mol: oechem.OEMolBase,
        *,
        ctx: CNotebookContext
) -> str:
    """Render a placeholder image for molecules that exceed the heavy atom limit.

    :param mol: Molecule (used to retrieve the title).
    :param ctx: Render context.
    :returns: HTML image tag.
    """
    image = _create_exceeds_heavy_atoms_image(mol, ctx=ctx)
    return oeimage_to_html(image, ctx=ctx, logical_width=image.GetWidth(), logical_height=image.GetHeight())


def oemol_to_disp(
        mol: oechem.OEMolBase,
        *,
        ctx: CNotebookContext,
        apply_callbacks: bool = True
) -> oedepict.OE2DMolDisplay:
    """Convert a valid OpenEye molecule object to a display object for depiction.

    The returned display references a prepared copy of *mol*, kept alive through
    the display's ``_cnotebook_owner`` attribute; *mol* is not modified.

    :param ctx: Render context
    :param mol: Molecule to convert
    :param apply_callbacks: Whether to apply context callbacks. Set to ``False`` for sizing passes.
    :return: Display object for depiction
    """
    return make_depiction(mol, ctx=ctx, apply_callbacks=apply_callbacks).display


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
        if (ctx.max_heavy_atoms is not None
                and oechem.OECount(mol, oechem.OEIsHeavy()) > ctx.max_heavy_atoms):
            return _create_exceeds_heavy_atoms_image(mol, ctx=ctx)

        disp = oemol_to_disp(mol, ctx=ctx)
        image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
        oedepict.OERenderMolecule(image, disp)
        return image

    if mol.NumAtoms() == 0:
        min_width, min_height = placeholder_size(ctx)

        image = oedepict.OEImage(min_width, min_height)
        image.DrawText(
            oedepict.OE2DPoint(min_width / 2, min_height / 2),
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
    min_width, min_height = placeholder_size(ctx)

    image = oedepict.OEImage(min_width, min_height)
    image.DrawText(
        oedepict.OE2DPoint(min_width / 2, min_height / 2),
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


def _draw_du_label(image: oedepict.OEImageBase, scale: float = 1.0) -> None:
    """Draw a small semi-transparent "OEDesignUnit" label in the upper right.

    :param image: Image to draw the label on.
    :param scale: Scaling factor for HiDPI rendering (font size is multiplied by this).
    """
    padding = int(4 * scale)
    font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial,
        oedepict.OEFontStyle_Bold,
        int(14 * scale),
        oedepict.OEAlignment_Right,
        oechem.OEColor(180, 180, 180, 128)
    )
    image.DrawText(
        oedepict.OE2DPoint(image.GetWidth() - padding, image.GetHeight() - padding),  # + 12
        "OEDesignUnit",
        font
    )


def oedu_to_disp(du: oechem.OEDesignUnit, *, ctx: CNotebookContext, apply_callbacks: bool = True) -> Depiction | None:
    """Depict the ligand of a design unit.

    :param du: Design unit.
    :param ctx: Render context.
    :param apply_callbacks: Whether to apply context callbacks. Set to ``False`` for sizing passes.
    :returns: A :class:`Depiction` of the ligand, or ``None`` for an apo design unit or over-limit ligand.
    """
    lig = oechem.OEGraphMol()
    du.GetLigand(lig)
    if lig.NumAtoms() == 0:
        return None
    # Check heavy-atom limit
    if (lig.IsValid() and ctx.max_heavy_atoms is not None
            and oechem.OECount(lig, oechem.OEIsHeavy()) > ctx.max_heavy_atoms):
        return None
    return make_depiction(lig, ctx=ctx, apply_callbacks=apply_callbacks)


def oedu_to_image(
        du: oechem.OEDesignUnit,
        *,
        ctx: CNotebookContext,
        dep: Depiction | None = None
) -> oedepict.OEImage:
    """Convert an OEDesignUnit to an OEImage.

    If the design unit has a ligand, renders the ligand with a small
    "OEDesignUnit" label. If no ligand is present (apo structure),
    renders a placeholder image with "Apo DesignUnit" text. If the
    ligand exceeds the heavy-atom limit, renders the exceeds placeholder.

    :param du: Design unit to render.
    :param ctx: Render context.
    :param dep: Pre-built depiction to reuse (avoids duplicate callback invocations).
    :returns: Rendered image.
    """
    # Extract ligand to check for apo vs. over-limit
    lig = oechem.OEGraphMol()
    du.GetLigand(lig)
    is_apo = lig.NumAtoms() == 0
    is_over_limit = (not is_apo and lig.IsValid() and ctx.max_heavy_atoms is not None
                     and oechem.OECount(lig, oechem.OEIsHeavy()) > ctx.max_heavy_atoms)

    # Use provided depiction or create one
    if dep is None:
        dep = oedu_to_disp(du, ctx=ctx)

    if dep is not None:
        # Render with DPR oversampling
        image = _render_display_image(dep.display, ctx)
        # Scale label font for oversampling
        scale = ctx.device_pixel_ratio if ctx.image_format == "png" else 1.0
        _draw_du_label(image, scale=scale)
        return image

    # Over-limit case: render the exceeds placeholder
    if is_over_limit:
        return _create_exceeds_heavy_atoms_image(lig, ctx=ctx)

    # Apo case: no ligand
    min_width, min_height = placeholder_size(ctx)

    image = oedepict.OEImage(min_width, min_height)
    _draw_du_label(image)
    image.DrawText(
        oedepict.OE2DPoint(min_width / 2, min_height / 2),
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
    # Valid molecules within heavy-atom limit use depictions (oversampled)
    if mol.IsValid() and (ctx.max_heavy_atoms is None or oechem.OECount(mol, oechem.OEIsHeavy()) <= ctx.max_heavy_atoms):
        return make_depiction(mol, ctx=ctx).to_html(ctx)

    # Placeholders (empty, invalid, exceeds limit) are not oversampled
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
    dep = oedu_to_disp(du, ctx=ctx)
    if dep is not None:
        # Ligand case: reuse the depiction to avoid duplicate callback invocations
        image = oedu_to_image(du, ctx=ctx, dep=dep)
        return oeimage_to_html(image, ctx=ctx, logical_width=dep.display.GetWidth(), logical_height=dep.display.GetHeight())
    else:
        # Apo case: placeholder (not oversampled)
        return oeimage_to_html(oedu_to_image(du, ctx=ctx, dep=dep), ctx=ctx)


@pass_cnotebook_context
def oeimage_to_html(image: oedepict.OEImage, *, ctx: CNotebookContext, logical_width: int | None = None, logical_height: int | None = None) -> str:
    """
    Convert an OEImage to HTML
    :param ctx: Render context
    :param image: Image to render
    :param logical_width: Logical display width (pre-oversampling), defaults to image width
    :param logical_height: Logical display height (pre-oversampling), defaults to image height
    :return: HTML string
    """
    # Convert the image to an <img> tag
    image_bytes = oedepict.OEWriteImageToString(ctx.image_format, image)

    # Resolve display dimensions: prefer ctx when set, else intrinsic
    # Check for attached logical size first
    if logical_width is None and logical_height is None:
        attached_size = getattr(image, "_cnotebook_logical_size", None)
        if attached_size is not None:
            logical_width, logical_height = attached_size

    intrinsic_w, intrinsic_h = (logical_width or image.GetWidth()), (logical_height or image.GetHeight())
    if ctx.width > 0 and ctx.height > 0:
        display_width, display_height = ctx.width, ctx.height
    elif ctx.width > 0:
        display_width = ctx.width
        display_height = intrinsic_h * (ctx.width / intrinsic_w) if intrinsic_w > 0 else ctx.width
    elif ctx.height > 0:
        display_height = ctx.height
        display_width = intrinsic_w * (ctx.height / intrinsic_h) if intrinsic_h > 0 else ctx.height
    else:
        display_width, display_height = intrinsic_w, intrinsic_h

    # Track original dimensions before clamping
    unclamped_width, unclamped_height = display_width, display_height

    # Clamp to max dimensions
    if ctx.max_width is not None and display_width > ctx.max_width:
        display_height = display_height * (ctx.max_width / display_width) if display_width else display_height
        display_width = ctx.max_width
    if ctx.max_height is not None and display_height > ctx.max_height:
        display_width = display_width * (ctx.max_height / display_height) if display_height else display_width
        display_height = ctx.max_height

    # Emit explicit height if clamping changed dimensions or both logical dimensions were provided
    clamping_changed = (display_width != unclamped_width or display_height != unclamped_height)
    both_logical_dims = (logical_width is not None and logical_height is not None)
    explicit_height = clamping_changed or both_logical_dims

    return create_img_tag(
        display_width,
        display_height,
        image_mime_type=ctx.image_mime_type,
        image_bytes=image_bytes,
        wrap_svg=not ctx.auto_scale,
        explicit_height=explicit_height
    )



def _check_format(fmt: str) -> None:
    if fmt not in IMAGE_FORMATS:
        raise ValueError(f"format must be one of {IMAGE_FORMATS} (got {fmt!r})")


def _options_context(ctx: CNotebookContext | None, fmt: str, options: dict[str, Any]) -> CNotebookContext:
    """Copy *ctx* (or the global context), apply *options* and *fmt*."""
    resolved = (ctx if ctx is not None else cnotebook_context.get()).copy()
    for name, value in options.items():
        if not isinstance(getattr(CNotebookContext, name, None), property):
            raise TypeError(f"Unknown render option {name!r}")
        setattr(resolved, name, value)
    resolved.image_format = fmt
    return resolved


def render_molecule(
    mol: oechem.OEMolBase, *, format: str = "png", ctx: CNotebookContext | None = None, **options: Any
) -> bytes:
    """Render a molecule to image bytes without touching the notebook display machinery.

    :param mol: Molecule (not modified).
    :param format: ``"png"`` or ``"svg"``.
    :param ctx: Base render context; the global context when ``None``.
    :param options: Context attributes applied on a copy of the base context.
    :returns: Encoded image bytes.
    :raises ValueError: If *format* is not supported.
    :raises TypeError: If an option name is not a context attribute.
    """
    _check_format(format)
    resolved = _options_context(ctx, format, options)
    if mol.IsValid() and (
        resolved.max_heavy_atoms is None
        or oechem.OECount(mol, oechem.OEIsHeavy()) <= resolved.max_heavy_atoms
    ):
        image = make_depiction(mol, ctx=resolved).render_image(resolved)
    else:
        image = oemol_to_image(mol, ctx=resolved)
    return bytes(oedepict.OEWriteImageToString(format, image))


def render_display(
    disp: oedepict.OE2DMolDisplay, *, format: str = "png", ctx: CNotebookContext | None = None
) -> bytes:
    """Render an existing display object to image bytes.

    :param disp: Display to render.
    :param format: ``"png"`` or ``"svg"``.
    :param ctx: Render context used for oversampling; the global context when ``None``.
    :returns: Encoded image bytes.
    """
    _check_format(format)
    resolved = _options_context(ctx, format, {})
    return bytes(oedepict.OEWriteImageToString(format, _render_display_image(disp, resolved)))


def render_design_unit(
    du: oechem.OEDesignUnit, *, format: str = "png", ctx: CNotebookContext | None = None, **options: Any
) -> bytes:
    """Render a design unit's ligand (or the apo placeholder) to image bytes.

    :param du: Design unit.
    :param format: ``"png"`` or ``"svg"``.
    :param ctx: Base render context.
    :param options: Context attributes applied on a copy.
    :returns: Encoded image bytes.
    """
    _check_format(format)
    resolved = _options_context(ctx, format, options)
    return bytes(oedepict.OEWriteImageToString(format, oedu_to_image(du, ctx=resolved)))


def save_image(
    obj: Any, path: str | os.PathLike[str], *, format: str | None = None,
    ctx: CNotebookContext | None = None, **options: Any,
) -> Path:
    """Write a molecule, display or design unit image to *path*.

    :param obj: ``OEMolBase``, ``OE2DMolDisplay`` or ``OEDesignUnit``.
    :param path: Destination; the suffix selects the format when *format* is ``None``.
    :param format: Explicit image format.
    :param ctx: Base render context.
    :param options: Context attributes applied on a copy for molecules and design units; a prepared ``OE2DMolDisplay`` carries its own settings and ignores them.
    :returns: The written path.
    :raises ValueError: If the format cannot be determined or is unsupported.
    :raises TypeError: If *obj* is not a renderable type.
    """
    import tempfile

    target = Path(path)
    # Only use suffix when format is None (not when it's an empty string)
    fmt = target.suffix.lstrip(".").lower() if format is None else format
    _check_format(fmt)
    if isinstance(obj, oedepict.OE2DMolDisplay):
        data = render_display(obj, format=fmt, ctx=ctx)
    elif isinstance(obj, oechem.OEDesignUnit):
        data = render_design_unit(obj, format=fmt, ctx=ctx, **options)
    elif isinstance(obj, oechem.OEMolBase):
        data = render_molecule(obj, format=fmt, ctx=ctx, **options)
    else:
        raise TypeError(f"Cannot render object of type {type(obj).__name__}")

    # Write to temp file in same directory, then atomically replace
    target_dir = target.parent
    temp_fd, temp_path = tempfile.mkstemp(dir=target_dir, suffix=".tmp")
    temp_file = Path(temp_path)
    try:
        # Write through a context-managed file object to ensure all bytes are written
        with os.fdopen(temp_fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        # Atomic replacement (only after write block completed)
        os.replace(temp_path, target)
        return target
    except BaseException:
        # Clean up temp file on failure; log but don't mask original error
        try:
            temp_file.unlink(missing_ok=True)
        except OSError:
            # Cleanup failed, but original error is more important
            log.debug(f"Failed to clean up temporary file {temp_path}")
        raise
