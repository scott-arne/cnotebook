"""C3D class for interactive 3D molecule viewing in notebooks."""

from __future__ import annotations

import json
import sys
from html import escape
from pathlib import Path
from collections.abc import Iterable, Sequence
from typing import Any, Dict, List, Optional, Union

from cnotebook.c3d.convert import MoleculeData, convert_design_unit, convert_map, convert_molecule

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
_SURFACE_TYPES = {"molecular", "sasa"}
_SURFACE_MODES = {"surface", "wireframe"}
_ISOSURFACE_REPRESENTATIONS = {"mesh", "surface"}


def _is_marimo() -> bool:
    """Check if running in a marimo notebook environment.

    Checks both that marimo is imported AND that we are inside a marimo
    runtime (not just a plain Python script that happens to import marimo).

    :returns: True if running inside a marimo notebook.
    """
    if "marimo" not in sys.modules:
        return False
    try:
        import marimo as mo  # pyright: ignore[reportMissingImports]

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
            .add_style("cartoon", {"chain": "A"})
            .set_background("#ffffff")
        )
        viewer.display()
    """

    _DEFAULT_HEIGHT_SMALL = 300
    _DEFAULT_HEIGHT_LARGE = 600
    _ATOM_THRESHOLD = 1000

    def __init__(self, width: int = 800, height: int | None = None, theme: str = "auto"):
        """Create a new C3D viewer instance.

        :param width: Viewer width in pixels.
        :param height: Viewer height in pixels. When ``None`` (the default),
            the height is chosen automatically: 300 px if the largest
            molecule has at most 1 000 atoms, otherwise 600 px.
        :param theme: Color theme. ``"auto"`` detects from the host
            environment, ``"dark"`` or ``"light"`` sets explicitly.
        """
        if theme not in ("auto", "light", "dark"):
            raise ValueError(
                f"Unknown theme '{theme}'. Choose 'auto', 'light', or 'dark'."
            )
        self._width = width
        self._height = height
        self._molecules: List[MoleculeData] = []
        self._operations: List[Dict[str, Any]] = []
        self._active_maps: set[str] = set()
        self._ui: Dict[str, bool] = {
            "sidebar": True,
            "menubar": True,
            "terminal": True,
        }
        self._ui_explicit = False
        self._background: Optional[str] = None
        self._background_explicit = False
        self._theme: str = theme
        self._zoom_to: Optional[Union[str, Dict[str, Any]]] = None
        self._orient: Optional[Union[bool, str, Dict[str, Any]]] = None

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

    # ------------------------------------------------------------------
    # Batch helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_enable(enable: str | Sequence[bool]) -> None:
        """Validate the enable parameter eagerly.

        :param enable: Enable mode to validate.
        :raises ValueError: If *enable* is an unrecognized string.
        :raises TypeError: If *enable* is not a string or ``Sequence``.
        """
        if isinstance(enable, str):
            if enable not in ("all", "first"):
                raise ValueError(
                    f"Unknown enable mode '{enable}'. Choose 'all' or 'first'."
                )
        elif not isinstance(enable, Sequence):
            raise TypeError(
                f"enable must be 'all', 'first', or a Sequence[bool], "
                f"got {type(enable).__name__}"
            )

    @staticmethod
    def _resolve_disabled(enable: str | Sequence[bool], index: int) -> bool:
        """Compute the disabled flag for a batch entry.

        Assumes *enable* has already been validated by :meth:`_validate_enable`.

        :param enable: Enable mode — ``"all"``, ``"first"``, or a sequence of bools.
        :param index: 0-based index of the current entry.
        :returns: True if the entry should be disabled.
        """
        if isinstance(enable, str):
            if enable == "all":
                return False
            return index != 0  # "first"
        if index < len(enable):
            return not enable[index]
        return True

    @staticmethod
    def _resolve_batch_name(title: str, prefix: str, index: int) -> str:
        """Compute the prefixed name for a batch entry.

        :param title: The object's title (may be empty).
        :param prefix: The prefix string.
        :param index: 0-based index of the current entry.
        :returns: Prefixed name string.
        """
        base = title if title else str(index + 1)
        return f"{prefix}{base}"

    # ------------------------------------------------------------------
    # Batch add methods
    # ------------------------------------------------------------------

    def add_molecules(
        self,
        mols: Iterable,
        prefix: str | None = None,
        enable: str | Sequence[bool] = "first",
    ) -> C3D:
        """Add multiple OpenEye molecules to the viewer.

        :param mols: Iterable of OpenEye molecules (``OEMolBase`` subclasses).
        :param prefix: Optional prefix prepended to each entry's name via
            ``f"{prefix}{base_name}"``.
        :param enable: Controls which entries are visible on load.
            ``"all"`` enables all, ``"first"`` enables only the first
            (default), or a ``Sequence[bool]`` where ``True`` means enabled.
            If the sequence is shorter than *mols*, remaining entries are
            disabled.
        :returns: Self, for method chaining.
        :raises ValueError: If *enable* is an unrecognized string.
        :raises TypeError: If *enable* is not a string or ``Sequence``.
        """
        self._validate_enable(enable)
        items = list(mols)
        for i, mol in enumerate(items):
            disabled = self._resolve_disabled(enable, i)
            name = self._resolve_batch_name(mol.GetTitle(), prefix, i) if prefix is not None else None
            self.add_molecule(mol, name=name, disabled=disabled)
        return self

    def add_design_units(
        self,
        dus: Iterable,
        prefix: str | None = None,
        enable: str | Sequence[bool] = "first",
    ) -> C3D:
        """Add multiple OpenEye design units to the viewer.

        :param dus: Iterable of OpenEye design units (``OEDesignUnit``).
        :param prefix: Optional prefix prepended to each entry's name via
            ``f"{prefix}{base_name}"``.
        :param enable: Controls which entries are visible on load.
            ``"all"`` enables all, ``"first"`` enables only the first
            (default), or a ``Sequence[bool]`` where ``True`` means enabled.
            If the sequence is shorter than *dus*, remaining entries are
            disabled.
        :returns: Self, for method chaining.
        :raises ValueError: If *enable* is an unrecognized string.
        :raises TypeError: If *enable* is not a string or ``Sequence``.
        """
        self._validate_enable(enable)
        items = list(dus)
        for i, du in enumerate(items):
            disabled = self._resolve_disabled(enable, i)
            name = self._resolve_batch_name(du.GetTitle(), prefix, i) if prefix is not None else None
            self.add_design_unit(du, name=name, disabled=disabled)
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
            recognized preset name.

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
        style_dict = self._normalize_style(style, color=color)
        self._operations.append(
            {"op": "style", "selection": selection, "style": style_dict}
        )
        return self

    def remove_style(
        self,
        style: Union[str, Dict[str, Any]],
        selection: Union[str, Dict[str, Any], None] = None,
    ) -> C3D:
        """Remove a visual style from selected atoms.

        :param style: Either a preset name accepted by :meth:`add_style`,
            ``"everything"`` to clear all styles from the selection, or a raw
            3Dmol.js style dict. For dicts, the top-level style keys are
            removed from the matching atoms.
        :param selection: Atoms to modify. Uses the same selection forms as
            :meth:`add_style`.
        :returns: Self, for method chaining.
        :raises ValueError: If *style* is a string that is not a recognized
            preset name.

        Example::

            viewer = C3D()
            viewer.add_molecule(mol, name="complex")
            viewer.add_style("cartoon")
            viewer.add_style("stick", "resn LIG")

            # Hide the ligand sticks while leaving cartoon visible
            viewer.remove_style("stick", "resn LIG")
        """
        style_dict = self._normalize_style(style, allow_everything=True)
        self._operations.append(
            {"op": "remove_style", "selection": selection, "style": style_dict}
        )
        return self

    def show_style(
        self,
        style: Union[str, Dict[str, Any]],
        selection: Union[str, Dict[str, Any], None] = None,
        color: str | None = None,
    ) -> C3D:
        """Synonym for :meth:`add_style`.

        :param style: Style preset or raw 3Dmol.js style dict.
        :param selection: Atoms to style.
        :param color: Optional color for preset styles.
        :returns: Self, for method chaining.
        """
        return self.add_style(style, selection=selection, color=color)

    def hide_style(
        self,
        style: Union[str, Dict[str, Any]],
        selection: Union[str, Dict[str, Any], None] = None,
    ) -> C3D:
        """Synonym for :meth:`remove_style`.

        :param style: Style preset or raw 3Dmol.js style dict.
        :param selection: Atoms to modify.
        :returns: Self, for method chaining.
        """
        return self.remove_style(style, selection=selection)

    def show_polar_hydrogens(self, rep: Union[str, Dict[str, Any]]) -> C3D:
        """Show a representation for polar hydrogens.

        :param rep: Style preset or raw 3Dmol.js style dict to add.
        :returns: Self, for method chaining.
        """
        return self.add_style(rep, "polar_hydrogen")

    def hide_nonpolar_hydrogens(
        self,
        rep: Union[str, Dict[str, Any], None] = None,
    ) -> C3D:
        """Hide a representation for nonpolar hydrogens.

        :param rep: Style preset or raw 3Dmol.js style dict to remove. When
            ``None``, all styles are removed from nonpolar hydrogens.
        :returns: Self, for method chaining.
        """
        return self.remove_style(
            "everything" if rep is None else rep,
            "nonpolar_hydrogen",
        )

    def add_surface(
        self,
        selection: Union[str, Dict[str, Any]],
        name: str | None = None,
        type: str = "molecular",
        color: str = "#FFFFFF",
        opacity: float = 0.75,
        mode: str = "surface",
    ) -> C3D:
        """Add a named surface operation to the scene.

        :param selection: Atoms used to generate the surface.
        :param name: Optional surface name for later removal.
        :param type: Surface type. Accepted values are ``"molecular"`` and
            ``"sasa"``.
        :param color: CSS color string.
        :param opacity: Surface opacity.
        :param mode: Surface display mode. Accepted values are ``"surface"``
            and ``"wireframe"``.
        :returns: Self, for method chaining.
        :raises ValueError: If *type* or *mode* is not recognized.
        """
        surface_type = type.lower()
        if surface_type not in _SURFACE_TYPES:
            raise ValueError(
                f"Unknown surface type '{type}'. "
                f"Choose from: {', '.join(sorted(_SURFACE_TYPES))}"
            )

        surface_mode = mode.lower()
        if surface_mode not in _SURFACE_MODES:
            raise ValueError(
                f"Unknown surface mode '{mode}'. "
                f"Choose from: {', '.join(sorted(_SURFACE_MODES))}"
            )

        self._operations.append(
            {
                "op": "add_surface",
                "selection": selection,
                "name": name,
                "type": surface_type,
                "color": color,
                "opacity": opacity,
                "mode": surface_mode,
            }
        )
        return self

    def remove_surface(self, name: str) -> C3D:
        """Remove a previously added surface by name.

        :param name: Surface name to remove.
        :returns: Self, for method chaining.
        """
        self._operations.append({"op": "remove_surface", "name": name})
        return self

    def add_map(
        self,
        path_or_grid: Union[str, Path, Any],
        name: str | None = None,
        format: str | None = None,
        color: str = "#38BDF8",
        opacity: float = 1.0,
        show_box: bool = False,
    ) -> C3D:
        """Add a volumetric map operation to the scene.

        :param path_or_grid: Map file path or OpenEye scalar grid.
        :param name: Optional map name. Path inputs default to the file stem;
            grid inputs default to the grid title when available.
        :param format: Optional map format override for path inputs.
        :param color: CSS color string.
        :param opacity: Map opacity.
        :param show_box: If True, show the map bounding box.
        :returns: Self, for method chaining.
        :raises ValueError: If a map with the resolved name is already active.
        """
        map_data = convert_map(path_or_grid, name=name, format=format)
        if map_data.name in self._active_maps:
            raise ValueError(f'Map "{map_data.name}" has already been added')

        self._active_maps.add(map_data.name)
        self._operations.append(
            {
                "op": "add_map",
                "name": map_data.name,
                "format": map_data.format,
                "encoding": map_data.encoding,
                "data": map_data.data,
                "color": color,
                "opacity": opacity,
                "showBoundingBox": show_box,
            }
        )
        return self

    def remove_map(self, name: str) -> C3D:
        """Remove a previously added map by name.

        :param name: Map name to remove.
        :returns: Self, for method chaining.
        """
        self._active_maps.discard(name)
        self._operations.append({"op": "remove_map", "name": name})
        return self

    def add_isosurface(
        self,
        map_name: str,
        name: str | None = None,
        level: float | None = None,
        selection: Union[str, Dict[str, Any], None] = None,
        buffer: float | None = None,
        carve: float | None = None,
        representation: str = "mesh",
        color: str = "#0000FF",
        opacity: float = 0.75,
    ) -> C3D:
        """Add an isosurface operation for an active map.

        :param map_name: Name of a map added by :meth:`add_map`.
        :param name: Optional isosurface name for later removal.
        :param level: Contour level. ``None`` lets the GUI choose a default.
        :param selection: Optional atom selection used for clipping.
        :param buffer: Optional selection buffer distance.
        :param carve: Optional carve distance.
        :param representation: Isosurface representation. Accepted values are
            ``"mesh"`` and ``"surface"``.
        :param color: CSS color string.
        :param opacity: Isosurface opacity.
        :returns: Self, for method chaining.
        :raises ValueError: If *map_name* is not active or *representation* is
            not recognized.
        """
        if map_name not in self._active_maps:
            raise ValueError(f'Map "{map_name}" has not been added')

        surface_representation = representation.lower()
        if surface_representation not in _ISOSURFACE_REPRESENTATIONS:
            raise ValueError(
                f"Unknown isosurface representation '{representation}'. "
                f"Choose from: {', '.join(sorted(_ISOSURFACE_REPRESENTATIONS))}"
            )

        self._operations.append(
            {
                "op": "add_isosurface",
                "mapName": map_name,
                "name": name,
                "level": level,
                "selection": selection,
                "buffer": buffer,
                "carve": carve,
                "representation": surface_representation,
                "color": color,
                "opacity": opacity,
            }
        )
        return self

    def remove_isosurface(self, name: str) -> C3D:
        """Remove a previously added isosurface by name.

        :param name: Isosurface name to remove.
        :returns: Self, for method chaining.
        """
        self._operations.append({"op": "remove_isosurface", "name": name})
        return self

    @staticmethod
    def _normalize_style(
        style: Union[str, Dict[str, Any]],
        color: str | None = None,
        allow_everything: bool = False,
    ) -> Dict[str, Any]:
        """Convert a C3D style preset or raw style dict to a style dict.

        :param style: Style preset or raw 3Dmol.js style dict.
        :param color: Optional color for preset styles.
        :param allow_everything: Allow the removal-only ``"everything"``
            sentinel.
        :returns: Normalized style dictionary.
        :raises ValueError: If *style* is an unknown preset string.
        """
        if isinstance(style, str):
            if allow_everything and style == "everything":
                return {"everything": {}}
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
        return style_dict

    def set_color(
        self,
        selection: Union[str, Dict[str, Any]],
        color: str,
        hets: bool = True,
    ) -> C3D:
        """Set the color for atoms matching a selection.

        Operations are applied in the order they are called, so colors
        set after a preset will override the preset's coloring.

        :param selection: Atoms to color. Can be a selection expression
            string (e.g. ``"chain A"``, ``"resn LIG"``), an entry name
            to target a specific molecule, or a raw 3Dmol.js selection
            dict (e.g. ``{"chain": "A"}``).
        :param color: CSS color string (e.g. ``"green"``, ``"#00ff00"``).
        :param hets: If ``True`` (default), all atoms in the selection
            are recolored. If ``False``, only carbon atoms are recolored,
            preserving element coloring for heteroatoms (N, O, S, etc.).
        :returns: Self, for method chaining.

        Example::

            viewer = C3D()
            viewer.add_molecule(mol, name="protein")
            viewer.set_preset("sites")
            viewer.set_color("chain A", "blue")
            viewer.set_color("resn V4M", "magenta", hets=False)
        """
        self._operations.append({"op": "color", "selection": selection, "color": color, "hets": hets})
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
        """Set the viewer background color.

        :param color: CSS color string (e.g. ``"#ffffff"`` or ``"white"``).
        :returns: Self, for method chaining.
        """
        self._background = color
        self._background_explicit = True
        return self

    def set_theme(self, theme: str = "auto") -> C3D:
        """Set the GUI color theme.

        Controls the overall UI appearance (panel backgrounds, text color,
        borders) **and** the viewer background color when no explicit
        background has been set via :meth:`set_background`.

        :param theme: ``"auto"``, ``"light"``, or ``"dark"``.
        :returns: Self, for method chaining.
        :raises ValueError: If *theme* is not ``"auto"``, ``"light"``, or ``"dark"``.
        """
        if theme not in ("auto", "light", "dark"):
            raise ValueError(
                f"Unknown theme '{theme}'. Choose 'auto', 'light', or 'dark'."
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

        - ``"simple"`` -- Element-colored cartoon with per-chain carbons
          and sticks for ligands.
        - ``"sites"`` -- Like *simple*, plus stick representation for
          residues within 5 angstroms of ligands.
        - ``"ball-and-stick"`` -- Ball-and-stick for ligands only.

        :param name: Preset name (case-insensitive).
        :returns: Self, for method chaining.
        :raises ValueError: If *name* is not a recognized preset.
        """
        key = name.lower()
        if key not in _VIEW_PRESETS:
            raise ValueError(
                f"Unknown view preset '{name}'. "
                f"Choose from: {', '.join(sorted(_VIEW_PRESETS))}"
            )
        self._operations.append({"op": "preset", "name": key})
        return self

    # ------------------------------------------------------------------
    # Payload & HTML generation
    # ------------------------------------------------------------------

    def _build_init_payload(self) -> Dict[str, Any]:
        """Build the JSON-serializable initialization payload.

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
            "operations": list(self._operations),
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
        is returned.  Otherwise, the height is chosen based on the maximum
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
            import marimo as mo  # pyright: ignore[reportMissingImports]

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
