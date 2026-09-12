"""MolGrid: molecule grid with a live front end and a static HTML fallback."""

from __future__ import annotations

import functools
import logging
import os
import stat
import sys
import tempfile
import uuid
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

from openeye import oechem, oedepict  # type: ignore[import-untyped]

from cnotebook import config as _config
from cnotebook.config import UNSET
from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import CNotebookError, warn
from cnotebook.core.render import oedisp_to_html, oemol_to_html, prepare_depiction_copy

log = logging.getLogger("cnotebook")

# Front-end assets shipped with the package. The live widget loads them through
# anywidget; the static document inlines them so a saved file needs no network.
_STATIC_DIR = Path(__file__).parent / "static"
_DEFAULT_RENDER_CONTEXT = CNotebookContext()
DEFAULT_STRUCTURE_SCALE = _DEFAULT_RENDER_CONTEXT.structure_scale
DEFAULT_ATOM_LABEL_FONT_SCALE = _DEFAULT_RENDER_CONTEXT.atom_label_font_scale

# Sentinel ``depict_orientation`` requesting per-molecule best-fit selection.
# Real OEDepictOrientation values are positive, so a negative value cannot
# collide with one that would be passed to ``SetDepictOrientation``.
BEST_FIT_ORIENTATION = -1

# Orientations considered when ``BEST_FIT_ORIENTATION`` is selected. Default is
# tried first so it wins ties: elongated molecules only rotate to Horizontal
# when doing so lets them render larger than their natural orientation.
_BEST_FIT_CANDIDATES = (
    oedepict.OEDepictOrientation_Default,
    oedepict.OEDepictOrientation_Horizontal,
)

# Depiction margin (percent) used for grid cards. In fixed-scale mode the
# margin bounds how large a molecule that must shrink to fit can be drawn;
# OpenEye's default 5% leaves visible whitespace around large structures, so
# the grid uses OpenEye's 3% floor to let them render a touch larger. Molecules
# small enough to render at the full structure scale are unaffected.
_GRID_DEPICTION_MARGIN = 3.0

# Card themes accepted by the front end.
_THEMES = ("auto", "light", "dark")

# Label used for molecules with no cluster value.
_UNCATEGORIZED = "Uncategorized"

# Rendered images are cached per grid; the cap bounds memory for very large
# grids, where only the visited pages are ever rendered.
_MAX_CACHE = 5000

_RENDER_OPTION_UNSET = object()


def _collect_render_options(**options: Any) -> dict[str, Any]:
    """Collect render options explicitly provided by the caller.

    :param options: Render option names and values.
    :returns: Mapping containing only caller-provided options.
    """
    return {
        name: value for name, value in options.items()
        if value is not _RENDER_OPTION_UNSET
    }


def _is_marimo() -> bool:
    """Check if running in marimo environment.

    Checks both if marimo is imported AND if we're in a marimo runtime.
    """
    if "marimo" not in sys.modules:
        return False
    try:
        import marimo as mo  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]
        # Check if we're actually in a marimo runtime
        return mo.running_in_notebook()
    except (ImportError, AttributeError):
        return False


def _is_missing(value: Any) -> bool:
    """Check whether a field value should be treated as missing.

    Works without pandas: ``None``, ``NaN`` and pandas' ``NA`` are the only
    values that are missing, and the last two are recognised by not comparing
    equal to themselves. ``NA`` goes one step further and has no truth value at
    all, which is why the ``TypeError`` branch counts as missing; array-like
    values compare elementwise and raise ``ValueError`` instead, so they are
    reported as present.

    :param value: Value to inspect.
    :returns: ``True`` when the value is missing.
    """
    if value is None:
        return True
    try:
        return bool(value != value)  # noqa: PLR0124 (self-comparison is the NaN test)
    except TypeError:
        return True
    except ValueError:
        return False


def _text(value: Any) -> str:
    """Render a field value as display text.

    :param value: Value to convert.
    :returns: Empty string for missing values, ``str(value)`` otherwise.
    """
    return "" if _is_missing(value) else str(value)


def _safe_observer(
    fn: Callable[[dict[str, Any]], None],
) -> Callable[[dict[str, Any]], None]:
    """Wrap a trait observer so a failure in it cannot break the update that ran it.

    Observers run inside the trait assignment that delivers the front end's message. An
    exception there would abort that assignment and leave the grid's Python state
    half-applied while the browser has already moved on, so a failure is reported
    through the package logger (visible at ``ERROR``) instead.

    :param fn: Observer to protect.
    :returns: The same observer, guarded.
    """

    @functools.wraps(fn)
    def observer(change: dict[str, Any]) -> None:
        try:
            fn(change)
        except Exception:
            log.exception("cnotebook: MolGrid %s raised", fn.__name__)

    return observer


def _smarts_request(value: Any) -> tuple[int, str, str] | None:
    """Read a SMARTS request exactly as the front end sends one.

    Nothing is coerced. A sequence number that is not a plain integer, or a missing
    view token, means the message did not come from this protocol, and answering it
    would publish a result no view can match to a question it asked. :class:`bool` is
    an :class:`int` in Python but never a sequence number, so it is rejected too.

    :param value: Raw ``smarts_request`` payload.
    :returns: ``(seq, query, view)``, or ``None`` when the payload is malformed.
    """
    if not isinstance(value, dict):
        return None
    seq = value.get("seq")
    query = value.get("query")
    view = value.get("view")
    if isinstance(seq, bool) or not isinstance(seq, int):
        return None
    if not isinstance(query, str) or not isinstance(view, str):
        return None
    return seq, query, view


def _is_pandas(obj: Any) -> bool:
    """Report whether a frame or column is pandas' rather than polars'.

    Both dataframe accessors hand MolGrid their own frame without converting it, and
    the two libraries address a row differently. The kind is recognized by pandas'
    positional indexer instead of by importing pandas, which the grid does not
    otherwise need.

    :param obj: DataFrame or column supplied by either accessor.
    :returns: True for a pandas object.
    """
    return hasattr(obj, "iloc")


