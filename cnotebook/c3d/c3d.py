"""C3D class for interactive 3D molecule viewing in notebooks."""

from __future__ import annotations

import asyncio
import functools
import os
import stat
import sys
import tempfile
from collections.abc import Callable, Iterable, Sequence
from html import escape
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cnotebook import config
from cnotebook.config import UNSET
from cnotebook.core import viewer3d
from cnotebook.core.convert import (
    MoleculeData,
    convert_design_unit,
    convert_map,
    convert_molecule,
)
from cnotebook.core.errors import CNotebookError, warn
from cnotebook.core.vocabulary import (
    ISOSURFACE_REPRESENTATIONS as _ISOSURFACE_REPRESENTATION_TUPLE,
)
from cnotebook.core.vocabulary import (
    STYLE_PRESETS as _STYLE_PRESETS,
)
from cnotebook.core.vocabulary import (
    SURFACE_MODES as _SURFACE_MODE_TUPLE,
)
from cnotebook.core.vocabulary import (
    SURFACE_TYPES as _SURFACE_TYPE_TUPLE,
)
from cnotebook.core.vocabulary import (
    VIEW_PRESETS as _VIEW_PRESET_TUPLE,
)

if TYPE_CHECKING:  # Importing the widget module for real would pull in anywidget.
    from cnotebook.c3d.widget import C3DWidget, CommandHandle, PickEvent

__all__ = ["C3D"]

# ---------------------------------------------------------------------------
# Style presets
# ---------------------------------------------------------------------------

_VIEW_PRESETS = set(_VIEW_PRESET_TUPLE)
_SURFACE_TYPES = set(_SURFACE_TYPE_TUPLE)
_SURFACE_MODES = set(_SURFACE_MODE_TUPLE)
_ISOSURFACE_REPRESENTATIONS = set(_ISOSURFACE_REPRESENTATION_TUPLE)

# Design section D3: a screenshot request that the front end never answers fails after
# this long rather than leaving the caller's cell awaiting forever.
_SCREENSHOT_TIMEOUT = 30.0

# The eight bytes every PNG file starts with (PNG specification, clause 5.2).
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _prepare_target(path: str | os.PathLike[str]) -> Path:
    """Validate that *path* can be written and return it as a :class:`~pathlib.Path`.

    The directory is checked before any work is done so a mistyped path fails
    immediately rather than after a render or a 30 s wait for the front end.

    :param path: Destination file.
    :returns: The destination as a path.
    :raises CNotebookError: If the destination's directory does not exist.
    """
    target = Path(path)
    directory = target.parent
    if not directory.is_dir():
        raise CNotebookError(f"Cannot write {target}: the directory {directory} does not exist")
    return target


@functools.cache
def _default_file_mode() -> int:
    """Return the permissions a plain ``open(path, "wb")`` would give a new file.

    The umask can only be read by setting it, which is process-global and therefore
    momentarily wrong for every other thread. The answer is cached so that window is
    opened once per process instead of once per saved file; a program that changes its
    umask mid-run is not worth reopening it for.

    :returns: The mode bits for a newly created output file.
    """
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def _apply_output_permissions(temporary: Path, target: Path) -> None:
    """Give the temporary file the permissions the finished document should have.

    :func:`tempfile.mkstemp` creates its file 0600 because temporary files may hold
    secrets. A saved document is an ordinary output file, so it takes the mode of the
    file it replaces, or the mode a plain ``open()`` would have produced.

    :param temporary: The file about to be moved into place.
    :param target: The destination, which may or may not exist yet.
    """
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except OSError:
        mode = _default_file_mode()
    os.chmod(temporary, mode)


