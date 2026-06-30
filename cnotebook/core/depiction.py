"""Generic depiction primitives for classification results.

Domain-agnostic: these functions take only OpenEye molecules and plain-data
tuples, never any consumer's domain types, so they are reusable across the whole
filtering/alerting surface and testable with hand-built tuples.
"""
from __future__ import annotations

import logging

from openeye import oechem, oedepict

from cnotebook.core.context import CNotebookContext, cnotebook_context
from cnotebook.core.helpers import escape_html
from cnotebook.core.render import oemol_to_image, create_img_tag, oeimage_to_html

log = logging.getLogger("cnotebook")

#: (label, color-or-None, atom-index match tuples) for one highlightable alert.
AlertGroup = tuple[str, "oechem.OEColor | None", tuple[tuple[int, ...], ...]]
#: (label, YES/NO answer, detail) for one decision step.
PathStep = tuple[str, bool, str]
#: (name, color-or-None, description) for an outcome badge.
Terminal = tuple[str, "oechem.OEColor | None", str]


def _resolve_ctx(ctx: CNotebookContext | None) -> CNotebookContext:
    return ctx if ctx is not None else cnotebook_context.get()


def _atom_bond_set(mol: oechem.OEMolBase, indices: tuple[int, ...]) -> oechem.OEAtomBondSet:
    """Build an OEAtomBondSet from atom indices, skipping out-of-range ones."""
    abset = oechem.OEAtomBondSet()
    wanted = set(indices)
    for atom in mol.GetAtoms():
        if atom.GetIdx() in wanted:
            abset.AddAtom(atom)
    for bond in mol.GetBonds():
        if bond.GetBgn().GetIdx() in wanted and bond.GetEnd().GetIdx() in wanted:
            abset.AddBond(bond)
    return abset


def highlight_alerts(
    mol: oechem.OEMolBase,
    groups: list[AlertGroup],
    *,
    style: str = "ball_and_stick",
    ctx: CNotebookContext | None = None,
) -> oedepict.OEImage:
    """Render a molecule with each alert group's atoms highlighted.

    Each group is highlighted in its own color (auto-assigned from
    :func:`oechem.OEGetContrastColors` when the group's color is ``None``).
    Overlapping groups render correctly in ball-and-stick style. Groups with no
    matches are skipped. This primitive returns a bare highlighted image; the
    color -> label legend is an HTML concern owned by :func:`render_summary`.

    :param mol: Molecule to depict.
    :param groups: ``(label, color | None, match-tuples)`` per alert.
    :param style: ``"ball_and_stick"`` (default) or ``"stick"``.
    :param ctx: Render context; the global context is used when ``None``.
    :returns: The rendered image (empty/invalid molecules yield a placeholder image).
    """
    render_ctx = _resolve_ctx(ctx)
    if not mol.IsValid() or mol.NumAtoms() == 0:
        return oemol_to_image(mol, ctx=render_ctx)

    # Honor max_heavy_atoms limit for valid molecules
    if (render_ctx.max_heavy_atoms is not None
            and oechem.OECount(mol, oechem.OEIsHeavy()) > render_ctx.max_heavy_atoms):
        return oemol_to_image(mol, ctx=render_ctx)

    work = oechem.OEGraphMol(mol)
    oedepict.OEPrepareDepiction(work)
    # create_molecule_display honors the context's sizing/scale rules (and is the
    # same path oemol_to_disp uses). display_options is a PROPERTY (no parens).
    disp = render_ctx.create_molecule_display(work)

    colors = oechem.OEGetContrastColors()
    color_iter = iter(colors)
    style_int = (
        oedepict.OEHighlightStyle_Stick if style == "stick"
        else oedepict.OEHighlightStyle_BallAndStick
    )
    for label, color, matches in groups:
        if not matches:
            continue
        if color is None:
            color = next(color_iter, oechem.OEColor(oechem.OELightBlue))
        if style == "ball_and_stick":
            highlight = oedepict.OEHighlightByBallAndStick(color)
            for match in matches:
                oedepict.OEAddHighlighting(disp, highlight, _atom_bond_set(work, match))
        else:
            for match in matches:
                oedepict.OEAddHighlighting(disp, color, style_int, _atom_bond_set(work, match))

    image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
    oedepict.OERenderMolecule(image, disp)
    return image


_VALID_FORMATS = ("html", "png", "svg")


def _color_hex(color: "oechem.OEColor | None", default: str = "#666666") -> str:
    if color is None:
        return default
    # OEColor channel accessors are GetR()/GetG()/GetB() (not R()/G()/B()).
    return "#{:02X}{:02X}{:02X}".format(color.GetR(), color.GetG(), color.GetB())


