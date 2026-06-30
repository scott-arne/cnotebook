"""Generic depiction primitives for classification results.

Domain-agnostic: these functions take only OpenEye molecules and plain-data
tuples, never any consumer's domain types, so they are reusable across the whole
filtering/alerting surface and testable with hand-built tuples.
"""
from __future__ import annotations

import logging

from openeye import oechem, oedepict

from cnotebook.core.context import CNotebookContext, cnotebook_context
from cnotebook.core.render import oemol_to_image

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
