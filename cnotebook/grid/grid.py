"""MolGrid: molecule grid with a live front end and a static HTML fallback."""

from __future__ import annotations

import json
import sys
import uuid
from collections import OrderedDict
from collections.abc import Hashable, Iterable, Mapping, Sequence
from html import escape
from pathlib import Path
from typing import Any

from openeye import oechem, oedepict  # type: ignore[import-untyped]

from cnotebook import config as _config
from cnotebook.config import UNSET
from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import warn
from cnotebook.core.render import oedisp_to_html, oemol_to_html, prepare_depiction_copy

# Load List.js from local static file
_STATIC_DIR = Path(__file__).parent / "static"
_LIST_JS = (_STATIC_DIR / "list.min.js").read_text()
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


# CSS matching backup styling
_CSS = '''
/* Base styles */
body {
    overflow-x: hidden;
    overflow-y: auto;
}

/* MolGrid Container */
.molgrid-container {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
        "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    color: #333;
    max-width: 100%;
    margin: 0 auto;
    padding: 10px;
    box-sizing: border-box;
    overflow: visible;
}

/* Toolbar */
.molgrid-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px 15px;
    padding: 10px;
    margin-bottom: 15px;
    background: #f8f9fa;
    border-radius: 6px;
    border: 1px solid #e9ecef;
    overflow: visible;
    position: relative;
}

/* Responsive toolbar layout */
@media (max-width: 900px) {
    .molgrid-toolbar {
        gap: 8px 12px;
    }
    .molgrid-info {
        font-size: 12px;
    }
    .toggle-text {
        font-size: 11px;
    }
}

@media (max-width: 700px) {
    .molgrid-search {
        order: 1;
        flex-basis: 100%;
        min-width: unset;
    }
    .molgrid-info {
        order: 2;
        flex: 1;
        min-width: 0;
    }
    .molgrid-actions {
        order: 3;
        flex-shrink: 0;
    }
}

@media (max-width: 500px) {
    .molgrid-toolbar {
        gap: 6px 10px;
    }
    .molgrid-search {
        flex-direction: column;
        align-items: stretch;
        gap: 8px;
    }
    .toggle-switch {
        justify-content: center;
    }
}

/* Search */
.molgrid-search {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: 1;
    min-width: 200px;
}

.molgrid-search-input {
    flex: 1;
    padding: 8px 12px;
    border: 1px solid #ced4da;
    border-radius: 4px;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s, box-shadow 0.2s;
}

.molgrid-search-input:focus {
    border-color: #80bdff;
    box-shadow: 0 0 0 3px rgba(0, 123, 255, 0.15);
}

/* Toggle Switch */
.toggle-switch {
    display: flex;
    align-items: center;
}

.toggle-label {
    display: flex;
    align-items: center;
    cursor: pointer;
    user-select: none;
    gap: 6px;
}

.toggle-label input[type="checkbox"] {
    position: relative;
    width: 40px;
    height: 20px;
    appearance: none;
    -webkit-appearance: none;
    background: #6c757d;
    border-radius: 10px;
    cursor: pointer;
    transition: background 0.3s;
    margin: 0;
}

.toggle-label input[type="checkbox"]:checked {
    background: #007bff;
}

.toggle-label input[type="checkbox"]::before {
    content: "";
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    background: white;
    border-radius: 50%;
    transition: transform 0.3s;
}

.toggle-label input[type="checkbox"]:checked::before {
    transform: translateX(20px);
}

.toggle-text {
    font-size: 12px;
    color: #6c757d;
}

.toggle-text.active {
    color: #333;
    font-weight: 500;
}

/* Info */
.molgrid-info {
    color: #6c757d;
    font-size: 13px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex-shrink: 1;
}

/* Grid List */
.molgrid-list {
    display: grid;
    grid-template-columns: repeat(
        auto-fill, minmax(var(--molgrid-cell-width, 220px), 1fr)
    );
    gap: 12px;
    list-style: none;
    padding: 0;
    margin: 0;
    overflow: visible;
}

/* Cell */
.molgrid-cell {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px;
    background: white;
    border: 1px solid #e9ecef;
    border-radius: 6px;
    transition: border-color 0.2s, box-shadow 0.2s;
    cursor: pointer;
    overflow: hidden;
    box-sizing: border-box;
}

.molgrid-cell:hover {
    border-color: #80bdff;
    box-shadow: 0 2px 8px rgba(0, 123, 255, 0.15);
}

.molgrid-cell.selected {
    border-color: #007bff;
    background: #f0f7ff;
}

/* Checkbox */
.molgrid-checkbox {
    position: absolute;
    top: 8px;
    left: 8px;
    width: 16px;
    height: 16px;
    cursor: pointer;
    z-index: 10;
}

/* Info Button */
.molgrid-info-btn {
    position: absolute;
    top: 8px;
    right: 8px;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: #e9ecef;
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 600;
    font-style: italic;
    font-family: Georgia, "Times New Roman", serif;
    color: #6c757d;
    transition: background 0.2s, color 0.2s, transform 0.2s;
    z-index: 10;
    padding: 0;
    line-height: 1;
}

.molgrid-info-btn:hover {
    background: #007bff;
    color: white;
    transform: scale(1.1);
}

/* Info Tooltip */
.molgrid-info-tooltip {
    display: none;
    position: absolute;
    top: 30px;
    right: 8px;
    min-width: 120px;
    max-width: 220px;
    background: #212529;
    color: white;
    padding: 8px 10px;
    border-radius: 6px;
    font-size: 12px;
    z-index: 100;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.25);
}

.molgrid-info-tooltip::before {
    content: "";
    position: absolute;
    top: -6px;
    right: 12px;
    border-left: 6px solid transparent;
    border-right: 6px solid transparent;
    border-bottom: 6px solid #212529;
}

/* Show on hover OR when pinned */
.molgrid-info-btn:hover + .molgrid-info-tooltip,
.molgrid-info-tooltip.pinned {
    display: block;
}

/* Highlight button when tooltip is pinned */
.molgrid-info-btn.active {
    background: #007bff;
    color: white;
}

.molgrid-info-tooltip-row {
    display: flex;
    margin-bottom: 4px;
}

.molgrid-info-tooltip-row:last-child {
    margin-bottom: 0;
}

.molgrid-info-tooltip-label {
    font-weight: 600;
    margin-right: 6px;
    color: #adb5bd;
}

.molgrid-info-tooltip-value {
    word-break: break-word;
}

/* Image */
.molgrid-image {
    display: flex;
    justify-content: center;
    align-items: center;
    width: 100%;
    height: var(--molgrid-image-height, 150px);
    overflow: hidden;
    flex-shrink: 0;
}

.molgrid-image svg {
    max-width: 100%;
    max-height: 100%;
    width: auto !important;
    height: auto !important;
}

.molgrid-image img {
    max-width: 100%;
    max-height: 100%;
    width: auto;
    height: auto;
    object-fit: contain;
}

/* Title */
.molgrid-title {
    margin-top: 8px;
    font-size: 13px;
    font-weight: 500;
    text-align: center;
    word-break: break-word;
    color: #495057;
}

/* Pagination */
.molgrid-pagination {
    display: flex;
    justify-content: center;
    margin-top: 20px;
    padding: 10px;
}

.molgrid-pagination .pagination {
    display: flex;
    list-style: none;
    padding: 0;
    margin: 0;
    gap: 4px;
}

.molgrid-pagination .pagination li {
    display: inline-block;
}

.molgrid-pagination .pagination li a,
.molgrid-pagination .pagination li span {
    display: inline-block;
    padding: 6px 12px;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    color: #007bff;
    text-decoration: none;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
}

.molgrid-pagination .pagination li a:hover {
    background: #e9ecef;
    border-color: #dee2e6;
}

.molgrid-pagination .pagination li.active a,
.molgrid-pagination .pagination li.active span {
    background: #007bff;
    border-color: #007bff;
    color: white;
}

.molgrid-pagination .pagination li.disabled a,
.molgrid-pagination .pagination li.disabled span {
    color: #6c757d;
    cursor: not-allowed;
    background: #f8f9fa;
}

/* Prev/Next Buttons */
.molgrid-pagination-nav {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    margin-top: 20px;
    padding: 10px;
}

.molgrid-pagination-nav button {
    width: 100px;
    padding: 6px 12px;
    border: 1px solid #dee2e6;
    border-radius: 4px;
    background: white;
    color: #007bff;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
}

.molgrid-pagination-nav button:hover:not(:disabled) {
    background: #e9ecef;
    border-color: #dee2e6;
}

.molgrid-pagination-nav button:disabled {
    color: #6c757d;
    cursor: not-allowed;
    background: #f8f9fa;
}

.molgrid-pagination-nav .molgrid-pagination {
    margin-top: 0;
    padding: 0;
}

/* Actions Dropdown */
.molgrid-actions {
    position: relative;
    overflow: visible;
}

.molgrid-actions-btn {
    padding: 6px 12px;
    border: 1px solid #ced4da;
    border-radius: 4px;
    background: white;
    color: #495057;
    font-size: 16px;
    font-weight: bold;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
    line-height: 1;
}

.molgrid-actions-btn:hover {
    background: #e9ecef;
    border-color: #adb5bd;
}

.molgrid-dropdown {
    display: none;
    position: fixed;
    min-width: 180px;
    background: white;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
}

.molgrid-dropdown.show {
    display: block;
}

.molgrid-dropdown-item {
    display: block;
    width: 100%;
    padding: 10px 14px;
    border: none;
    background: none;
    text-align: left;
    font-size: 14px;
    color: #212529;
    cursor: pointer;
    transition: background 0.15s;
}

.molgrid-dropdown-item:hover {
    background: #f8f9fa;
}

.molgrid-dropdown-divider {
    height: 1px;
    margin: 4px 0;
    background: #e9ecef;
}

/* Cluster Filter Row */
.molgrid-cluster-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 10px;
    background: #f8f9fa;
    border-radius: 6px 6px 0 0;
    border: 1px solid #e9ecef;
    border-bottom: none;
}

.molgrid-cluster-row + .molgrid-toolbar {
    border-radius: 0 0 6px 6px;
    border-top: 1px solid #e9ecef;
}

/* Cluster Dropdown Button */
.molgrid-cluster-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 12px;
    border: 1px solid #ced4da;
    border-radius: 4px;
    background: white;
    color: #495057;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
    white-space: nowrap;
}

.molgrid-cluster-btn:hover {
    background: #e9ecef;
    border-color: #adb5bd;
}

.molgrid-cluster-btn svg {
    width: 12px;
    height: 12px;
    fill: currentColor;
}

/* Cluster Dropdown Menu */
.molgrid-cluster-dropdown {
    display: none;
    position: fixed;
    min-width: 200px;
    max-width: 300px;
    max-height: 300px;
    background: white;
    border: 1px solid #dee2e6;
    border-radius: 6px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    z-index: 1000;
    overflow: hidden;
}

.molgrid-cluster-dropdown.show {
    display: flex;
    flex-direction: column;
}

.molgrid-cluster-search {
    padding: 8px;
    border-bottom: 1px solid #e9ecef;
}

.molgrid-cluster-search input {
    width: 100%;
    padding: 6px 10px;
    border: 1px solid #ced4da;
    border-radius: 4px;
    font-size: 13px;
    outline: none;
    box-sizing: border-box;
}

.molgrid-cluster-search input:focus {
    border-color: #80bdff;
    box-shadow: 0 0 0 2px rgba(0, 123, 255, 0.15);
}

.molgrid-cluster-list {
    flex: 1;
    overflow-y: auto;
    max-height: 240px;
}

.molgrid-cluster-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 12px;
    cursor: pointer;
    transition: background 0.15s;
}

.molgrid-cluster-item:hover {
    background: #f8f9fa;
}

.molgrid-cluster-item.selected {
    background: #e7f1ff;
}

.molgrid-cluster-label {
    font-size: 14px;
    color: #212529;
}

.molgrid-cluster-count {
    font-size: 12px;
    color: #6c757d;
    margin-left: 8px;
}

/* Cluster Pills */
.molgrid-cluster-pills {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    align-items: center;
}

.molgrid-cluster-pill {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 8px;
    background: #e7f1ff;
    border: 1px solid #b6d4fe;
    border-radius: 16px;
    font-size: 13px;
    color: #0a58ca;
}

.molgrid-cluster-pill-remove {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border: none;
    background: transparent;
    color: #0a58ca;
    cursor: pointer;
    border-radius: 50%;
    padding: 0;
    font-size: 14px;
    line-height: 1;
    transition: background 0.15s, color 0.15s;
}

.molgrid-cluster-pill-remove:hover {
    background: #0a58ca;
    color: white;
}
'''


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
        mol_col: str | None = None,
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
        :param dataframe: Optional pandas DataFrame with per-molecule data
            (polars frames are converted by the polars accessor).
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
        self._mol_col = mol_col
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
            values = list(self._dataframe[self.cluster])
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
                present = dataframe[col].dropna()
                first_valid = present.iloc[0] if len(present) > 0 else None
                if isinstance(first_valid, str):
                    search_fields.append(name)
            except (IndexError, KeyError):
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
            return self._dataframe.iloc[idx][self._fields[field]]

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

        :param pattern: SMARTS pattern.
        :returns: ``(matching indices, error message)``; the error is ``None``
            for a valid pattern and the indices are empty for an invalid one.
        """
        query = oechem.OESubSearch()
        if not query.Init(pattern):
            return [], f"Invalid SMARTS pattern: {pattern}"

        matches: list[int] = []
        for idx, mol in enumerate(self._molecules):
            if isinstance(mol, oechem.OEMolBase) and mol.IsValid():
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
        images and increments :attr:`revision`.

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

    def close(self) -> None:
        """Release the front end and drop cached images."""
        if self._widget is not None:
            try:
                self._widget.close()
            finally:
                self._widget = None
        self._images.clear()
        self.closed = True

    # -- legacy helpers for the static template below --------------------------
    # ``to_html`` still renders through the original List.js template, which
    # needs the raw (unstringified) field values these helpers return. They go
    # away with the template when the new front end lands.

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
        """Prepare molecule data for the static template.

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

    def to_html(self) -> str:
        """Generate HTML representation of the grid.

        :returns: Complete HTML document as string.
        """
        if len(self._molecules) > self.static_max_items:
            warn(
                f"Rendering {len(self._molecules)} molecules as static HTML; "
                f"grids above {self.static_max_items} items may be slow to load. "
                "Pass static_max_items to raise the threshold."
            )

        items = self._prepare_data()
        export_data = self._prepare_export_data()
        grid_id = self.name
        items_per_page = self.n_items_per_page
        total_items = len(items)

        # Prepare export data as JSON for JavaScript
        export_data_js = json.dumps(export_data)
        # Get column names for CSV header
        export_columns = ["smiles", *self._frame_columns()]
        export_columns_js = json.dumps(export_columns)

        # Prepare cluster data for JavaScript
        cluster_data_js = "null"
        cluster_counts_js = "null"
        cluster_enabled = self.cluster is not None
        cluster_map: dict[str, list[int]] = {}

        if cluster_enabled:
            # Build cluster metadata: {label: [indices], ...}
            for item in items:
                label = item.get("cluster", "Uncategorized")
                if label not in cluster_map:
                    cluster_map[label] = []
                cluster_map[label].append(item["index"])

            cluster_data_js = json.dumps(cluster_map)

            if self.cluster_counts:
                cluster_counts = {label: len(indices) for label, indices in cluster_map.items()}
                cluster_counts_js = json.dumps(cluster_counts)

        # Build item HTML - IMPORTANT: data-smiles on cell element for working selection
        items_html = ""
        for item in items:
            tooltip_str = ""
            if item["tooltip"]:
                tooltip_parts = [f"{k}: {v}" for k, v in item["tooltip"].items() if v]
                tooltip_str = "&#10;".join(tooltip_parts)

            # Visible title display
            title_display_html = ""
            if item["title"]:
                title_display_html = f'<div class="molgrid-title">{escape(str(item["title"]))}</div>'

            # Hidden title span for List.js search (always present for consistent indexing)
            title_value = escape(str(item["title"])) if item["title"] else ""

            checkbox_html = ""
            if self.selection_enabled:
                checkbox_html = f'<input type="checkbox" class="molgrid-checkbox" data-index="{item["index"]}">'

            # Info button with tooltip
            info_html = ""
            if self.information_enabled:
                # Build tooltip content: Index always, Title if available, then data fields
                info_rows = (
                    '<div class="molgrid-info-tooltip-row">'
                    '<span class="molgrid-info-tooltip-label">Index:</span>'
                    f'<span class="molgrid-info-tooltip-value">{item["index"]}</span>'
                    '</div>'
                )
                if item.get("mol_title"):
                    mol_title_escaped = escape(str(item["mol_title"]))
                    info_rows += (
                        '<div class="molgrid-info-tooltip-row">'
                        '<span class="molgrid-info-tooltip-label">Title:</span>'
                        f'<span class="molgrid-info-tooltip-value">{mol_title_escaped}</span>'
                        '</div>'
                    )
                # Add data fields from info_fields
                for field, value in item.get("info_fields", {}).items():
                    if value is not None:
                        display_value = escape(str(value))
                        info_rows += (
                            '<div class="molgrid-info-tooltip-row">'
                            f'<span class="molgrid-info-tooltip-label">{escape(field)}:</span>'
                            f'<span class="molgrid-info-tooltip-value">{display_value}</span>'
                            '</div>'
                        )
                info_html = (
                    '<button class="molgrid-info-btn" type="button">i</button>\n'
                    f'                <div class="molgrid-info-tooltip">{info_rows}</div>'
                )

            tooltip_attr = f'title="{tooltip_str}"' if tooltip_str else ""

            # Build data-cluster attribute if enabled
            cluster_attr = ""
            if cluster_enabled and "cluster" in item:
                cluster_attr = f'data-cluster="{escape(str(item["cluster"]))}"'

            # Build hidden spans for search fields
            search_fields_html = ""
            for field, value in item["search_fields"].items():
                safe_value = escape(str(value)) if value is not None else ""
                search_fields_html += (
                    f'<span class="{escape(field)}" style="display:none;">'
                    f'{safe_value}</span>\n                '
                )

            # Keep data-smiles on cell element (critical for selection to work)
            # Add hidden spans for List.js valueNames (index, smiles, title, search fields)
            smiles_escaped = escape(item["smiles"])
            items_html += f'''
            <li class="molgrid-cell"
                data-index="{item["index"]}"
                data-smiles="{smiles_escaped}"
                {cluster_attr}
                {tooltip_attr}>
                {checkbox_html}
                {info_html}
                <div class="molgrid-image">{item["img"]}</div>
                {title_display_html}
                <span class="title" style="display:none;">{title_value}</span>
                <span class="index" style="display:none;">{item["index"]}</span>
                <span class="smiles" style="display:none;">{smiles_escaped}</span>
                {search_fields_html}
            </li>
            '''

        # Build cluster row HTML if enabled
        cluster_row_html = ""
        if cluster_enabled:
            # Get unique cluster labels sorted
            cluster_labels = sorted(cluster_map.keys())

            # Build cluster items for dropdown
            cluster_items_html = ""
            for label in cluster_labels:
                count_html = ""
                if self.cluster_counts:
                    count = len(cluster_map[label])
                    count_html = f'<span class="molgrid-cluster-count">({count})</span>'
                cluster_items_html += f'''
                <div class="molgrid-cluster-item" data-cluster="{escape(str(label))}">
                    <span class="molgrid-cluster-label">{escape(str(label))}</span>
                    {count_html}
                </div>'''

            cluster_row_html = f'''
        <div class="molgrid-cluster-row">
            <button class="molgrid-cluster-btn" type="button">
                Cluster
                <svg viewBox="0 0 12 12"><path d="M2 4l4 4 4-4z"/></svg>
            </button>
            <div class="molgrid-cluster-dropdown">
                <div class="molgrid-cluster-search">
                    <input type="text"
                           placeholder="Search clusters..."
                           class="molgrid-cluster-search-input">
                </div>
                <div class="molgrid-cluster-list">
                    {cluster_items_html}
                </div>
            </div>
            <div class="molgrid-cluster-pills"></div>
        </div>'''

        # Prepare search fields for JavaScript
        search_fields_js = json.dumps(self.search_fields or [])

        # JavaScript for selection sync with List.js pagination
        # Only include cluster variables if clustering is enabled
        cluster_vars_js = ""
        if cluster_enabled:
            cluster_vars_js = f"""
    var clusterData = {cluster_data_js};
    var clusterCounts = {cluster_counts_js};
    var clusterEnabled = true;"""
        js = f'''
(function() {{
    var gridId = "{grid_id}";
    var itemsPerPage = {items_per_page};
    var searchFields = {search_fields_js};
    var exportData = {export_data_js};
    var exportColumns = {export_columns_js};{cluster_vars_js}
    var container = document.getElementById(gridId);
    var selectedIndices = new Set();
    var searchMode = 'properties';  // 'properties' or 'smarts'

    // Initialize List.js with pagination
    var options = {{
        valueNames: ['title', 'index', 'smiles'].concat(searchFields),
        page: itemsPerPage,
        pagination: {{
            innerWindow: 1,
            outerWindow: 1,
            left: 1,
            right: 1,
            paginationClass: 'pagination',
            item: '<li><a class="page" href="javascript:void(0)"></a></li>'
        }}
    }};

    var molgridList = new List(gridId, options);

    // Prev/Next buttons
    var prevBtn = container.querySelector('.molgrid-prev');
    var nextBtn = container.querySelector('.molgrid-next');

    // Update showing info text and prev/next button states
    function updateShowingInfo() {{
        var totalItems = molgridList.matchingItems.length;
        var currentPage = molgridList.i;
        var perPage = molgridList.page;

        var start = totalItems > 0 ? currentPage : 0;
        var end = Math.min(currentPage + perPage - 1, totalItems);

        var showingStart = container.querySelector('.showing-start');
        var showingEnd = container.querySelector('.showing-end');
        var showingTotal = container.querySelector('.showing-total');

        if (showingStart) showingStart.textContent = start;
        if (showingEnd) showingEnd.textContent = end;
        if (showingTotal) showingTotal.textContent = totalItems;

        // Update prev/next button states
        var totalPages = Math.ceil(totalItems / perPage);
        var currentPageNum = Math.ceil(currentPage / perPage);

        prevBtn.disabled = currentPageNum <= 1;
        nextBtn.disabled = currentPageNum >= totalPages || totalPages <= 1;
    }}

    // Prev button click handler
    prevBtn.addEventListener('click', function() {{
        var totalItems = molgridList.matchingItems.length;
        var currentPage = molgridList.i;
        var perPage = molgridList.page;

        if (currentPage > 1) {{
            var newStart = currentPage - perPage;
            if (newStart < 1) newStart = 1;
            molgridList.show(newStart, perPage);
        }}
    }});

    // Next button click handler
    nextBtn.addEventListener('click', function() {{
        var totalItems = molgridList.matchingItems.length;
        var currentPage = molgridList.i;
        var perPage = molgridList.page;
        var totalPages = Math.ceil(totalItems / perPage);
        var currentPageNum = Math.ceil(currentPage / perPage);

        if (currentPageNum < totalPages) {{
            var newStart = currentPage + perPage;
            molgridList.show(newStart, perPage);
        }}
    }});

    // Search functionality
    var searchInput = container.querySelector('.molgrid-search-input');
    var searchModeToggle = container.querySelector('.search-mode-toggle');
    var toggleTexts = container.querySelectorAll('.toggle-text');
    var smartsMatchIndices = null;  // Store SMARTS match results

    // Debounce function for search
    function debounce(func, wait) {{
        var timeout;
        return function() {{
            var context = this;
            var args = arguments;
            clearTimeout(timeout);
            timeout = setTimeout(function() {{
                func.apply(context, args);
            }}, wait);
        }};
    }}

    // Apply combined filter (SMARTS + cluster) to the grid.
    // List.js only supports a single filter function, so both filters
    // must be combined into one call to molgridList.filter().
    function applyCombinedFilter() {{
        var hasSmarts = smartsMatchIndices !== null;
        var hasClusters = typeof selectedClusters !== 'undefined' && selectedClusters.size > 0;

        if (!hasSmarts && !hasClusters) {{
            molgridList.filter();  // Clear all filters
        }} else {{
            molgridList.filter(function(item) {{
                if (hasSmarts) {{
                    var idx = parseInt(item.values().index, 10);
                    if (!smartsMatchIndices.has(idx)) return false;
                }}
                if (hasClusters) {{
                    var clusterValue = item.elm.getAttribute('data-cluster');
                    if (!selectedClusters.has(clusterValue)) return false;
                }}
                return true;
            }});
        }}
        molgridList.i = 1;  // Reset to first page
        updateShowingInfo();
    }}

    // Apply SMARTS filter based on matching indices
    function applySmartsFilter(matchIndices) {{
        smartsMatchIndices = new Set(matchIndices);
        applyCombinedFilter();
    }}

    // Clear SMARTS filter
    function clearSmartsFilter() {{
        smartsMatchIndices = null;
        applyCombinedFilter();
    }}

    // Send SMARTS query to Python
    function sendSmartsQuery(query) {{
        window.parent.postMessage({{
            type: "MOLGRID_SMARTS_QUERY",
            gridId: gridId,
            query: query
        }}, "*");
    }}

    // Listen for SMARTS results from Python
    window.addEventListener("message", function(event) {{
        var isSmartsResult = event.data &&
            event.data.gridId === gridId &&
            event.data.type === "MOLGRID_SMARTS_RESULTS";
        if (isSmartsResult) {{
            var matches = JSON.parse(event.data.matches);
            applySmartsFilter(matches);
        }}
    }});

    // Perform search based on current mode
    function performSearch(query) {{
        if (!query) {{
            molgridList.search();  // Clear text search
            clearSmartsFilter();   // Clear SMARTS filter
        }} else if (searchMode === 'smarts') {{
            // SMARTS mode - send to Python for substructure search
            molgridList.search();  // Clear any text search
            sendSmartsQuery(query);
        }} else {{
            // Properties mode - search title and configured fields
            clearSmartsFilter();  // Clear any SMARTS filter
            var fieldsToSearch = ['title'].concat(searchFields);
            molgridList.search(query, fieldsToSearch);
            molgridList.i = 1;  // Reset to first page
            updateShowingInfo();
        }}
    }}

    // Debounced search handler
    var debouncedSearch = debounce(function(e) {{
        performSearch(e.target.value);
    }}, 300);

    searchInput.addEventListener('input', debouncedSearch);

    // Search mode toggle handler
    searchModeToggle.addEventListener('change', function() {{
        searchMode = this.checked ? 'smarts' : 'properties';

        // Update toggle text styling
        toggleTexts[0].classList.toggle('active', !this.checked);
        toggleTexts[1].classList.toggle('active', this.checked);

        // Re-trigger search with current query
        if (searchInput.value) {{
            performSearch(searchInput.value);
        }} else {{
            // Clear any existing filter when switching modes with empty query
            clearSmartsFilter();
        }}
    }});

    // Update checkboxes based on selection state (after page change)
    function updateCheckboxes() {{
        var checkboxes = container.querySelectorAll('.molgrid-checkbox');
        checkboxes.forEach(function(checkbox) {{
            var index = parseInt(checkbox.getAttribute('data-index'), 10);
            checkbox.checked = selectedIndices.has(index);
            var cell = checkbox.closest('.molgrid-cell');
            if (cell) {{
                cell.classList.toggle('selected', checkbox.checked);
            }}
        }});
    }}

    function syncSelection() {{
        var selection = {{}};
        selectedIndices.forEach(function(idx) {{
            var cell = container.querySelector('.molgrid-cell[data-index="' + idx + '"]');
            var smiles = cell ? cell.getAttribute("data-smiles") : '';
            selection[idx] = smiles;
        }});

        var globalName = "_MOLGRID_" + gridId;
        var model = window.parent[globalName];

        if (model) {{
            model.set("selection", JSON.stringify(selection));
            model.save_changes();
        }} else {{
            window.parent.postMessage({{
                type: "MOLGRID_SELECTION",
                gridId: gridId,
                selection: selection
            }}, "*");
        }}
    }}

    // Listen for List.js updates (page changes, filtering)
    molgridList.on('updated', function() {{
        updateShowingInfo();
        updateCheckboxes();
    }});

    container.addEventListener("change", function(e) {{
        if (e.target.classList.contains("molgrid-checkbox")) {{
            var index = parseInt(e.target.getAttribute("data-index"), 10);
            var cell = e.target.closest(".molgrid-cell");

            if (e.target.checked) {{
                selectedIndices.add(index);
                cell.classList.add("selected");
            }} else {{
                selectedIndices.delete(index);
                cell.classList.remove("selected");
            }}

            syncSelection();
        }}
    }});

    container.addEventListener("click", function(e) {{
        var cell = e.target.closest(".molgrid-cell");
        // Don't toggle selection when clicking checkbox, info button, or tooltip
        var isCheckbox = e.target.classList.contains("molgrid-checkbox");
        var isInfoBtn = e.target.classList.contains("molgrid-info-btn");
        var isInfoTooltip = e.target.closest(".molgrid-info-tooltip");
        if (cell && !isCheckbox && !isInfoBtn && !isInfoTooltip) {{
            var checkbox = cell.querySelector(".molgrid-checkbox");
            if (checkbox) {{
                checkbox.checked = !checkbox.checked;
                checkbox.dispatchEvent(new Event("change", {{ bubbles: true }}));
            }}
        }}
    }});

    // Prevent default on pagination links (fixes Marimo navigation issue)
    container.querySelector('.molgrid-pagination').addEventListener('click', function(e) {{
        if (e.target.tagName === 'A') {{
            e.preventDefault();
        }}
    }});

    // Send height to parent for proper iframe sizing
    function sendHeight() {{
        var height = document.body.scrollHeight;
        window.parent.postMessage({{
            type: "MOLGRID_HEIGHT",
            gridId: gridId,
            height: height
        }}, "*");
    }}

    // Initial update
    updateShowingInfo();

    // Send initial height after a short delay for rendering
    setTimeout(sendHeight, 100);

    // Also send height after List.js updates
    molgridList.on('updated', function() {{
        setTimeout(sendHeight, 50);
    }});

    // ========================================
    // Info Button Click-to-Pin
    // ========================================

    // Handle info button clicks to pin/unpin tooltips
    container.addEventListener('click', function(e) {{
        if (e.target.classList.contains('molgrid-info-btn')) {{
            e.stopPropagation();
            var btn = e.target;
            var tooltip = btn.nextElementSibling;
            if (tooltip && tooltip.classList.contains('molgrid-info-tooltip')) {{
                var isPinned = tooltip.classList.contains('pinned');
                if (isPinned) {{
                    // Unpin this tooltip
                    tooltip.classList.remove('pinned');
                    btn.classList.remove('active');
                }} else {{
                    // Pin this tooltip (don't unpin others - allow comparison)
                    tooltip.classList.add('pinned');
                    btn.classList.add('active');
                }}
            }}
        }}
    }});

    // ========================================
    // Actions Dropdown
    // ========================================

    var actionsBtn = container.querySelector('.molgrid-actions-btn');
    var dropdown = container.querySelector('.molgrid-dropdown');

    // Position and toggle dropdown
    function positionDropdown() {{
        var rect = actionsBtn.getBoundingClientRect();
        var dropdownHeight = dropdown.offsetHeight || 250;
        var viewportHeight = window.innerHeight;

        // Check if there's room below the button
        var spaceBelow = viewportHeight - rect.bottom;
        var spaceAbove = rect.top;

        if (spaceBelow >= dropdownHeight || spaceBelow >= spaceAbove) {{
            // Position below
            dropdown.style.top = rect.bottom + 4 + 'px';
            dropdown.style.bottom = 'auto';
        }} else {{
            // Position above
            dropdown.style.bottom = (viewportHeight - rect.top + 4) + 'px';
            dropdown.style.top = 'auto';
        }}
        // Always align to right edge of viewport with 10px margin
        dropdown.style.right = '10px';
        dropdown.style.left = 'auto';
    }}

    // Toggle dropdown
    actionsBtn.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isShowing = dropdown.classList.contains('show');
        if (!isShowing) {{
            positionDropdown();
        }}
        dropdown.classList.toggle('show');
    }});

    // Reposition on scroll/resize
    window.addEventListener('scroll', function() {{
        if (dropdown.classList.contains('show')) {{
            positionDropdown();
        }}
    }});

    // Close dropdown when clicking outside
    document.addEventListener('click', function(e) {{
        if (!dropdown.contains(e.target) && e.target !== actionsBtn) {{
            dropdown.classList.remove('show');
        }}
    }});

    // Get all item indices (respecting current filter)
    function getAllIndices() {{
        return molgridList.items.map(function(item) {{
            return parseInt(item.values().index, 10);
        }});
    }}

    // Get matching item indices (respecting current filter/search)
    function getMatchingIndices() {{
        return molgridList.matchingItems.map(function(item) {{
            return parseInt(item.values().index, 10);
        }});
    }}

    // Select All action
    function selectAll() {{
        var indices = getMatchingIndices();
        indices.forEach(function(idx) {{
            selectedIndices.add(idx);
        }});
        updateCheckboxes();
        syncSelection();
    }}

    // Clear Selection action
    function clearSelection() {{
        selectedIndices.clear();
        updateCheckboxes();
        syncSelection();
    }}

    // Invert Selection action
    function invertSelection() {{
        var indices = getMatchingIndices();
        indices.forEach(function(idx) {{
            if (selectedIndices.has(idx)) {{
                selectedIndices.delete(idx);
            }} else {{
                selectedIndices.add(idx);
            }}
        }});
        updateCheckboxes();
        syncSelection();
    }}

    // CSV escape helper
    function csvEscape(val) {{
        if (val === null || val === undefined) return '';
        var str = String(val);
        if (str.indexOf(',') !== -1 || str.indexOf('"') !== -1 || str.indexOf('\\n') !== -1) {{
            return '"' + str.replace(/"/g, '""') + '"';
        }}
        return str;
    }}

    // Get data for export (selected or all, respecting active filters)
    function getExportRows() {{
        var matching = getMatchingIndices();
        var indices;
        if (selectedIndices.size > 0) {{
            // Intersect selection with currently matching (filtered) items
            var matchingSet = new Set(matching);
            indices = Array.from(selectedIndices)
                .filter(function(idx) {{ return matchingSet.has(idx); }})
                .sort(function(a, b) {{ return a - b; }});
        }} else {{
            indices = matching;
        }}
        return indices.map(function(idx) {{
            return exportData[idx];
        }});
    }}

    // Generate CSV content
    function generateCSV() {{
        var rows = getExportRows();
        var lines = [];
        // Header
        lines.push(exportColumns.map(csvEscape).join(','));
        // Data rows
        rows.forEach(function(row) {{
            var values = exportColumns.map(function(col) {{
                return csvEscape(row[col] || '');
            }});
            lines.push(values.join(','));
        }});
        return lines.join('\\n');
    }}

    // Generate SMILES content
    function generateSMILES() {{
        var rows = getExportRows();
        return rows.map(function(row) {{
            return row.smiles || '';
        }}).filter(function(s) {{ return s; }}).join('\\n');
    }}

    // Copy to Clipboard action
    function copyToClipboard() {{
        var csv = generateCSV();
        navigator.clipboard.writeText(csv).then(function() {{
            // Optional: show feedback
        }}).catch(function(err) {{
            console.error('Failed to copy:', err);
        }});
    }}

    // Save file helper
    function saveFile(content, filename, mimeType) {{
        var blob = new Blob([content], {{ type: mimeType }});
        var url = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }}

    // Save to SMILES action
    function saveToSMILES() {{
        var content = generateSMILES();
        saveFile(content, 'molgrid.smi', 'chemical/x-daylight-smiles');
    }}

    // Save to CSV action
    function saveToCSV() {{
        var content = generateCSV();
        saveFile(content, 'molgrid.csv', 'text/csv');
    }}

    // Handle dropdown item clicks
    dropdown.addEventListener('click', function(e) {{
        var item = e.target.closest('.molgrid-dropdown-item');
        if (!item) return;

        var action = item.dataset.action;
        dropdown.classList.remove('show');

        switch (action) {{
            case 'select-all':
                selectAll();
                break;
            case 'clear-selection':
                clearSelection();
                break;
            case 'invert-selection':
                invertSelection();
                break;
            case 'copy-clipboard':
                copyToClipboard();
                break;
            case 'save-smiles':
                saveToSMILES();
                break;
            case 'save-csv':
                saveToCSV();
                break;
        }}
    }});

    // ========================================
    // Cluster Filtering
    // ========================================

    if (clusterEnabled) {{
        var selectedClusters = new Set();
        var clusterBtn = container.querySelector('.molgrid-cluster-btn');
        var clusterDropdown = container.querySelector('.molgrid-cluster-dropdown');
        var clusterSearchInput = container.querySelector('.molgrid-cluster-search-input');
        var clusterList = container.querySelector('.molgrid-cluster-list');
        var clusterPillsContainer = container.querySelector('.molgrid-cluster-pills');

        // Position cluster dropdown
        function positionClusterDropdown() {{
            var rect = clusterBtn.getBoundingClientRect();
            var dropdownHeight = clusterDropdown.offsetHeight || 300;
            var viewportHeight = window.innerHeight;

            var spaceBelow = viewportHeight - rect.bottom;
            if (spaceBelow >= dropdownHeight || spaceBelow >= rect.top) {{
                clusterDropdown.style.top = rect.bottom + 4 + 'px';
                clusterDropdown.style.bottom = 'auto';
            }} else {{
                clusterDropdown.style.bottom = (viewportHeight - rect.top + 4) + 'px';
                clusterDropdown.style.top = 'auto';
            }}
            clusterDropdown.style.left = rect.left + 'px';
        }}

        // Toggle cluster dropdown
        clusterBtn.addEventListener('click', function(e) {{
            e.stopPropagation();
            var isShowing = clusterDropdown.classList.contains('show');
            if (!isShowing) {{
                positionClusterDropdown();
            }}
            clusterDropdown.classList.toggle('show');
            if (!isShowing) {{
                clusterSearchInput.focus();
            }}
        }});

        // Close dropdown when clicking outside
        document.addEventListener('click', function(e) {{
            if (!clusterDropdown.contains(e.target) && e.target !== clusterBtn) {{
                clusterDropdown.classList.remove('show');
            }}
        }});

        // Reposition on scroll
        window.addEventListener('scroll', function() {{
            if (clusterDropdown.classList.contains('show')) {{
                positionClusterDropdown();
            }}
        }});

        // Filter cluster list by search
        clusterSearchInput.addEventListener('input', function(e) {{
            var query = e.target.value.toLowerCase();
            var items = clusterList.querySelectorAll('.molgrid-cluster-item');
            items.forEach(function(item) {{
                var labelEl = item.querySelector('.molgrid-cluster-label');
                var label = labelEl.textContent.toLowerCase();
                var isMatch = label.indexOf(query) !== -1;
                item.style.display = isMatch ? '' : 'none';
            }});
        }});

        // Apply cluster filter to grid (uses combined filter to preserve SMARTS)
        function applyClusterFilterToGrid() {{
            applyCombinedFilter();
        }}

        // Create a pill element
        function createPill(label) {{
            var pill = document.createElement('span');
            pill.className = 'molgrid-cluster-pill';
            pill.setAttribute('data-cluster', label);
            var labelSpan = document.createElement('span');
            labelSpan.textContent = label;
            var removeBtn = document.createElement('button');
            removeBtn.className = 'molgrid-cluster-pill-remove';
            removeBtn.type = 'button';
            removeBtn.innerHTML = '&times;';
            pill.appendChild(labelSpan);
            pill.appendChild(removeBtn);

            removeBtn.addEventListener('click', function(e) {{
                e.stopPropagation();
                removeCluster(label);
            }});

            return pill;
        }}

        // Add a cluster to selection
        function addCluster(label) {{
            if (!selectedClusters.has(label)) {{
                selectedClusters.add(label);
                clusterPillsContainer.appendChild(createPill(label));

                // Update item styling
                var escapedLabel = CSS.escape(label);
                var selector = '.molgrid-cluster-item[data-cluster="' +
                    escapedLabel + '"]';
                var item = clusterList.querySelector(selector);
                if (item) item.classList.add('selected');

                applyClusterFilterToGrid();
            }}
        }}

        // Remove a cluster from selection
        function removeCluster(label) {{
            selectedClusters.delete(label);

            // Remove pill
            var escapedLabel = CSS.escape(label);
            var pillSelector = '.molgrid-cluster-pill[data-cluster="' +
                escapedLabel + '"]';
            var pill = clusterPillsContainer.querySelector(pillSelector);
            if (pill) pill.remove();

            // Update item styling
            var itemSelector = '.molgrid-cluster-item[data-cluster="' +
                escapedLabel + '"]';
            var item = clusterList.querySelector(itemSelector);
            if (item) item.classList.remove('selected');

            applyClusterFilterToGrid();
        }}

        // Handle cluster item click
        clusterList.addEventListener('click', function(e) {{
            var item = e.target.closest('.molgrid-cluster-item');
            if (!item) return;

            var label = item.getAttribute('data-cluster');
            if (selectedClusters.has(label)) {{
                removeCluster(label);
            }} else {{
                addCluster(label);
            }}
        }});
    }}
}})();
'''

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MolGrid</title>
    <script>{_LIST_JS}</script>
    <style>
        :root {{
            --molgrid-image-width: {self.width}px;
            --molgrid-image-height: {self.height}px;
            --molgrid-cell-width: {self.width + 24}px;
        }}
{_CSS}
    </style>