def _path_html(steps: list[PathStep], terminal: Terminal) -> str:
    rows = []
    for label, answer, detail in steps:
        chip_bg = "#2E7D32" if answer else "#9E9E9E"
        chip = "YES" if answer else "NO"
        rows.append(
            f"<li style='margin:2px 0'>"
            f"<span style='display:inline-block;min-width:34px;padding:1px 6px;"
            f"border-radius:3px;color:#fff;background:{chip_bg};font-size:11px;"
            f"text-align:center'>{chip}</span> "
            f"<span>{escape_html(label)}</span>"
            f"<span style='color:#888;font-size:11px'> — {escape_html(detail)}</span></li>"
        )
    name, color, description = terminal
    badge = (
        f"<div style='margin-top:6px;padding:4px 10px;border-radius:4px;"
        f"display:inline-block;color:#fff;background:{_color_hex(color, '#B71C1C')};"
        f"font-weight:600'>{escape_html(name)}</div>"
        f"<div style='color:#666;font-size:11px;margin-top:2px'>{escape_html(description)}</div>"
    )
    return (
        "<div style='font-family:sans-serif;font-size:13px'>"
        f"<ol style='list-style:none;padding-left:0;margin:0'>{''.join(rows)}</ol>"
        f"{badge}</div>"
    )


def _path_image(steps: list[PathStep], terminal: Terminal, fmt: str, ctx: CNotebookContext) -> str:
    # A simple vertical breadcrumb drawn with OEImage text primitives.
    row_h = 22
    width = int(ctx.width) if ctx.width and ctx.width > 0 else 360
    default_height = max(row_h * (len(steps) + 2), row_h * 2)
    height = int(ctx.height) if ctx.height and ctx.height > 0 else default_height
    image = oedepict.OEImage(width, height)
    font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial, oedepict.OEFontStyle_Normal, 12,
        oedepict.OEAlignment_Left, oechem.OEBlack,
    )
    y = row_h
    for label, answer, detail in steps:
        mark = "Y" if answer else "N"
        image.DrawText(oedepict.OE2DPoint(8, y), f"[{mark}] {label}", font)
        y += row_h
    name, color, _description = terminal
    badge_font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial, oedepict.OEFontStyle_Bold, 13,
        oedepict.OEAlignment_Left, oechem.OEColor(oechem.OEBlack) if color is None else color,
    )
    image.DrawText(oedepict.OE2DPoint(8, y + 4), f"=> {name}", badge_font)
    image_bytes = oedepict.OEWriteImageToString(fmt, image)
    return create_img_tag(width, height, image_mime_type=f"image/{fmt}" if fmt != "svg" else "image/svg+xml",
                          image_bytes=image_bytes, wrap_svg=True)


def render_path(
    steps: list[PathStep],
    terminal: Terminal,
    *,
    format: str = "html",
    ctx: CNotebookContext | None = None,
) -> str:
    """Render a decision path as an HTML fragment or an embeddable image string.

    :param steps: Ordered ``(label, answer, detail)`` steps.
    :param terminal: ``(name, color | None, description)`` outcome badge.
    :param format: ``"html"`` (default), ``"png"``, or ``"svg"``.
    :param ctx: Render context; the global context is used when ``None``.
    :returns: An HTML fragment (``format="html"``) or an embeddable ``<img>``/SVG
        fragment (``format`` in ``{"png","svg"}``).
    :raises ValueError: If ``format`` is not one of html/png/svg.
    """
    if format not in _VALID_FORMATS:
        raise ValueError(f"format must be one of {_VALID_FORMATS}, got {format!r}")
    if format == "html":
        return _path_html(steps, terminal)
    return _path_image(steps, terminal, format, _resolve_ctx(ctx))


def _legend_html(groups: list[AlertGroup]) -> str:
    if not groups:
        return ""
    items = []
    color_iter = iter(oechem.OEGetContrastColors())
    for label, color, matches in groups:
        if matches:
            swatch = _color_hex(color if color is not None else next(color_iter, None))
            items.append(
                f"<li><span style='display:inline-block;width:10px;height:10px;"
                f"background:{swatch};margin-right:4px'></span>{escape_html(label)}</li>"
            )
        else:
            items.append(f"<li style='color:#888'>{escape_html(label)} (not structurally localizable)</li>")
    return ("<ul style='list-style:none;padding-left:0;margin:4px 0;font-size:11px;"
            f"font-family:sans-serif'>{''.join(items)}</ul>")


def _summary_html(mol_html, alert_groups, paths, render_ctx, legend) -> str:
    path_blocks = []
    for source_label, steps, terminal in paths:
        path_blocks.append(
            f"<div style='margin:4px 0'><div style='font-weight:600;font-size:12px;"
            f"font-family:sans-serif'>{source_label}</div>"
            f"{render_path(steps, terminal, format='html', ctx=render_ctx)}</div>"
        )
    legend_html = _legend_html(alert_groups) if legend else ""
    return (
        "<div style='display:flex;gap:16px;align-items:flex-start'>"
        f"<div>{mol_html}{legend_html}</div>"
        f"<div>{''.join(path_blocks)}</div>"
        "</div>"
    )