def _search_copy(mol: oechem.OEMolBase) -> oechem.OEMolBase:
    """Copy a molecule for substructure searching.

    ``OEPrepareSearch`` rewrites perception (aromaticity, hybridisation) on the
    molecule it is handed, so searching has to work on a copy or it would mutate
    the caller's molecules. The copy keeps the source's kind so query and
    multiconformer molecules survive the round trip.

    :param mol: Source molecule.
    :returns: A copy safe to perceive into.
    """
    if isinstance(mol, oechem.OEQMolBase):
        return oechem.OEQMol(mol)
    if isinstance(mol, oechem.OEMCMolBase):
        return oechem.OEMol(mol)
    return oechem.OEGraphMol(mol)


@functools.cache
def _static_asset(name: str) -> str:
    """Read a front-end asset from the package's static directory.

    The static document inlines the same module and stylesheet for every grid it
    exports, so the text is cached rather than re-read per call. Reading it lazily
    instead of at import keeps the cost off ``import cnotebook.grid``, which the
    dataframe accessors pay whether or not anything is ever exported.

    :param name: File name inside ``cnotebook/grid/static``.
    :returns: The file's text.
    """
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


def _has_display_frontend() -> bool:
    """Check whether something in this process could render a widget.

    A widget is a message to a front end, not a value: without one it has nothing to
    draw into and shows as a bare repr. A terminal IPython session counts as no front
    end even though it has a shell, because it has no widget manager. The kernel shell
    is recognized through the MRO so a front end that subclasses it (Colab does) still
    counts. The check is made per call rather than once at import, because a session
    can acquire a shell after cnotebook loads.

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


def _prepare_target(path: str | os.PathLike[str]) -> Path:
    """Validate that *path* can be written and return it as a :class:`~pathlib.Path`.

    The directory is checked before any work is done so a mistyped path fails
    immediately rather than after every molecule in the grid has been rendered.

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
    opened once per process instead of once per saved file.

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

    The bytes go to a temporary file in the destination directory and are moved onto
    the target with :func:`os.replace`, which is atomic within one filesystem. A reader
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