</head>
<body>
    <div id="{grid_id}" class="molgrid-container">
        {cluster_row_html}
        <div class="molgrid-toolbar">
            <div class="molgrid-search">
                <input type="text" class="molgrid-search-input" placeholder="Search...">
                <div class="toggle-switch">
                    <label class="toggle-label">
                        <span class="toggle-text active">Properties</span>
                        <input type="checkbox" class="search-mode-toggle">
                        <span class="toggle-text">SMARTS</span>
                    </label>
                </div>
            </div>
            <div class="molgrid-info">
                Showing <span class="showing-start">1</span>-<span
                    class="showing-end">{min(items_per_page, total_items)}</span>
                of <span class="showing-total">{total_items}</span> molecules
            </div>
            <div class="molgrid-actions">
                <button class="molgrid-actions-btn" title="Actions">
                    &#8943;
                </button>
                <div class="molgrid-dropdown">
                    <button class="molgrid-dropdown-item"
                            data-action="select-all">Select All</button>
                    <button class="molgrid-dropdown-item"
                            data-action="clear-selection">Clear Selection</button>
                    <button class="molgrid-dropdown-item"
                            data-action="invert-selection">Invert Selection</button>
                    <div class="molgrid-dropdown-divider"></div>
                    <button class="molgrid-dropdown-item"
                            data-action="copy-clipboard">Copy to Clipboard</button>
                    <button class="molgrid-dropdown-item"
                            data-action="save-smiles">Save to SMILES</button>
                    <button class="molgrid-dropdown-item"
                            data-action="save-csv">Save to CSV</button>
                </div>
            </div>
        </div>
        <ul class="molgrid-list list">
            {items_html}
        </ul>
        <div class="molgrid-pagination-nav">
            <button class="molgrid-prev" disabled>&laquo; Previous</button>
            <div class="molgrid-pagination">
                <ul class="pagination"></ul>
            </div>
            <button class="molgrid-next">Next &raquo;</button>
        </div>
    </div>
    <script>
{js}
    </script>
