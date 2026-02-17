"""C3D class for interactive 3D molecule viewing in notebooks."""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from cnotebook.c3d.convert import MoleculeData, convert_design_unit, convert_molecule

# ---------------------------------------------------------------------------
# Load static assets at module level
# ---------------------------------------------------------------------------

_STATIC_DIR = Path(__file__).parent / "static"
_3DMOL_JS = (_STATIC_DIR / "3Dmol-min.js").read_text()
_GUI_JS = (_STATIC_DIR / "3dmol-gui.js").read_text()
_GUI_CSS = (_STATIC_DIR / "3dmol-gui.css").read_text()

# ---------------------------------------------------------------------------
# Style presets
# ---------------------------------------------------------------------------

_STYLE_PRESETS = {
    "cartoon": "cartoon",
    "stick": "stick",
    "sphere": "sphere",
    "line": "line",
    "cross": "cross",
    "surface": "surface",
}


def _is_marimo() -> bool:
    """Check if running in a marimo notebook environment.

    Checks both that marimo is imported AND that we are inside a marimo
    runtime (not just a plain Python script that happens to import marimo).

    :returns: True if running inside a marimo notebook.
    """
    if "marimo" not in sys.modules:
        return False
    try:
        import marimo as mo

        return mo.running_in_notebook()
    except (ImportError, AttributeError):
        return False


