"""Pure 3D viewer payload and self-contained HTML builder.

Lifted out of C3D so the same logic serves notebook display (cnotebook) and
the HTTP API (oefastapi). Depends only on the standard library and the inlined
3Dmol.js + GUI assets shipped in cnotebook/core/static.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cnotebook.core.convert import MoleculeData

_STATIC_DIR = Path(__file__).parent / "static"
_3DMOL_JS = (_STATIC_DIR / "3Dmol-min.js").read_text()
_GUI_JS = (_STATIC_DIR / "3dmol-gui.js").read_text()
_GUI_CSS = (_STATIC_DIR / "3dmol-gui.css").read_text()

_DEFAULT_HEIGHT_SMALL = 300
_DEFAULT_HEIGHT_CONSOLE = 500
_DEFAULT_HEIGHT_LARGE = 600
_ATOM_THRESHOLD = 1000


def build_init_payload(
    molecules: list[MoleculeData],
    operations: list[dict[str, Any]],
    *,
    ui: dict[str, bool] | None,
    ui_explicit: bool,
    theme: str,
    background: str | None,
    zoom_to: Any,
    orient: Any,
) -> dict[str, Any]:
    """Build the JSON-serializable ``window.__C3D_INIT__`` payload.

    :param molecules: Converted molecule entries.
    :param operations: Ordered list of scene operation dicts (each carries an ``op`` key).
    :param ui: Explicit UI panel flags, or ``None`` to apply molecule-count smart defaults.
    :param ui_explicit: Whether *ui* was explicitly set by the caller.
    :param theme: ``"auto"``, ``"light"``, or ``"dark"``.
    :param background: CSS background color, or ``None``.
    :param zoom_to: Zoom target selection, or ``None``.
    :param orient: Orient setting, or ``None``.
    :returns: Payload dictionary consumed by the 3dmol-js-gui front end.
    """
    mol_payload = [
        {"name": m.name, "data": m.data, "format": m.format, "disabled": m.disabled}
        for m in molecules
    ]
    n_mols = len(molecules)

    if ui_explicit and ui is not None:
        resolved_ui = dict(ui)
    elif n_mols <= 1:
        resolved_ui = {"sidebar": False, "menubar": False, "console": False}
    elif n_mols == 2:
        resolved_ui = {"sidebar": True, "menubar": False, "console": False}
    else:
        resolved_ui = {"sidebar": True, "menubar": True, "console": True}

    resolved_orient = orient
    if orient is None and zoom_to is None:
        resolved_orient = True

    return {
        "molecules": mol_payload,
        "operations": list(operations),
        "ui": resolved_ui,
        "theme": theme,
        "background": background,
        "zoomTo": zoom_to,
        "orient": resolved_orient,
    }


def effective_height(
    molecules: list[MoleculeData],
    ui: dict[str, bool],
    ui_explicit: bool,
    height: int | None,
) -> int:
    """Resolve a viewer height when one was not given explicitly.

    Mirrors C3D's atom-count + console heuristic.

    :param molecules: Converted molecule entries.
    :param ui: Resolved UI panel flags.
    :param ui_explicit: Whether UI was explicitly set.
    :param height: Explicit height, or ``None`` to compute.
    :returns: Height in pixels.
    """
    if height is not None:
        return height
    n_mols = len(molecules)
    max_atoms = max((m.num_atoms for m in molecules), default=0)
    if max_atoms > _ATOM_THRESHOLD:
        return _DEFAULT_HEIGHT_LARGE
    console_visible = ui.get("console", False) if ui_explicit else n_mols >= 3
    if console_visible:
        return _DEFAULT_HEIGHT_CONSOLE
    return _DEFAULT_HEIGHT_SMALL


def _script_safe_json(payload: dict[str, Any]) -> str:
    """Serialize *payload* for safe embedding in an inline ``<script>`` block.

    User-controlled fields (e.g. molecule names) may contain ``</script>`` or
    the line/paragraph separators that break inline scripts. Escaping ``<``,
    ``>``, ``&``, U+2028, and U+2029 prevents script-context breakout.

    :param payload: JSON-serializable payload.
    :returns: A JSON string safe to inline in HTML.
    """
    raw = json.dumps(payload)
    return (
        raw.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace(chr(0x2028), "\\u2028")
        .replace(chr(0x2029), "\\u2029")
    )


def render_html(payload: dict[str, Any], *, width: int, height: int) -> str:
    """Render a self-contained HTML document for the viewer.

    All JavaScript and CSS are inlined; the root container is sized to
    *width* x *height* so the standalone document needs no host styling. The
    payload is escaped for safe embedding in the inline ``<script>`` block.

    :param payload: Payload from :func:`build_init_payload`.
    :param width: Container width in pixels.
    :param height: Container height in pixels.
    :returns: Complete HTML document.
    """
    payload_json = _script_safe_json(payload)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        "<style>\n"
        f"{_GUI_CSS}\n"
        f"#app {{ width: {int(width)}px; height: {int(height)}px; }}\n"
        "</style>\n"
        "<script>\n"
        f"{_3DMOL_JS}\n"
        "</script>\n"
        "</head>\n"
        "<body>\n"
        '<div id="app">\n'
        '  <div id="menubar-container" class="menubar"></div>\n'
        '  <div id="viewer-container" class="viewer-container"></div>\n'
        '  <div id="sidebar-container" class="sidebar"></div>\n'
        '  <div id="terminal-container" class="terminal"></div>\n'
        "</div>\n"
        "<script>\n"
        f"window.__C3D_INIT__ = {payload_json};\n"
        "</script>\n"
        '<script type="module">\n'
        f"{_GUI_JS}\n"
        "</script>\n"
        "</body>\n"
        "</html>"
    )