</body>
</html>'''

    def get_selection(self) -> list:
        """Get list of selected molecules.

        :returns: List of selected OEMol objects.
        """
        return [self._molecules[idx] for idx in sorted(self.selection)]

    def get_selection_indices(self) -> list[int]:
        """Get indices of selected molecules.

        :returns: List of selected indices.
        """
        return sorted(self.selection)

    def display(self):
        """Display the grid in the notebook.

        Automatically detects Jupyter vs Marimo environment.

        :returns: Displayable HTML object.
        """
        html_content = self.to_html()
        iframe_id = f"molgrid-iframe-{self.name}"

        iframe_html = f'''<iframe
            id="{iframe_id}"
            class="molgrid-iframe"
            style="width: 100%; border: none; height: 500px; overflow: hidden;"
            srcdoc="{escape(html_content)}"
        ></iframe>'''

        if _is_marimo():
            import marimo as mo  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]
            return mo.Html(iframe_html)

        # Imported here so the grid module stays usable without IPython installed.
        try:
            from IPython.display import HTML
        except ModuleNotFoundError:
            return iframe_html
        return HTML(iframe_html)

    def get_marimo_selection(self):
        """Get marimo reactive state for selection.

        Only available in marimo environment.

        :returns: State getter function.
        :raises RuntimeError: If not in marimo environment.
        """
        if not _is_marimo():
            raise RuntimeError("This method is only available in a marimo notebook.")

        def get_state():
            return sorted(self.selection)

        return get_state