def summary_image(
    mol: oechem.OEMolBase,
    alert_groups: list[AlertGroup],
    paths: list[tuple[str, list[PathStep], Terminal]],
    *,
    ctx: CNotebookContext | None = None,
) -> oedepict.OEImage:
    """Compose the highlighted molecule + per-tree path breadcrumbs into one image.

    The molecule (with all alert groups highlighted) is rendered into the left
    cell of a 1x2 :class:`OEImageGrid`; each path's steps and terminal are drawn as
    text into the right cell. Shared by :func:`render_summary` (png/svg) and any
    consumer needing the raw composed image.

    :param mol: The molecule.
    :param alert_groups: Combined ``(label, color | None, matches)`` groups.
    :param paths: ``(source_label, steps, terminal)`` per tree.
    :param ctx: Render context (reserved for future sizing use).
    :returns: The composed image.
    """
    n_lines = sum(len(steps) for _l, steps, _t in paths) + 2 * max(len(paths), 1)
    width, height = 720, max(300, 24 * n_lines)
    image = oedepict.OEImage(width, height)
    grid = oedepict.OEImageGrid(image, 1, 2)
    mol_cell = grid.GetCell(1, 1)
    if not mol.IsValid() or mol.NumAtoms() == 0:
        # Empty/invalid: draw a placeholder label rather than a display on 0 atoms.
        placeholder_font = oedepict.OEFont(
            oedepict.OEFontFamily_Arial, oedepict.OEFontStyle_Normal, 14,
            oedepict.OEAlignment_Center, oechem.OEDarkBlue,
        )
        label = "Empty Molecule" if mol.NumAtoms() == 0 else "Invalid Molecule"
        mol_cell.DrawText(
            oedepict.OE2DPoint(mol_cell.GetWidth() / 2, mol_cell.GetHeight() / 2),
            label, placeholder_font,
        )
    else:
        work = oechem.OEGraphMol(mol)
        oedepict.OEPrepareDepiction(work)
        opts = oedepict.OE2DMolDisplayOptions(
            mol_cell.GetWidth(), mol_cell.GetHeight(), oedepict.OEScale_AutoScale
        )
        disp = oedepict.OE2DMolDisplay(work, opts)
        color_iter = iter(oechem.OEGetContrastColors())
        for _label, color, matches in alert_groups:
            if not matches:
                continue
            if color is None:
                color = next(color_iter, oechem.OEColor(oechem.OELightBlue))
            highlight = oedepict.OEHighlightByBallAndStick(color)
            for match in matches:
                oedepict.OEAddHighlighting(disp, highlight, _atom_bond_set(work, match))
        oedepict.OERenderMolecule(mol_cell, disp)

    path_cell = grid.GetCell(1, 2)
    font = oedepict.OEFont(
        oedepict.OEFontFamily_Arial, oedepict.OEFontStyle_Normal, 12,
        oedepict.OEAlignment_Left, oechem.OEBlack,
    )
    y = 20
    for source_label, steps, terminal in paths:
        path_cell.DrawText(oedepict.OE2DPoint(8, y), source_label, font)
        y += 22
        for label, answer, _detail in steps:
            mark = "Y" if answer else "N"
            path_cell.DrawText(oedepict.OE2DPoint(8, y), f"[{mark}] {label}", font)
            y += 22
        path_cell.DrawText(oedepict.OE2DPoint(8, y), f"=> {terminal[0]}", font)
        y += 28
    return image


def render_summary(
    mol: oechem.OEMolBase,
    alert_groups: list[AlertGroup],
    paths: list[tuple[str, list[PathStep], Terminal]],
    *,
    format: str = "html",
    legend: bool = True,
    ctx: CNotebookContext | None = None,
) -> str:
    """Render one molecule's combined alerts plus per-tree decision paths.

    :param mol: The molecule (depicted once with all alert groups highlighted).
    :param alert_groups: Combined, source-qualified groups across all trees.
    :param paths: ``(source_label, steps, terminal)`` per tree.
    :param format: ``"html"`` (default), ``"png"``, or ``"svg"``.
    :param legend: Whether to include the shared color -> label legend (HTML only).
    :param ctx: Render context; the global context is used when ``None``.
    :returns: An HTML fragment (``format="html"``) or an embeddable ``<img>``/SVG
        fragment composing molecule + paths (``format`` in ``{"png","svg"}``).
    :raises ValueError: If ``format`` is not one of html/png/svg.
    """
    if format not in _VALID_FORMATS:
        raise ValueError(f"format must be one of {_VALID_FORMATS}, got {format!r}")
    render_ctx = _resolve_ctx(ctx)
    if format == "html":
        image = highlight_alerts(mol, alert_groups, ctx=render_ctx)
        mol_html = oeimage_to_html(image, ctx=render_ctx)
        return _summary_html(mol_html, alert_groups, paths, render_ctx, legend)
    composed = summary_image(mol, alert_groups, paths, ctx=render_ctx)
    image_bytes = oedepict.OEWriteImageToString(format, composed)
    mime = "image/svg+xml" if format == "svg" else f"image/{format}"
    return create_img_tag(composed.GetWidth(), composed.GetHeight(),
                          image_mime_type=mime, image_bytes=image_bytes, wrap_svg=True)