class MolGrid:
    """Interactive molecule grid (live widget by default, static HTML on request)."""

    # Grid attributes that become render context arguments. Named here so a
    # candidate context can be built from proposed values before they are
    # committed to the instance.
    _CONTEXT_ATTRS = (
        "width",
        "height",
        "min_width",
        "min_height",
        "max_width",
        "max_height",
        "structure_scale",
        "auto_scale",
        "atom_label_font_scale",
        "title_font_scale",
        "image_format",
        "render_title",
        "max_heavy_atoms",
        "device_pixel_ratio",
    )

    def __init__(
        self,
        mols: Iterable,
        *,
        dataframe=None,
        mol_col: Hashable | None = None,
        title: bool | str | None = True,
        tooltip_fields: list[str] | None = None,
        n_items_per_page: int = UNSET,
        width: int = UNSET,
        height: int = UNSET,
        min_width: float | None = 260.0,
        min_height: float | None = 240.0,
        max_width: float | None = None,
        max_height: float | None = None,
        structure_scale: float = DEFAULT_STRUCTURE_SCALE,
        auto_scale: bool = False,
        atom_label_font_scale: float = DEFAULT_ATOM_LABEL_FONT_SCALE,
        title_font_scale: float = 1.0,
        image_format: str = UNSET,
        bond_width_scaling: bool = True,
        render_title: bool = False,
        depict_orientation: int = BEST_FIT_ORIENTATION,
        max_heavy_atoms: int | None = 100,
        select: bool = True,
        information: bool = True,
        data: str | list[str] | None = None,
        search_fields: list[str] | None = None,
        name: str | None = None,
        cluster: str | Sequence[Hashable] | Mapping[int, Hashable] | None = None,
        cluster_counts: bool = True,
        theme: str = UNSET,
        sort_by: str | tuple[str, bool] | None = None,
        badges: Sequence[str] | None = None,
        static_max_items: int = 2000,
    ):
        """Create a molecule grid; nothing is rendered or displayed until asked for.

        :param mols: Molecules to show. ``None`` entries become placeholders.
        :param dataframe: Optional pandas or polars DataFrame with per-molecule data.
        :param mol_col: Molecule column of *dataframe*, excluded from data fields.
        :param title: Card label mode. ``True`` uses the molecule title, a
            string names a field, ``None``/``False`` hides labels.
        :param tooltip_fields: Fields shown in the hover tooltip.
        :param n_items_per_page: Cards per page. Defaults to the configured
            ``molgrid.n_items_per_page``.
        :param width: Image width in pixels. Defaults to the configured
            ``molgrid.width``.
        :param height: Image height in pixels. Defaults to the configured
            ``molgrid.height``.
        :param min_width: Minimum image width in pixels.
        :param min_height: Minimum image height in pixels.
        :param max_width: Maximum image width in pixels, or None for no limit.
        :param max_height: Maximum image height in pixels, or None for no limit.
        :param structure_scale: Scale factor applied to OpenEye's default
            structure scale. Defaults to the standard CNotebook molecule scale
            factor so grid depictions match single-molecule depictions when no
            shrink-to-fit is needed. Ignored when ``auto_scale`` is ``True``.
        :param auto_scale: When ``True``, size structures to fill each grid
            card (OpenEye AutoScale) instead of using ``structure_scale``.
        :param atom_label_font_scale: Scale factor for atom labels.
        :param title_font_scale: Scale factor for title font.
        :param image_format: ``"svg"`` or ``"png"``. Defaults to the configured
            ``molgrid.image_format``.
        :param bond_width_scaling: Whether MolGrid should reduce bond widths
            when a molecule is shrunk below the baseline structure scale.
        :param render_title: Whether to draw molecule titles inside rendered
            images. Card labels remain controlled by ``title``.
        :param depict_orientation: Preferred 2D depiction orientation. Defaults
            to :data:`BEST_FIT_ORIENTATION`, which prepares each molecule in
            whichever orientation renders largest in the card. Pass an explicit
            ``oedepict.OEDepictOrientation_*`` value to force one orientation.
        :param max_heavy_atoms: Maximum heavy atom count to render, or None.
        :param select: Enable selection checkboxes.
        :param information: Enable the per-card information button.
        :param data: Field(s) shown in the information tooltip. ``None``
            auto-detects the data columns of *dataframe*.
        :param search_fields: Fields for text search. ``None`` auto-detects the
            text columns of *dataframe*.
        :param name: Grid identifier. Defaults to a generated unique name.
        :param cluster: Cluster labels as a *dataframe* column name, a
            per-molecule sequence, or an ``{index: label}`` mapping. Molecules
            with no label are reported as ``"Uncategorized"``.
        :param cluster_counts: Show molecule counts next to cluster labels.
        :param theme: ``"auto"``, ``"light"`` or ``"dark"``. Defaults to the
            configured ``molgrid.theme``.
        :param sort_by: Initial sort field, or ``(field, descending)``.
        :param badges: Fields shown as chips on each card.
        :param static_max_items: :meth:`to_html` warns above this many molecules.
        :raises ValueError: For an unknown theme, a cluster sequence whose
            length does not match *mols*, or a cluster column that does not
            exist in *dataframe*.
        :raises TypeError: For a cluster argument that is not a column name,
            sequence or mapping.
        """
        self._molecules = list(mols)
        self._dataframe = dataframe
        # One mapping of exposed field name -> original column label, built and
        # validated once so every field lookup resolves the same way.
        self._fields = self._build_field_map(dataframe, mol_col)
        self.title = title if title else None
        self.tooltip_fields = list(tooltip_fields or [])
        self.n_items_per_page = _config.resolve("molgrid", "n_items_per_page", n_items_per_page)
        self.width = _config.resolve("molgrid", "width", width)
        self.height = _config.resolve("molgrid", "height", height)
        self.image_format = _config.resolve("molgrid", "image_format", image_format)
        self.theme = _config.resolve("molgrid", "theme", theme)
        if self.theme not in _THEMES:
            raise ValueError(f"Unknown theme '{self.theme}'. Choose 'auto', 'light', or 'dark'.")

        # The display mode is snapshotted here so a later configuration change
        # cannot retroactively alter how an existing grid displays itself.
        self._display_mode = _config.resolve("display", "mode", UNSET)

        self.selection_enabled = select
        self.information_enabled = information
        self.name = name or f"molgrid-{uuid.uuid4().hex[:8]}"
        self.min_width = min_width
        self.min_height = min_height
        self.max_width = max_width
        self.max_height = max_height
        self.structure_scale = structure_scale
        self.auto_scale = auto_scale
        self.atom_label_font_scale = atom_label_font_scale
        self.title_font_scale = title_font_scale
        self.bond_width_scaling = bond_width_scaling
        self.render_title = render_title
        self.depict_orientation = depict_orientation
        self.max_heavy_atoms = max_heavy_atoms
        self.device_pixel_ratio = 2.0
        self.cluster_counts = cluster_counts
        self.static_max_items = static_max_items
        self.badges = list(badges or [])
        if isinstance(sort_by, str):
            self.sort_by: tuple[str, bool] | None = (sort_by, False)
        elif sort_by:
            field, descending = sort_by
            self.sort_by = (str(field), bool(descending))
        else:
            self.sort_by = None
        self.cluster = self._validate_cluster(cluster)

        if data is not None:
            self.information_fields = [data] if isinstance(data, str) else list(data)
        else:
            self.information_fields = self._auto_detect_info_fields()

        if search_fields is None:
            self.search_fields: list[str] = self._auto_detect_search_fields()
        else:
            self.search_fields = list(search_fields)

        self._images: OrderedDict[int, str] = OrderedDict()
        self.revision = 0
        self.selection: list[int] = []
        self._widget: Any = None
        self.closed = False

    # -- validation and data --------------------------------------------------

    def _validate_cluster(self, cluster):
        """Normalize and validate the ``cluster`` constructor argument.

        :param cluster: Column name, per-molecule sequence, or index mapping.
        :returns: The validated column name, label list, or label mapping.
        :raises ValueError: For a missing column or a mismatched sequence length.
        :raises TypeError: For any other argument type.
        """
        if cluster is None:
            return None
        if isinstance(cluster, str):
            if self._dataframe is None:
                raise ValueError("cluster requires a DataFrame when given as a column name")
            if cluster not in self._dataframe.columns:
                raise ValueError(f"Column '{cluster}' not found in DataFrame")
            return cluster
        if isinstance(cluster, Mapping):
            return dict(cluster)
        if isinstance(cluster, Sequence):
            labels = list(cluster)
            if len(labels) != len(self._molecules):
                raise ValueError(
                    f"cluster sequence has {len(labels)} entries for {len(self._molecules)} molecules"
                )
            return labels
        raise TypeError(
            "cluster must be a string (column name), a sequence of labels, "
            "or a mapping from index to label"
        )

    def cluster_labels(self) -> list[str] | None:
        """Per-molecule cluster labels.

        :returns: One label per molecule, or ``None`` when clustering is off.
        """
        if self.cluster is None:
            return None
        if isinstance(self.cluster, str):
            # _validate_cluster rejects a column name without a DataFrame.
            assert self._dataframe is not None
            frame = self._dataframe
            values = (
                list(frame[self.cluster])
                if _is_pandas(frame)
                else frame.get_column(self.cluster).to_list()
            )
            return [_UNCATEGORIZED if _is_missing(v) else str(v) for v in values]
        if isinstance(self.cluster, dict):
            return [
                _UNCATEGORIZED if _is_missing(self.cluster.get(i)) else str(self.cluster[i])
                for i in range(len(self._molecules))
            ]
        return [_UNCATEGORIZED if _is_missing(v) else str(v) for v in self.cluster]

    @staticmethod
    def _build_field_map(dataframe, mol_col) -> dict[str, Any]:
        """Map exposed field names to the source frame's data column labels.

        Field names travel to the front end as strings, so a frame can hold two
        labels that collapse to one name (``0`` and ``"0"``). Resolving a name
        against a freshly stringified view of every column is what lets the
        molecule column shadow a data column, so the mapping is built once
        here, excludes the molecule column entirely and rejects any remaining
        ambiguity.

        :param dataframe: Source DataFrame, or None.
        :param mol_col: Molecule column label, which is never a field.
        :returns: Ordered mapping of field name to original column label.
        :raises ValueError: If two data columns share an exposed field name.
        """
        if dataframe is None:
            return {}
        fields: dict[str, Any] = {}
        for col in dataframe.columns:
            if col == mol_col:
                continue
            name = str(col)
            if name in fields:
                raise ValueError(
                    f"DataFrame column labels {fields[name]!r} and {col!r} both become "
                    f"'{name}' as grid field names; rename one of them"
                )
            fields[name] = col
        return fields

    def _frame_columns(self) -> list[str]:
        """Exposed field names of the source frame's data columns.

        :returns: Field names in frame order, excluding the molecule column.
        """
        return list(self._fields)

    def _auto_detect_search_fields(self) -> list[str]:
        """Auto-detect searchable text columns from the source DataFrame.

        :returns: Exposed field names of the searchable columns.
        """
        dataframe = self._dataframe
        if dataframe is None:
            return []

        search_fields = []
        for name, col in self._fields.items():
            dtype_str = str(dataframe[col].dtype).lower()

            # Skip molecule dtypes (oepandas MoleculeDtype) and numbers.
            if "molecule" in dtype_str:
                continue
            if any(t in dtype_str for t in ("int", "float", "double", "decimal")):
                continue

            if "object" in dtype_str or "str" in dtype_str:
                search_fields.append(name)
                continue

            # Extension dtypes such as ``category`` hide their value type, so
            # fall back to inspecting the first value actually stored.
            try:
                column = dataframe[col]
                if _is_pandas(column):
                    present = column.dropna()
                    first_valid = present.iloc[0] if len(present) > 0 else None
                else:
                    present = column.drop_nulls()
                    first_valid = present[0] if len(present) > 0 else None
                if isinstance(first_valid, str):
                    search_fields.append(name)
            except (IndexError, KeyError, AttributeError):
                pass

        return search_fields

    def _auto_detect_info_fields(self) -> list[str]:
        """Auto-detect data columns from the source DataFrame for the tooltip.

        :returns: Exposed field names of the columns holding displayable data.
        """
        dataframe = self._dataframe
        if dataframe is None:
            return []

        info_fields = []
        for name, col in self._fields.items():
            # Skip the chemistry dtypes, whose values have no useful text form.
            dtype_str = str(dataframe[col].dtype).lower()
            if "molecule" in dtype_str or "display" in dtype_str or "design" in dtype_str:
                continue

            info_fields.append(name)

        return info_fields

    def _field_value(self, idx: int, mol, field: str):
        """Get a field value from a DataFrame column or a molecule property.

        :param idx: Row index in the dataframe.
        :param mol: OpenEye molecule object, or None.
        :param field: Field name to retrieve.
        :returns: Raw field value, or None when the field is unknown.
        """
        if self._dataframe is not None and field in self._fields:
            column = self._fields[field]
            frame = self._dataframe
            if _is_pandas(frame):
                return frame.iloc[idx][column]
            return frame.row(idx, named=True)[column]

        if not isinstance(mol, oechem.OEMolBase):
            return None
        if field == "Title":
            return mol.GetTitle() or None
        return oechem.OEGetSDData(mol, field) or None

    def items(self) -> list[dict[str, Any]]:
        """Build the per-molecule index consumed by the front end.

        The payload is plain JSON-serializable data and carries no images;
        images are rendered on demand by :meth:`render_indices`.

        :returns: One dict per molecule with index, title, SMILES, fields,
            badges and cluster label.
        """
        labels = self.cluster_labels()
        fields = list(dict.fromkeys([
            *self._frame_columns(),
            *self.search_fields,
            *self.information_fields,
            *self.tooltip_fields,
        ]))
        out: list[dict[str, Any]] = []
        for idx, mol in enumerate(self._molecules):
            valid = isinstance(mol, oechem.OEMolBase) and mol.IsValid()
            title = None
            if self.title is True:
                title = mol.GetTitle() if valid else None
            elif self.title:
                title = _text(self._field_value(idx, mol, self.title)) or None
            out.append({
                "i": idx,
                "title": title or None,
                "smiles": oechem.OEMolToSmiles(mol) if valid else "",
                "fields": {f: _text(self._field_value(idx, mol, f)) for f in fields},
                "badges": [f"{b}: {_text(self._field_value(idx, mol, b))}" for b in self.badges],
                "cluster": labels[idx] if labels else None,
            })
        return out

    def widget_config(self, *, static: bool) -> dict[str, Any]:
        """Build the configuration dictionary consumed by the front end.

        :param static: Whether the front end runs without a kernel connection.
        :returns: JSON-serializable grid configuration.
        """
        labels = self.cluster_labels()
        return {
            "page_size": int(self.n_items_per_page),
            "sort_by": (
                {"field": self.sort_by[0], "descending": bool(self.sort_by[1])}
                if self.sort_by else None
            ),
            "badges": list(self.badges),
            "search_fields": list(self.search_fields),
            "info_fields": list(self.information_fields),
            # The hover surface shows these when the grid was given them, and falls back to
            # the information fields when it was not.
            "tooltip_fields": list(self.tooltip_fields),
            "export_columns": list(dict.fromkeys([*self._frame_columns(), *self.information_fields])),
            "cluster_labels": sorted(set(labels)) if labels else None,
            "cluster_counts": bool(self.cluster_counts),
            "theme": self.theme,
            "static": static,
            "select": bool(self.selection_enabled),
            "information": bool(self.information_enabled),
            "title": self.title is not None,
            "image_width": int(self.width),
            "image_height": int(self.height),
        }

    # -- rendering ------------------------------------------------------------

    def _create_render_context(
        self, overrides: Mapping[str, Any] | None = None
    ) -> CNotebookContext:
        """Create a render context from the grid's render options.

        :param overrides: Proposed render option values to use in place of the
            grid's own. Names that are not render context arguments are
            ignored. Passing candidate values lets the caller validate them
            through the context's setters without mutating the grid.
        :returns: CNotebook context used to render each grid molecule.
        """
        values: dict[str, Any] = {name: getattr(self, name) for name in self._CONTEXT_ATTRS}
        if overrides:
            values.update(
                (name, value) for name, value in overrides.items() if name in values
            )
        return CNotebookContext(
            bond_width_scaling=False,
            title=values.pop("render_title"),
            scope="local",
            **values,
        )

    @staticmethod
    def _prepare_in_orientation(mol, orientation: int):
        """Create a depiction-prepared copy of ``mol`` in a given orientation.

        The copy is made through :func:`prepare_depiction_copy` so multiconformer
        and query molecules become plain 2D depiction molecules and the caller's
        molecule is never touched.

        :param mol: OpenEye molecule object.
        :param orientation: OEDepictOrientation value.
        :returns: Prepared molecule copy.
        """
        render_mol = prepare_depiction_copy(mol, clear_coords=True)
        opts = oedepict.OEPrepareDepictionOptions()
        opts.SetDepictOrientation(orientation)
        oedepict.OEPrepareDepiction(render_mol, opts)
        return render_mol

    @property
    def _baseline_scale(self) -> float:
        """Absolute OpenEye scale for this grid's ``structure_scale`` factor.

        ``structure_scale`` is a multiplier of OpenEye's default structure
        scale, whereas OpenEye display and fitting APIs work in absolute scale
        units. This resolves the factor to the absolute value used internally
        for shrink-to-fit comparisons and bond-width scaling.

        :returns: ``structure_scale`` multiplied by ``oedepict.OEScale_Default``.
        """
        return self.structure_scale * oedepict.OEScale_Default

    def _fitting_scale(self, prepared) -> float:
        """Largest depiction scale that fits ``prepared`` in the grid card.

        Uses OpenEye's AutoScale on the grid card dimensions and caps the
        result at the baseline scale so molecules small enough to render at
        full scale are not enlarged past it.

        :param prepared: Depiction-prepared molecule.
        :returns: Capped fitting scale for this molecule in the grid card.
        """
        opts = oedepict.OE2DMolDisplayOptions()
        opts.SetWidth(self.width)
        opts.SetHeight(self.height)
        opts.SetScale(oedepict.OEScale_AutoScale)
        opts.SetMargins(_GRID_DEPICTION_MARGIN)
        opts.SetTitleLocation(oedepict.OETitleLocation_Hidden)
        fit = oedepict.OE2DMolDisplay(prepared, opts).GetScale()
        return min(self._baseline_scale, fit)

    def _prepare_best_fit(self, mol):
        """Prepare ``mol`` in whichever candidate orientation renders largest.

        Compact molecules render at the capped baseline scale in every
        orientation and so keep their natural (Default) depiction. Elongated
        molecules that must shrink to fit pick the orientation that lets them
        fill the card, avoiding narrow vertical strips.

        :param mol: OpenEye molecule object.
        :returns: Prepared molecule copy in the best-fitting orientation.
        """
        best_mol = self._prepare_in_orientation(mol, _BEST_FIT_CANDIDATES[0])
        best_scale = self._fitting_scale(best_mol)
        for orientation in _BEST_FIT_CANDIDATES[1:]:
            prepared = self._prepare_in_orientation(mol, orientation)
            scale = self._fitting_scale(prepared)
            if scale > best_scale:
                best_scale = scale
                best_mol = prepared
        return best_mol

    def _prepare_molecule_for_rendering(self, mol):
        """Create a molecule copy prepared for MolGrid rendering.

        With ``depict_orientation`` set to :data:`BEST_FIT_ORIENTATION` (the
        default), each molecule is prepared in whichever candidate orientation
        lets it render largest in the grid card, so elongated drug-like
        molecules use card width instead of becoming narrow vertical strips
        while compact molecules keep their natural single-molecule depiction.
        Any explicit orientation is honored as-is.

        :param mol: OpenEye molecule object, or None.
        :returns: Prepared molecule copy, or the input for anything that cannot
            be depicted (placeholders are rendered from the original).
        """
        if not isinstance(mol, oechem.OEMolBase):
            return mol
        if not (mol.IsValid() and mol.NumAtoms() > 0):
            return mol

        if self.depict_orientation == BEST_FIT_ORIENTATION:
            return self._prepare_best_fit(mol)

        return self._prepare_in_orientation(mol, self.depict_orientation)

    @staticmethod
    def _set_bond_display_line_width(
        bond_display: oedepict.OE2DBondDisplay,
        line_width: float,
    ) -> None:
        """Set both pens on a bond display while preserving existing styling.

        :param bond_display: Bond display to update.
        :param line_width: New line width.
        """
        for get_pen, set_pen in (
            (bond_display.GetBgnPen, bond_display.SetBgnPen),
            (bond_display.GetEndPen, bond_display.SetEndPen),
        ):
            pen = oedepict.OEPen(get_pen())
            pen.SetLineWidth(line_width)
            set_pen(pen)

    def _scale_bond_widths_for_display(
        self,
        disp: oedepict.OE2DMolDisplay,
        *,
        baseline_scale: float,
    ) -> None:
        """Reduce bond widths when the display was shrunk below baseline scale.

        OpenEye's built-in bond-width scaling changes the default baseline pen
        too aggressively for MolGrid. This keeps unshrunk molecules visually
        consistent with single-molecule rendering and only scales pens down
        when the structure itself had to shrink to fit the grid card.

        :param disp: Molecule display to update.
        :param baseline_scale: Structure scale used when no shrink-to-fit occurs.
        """
        if not self.bond_width_scaling or baseline_scale <= 0:
            return

        scale = disp.GetScale()
        if scale >= baseline_scale:
            return

        default_width = oedepict.OE2DMolDisplayOptions().GetDefaultBondPen().GetLineWidth()
        line_width = max(1.0, default_width * (scale / baseline_scale))
        for bond_display in disp.GetBondDisplays():
            self._set_bond_display_line_width(bond_display, line_width)

    def _create_molecule_display(
        self,
        mol: oechem.OEMolBase,
        ctx: CNotebookContext | None = None,
    ) -> oedepict.OE2DMolDisplay:
        """Create a grid molecule display with MolGrid bond-width handling.

        :param mol: Prepared molecule to display.
        :param ctx: Optional render context. Defaults to this grid's context.
        :returns: Molecule display.
        """
        if ctx is None:
            ctx = self._create_render_context()

        if not ctx.auto_scale:
            # Fixed-scale mode (the grid default): replicate the context's
            # display construction but tighten the depiction margin so large
            # molecules that must shrink to fit are drawn a touch larger. The
            # context returns early without min/max handling in this mode, so
            # nothing is lost by building the display here.
            opts = ctx.display_options
            opts.SetMargins(_GRID_DEPICTION_MARGIN)
            disp = oedepict.OE2DMolDisplay(mol, opts)
        else:
            disp = ctx.create_molecule_display(mol)

        # The display keeps no reference to the molecule it was built from, so
        # hold one here to stop the prepared copy from being collected early.
        disp._cnotebook_owner = mol  # type: ignore[attr-defined]
        self._scale_bond_widths_for_display(disp, baseline_scale=self._baseline_scale)
        return disp

    def render_item(self, idx: int) -> str:
        """Render one molecule as HTML image markup.

        Results are cached until the next :meth:`set_render_options` call.

        :param idx: Molecule index.
        :returns: HTML image markup, or placeholder markup for molecules that
            cannot be depicted.
        """
        cached = self._images.get(idx)
        if cached is not None:
            self._images.move_to_end(idx)
            return cached

        ctx = self._create_render_context()
        mol = self._molecules[idx]
        render_mol = self._prepare_molecule_for_rendering(mol)
        if (
            isinstance(render_mol, oechem.OEMolBase)
            and render_mol.IsValid()
            and render_mol.NumAtoms() > 0
            and (
                ctx.max_heavy_atoms is None
                or oechem.OECount(render_mol, oechem.OEIsHeavy()) <= ctx.max_heavy_atoms
            )
        ):
            image_html = oedisp_to_html(self._create_molecule_display(render_mol, ctx), ctx=ctx)
        elif isinstance(mol, oechem.OEMolBase):
            image_html = oemol_to_html(mol, ctx=ctx)
        else:
            image_html = oemol_to_html(oechem.OEGraphMol(), ctx=ctx)

        self._images[idx] = image_html
        while len(self._images) > _MAX_CACHE:
            self._images.popitem(last=False)
        return image_html

    def render_indices(self, indices: Iterable[int]) -> dict[str, str]:
        """Render the given molecules.

        :param indices: Molecule indices; out-of-range entries are ignored.
        :returns: Mapping of ``"<index>"`` to HTML image markup.
        """
        return {
            str(i): self.render_item(int(i))
            for i in indices
            if 0 <= int(i) < len(self._molecules)
        }

    def search_smarts(self, pattern: str) -> tuple[list[int], str | None]:
        """Find molecules matching a SMARTS pattern.

        Query molecules are skipped: matching one pattern against another is not
        something OEChem supports, and its stub for it aborts the whole process.

        :param pattern: SMARTS pattern.
        :returns: ``(matching indices, error message)``; the error is ``None``
            for a valid pattern and the indices are empty for an invalid one.
        """
        query = oechem.OESubSearch()
        if not query.Init(pattern):
            return [], f"Invalid SMARTS pattern: {pattern}"

        matches: list[int] = []
        for idx, mol in enumerate(self._molecules):
            if (
                isinstance(mol, oechem.OEMolBase)
                and not isinstance(mol, oechem.OEQMolBase)
                and mol.IsValid()
            ):
                probe = _search_copy(mol)
                oechem.OEPrepareSearch(probe, query)
                if query.SingleMatch(probe):
                    matches.append(idx)
        return matches, None

    def set_render_options(
        self,
        *,
        width=_RENDER_OPTION_UNSET,
        height=_RENDER_OPTION_UNSET,
        min_width=_RENDER_OPTION_UNSET,
        min_height=_RENDER_OPTION_UNSET,
        max_width=_RENDER_OPTION_UNSET,
        max_height=_RENDER_OPTION_UNSET,
        structure_scale=_RENDER_OPTION_UNSET,
        auto_scale=_RENDER_OPTION_UNSET,
        atom_label_font_scale=_RENDER_OPTION_UNSET,
        title_font_scale=_RENDER_OPTION_UNSET,
        image_format=_RENDER_OPTION_UNSET,
        bond_width_scaling=_RENDER_OPTION_UNSET,
        title=_RENDER_OPTION_UNSET,
        depict_orientation=_RENDER_OPTION_UNSET,
        max_heavy_atoms=_RENDER_OPTION_UNSET,
        device_pixel_ratio=_RENDER_OPTION_UNSET,
    ) -> None:
        """Set rendering options for molecules in this grid.

        These options mirror the molecule render settings used by the dataframe
        chemistry accessors. The ``title`` option controls titles drawn inside
        molecule images; grid card labels remain controlled by the MolGrid
        ``title`` constructor argument. Applying any option clears the rendered
        images, increments :attr:`revision` and, when a live widget exists,
        publishes the new revision to it.

        :param width: Image width in pixels. If 0, determined by structure scale.
        :param height: Image height in pixels. If 0, determined by structure scale.
        :param min_width: Minimum image width in pixels.
        :param min_height: Minimum image height in pixels.
        :param max_width: Maximum image width in pixels, or None for no limit.
        :param max_height: Maximum image height in pixels, or None for no limit.
        :param structure_scale: Scale factor applied to OpenEye's default
            structure scale. Ignored when ``auto_scale`` is ``True``.
        :param auto_scale: When ``True``, size structures to fill each grid card
            (OpenEye AutoScale) instead of using ``structure_scale``.
        :param atom_label_font_scale: Scale factor for atom labels.
        :param title_font_scale: Scale factor for title font.
        :param image_format: Output image format, such as ``"png"`` or ``"svg"``.
        :param bond_width_scaling: Whether to scale bond widths with structure scale.
        :param title: Whether to display molecule titles inside rendered images.
        :param depict_orientation: Preferred 2D depiction orientation for grid
            renderings, or :data:`BEST_FIT_ORIENTATION` to pick per molecule.
        :param max_heavy_atoms: Maximum heavy atom count to render, or None to disable.
        :param device_pixel_ratio: Raster oversampling factor for PNG output.
        :raises ValueError: If an option value is rejected by the render context.
        """
        options = _collect_render_options(
            width=width,
            height=height,
            min_width=min_width,
            min_height=min_height,
            max_width=max_width,
            max_height=max_height,
            structure_scale=structure_scale,
            auto_scale=auto_scale,
            atom_label_font_scale=atom_label_font_scale,
            title_font_scale=title_font_scale,
            image_format=image_format,
            bond_width_scaling=bond_width_scaling,
            title=title,
            depict_orientation=depict_orientation,
            max_heavy_atoms=max_heavy_atoms,
            device_pixel_ratio=device_pixel_ratio,
        )
        if not options:
            return

        if "title" in options:
            options["render_title"] = options.pop("title")

        # Building a candidate context validates the new values through its
        # setters before anything is committed, so a rejected value leaves the
        # grid's attributes, cached images and revision untouched.
        self._create_render_context(options)

        for name, value in options.items():
            setattr(self, name, value)

        self._images.clear()
        self.revision += 1
        if self._widget is not None:
            self._push_revision()

    def close(self) -> None:
        """Release the front end and drop cached images."""
        if self._widget is not None:
            try:
                self._widget.close()
            finally:
                self._widget = None
        self._images.clear()
        self.closed = True

    # -- raw-value helpers ------------------------------------------------------
    # The front end is handed stringified fields, but callers that work in Python --
    # and the tests -- need the values as they come out of the frame or the molecule.
    # These return them untouched.

    def _get_field_value(self, idx: int, mol, field: str):
        """Get a field value from a DataFrame column or a molecule property.

        :param idx: Row index in the dataframe.
        :param mol: OpenEye molecule object.
        :param field: Field name to retrieve.
        :returns: Raw field value, or None.
        """
        return self._field_value(idx, mol, field)

    def _search_smarts(self, smarts_pattern: str) -> list[int]:
        """Search molecules by SMARTS pattern.

        :param smarts_pattern: SMARTS pattern string.
        :returns: List of indices of matching molecules (empty when invalid).
        """
        return self.search_smarts(smarts_pattern)[0]

    def _prepare_data(self) -> list[dict[str, Any]]:
        """Prepare molecule data with raw field values.

        :returns: List of dicts with molecule data for each item.
        """
        data: list[dict[str, Any]] = []
        labels = self.cluster_labels()

        for idx, mol in enumerate(self._molecules):
            valid = isinstance(mol, oechem.OEMolBase) and mol.IsValid()
            item: dict[str, Any] = {
                "index": idx,
                "title": None,
                "mol_title": mol.GetTitle() if valid else None,
                "tooltip": {},
                "smiles": oechem.OEMolToSmiles(mol) if valid else "",
                "img": self.render_item(idx),
            }

            if self.title is True:
                item["title"] = mol.GetTitle() if valid else None
            elif self.title:
                item["title"] = self._field_value(idx, mol, self.title)

            for field in self.tooltip_fields:
                item["tooltip"][field] = self._field_value(idx, mol, field)

            item["search_fields"] = {
                field: self._field_value(idx, mol, field) for field in self.search_fields
            }
            item["info_fields"] = {
                field: self._field_value(idx, mol, field) for field in self.information_fields
            }

            if labels is not None:
                item["cluster"] = labels[idx]

            data.append(item)

        return data

    def _prepare_export_data(self) -> list[dict]:
        """Prepare molecule data for CSV/SMILES export.

        :returns: List of dicts with all exportable data for each molecule.
        """
        columns = self._frame_columns()
        export_data = []
        for item in self.items():
            row: dict[str, Any] = {"index": item["i"], "smiles": item["smiles"]}
            for col in columns:
                row[col] = item["fields"].get(col, "")
            export_data.append(row)
        return export_data

    # -- widget ---------------------------------------------------------------

    def _initial_indices(self) -> list[int]:
        """Molecule indices to render before the front end has asked for anything.

        The first page and the one after it: the grid appears filled immediately and
        the first page turn needs no round trip, while a grid of thousands of molecules
        still renders only what is about to be looked at.

        :returns: Indices of the first two pages.
        """
        return list(range(min(len(self._molecules), 2 * int(self.n_items_per_page))))

    def _push_revision(self) -> None:
        """Publish a new render revision to the live widget.

        The empty ``images`` goes out first, so no view keeps a depiction drawn with the
        previous options, and the window each view last reported is then rendered from
        here: a view that has not scrolled republishes the same ``visible``, and
        traitlets delivers no notification for a value that has not changed.
        """
        widget = self._widget
        widget.images = {}
        widget.revision = self.revision
        widget.config = self.widget_config(static=False)
        if widget.visible:
            widget.images = self.render_indices(widget.visible)

    @property
    def widget(self) -> Any:
        """The live widget for this grid, created on first access and cached.

        The widget module is imported here rather than at the top of this one, so a
        grid that is only ever exported or displayed statically never needs anywidget.

        :returns: The :class:`~cnotebook.grid.widget.MolGridWidget` backing this grid.
        :raises ImportError: If anywidget is not installed.
        """
        if self._widget is None:
            from cnotebook.grid.widget import MolGridWidget

            widget = MolGridWidget(
                items=self.items(),
                config=self.widget_config(static=False),
                revision=self.revision,
                images=self.render_indices(self._initial_indices()),
                selection=list(self.selection),
            )
            # These observers hold the grid, deliberately. Images, searches and the
            # selection are all answered on this side, so a widget whose grid had been
            # collected would render nothing and answer nothing; and the grid is
            # frequently nameless, as in ``display(df.chem.molgrid())``. The pair is
            # released by :meth:`close`, which closes the widget and drops it from
            # ipywidgets' registry of open widgets.
            grid = self

            def on_visible(change: dict[str, Any]) -> None:
                missing = [i for i in change["new"] if str(i) not in widget.images]
                if not missing:
                    return
                try:
                    rendered = grid.render_indices(missing)
                except Exception as exc:
                    # A depiction failure is the user's to see: without this the front
                    # end would sit on a page of permanently blank cards.
                    log.exception("cnotebook: MolGrid could not render %s", missing)
                    widget.error = f"Could not render molecules: {exc}"
                    return
                widget.error = ""
                # A new mapping: traitlets compares containers, and images appended to
                # the one the widget already holds would never reach the browser.
                widget.images = {**widget.images, **rendered}

            def on_smarts(change: dict[str, Any]) -> None:
                request = _smarts_request(change["new"])
                if request is None:
                    log.debug(
                        "cnotebook: MolGrid ignoring malformed SMARTS request %r",
                        change["new"],
                    )
                    return
                seq, query, view = request
                matches, error = grid.search_smarts(query)
                # The view token is echoed verbatim: one widget can be shown in several
                # cells, and each view must recognize the answer to its own question.
                widget.smarts_result = {
                    "seq": seq,
                    "view": view,
                    "matches": matches,
                    "error": error,
                }

            def on_selection(change: dict[str, Any]) -> None:
                grid.selection = sorted(int(i) for i in change["new"])

            widget.observe(_safe_observer(on_visible), names=["visible"])
            widget.observe(_safe_observer(on_smarts), names=["smarts_request"])
            widget.observe(_safe_observer(on_selection), names=["selection"])
            self._widget = widget
        return self._widget

    # -- display --------------------------------------------------------------

    def to_html(self) -> str:
        """Render the grid as a self-contained HTML document.

        Every image is embedded, along with the front-end module and the stylesheet, so
        the document works from a file, an email attachment or a static web server with
        no kernel to ask and nothing to fetch.

        :returns: A complete HTML document.
        """
        if len(self._molecules) > self.static_max_items:
            warn(
                f"MolGrid.to_html() is embedding {len(self._molecules)} molecules, above "
                f"static_max_items={self.static_max_items}; the document will be large. "
                "Use display() for the live widget or raise static_max_items."
            )
        # Imported here because the viewer module reads the bundled 3Dmol assets when it
        # is imported, which a grid export has no use for.
        from cnotebook.core.viewer3d import escape_script_json

        payload = {
            "items": self.items(),
            "config": self.widget_config(static=True),
            # A saved document has no kernel to ask for more, so it carries every image.
            "images": self.render_indices(range(len(self._molecules))),
            "selection": list(self.selection),
        }
        stylesheet = _static_asset("molgrid.css")
        module = _static_asset("molgrid.js")
        return (
            '<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            "<title>MolGrid</title>\n"
            f"<style>\n{stylesheet}\n</style>\n"
            '</head>\n<body>\n<div id="molgrid-root"></div>\n'
            # The payload is escaped for a script context, so a title or a field value
            # that looks like markup cannot close the element it travels in.
            f"<script>\nwindow.__CNOTEBOOK_MOLGRID_STATIC__ = {escape_script_json(payload)};\n"
            "</script>\n"
            f'<script type="module">\n{module}\n</script>\n'
            "</body>\n</html>"
        )

    def save(self, path: str | os.PathLike[str]) -> Path:
        """Write the static document to *path*.

        The document is moved into place only once it is complete, so an interrupted
        write leaves any previous file intact. Because the move is a rename, a symbolic
        link at *path* is replaced by the document rather than followed to its target.

        :param path: Destination file; its directory must exist.
        :returns: The path written.
        :raises CNotebookError: If the destination's directory does not exist.
        """
        # Checked here as well as in the write, so a mistyped path fails before every
        # molecule in the grid has been depicted.
        target = _prepare_target(path)
        return _write_atomically(target, self.to_html().encode("utf-8"))

    def _static_display(self):
        """Build the self-contained output for the current environment.

        The document is handed over in an iframe so its stylesheet cannot reach the
        rest of the notebook, and the other way round.

        :returns: ``marimo.Html`` in marimo, otherwise an object with ``_repr_html_``.
        """
        iframe_html = (
            '<iframe class="molgrid-iframe" '
            'style="width: 100%; border: none; height: 560px;" '
            f'srcdoc="{escape(self.to_html())}"></iframe>'
        )
        if _is_marimo():
            import marimo as mo  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

            return mo.Html(iframe_html)
        return _JupyterHtml(iframe_html)

    def display(self, static: bool | None = None):
        """Display the grid in the current notebook environment.

        :param static: ``True`` for the self-contained document, ``False`` for the live
            widget, ``None`` (the default) for the display mode snapshotted when this
            grid was created. Widget mode falls back to the static output, with one
            :class:`~cnotebook.core.errors.CNotebookWarning`, when anywidget is not
            installed.
        :returns: A displayable object for the current environment: the widget itself
            in Jupyter, ``marimo.ui.anywidget(widget)`` in marimo, or an iframe wrapper.
        """
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
                "anywidget is not installed; showing the static MolGrid output "
                "instead of the live widget"
            )
            return self._static_display()
        if _is_marimo():
            import marimo as mo  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

            return mo.ui.anywidget(widget)
        return widget

    # -- selection ------------------------------------------------------------

    def get_selection_indices(self) -> list[int]:
        """Indices of the selected molecules.

        :returns: The selected indices, in ascending order.
        """
        return sorted(self.selection)

    def get_selection(self) -> list:
        """The selected molecules themselves.

        :returns: The selected molecule objects, in index order.
        """
        return [self._molecules[idx] for idx in self.get_selection_indices()]

    def selection_frame(self):
        """The selected rows of the source DataFrame.

        :returns: A frame of the same kind the grid was created from, holding the
            selected rows in index order.
        :raises CNotebookError: If the grid was not created from a DataFrame.
        """
        if self._dataframe is None:
            raise CNotebookError(
                "selection_frame() needs a grid created from a DataFrame; "
                "use get_selection() for the selected molecules"
            )
        indices = self.get_selection_indices()
        frame = self._dataframe
        if _is_pandas(frame):
            return frame.iloc[indices]
        return frame[indices]

    def get_marimo_selection(self):
        """Getter returning the current selection indices (marimo convenience).

        :returns: A callable returning the selected indices.
        :raises RuntimeError: If not running in a marimo notebook.
        """
        if not _is_marimo():
            raise RuntimeError("This method is only available in a marimo notebook.")

        return self.get_selection_indices


class _JupyterHtml:
    """Minimal ``_repr_html_`` wrapper for the static output.

    A custom class rather than ``IPython.display.HTML``, which warns when the HTML it
    is given contains an ``<iframe>``, and which the grid would otherwise have to
    import on a path that needs no IPython at all.
    """

    def __init__(self, html_text: str):
        """Wrap already-rendered HTML.

        :param html_text: Markup to hand to the notebook front end.
        """
        self._html = html_text

    def _repr_html_(self) -> str:
        """Render for the notebook.

        :returns: The wrapped markup.
        """
        return self._html

