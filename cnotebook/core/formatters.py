"""Cell formatters shared by the pandas, polars and marimo adapters.

Every function is pure with respect to its inputs: molecules are depicted on
copies, and displays are copied for safety (callbacks are never re-applied to
prepared displays).
"""

from __future__ import annotations

import html
from typing import Any

from openeye import oechem, oedepict

from cnotebook.core.context import CNotebookContext
from cnotebook.core.render import (
    _render_display_image,
    make_depiction,
    oedu_to_disp,
    oedu_to_image,
    oeimage_to_html,
    oemol_to_image,
    render_empty_molecule,
    render_exceeds_max_heavy_atoms,
    render_invalid_molecule,
)


def _exceeds_limit(mol: oechem.OEMolBase, ctx: CNotebookContext) -> bool:
    return ctx.max_heavy_atoms is not None and oechem.OECount(mol, oechem.OEIsHeavy()) > ctx.max_heavy_atoms


def _tag(image: oedepict.OEImage, width: float, height: float) -> oedepict.OEImage:
    image._cnotebook_logical_size = (int(width), int(height))  # type: ignore[attr-defined]
    return image


def molecule_cell_html(value: Any, ctx: CNotebookContext) -> str:
    """HTML for one molecule (or query molecule) cell.

    :param value: ``OEMolBase``, ``None`` (empty cell) or any other object (escaped text).
    :param ctx: Column render context; its callbacks run on the depiction copy.
    :returns: HTML fragment.
    """
    if value is None:
        return ""
    if not isinstance(value, oechem.OEMolBase):
        return html.escape(str(value))
    if not value.IsValid():
        return render_empty_molecule(ctx=ctx) if value.NumAtoms() == 0 else render_invalid_molecule(ctx=ctx)
    if _exceeds_limit(value, ctx):
        return render_exceeds_max_heavy_atoms(value, ctx=ctx)
    depiction = make_depiction(value, ctx=ctx, apply_callbacks=False)
    for callback in ctx.callbacks:
        callback(depiction.display)
    return depiction.to_html(ctx)


def display_cell_html(value: Any, ctx: CNotebookContext) -> str:
    """HTML for one display-object cell; the display is copied for safety.

    Prepared displays already had callbacks applied when created; they are rendered as-is.

    :param value: ``OE2DMolDisplay``, ``None`` or any other object.
    :param ctx: Column render context.
    :returns: HTML fragment.
    """
    if value is None:
        return ""
    if not isinstance(value, oedepict.OE2DMolDisplay) or not value.IsValid():
        return html.escape(str(value))
    owner = getattr(value, "_cnotebook_owner", None)
    copy = oedepict.OE2DMolDisplay(value)
    copy._cnotebook_owner = owner  # type: ignore[attr-defined]
    return oeimage_to_html(
        _render_display_image(copy, ctx), ctx=ctx,
        logical_width=copy.GetWidth(), logical_height=copy.GetHeight(),
    )


def design_unit_cell_html(value: Any, ctx: CNotebookContext) -> str:
    """HTML for one design-unit cell.

    :param value: ``OEDesignUnit``, ``None`` or any other object.
    :param ctx: Column render context.
    :returns: HTML fragment.
    """
    if value is None:
        return ""
    if not isinstance(value, oechem.OEDesignUnit):
        return html.escape(str(value))
    return oeimage_to_html(oedu_to_image(value, ctx=ctx), ctx=ctx)


def molecule_cell_image(value: Any, ctx: CNotebookContext) -> oedepict.OEImage | None:
    """Image for one molecule cell (marimo path); ``None`` for ``None`` or non-molecules.

    :param value: ``OEMolBase`` or other.
    :param ctx: Column render context.
    :returns: Image tagged with ``_cnotebook_logical_size``.
    """
    if value is None or not isinstance(value, oechem.OEMolBase):
        return None
    if not value.IsValid() or _exceeds_limit(value, ctx):
        image = oemol_to_image(value, ctx=ctx)
        return _tag(image, image.GetWidth(), image.GetHeight())
    depiction = make_depiction(value, ctx=ctx, apply_callbacks=False)
    for callback in ctx.callbacks:
        callback(depiction.display)
    return _tag(depiction.render_image(ctx), depiction.display.GetWidth(), depiction.display.GetHeight())


def display_cell_image(value: Any, ctx: CNotebookContext) -> oedepict.OEImage | None:
    """Image for one display cell (marimo path).

    Prepared displays already had callbacks applied when created; they are rendered as-is.
    """
    if value is None or not isinstance(value, oedepict.OE2DMolDisplay) or not value.IsValid():
        return None
    owner = getattr(value, "_cnotebook_owner", None)
    copy = oedepict.OE2DMolDisplay(value)
    copy._cnotebook_owner = owner  # type: ignore[attr-defined]
    return _tag(_render_display_image(copy, ctx), copy.GetWidth(), copy.GetHeight())


def design_unit_cell_image(value: Any, ctx: CNotebookContext) -> oedepict.OEImage | None:
    """Image for one design-unit cell (marimo path)."""
    if value is None or not isinstance(value, oechem.OEDesignUnit):
        return None
    dep = oedu_to_disp(value, ctx=ctx, apply_callbacks=False)
    if dep is not None:
        # Ligand case: apply callbacks exactly once and reuse the depiction
        for callback in ctx.callbacks:
            callback(dep.display)
        image = oedu_to_image(value, ctx=ctx, dep=dep)
        return _tag(image, dep.display.GetWidth(), dep.display.GetHeight())
    else:
        # Apo case: placeholder (not oversampled)
        image = oedu_to_image(value, ctx=ctx, dep=dep)
        return _tag(image, image.GetWidth(), image.GetHeight())