class C3D:
    """Interactive 3D molecule viewer for Jupyter and Marimo notebooks.

    Provides a builder-style API for constructing a self-contained 3Dmol.js
    viewer that can be displayed inline in notebook cells.

    Example::

        from openeye import oechem
        from cnotebook.c3d import C3D

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        viewer = (
            C3D(width=800, height=600)
            .add_molecule(mol, name="benzene")
            .add_style({"chain": "A"}, "cartoon")
            .set_background("#ffffff")
        )
        viewer.display()
    """

    def __init__(self, width: int = 800, height: int = 600):
        """Create a new C3D viewer instance.

        :param width: Viewer width in pixels.
        :param height: Viewer height in pixels.
        """
        self._width = width
        self._height = height
        self._molecules: List[MoleculeData] = []
        self._styles: List[Dict[str, Any]] = []
        self._ui: Dict[str, bool] = {
            "sidebar": True,
            "menubar": True,
            "terminal": True,
        }
        self._background: Optional[str] = None
        self._zoom_to: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def add_molecule(self, mol: Any, name: str | None = None) -> C3D:
        """Add an OpenEye molecule to the viewer.

        The molecule is converted to SDF format via :func:`convert_molecule`.
        If the molecule lacks 3D coordinates, conformer generation is
        attempted automatically.

        :param mol: OpenEye molecule (``OEMolBase`` subclass).
        :param name: Optional display name for the molecule.
        :returns: Self, for method chaining.
        :raises TypeError: If *mol* is not an ``OEMolBase``.
        """
        mol_data = convert_molecule(mol, name=name)
        self._molecules.append(mol_data)
        return self

    def add_design_unit(self, du: Any, name: str | None = None) -> C3D:
        """Add an OpenEye design unit to the viewer.

        The design unit is converted to PDB format via
        :func:`convert_design_unit`.

        :param du: OpenEye design unit (``OEDesignUnit``).
        :param name: Optional display name for the design unit.
        :returns: Self, for method chaining.
        :raises TypeError: If *du* is not an ``OEDesignUnit``.
        """
        mol_data = convert_design_unit(du, name=name)
        self._molecules.append(mol_data)
        return self

    def add_style(
        self,
        selection: Dict[str, Any],
        style: Union[str, Dict[str, Any]],
        color: str | None = None,
    ) -> C3D:
        """Add a visual style to apply to selected atoms.

        :param selection: 3Dmol.js selection specification as a dict
            (e.g. ``{"chain": "A"}``).
        :param style: Either a preset name (``"cartoon"``, ``"stick"``,
            ``"sphere"``, ``"line"``, ``"cross"``, ``"surface"``) or a
            raw 3Dmol.js style dict that is passed through verbatim.
        :param color: Optional color string. When *style* is a preset
            name, this is set as the ``color`` key in the style spec.
            Ignored when *style* is a dict.
        :returns: Self, for method chaining.
        :raises ValueError: If *style* is a string that is not a
            recognised preset name.
        """
        if isinstance(style, str):
            if style not in _STYLE_PRESETS:
                raise ValueError(
                    f"Unknown style preset '{style}'. "
                    f"Choose from: {', '.join(sorted(_STYLE_PRESETS))}"
                )
            style_spec: Dict[str, Any] = {}
            if color is not None:
                style_spec["color"] = color
            style_dict = {_STYLE_PRESETS[style]: style_spec}
        else:
            style_dict = dict(style)

        self._styles.append({"selection": dict(selection), "style": style_dict})
        return self

    def set_ui(
        self,
        sidebar: bool = True,
        menubar: bool = True,
        terminal: bool = True,
    ) -> C3D:
        """Configure which UI panels are visible.

        :param sidebar: Show the sidebar panel.
        :param menubar: Show the menubar panel.
        :param terminal: Show the terminal panel.
        :returns: Self, for method chaining.
        """
        self._ui = {
            "sidebar": sidebar,
            "menubar": menubar,
            "terminal": terminal,
        }
        return self

    def set_background(self, color: str) -> C3D:
        """Set the viewer background colour.

        :param color: CSS colour string (e.g. ``"#ffffff"`` or ``"white"``).
        :returns: Self, for method chaining.
        """
        self._background = color
        return self

    def zoom_to(self, selection: Dict[str, Any] | None = None) -> C3D:
        """Set the zoom target after loading.

        :param selection: 3Dmol.js selection dict to zoom into, or
            ``None`` to fit all molecules in view.
        :returns: Self, for method chaining.
        """
        self._zoom_to = selection
        return self

    # ------------------------------------------------------------------
    # Payload & HTML generation
    # ------------------------------------------------------------------

    def _build_init_payload(self) -> Dict[str, Any]:
        """Build the JSON-serializable initialisation payload.

        This dict is embedded in the HTML page as
        ``window.__C3D_INIT__`` and consumed by the GUI JavaScript.

        :returns: Payload dictionary.
        """
        molecules = [
            {"name": m.name, "data": m.data, "format": m.format}
            for m in self._molecules
        ]

        return {
            "molecules": molecules,
            "styles": list(self._styles),
            "ui": dict(self._ui),
            "background": self._background,
            "zoomTo": self._zoom_to,
        }

    def to_html(self) -> str:
        """Generate a self-contained HTML document for the viewer.

        All JavaScript and CSS dependencies are inlined so the document
        requires no external network requests.

        :returns: Complete HTML document as a string.
        :raises ValueError: If no molecules have been added.
        """
        if not self._molecules:
            raise ValueError(
                "No molecules have been added. "
                "Call add_molecule() or add_design_unit() first."
            )

        payload = self._build_init_payload()
        payload_json = json.dumps(payload)

        return (
            "<!DOCTYPE html>\n"
            '<html lang="en">\n'
            "<head>\n"
            '<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "<style>\n"
            f"{_GUI_CSS}\n"
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

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def display(self):
        """Display the viewer in the current notebook environment.

        Wraps :meth:`to_html` in an ``<iframe>`` with ``srcdoc``.
        Automatically detects whether the environment is Marimo or Jupyter
        and returns the appropriate display object.

        :returns: A displayable object (``marimo.Html`` or
            ``IPython.display.HTML``).
        """
        html_content = self.to_html()

        iframe_html = (
            '<iframe style="width: 100%; border: none; '
            f'height: {self._height}px;" '
            f'srcdoc="{escape(html_content)}"></iframe>'
        )

        if _is_marimo():
            import marimo as mo

            return mo.Html(iframe_html)
        else:
            from IPython.display import HTML

            return HTML(iframe_html)