def _write_atomically(path: str | os.PathLike[str], data: bytes) -> Path:
    """Write *data* to *path* so a failed write never leaves a truncated file.

    The bytes go to a temporary file in the destination directory and are moved onto the
    target with :func:`os.replace`, which is atomic within one filesystem. A reader
    therefore sees either the previous file or the complete new one, and an interrupted
    write leaves the previous document in place.

    :param path: Destination file.
    :param data: Bytes to write.
    :returns: The destination path.
    :raises CNotebookError: If the destination's directory does not exist.
    :raises OSError: If the write or the move fails.
    """
    target = _prepare_target(path)
    descriptor, temporary = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        _apply_output_permissions(Path(temporary), target)
        os.replace(temporary, target)
    except BaseException:
        # os.replace consumed the temporary file on success; on any failure it is still
        # there, and a stray dot-file next to the user's output is its own small bug.
        Path(temporary).unlink(missing_ok=True)
        raise
    return target


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


def _has_display_frontend() -> bool:
    """Check whether something in this process could render a widget.

    A widget is a message to a front end, not a value: without one it has nothing to
    draw into and shows as a bare repr. A terminal IPython session counts as no front
    end even though it has a shell, because it has no widget manager. The kernel shell
    is recognized the same way :func:`cnotebook.get_env` recognizes it, by class name,
    but through the MRO so a front end that subclasses it (Colab does) still counts.
    The check is made per call rather than once at import, because a session can
    acquire a shell after cnotebook loads.

    :returns: True when a marimo notebook or a Jupyter kernel shell is running.
    """
    if _is_marimo():
        return True
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    if shell is None:
        return False
    return any(cls.__name__ == "ZMQInteractiveShell" for cls in type(shell).__mro__)


