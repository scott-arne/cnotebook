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

_VIEW_PRESETS = {"simple", "sites", "ball-and-stick"}


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

    _DEFAULT_HEIGHT_SMALL = 300
    _DEFAULT_HEIGHT_LARGE = 600
    _ATOM_THRESHOLD = 1000

    def __init__(self, width: int = 800, height: int | None = None):
        """Create a new C3D viewer instance.

        :param width: Viewer width in pixels.
        :param height: Viewer height in pixels. When ``None`` (the default),
            the height is chosen automatically: 300 px if the largest
            molecule has at most 1 000 atoms, otherwise 600 px.
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
        self._ui_explicit = False
        self._background: Optional[str] = None
        self._background_explicit = False
        self._theme: str = "light"
        self._zoom_to: Optional[Dict[str, Any]] = None
        self._orient: Optional[Union[bool, str, Dict[str, Any]]] = None
        self._preset: Optional[str] = None

    # ------------------------------------------------------------------
    # Builder methods
    # ------------------------------------------------------------------

    def add_molecule(
        self, mol: Any, name: str | None = None, disabled: bool = False
    ) -> C3D:
        """Add an OpenEye molecule to the viewer.

        The molecule is converted to SDF format via :func:`convert_molecule`.
        If the molecule lacks 3D coordinates, conformer generation is
        attempted automatically.

        :param mol: OpenEye molecule (``OEMolBase`` subclass).
        :param name: Optional display name for the molecule.
        :param disabled: If True, the molecule is hidden when the viewer
            starts. It can be made visible later via the sidebar.
        :returns: Self, for method chaining.
        :raises TypeError: If *mol* is not an ``OEMolBase``.
        """
        mol_data = convert_molecule(mol, name=name, disabled=disabled)
        self._molecules.append(mol_data)
        return self

    def add_design_unit(
        self, du: Any, name: str | None = None, disabled: bool = False
    ) -> C3D:
        """Add an OpenEye design unit to the viewer.

        The design unit is converted to PDB format via
        :func:`convert_design_unit`.

        :param du: OpenEye design unit (``OEDesignUnit``).
        :param name: Optional display name for the design unit.
        :param disabled: If True, the design unit is hidden when the viewer
            starts. It can be made visible later via the sidebar.
        :returns: Self, for method chaining.
        :raises TypeError: If *du* is not an ``OEDesignUnit``.
        """
        mol_data = convert_design_unit(du, name=name, disabled=disabled)
        self._molecules.append(mol_data)
        return self

    def add_style(
        self,
        style: Union[str, Dict[str, Any]],
        selection: Union[str, Dict[str, Any], None] = None,
        color: str | None = None,
    ) -> C3D:
        """Add a visual style to apply to selected atoms.

        :param style: Either a preset name (``"cartoon"``, ``"stick"``,
            ``"sphere"``, ``"line"``, ``"cross"``, ``"surface"``) or a
            raw 3Dmol.js style dict that is passed through verbatim.
        :param selection: Atoms to style. Can be ``None`` to style all
            atoms, a selection expression string (e.g. ``"chain A"``,
            ``"resn LIG"``), an entry name to target a specific
            molecule, or a raw 3Dmol.js selection dict (e.g.
            ``{"chain": "A"}``).
        :param color: Optional color string. When *style* is a preset
            name, this is set as the ``color`` key in the style spec.
            Ignored when *style* is a dict.
        :returns: Self, for method chaining.
        :raises ValueError: If *style* is a string that is not a
            recognised preset name.

        Example::

            viewer = C3D()
            viewer.add_molecule(mol, name="benzene")

            # Style everything
            viewer.add_style("stick")

            # Style by selection expression
            viewer.add_style("cartoon", "chain A")

            # Style a specific entry
            viewer.add_style("sphere", "benzene")

            # Style with a 3Dmol.js dict
            viewer.add_style("stick", {"chain": "A"}, color="green")
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

        self._styles.append({"selection": selection, "style": style_dict})
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
        self._ui_explicit = True
        return self

    def set_background(self, color: str) -> C3D:
        """Set the viewer background colour.

        :param color: CSS colour string (e.g. ``"#ffffff"`` or ``"white"``).
        :returns: Self, for method chaining.
        """
        self._background = color
        self._background_explicit = True
        return self

    def set_theme(self, theme: str = "light") -> C3D:
        """Set the GUI colour theme.

        Controls the overall UI appearance (panel backgrounds, text colour,
        borders) **and** the viewer background colour when no explicit
        background has been set via :meth:`set_background`.

        :param theme: ``"light"`` or ``"dark"``.
        :returns: Self, for method chaining.
        :raises ValueError: If *theme* is not ``"light"`` or ``"dark"``.
        """
        if theme not in ("light", "dark"):
            raise ValueError(
                f"Unknown theme '{theme}'. Choose 'light' or 'dark'."
            )
        self._theme = theme
        return self

    def zoom_to(self, selection: Union[str, Dict[str, Any], None] = None) -> C3D:
        """Set the zoom target after loading.

        :param selection: Selection to zoom into. Can be a selection
            expression string (e.g. ``"resn 502"``, ``"chain A"``),
            a raw 3Dmol.js selection dict (e.g. ``{"chain": "A"}``),
            or ``None`` to fit all molecules in view.
        :returns: Self, for method chaining.
        """
        self._zoom_to = selection
        return self

    def orient(
        self, selection: Union[bool, str, Dict[str, Any]] = True
    ) -> C3D:
        """Orient the view by aligning principal axes with the screen.

        Uses PCA to align the longest molecular dimension horizontally,
        the second-longest vertically, and the shortest perpendicular to
        the screen, then zooms to fit.  When used, this replaces any
        :meth:`zoom_to` setting.

        :param selection: Atoms to orient on. ``True`` orients on all
            atoms.  A string selection expression (e.g. ``"chain A"``)
            or a raw 3Dmol.js selection dict (e.g. ``{"chain": "A"}``)
            restricts orientation to the matching atoms.
        :returns: Self, for method chaining.
        """
        self._orient = selection
        return self

    def set_preset(self, name: str) -> C3D:
        """Apply a view preset.

        Presets are compound styles defined in the 3dmol-js-gui that combine
        multiple representations into a common visualization.  When a preset
        is set it replaces any styles added via :meth:`add_style`.

        Available presets:

        - ``"simple"`` -- Element-coloured cartoon with per-chain carbons
          and sticks for ligands.
        - ``"sites"`` -- Like *simple*, plus stick representation for
          residues within 5 angstroms of ligands.
        - ``"ball-and-stick"`` -- Ball-and-stick for ligands only.

        :param name: Preset name (case-insensitive).
        :returns: Self, for method chaining.
        :raises ValueError: If *name* is not a recognised preset.
        """
        key = name.lower()
        if key not in _VIEW_PRESETS:
            raise ValueError(
                f"Unknown view preset '{name}'. "
                f"Choose from: {', '.join(sorted(_VIEW_PRESETS))}"
            )
        self._preset = key
        return self

    # ------------------------------------------------------------------
    # Payload & HTML generation
    # ------------------------------------------------------------------

    def _build_init_payload(self) -> Dict[str, Any]:
        """Build the JSON-serializable initialisation payload.

        This dict is embedded in the HTML page as
        ``window.__C3D_INIT__`` and consumed by the GUI JavaScript.

        When the user has not explicitly configured UI or background,
        smart defaults are applied based on molecule count:

        - **1 molecule** -- no GUI panels, white background.
        - **2 molecules** -- sidebar only (no menubar or terminal).
        - **3+ molecules** -- full GUI (all panels visible).

        :returns: Payload dictionary.
        """
        molecules = [
            {
                "name": m.name,
                "data": m.data,
                "format": m.format,
                "disabled": m.disabled,
            }
            for m in self._molecules
        ]

        n_mols = len(self._molecules)

        # Smart UI defaults based on molecule count
        if self._ui_explicit:
            ui = dict(self._ui)
        elif n_mols <= 1:
            ui = {"sidebar": False, "menubar": False, "terminal": False}
        elif n_mols == 2:
            ui = {"sidebar": True, "menubar": False, "terminal": False}
        else:
            ui = dict(self._ui)

        # Default to orient when neither zoom_to nor orient was set
        orient = self._orient
        if self._orient is None and self._zoom_to is None:
            orient = True

        return {
            "molecules": molecules,
            "styles": list(self._styles),
            "preset": self._preset,
            "ui": ui,
            "theme": self._theme,
            "background": self._background,
            "zoomTo": self._zoom_to,
            "orient": orient,
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

    @property
    def _effective_height(self) -> int:
        """Compute the display height in pixels.

        When the height was explicitly set via the constructor, that value
        is returned.  Otherwise the height is chosen based on the maximum
        atom count across all molecules: 300 px when every entry has at
        most 1 000 atoms, 600 px otherwise.

        :returns: Height in pixels.
        """
        if self._height is not None:
            return self._height
        max_atoms = max((m.num_atoms for m in self._molecules), default=0)
        if max_atoms > self._ATOM_THRESHOLD:
            return self._DEFAULT_HEIGHT_LARGE
        return self._DEFAULT_HEIGHT_SMALL

    def display(self):
        """Display the viewer in the current notebook environment.

        Wraps :meth:`to_html` in an ``<iframe>`` with ``srcdoc``.
        Automatically detects whether the environment is Marimo or Jupyter
        and returns the appropriate display object.

        :returns: A displayable object (``marimo.Html`` or a Jupyter-compatible
            display object with ``_repr_html_``).
        """
        html_content = self.to_html()
        height = self._effective_height

        iframe_html = (
            '<iframe style="width: 100%; border: none; '
            f'height: {height}px;" '
            f'srcdoc="{escape(html_content)}"></iframe>'
        )

        if _is_marimo():
            import marimo as mo

            return mo.Html(iframe_html)
        else:
            return _JupyterIFrame(iframe_html)


class _JupyterIFrame:
    """Lightweight wrapper that renders an iframe via ``_repr_html_``.

    Using a custom class avoids the ``IPython.display.HTML`` warning
    about ``IFrame`` when the HTML data contains ``<iframe``.
    """

    def __init__(self, html: str):
        self._html = html

    def _repr_html_(self) -> str:
        return self._html