class C3D:
    """Interactive 3D molecule viewer for Jupyter and Marimo notebooks.

    Provides a builder-style API for constructing a self-contained 3Dmol.js
    viewer that can be displayed inline in notebook cells.

    :meth:`display` shows a live widget when the notebook can render one, and the
    self-contained HTML document otherwise. A live viewer can then be driven from
    Python: :meth:`execute` runs GUI terminal commands, :meth:`on_pick` and
    :attr:`picked` report atom picks, :attr:`view` and :meth:`set_view` move the
    camera, and :meth:`screenshot` captures the frame.

    A viewer is built, then shown. Once :attr:`widget` exists the builder methods
    refuse to change the scene, because the widget was initialized from the payload as
    it stood and would not see the change; drive the live viewer with :meth:`execute`,
    or build a second ``C3D``. :meth:`close` ends the live session for good.

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
    _DEFAULT_HEIGHT_CONSOLE = 500
    _DEFAULT_HEIGHT_LARGE = 600
    _ATOM_THRESHOLD = 1000

    def __init__(self, width: int = UNSET, height: int | None = UNSET, theme: str = UNSET):
        """Create a new C3D viewer instance.

        Every parameter left unset resolves through :func:`cnotebook.config.resolve`,
        so a configuration file or :func:`cnotebook.configure` sets the defaults.

        :param width: Viewer width in pixels (configured default 800).
        :param height: Viewer height in pixels. When ``None`` (the configured
            default), the height is chosen automatically: 300 px for small
            viewers, 500 px when the console is visible, or 600 px when the
            largest molecule has more than 1 000 atoms.
        :param theme: Color theme. ``"auto"`` detects from the host
            environment, ``"dark"`` or ``"light"`` sets explicitly.
        :raises ValueError: If *theme* is not ``"auto"``, ``"light"``, or ``"dark"``.
        """
        width = config.resolve("c3d", "width", width)
        height = config.resolve("c3d", "height", height)
        theme = config.resolve("c3d", "theme", theme)
        if theme not in ("auto", "light", "dark"):
            raise ValueError(
                f"Unknown theme '{theme}'. Choose 'auto', 'light', or 'dark'."
            )
        # The display mode is snapshotted here rather than read in display(), so a
        # viewer built in one cell behaves the same however the configuration changes
        # before it is shown.
        self._display_mode: str = config.resolve("display", "mode", UNSET)
        self._widget: C3DWidget | None = None
        self._closed = False
        self._views: dict[str, list[float]] = {}
        self._screenshot_timeout: float = _SCREENSHOT_TIMEOUT
        self._width = width
        self._height = height
        self._molecules: list[MoleculeData] = []
        self._operations: list[dict[str, Any]] = []
        self._active_maps: set[str] = set()
        self._ui: dict[str, bool] = {
            "sidebar": True,
            "menubar": True,
            "console": True,
        }
        self._ui_explicit = False
        self._background: str | None = None
        self._background_explicit = False
        self._theme: str = theme
        self._zoom_to: str | dict[str, Any] | None = None
        self._orient: bool | str | dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _assert_mutable(self) -> None:
        """Refuse a builder call once the viewer is on screen as a widget.

        The widget is initialized from the payload built when it was created, and it
        keeps no link back to the builder. Accepting a later ``add_molecule`` would
        change what :meth:`to_html` and :meth:`save` produce while the widget on screen
        went on showing the old scene, so the three outputs would quietly disagree.

        :raises CNotebookError: If a widget has been created for this viewer.
        """
        if self._widget is not None:
            raise CNotebookError(
                "this viewer is displayed as a widget; live changes go through "
                "execute(), or build a new C3D"
            )

    # ------------------------------------------------------------------
    # Builder methods
    #
    # Every method below changes what the viewer will show, so each one starts with
    # _assert_mutable() and raises CNotebookError once a widget exists.
    # ------------------------------------------------------------------

    def add_molecule(
        self, mol: Any, name: str | None = None, disabled: bool = False, *, generate_3d: bool = True
    ) -> C3D:
        """Add an OpenEye molecule to the viewer.

        The molecule is converted to SDF format via :func:`convert_molecule`.
        If the molecule lacks 3D coordinates, conformer generation is
        attempted automatically.

        :param mol: OpenEye molecule (``OEMolBase`` subclass).
        :param name: Optional display name for the molecule.
        :param disabled: If True, the molecule is hidden when the viewer
            starts. It can be made visible later via the sidebar.
        :param generate_3d: If False, skip automatic 3D coordinate generation.
        :returns: Self, for method chaining.
        :raises TypeError: If *mol* is not an ``OEMolBase``.
        """
        self._assert_mutable()
        mol_data = convert_molecule(mol, name=name, disabled=disabled, generate_3d=generate_3d)
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
        self._assert_mutable()
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
        *,
        generate_3d: bool = True,
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
        :param generate_3d: If False, skip automatic 3D coordinate generation.
        :returns: Self, for method chaining.
        :raises ValueError: If *enable* is an unrecognized string.
        :raises TypeError: If *enable* is not a string or ``Sequence``.
        """
        self._assert_mutable()
        self._validate_enable(enable)
        items = list(mols)
        for i, mol in enumerate(items):
            disabled = self._resolve_disabled(enable, i)
            name = self._resolve_batch_name(mol.GetTitle(), prefix, i) if prefix is not None else None
            self.add_molecule(mol, name=name, disabled=disabled, generate_3d=generate_3d)
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
        self._assert_mutable()
        self._validate_enable(enable)
        items = list(dus)
        for i, du in enumerate(items):
            disabled = self._resolve_disabled(enable, i)
            name = self._resolve_batch_name(du.GetTitle(), prefix, i) if prefix is not None else None
            self.add_design_unit(du, name=name, disabled=disabled)
        return self

    def add_style(
        self,
        style: str | dict[str, Any],
        selection: str | dict[str, Any] | None = None,
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
        self._assert_mutable()
        style_dict = self._normalize_style(style, color=color)
        self._operations.append(
            {"op": "style", "selection": selection, "style": style_dict}
        )
        return self

    def remove_style(
        self,
        style: str | dict[str, Any],
        selection: str | dict[str, Any] | None = None,
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
        self._assert_mutable()
        style_dict = self._normalize_style(style, allow_everything=True)
        self._operations.append(
            {"op": "remove_style", "selection": selection, "style": style_dict}
        )
        return self

    def show_style(
        self,
        style: str | dict[str, Any],
        selection: str | dict[str, Any] | None = None,
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
        style: str | dict[str, Any],
        selection: str | dict[str, Any] | None = None,
    ) -> C3D:
        """Synonym for :meth:`remove_style`.

        :param style: Style preset or raw 3Dmol.js style dict.
        :param selection: Atoms to modify.
        :returns: Self, for method chaining.
        """
        return self.remove_style(style, selection=selection)

    def show_polar_hydrogens(self, rep: str | dict[str, Any]) -> C3D:
        """Show a representation for polar hydrogens.

        :param rep: Style preset or raw 3Dmol.js style dict to add.
        :returns: Self, for method chaining.
        """
        return self.add_style(rep, "polar_hydrogen")

    def hide_nonpolar_hydrogens(
        self,
        rep: str | dict[str, Any] | None = None,
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
        selection: str | dict[str, Any],
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
        self._assert_mutable()
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
        self._assert_mutable()
        self._operations.append({"op": "remove_surface", "name": name})
        return self

    def add_map(
        self,
        path_or_grid: str | Path | Any,
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
        self._assert_mutable()
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
        self._assert_mutable()
        self._active_maps.discard(name)
        self._operations.append({"op": "remove_map", "name": name})
        return self

    def add_isosurface(
        self,
        map_name: str,
        name: str | None = None,
        level: float | None = None,
        selection: str | dict[str, Any] | None = None,
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
        self._assert_mutable()
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
        self._assert_mutable()
        self._operations.append({"op": "remove_isosurface", "name": name})
        return self

    @staticmethod
    def _normalize_style(
        style: str | dict[str, Any],
        color: str | None = None,
        allow_everything: bool = False,
    ) -> dict[str, Any]:
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
            style_spec: dict[str, Any] = {}
            if color is not None:
                style_spec["color"] = color
            style_dict = {_STYLE_PRESETS[style]: style_spec}
        else:
            style_dict = dict(style)
        return style_dict

    def set_color(
        self,
        selection: str | dict[str, Any],
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
        self._assert_mutable()
        self._operations.append({"op": "color", "selection": selection, "color": color, "hets": hets})
        return self

    def set_ui(
        self,
        sidebar: bool = True,
        menubar: bool = True,
        console: bool = True,
        terminal: bool | None = None,
    ) -> C3D:
        """Configure which UI panels are visible.

        :param sidebar: Show the sidebar panel.
        :param menubar: Show the menubar panel.
        :param console: Show the command console panel.
        :param terminal: Deprecated alias for ``console``.
        :returns: Self, for method chaining.
        """
        self._assert_mutable()
        if terminal is not None:
            console = terminal
        self._ui = {
            "sidebar": sidebar,
            "menubar": menubar,
            "console": console,
        }
        self._ui_explicit = True
        return self

    def set_background(self, color: str) -> C3D:
        """Set the viewer background color.

        :param color: CSS color string (e.g. ``"#ffffff"`` or ``"white"``).
        :returns: Self, for method chaining.
        """
        self._assert_mutable()
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
        self._assert_mutable()
        if theme not in ("auto", "light", "dark"):
            raise ValueError(
                f"Unknown theme '{theme}'. Choose 'auto', 'light', or 'dark'."
            )
        self._theme = theme
        return self

    def zoom_to(self, selection: str | dict[str, Any] | None = None) -> C3D:
        """Set the zoom target after loading.

        :param selection: Selection to zoom into. Can be a selection
            expression string (e.g. ``"resn 502"``, ``"chain A"``),
            a raw 3Dmol.js selection dict (e.g. ``{"chain": "A"}``),
            or ``None`` to fit all molecules in view.
        :returns: Self, for method chaining.
        """
        self._assert_mutable()
        self._zoom_to = selection
        return self

    def orient(
        self, selection: bool | str | dict[str, Any] = True
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
        self._assert_mutable()
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
        self._assert_mutable()
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

    def _build_init_payload(self) -> dict[str, Any]:
        """Build the JSON-serializable initialization payload (see core.viewer3d)."""
        return viewer3d.build_init_payload(
            self._molecules,
            self._operations,
            ui=self._ui,
            ui_explicit=self._ui_explicit,
            theme=self._theme,
            background=self._background,
            zoom_to=self._zoom_to,
            orient=self._orient,
        )

    def to_html(self) -> str:
        """Generate a self-contained HTML document for the viewer."""
        if not self._molecules:
            raise ValueError(
                "No molecules have been added. "
                "Call add_molecule() or add_design_unit() first."
            )
        payload = self._build_init_payload()
        return viewer3d.render_html(payload, width=self._width, height=self._effective_height)

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    @property
    def _effective_height(self) -> int:
        """Compute the display height in pixels.

        When the height was explicitly set via the constructor, that value
        is returned.  Otherwise, the height is chosen based on the maximum
        atom count across all molecules and whether the command console is
        visible.

        :returns: Height in pixels.
        """
        if self._height is not None:
            return self._height
        n_mols = len(self._molecules)
        max_atoms = max((m.num_atoms for m in self._molecules), default=0)
        if max_atoms > self._ATOM_THRESHOLD:
            return self._DEFAULT_HEIGHT_LARGE
        height = self._DEFAULT_HEIGHT_SMALL

        console_visible = (
            self._ui.get("console", False) if self._ui_explicit else n_mols >= 3
        )
        if console_visible:
            return max(height, self._DEFAULT_HEIGHT_CONSOLE)
        return height

    @property
    def widget(self) -> C3DWidget:
        """The live :class:`~cnotebook.c3d.widget.C3DWidget`, created on first access.

        The widget module is imported here rather than at the top of this one, so
        building and saving a static viewer never needs anywidget. Creating the widget
        freezes the viewer: the builder methods refuse further changes from then on.

        :returns: The widget backing this viewer.
        :raises ImportError: If anywidget is not installed.
        :raises CNotebookError: If :meth:`close` has been called; the widget it cached
            is bound to a comm that no longer exists.
        """
        if self._closed:
            raise CNotebookError(
                "viewer closed; build a new C3D to display another widget"
            )
        if self._widget is None:
            from cnotebook.c3d.widget import C3DWidget

            self._widget = C3DWidget(
                payload=viewer3d.escape_script_json(self._build_init_payload()),
                width=self._width,
                height=self._effective_height,
            )
        return self._widget

    def _static_display(self):
        """Build the self-contained iframe output for the current environment.

        :returns: ``marimo.Html`` in marimo, otherwise an object with ``_repr_html_``.
        """
        iframe_html = (
            '<iframe style="width: 100%; border: none; '
            f'height: {self._effective_height}px;" '
            f'srcdoc="{escape(self.to_html())}"></iframe>'
        )
        if _is_marimo():
            import marimo as mo  # pyright: ignore[reportMissingImports]

            return mo.Html(iframe_html)
        return _JupyterIFrame(iframe_html)

    def display(self, static: bool | None = None):
        """Display the viewer in the current notebook environment.

        :param static: ``True`` for the self-contained HTML output, ``False`` for the
            live widget, ``None`` (the default) for the display mode snapshotted when
            this viewer was created. Widget mode falls back to the static output, with
            one :class:`~cnotebook.core.errors.CNotebookWarning`, when anywidget is not
            installed.
        :returns: A displayable object for the current environment: the widget itself in
            Jupyter, ``marimo.ui.anywidget(widget)`` in marimo, or an iframe wrapper.
        :raises ValueError: If no molecule has been added.
        :raises CNotebookError: If widget mode is asked of a closed viewer. The static
            output still works after :meth:`close`.
        """
        if not self._molecules:
            raise ValueError(
                "No molecules have been added. "
                "Call add_molecule() or add_design_unit() first."
            )
        if static is None:
            # A widget needs a front end to render into. In a script, a REPL or a test
            # run there is none, and the widget would show as a bare repr, so the
            # self-contained document is the only useful output. Asking for the widget
            # explicitly still returns it, because the caller may want the object.
            use_static = self._display_mode == "static" or not _has_display_frontend()
        else:
            use_static = static
        if use_static:
            return self._static_display()
        try:
            widget = self.widget
        except ImportError:
            warn(
                "anywidget is not installed; showing the static C3D output "
                "instead of the live widget"
            )
            return self._static_display()
        if _is_marimo():
            import marimo as mo  # pyright: ignore[reportMissingImports]

            return mo.ui.anywidget(widget)
        return widget

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write the self-contained HTML document to *path*.

        The document is moved into place only once it is complete, so an interrupted
        write leaves any previous file intact. Because the move is a rename, a symbolic
        link at *path* is replaced by the document rather than followed to its target.

        :param path: Destination file; its directory must exist.
        :returns: The path written.
        :raises ValueError: If no molecule has been added.
        :raises CNotebookError: If the destination's directory does not exist.
        """
        # Checked here as well as in the write, so a mistyped path fails before the
        # document is rendered rather than after.
        target = _prepare_target(path)
        return _write_atomically(target, self.to_html().encode("utf-8"))

    def close(self) -> None:
        """Close the live widget, if one was ever created.

        Every command still queued on the front end settles as a failure and every
        pending screenshot is rejected, because the comm that would answer them goes
        away with the widget. Closing a viewer twice, or one that was only ever
        rendered statically, does nothing.

        Closing is final. Anything that needs the live widget - :attr:`widget`,
        :meth:`display` in widget mode, :meth:`execute`, :meth:`set_view`,
        :meth:`restore_view`, :meth:`screenshot` and :meth:`save_png` - raises
        afterwards, because reusing the cached widget would send to a dead comm and
        wait for an answer that cannot come. What needs no front end goes on working:
        :meth:`to_html`, :meth:`save`, ``display(static=True)``, and the last
        :attr:`view`, :attr:`views` and :attr:`picked` the viewer reported.
        """
        self._closed = True
        if self._widget is not None:
            self._widget.close()

    # ------------------------------------------------------------------
    # Live interaction
    # ------------------------------------------------------------------

    def execute(self, command: str) -> CommandHandle:
        """Queue a GUI terminal command on the live widget.

        :param command: Terminal command line, e.g. ``"zoom resn LIG"``.
        :returns: A :class:`~cnotebook.c3d.widget.CommandHandle` that settles, and can
            be awaited, when the front end reports the result.
        :raises ImportError: If anywidget is not installed.
        :raises CNotebookError: If the viewer has been closed.
        """
        return self.widget.submit(command)

    def on_pick(self, callback: Callable[[PickEvent], None]) -> None:
        """Call *callback* with a :class:`~cnotebook.c3d.widget.PickEvent` on every pick.

        :param callback: Callback taking the event; an exception from it is logged,
            not raised.
        :raises ImportError: If anywidget is not installed.
        """
        self.widget.on_pick(callback)

    @property
    def picked(self) -> PickEvent | None:
        """The last :class:`~cnotebook.c3d.widget.PickEvent`, or ``None``.

        Reading this never creates a widget: without one there can be no pick.
        """
        return self._widget.last_pick if self._widget is not None else None

    @property
    def view(self) -> list[float] | None:
        """The last view array the viewer reported, as a copy, or ``None``.

        The array is 3Dmol's ``getView()`` vector, ``[x, y, z, zoom, qx, qy, qz, qw]``.
        """
        if self._widget is None or not self._widget.view:
            return None
        return list(self._widget.view)

    def set_view(self, view: Iterable[float]) -> None:
        """Point the camera at a 3Dmol view array.

        :param view: Eight finite numbers, as :attr:`view` reports them.
        :raises ValueError: If the view is not a sequence of eight finite numbers.
        :raises ImportError: If anywidget is not installed.
        :raises CNotebookError: If the viewer has been closed.
        """
        from cnotebook.c3d.widget import _validate_view

        # Validated before the widget is touched: a rejected camera must not be the
        # thing that brings a live widget into being on a viewer never displayed. The
        # coordinates go on rather than the caller's iterable, which validating a
        # generator would have consumed.
        coordinates = _validate_view(view)
        self.widget.set_view(coordinates)

    def save_view(self, name: str) -> None:
        """Remember the current camera under *name*.

        :param name: Key to store the view under; an existing key is overwritten.
        :raises CNotebookError: If the viewer has not reported a view yet.
        """
        current = self.view
        if current is None:
            raise CNotebookError(
                "No view available yet; interact with the viewer or call set_view() first"
            )
        self._views[name] = current

    def restore_view(self, name: str) -> None:
        """Point the camera at a view saved with :meth:`save_view`.

        :param name: Key the view was saved under.
        :raises CNotebookError: If *name* is not a saved view, or the viewer is closed.
        :raises ImportError: If anywidget is not installed.
        """
        try:
            view = self._views[name]
        except KeyError as exc:
            known = ", ".join(sorted(self._views)) or "none"
            raise CNotebookError(f"No view saved as '{name}' (saved views: {known})") from exc
        # Through the widget, so the request counter moves: restoring the camera the
        # viewer already reports has to reach the front end all the same.
        self.set_view(list(view))

    @property
    def views(self) -> dict[str, list[float]]:
        """The saved views by name, as a copy of the mapping and of every array."""
        return {name: list(view) for name, view in self._views.items()}

    async def screenshot(self) -> bytes:
        """Capture the current frame as PNG bytes.

        :returns: The PNG image the front end rendered.
        :raises CNotebookError: If the viewer is closed, the capture failed, or the
            front end did not answer within 30 s.
        :raises ImportError: If anywidget is not installed.
        """
        future = self.widget.request_screenshot()
        try:
            return await asyncio.wait_for(future, self._screenshot_timeout)
        except TimeoutError as exc:
            # wait_for cancels the future it was given, which is what drops the request
            # from the widget's registry. Cancelling again costs nothing and keeps that
            # guarantee here, where the timeout is defined.
            future.cancel()
            raise CNotebookError(
                f"Screenshot did not arrive within {self._screenshot_timeout} s"
            ) from exc

    async def save_png(self, path: str | os.PathLike[str]) -> Path:
        """Capture the current frame and write it to *path*.

        The destination is checked before the capture is requested, and the image is
        moved into place only once it is complete, so a failed capture never replaces
        an existing screenshot with a truncated one. Because the move is a rename, a
        symbolic link at *path* is replaced by the image rather than followed to its
        target.

        :param path: Destination file; its directory must exist.
        :returns: The path written.
        :raises CNotebookError: If the destination's directory does not exist, the
            viewer is closed, the capture failed or timed out, or the answer is not a
            PNG image.
        :raises ImportError: If anywidget is not installed.
        """
        target = _prepare_target(path)
        png = await self.screenshot()
        if not png.startswith(_PNG_SIGNATURE):
            raise CNotebookError(
                f"The front end returned {len(png)} bytes that are not a PNG image; "
                f"nothing was written to {target}"
            )
        return _write_atomically(target, png)


class _JupyterIFrame:
    """Lightweight wrapper that renders an iframe via ``_repr_html_``.

    Using a custom class avoids the ``IPython.display.HTML`` warning
    about ``IFrame`` when the HTML data contains ``<iframe``.
    """

    def __init__(self, html: str):
        self._html = html

    def _repr_html_(self) -> str:
        return self._html
