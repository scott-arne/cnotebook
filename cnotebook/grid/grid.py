"""MolGrid class for displaying molecules in an interactive grid."""

import json
import sys
import uuid
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

import anywidget
import pandas as pd
import traitlets
from openeye import oechem

from cnotebook.context import CNotebookContext
from cnotebook.render import oemol_to_html

# Load List.js from local static file
_STATIC_DIR = Path(__file__).parent / "static"
_LIST_JS = (_STATIC_DIR / "list.min.js").read_text()

try:
    from IPython.display import HTML, display
except ModuleNotFoundError:
    pass


def _is_marimo() -> bool:
    """Check if running in marimo environment.

    Checks both if marimo is imported AND if we're in a marimo runtime.
    """
    if "marimo" not in sys.modules:
        return False
    try:
        import marimo as mo
        # Check if we're actually in a marimo runtime
        return mo.running_in_notebook()
    except (ImportError, AttributeError):
        return False


class MolGridWidget(anywidget.AnyWidget):
    """Jupyter widget for MolGrid selection synchronization.

    This widget handles communication between the MolGrid iframe and the
    Jupyter kernel for selection state and SMARTS query functionality.

    :ivar grid_id: Unique identifier for this grid instance.
    :ivar selection: JSON-encoded dictionary of selected molecule indices.
    :ivar smarts_query: Current SMARTS query string from user input.
    :ivar smarts_matches: JSON-encoded list of molecule indices matching the SMARTS query.
    """

    _esm = """
    function render({ model, el }) {
        const gridId = model.get("grid_id");
        const globalName = "_MOLGRID_" + gridId;

        // Store model globally so iframe can access it
        window[globalName] = model;

        // Listen for postMessage from iframe
        window.addEventListener("message", (event) => {
            if (event.data && event.data.gridId === gridId) {
                if (event.data.type === "MOLGRID_SELECTION") {
                    model.set("selection", JSON.stringify(event.data.selection));
                    model.save_changes();
                } else if (event.data.type === "MOLGRID_SMARTS_QUERY") {
                    model.set("smarts_query", event.data.query);
                    model.save_changes();
                }
            }
        });

        // Listen for SMARTS match results from Python
        model.on("change:smarts_matches", () => {
            const matches = model.get("smarts_matches");
            // Broadcast to iframe
            const iframe = document.querySelector("#molgrid-iframe-" + gridId);
            if (iframe && iframe.contentWindow) {
                iframe.contentWindow.postMessage({
                    type: "MOLGRID_SMARTS_RESULTS",
                    gridId: gridId,
                    matches: matches
                }, "*");
            }
        });

        // Listen for height updates from iframe
        window.addEventListener("message", (event) => {
            if (event.data && event.data.gridId === gridId && event.data.type === "MOLGRID_HEIGHT") {
                const iframe = document.querySelector("#molgrid-iframe-" + gridId);
                if (iframe) {
                    iframe.style.height = event.data.height + "px";
                }
            }
        });

    }

    export default { render };
    """

    grid_id = traitlets.Unicode("").tag(sync=True)
    selection = traitlets.Unicode("{}").tag(sync=True)
    smarts_query = traitlets.Unicode("").tag(sync=True)
    smarts_matches = traitlets.Unicode("[]").tag(sync=True)


# CSS matching backup styling
_CSS = '''
/* Base styles */
body {
    overflow-x: hidden;
    overflow-y: auto;
}

/* MolGrid Container */
.molgrid-container {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
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
    grid-template-columns: repeat(auto-fill, minmax(var(--molgrid-cell-width, 220px), 1fr));
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
'''


class MolGrid:
    """Interactive molecule grid widget for displaying and selecting molecules."""

    # Class-level selection storage
    _selections: Dict[str, Dict[int, str]] = {}

    def __init__(
        self,
        mols: Iterable,
        *,
        dataframe=None,
        mol_col: Optional[str] = None,
        title: Union[bool, str, None] = True,
        tooltip_fields: Optional[List[str]] = None,
        n_items_per_page: int = 24,
        width: int = 200,
        height: int = 200,
        atom_label_font_scale: float = 1.5,
        image_format: str = "svg",
        select: bool = True,
        information: bool = True,
        data: Optional[Union[str, List[str]]] = None,
        search_fields: Optional[List[str]] = None,
        name: Optional[str] = None,
        cluster: Optional[Union[str, Dict]] = None,
        cluster_counts: bool = True,
    ):
        """Create an interactive molecule grid widget.

        :param mols: Iterable of OpenEye molecule objects.
        :param dataframe: Optional DataFrame with molecule data.
        :param mol_col: Column name containing molecules (if using DataFrame).
        :param title: Title display mode. True uses molecule's title, a string
            specifies a field name, None/False hides titles.
        :param tooltip_fields: List of fields for tooltip display.
        :param n_items_per_page: Number of molecules per page.
        :param width: Image width in pixels.
        :param height: Image height in pixels.
        :param atom_label_font_scale: Scale factor for atom labels.
        :param image_format: Image format ("svg" or "png").
        :param select: Enable selection checkboxes.
        :param information: Enable info button with hover tooltip.
        :param data: Column(s) to display in info tooltip. If None, auto-detects
            simple types (string, int, float) from DataFrame.
        :param search_fields: Fields for text search.
        :param name: Grid identifier.
        :param cluster: Cluster filtering mode. A string specifies a DataFrame column
            name containing cluster labels. A dict maps values to display labels.
            None disables cluster filtering.
        :param cluster_counts: Show molecule count next to cluster labels in dropdown.
        """
        self._molecules = list(mols)
        self._dataframe = dataframe
        self._mol_col = mol_col
        self.title = title if title else None
        self.tooltip_fields = tooltip_fields or []
        self.n_items_per_page = n_items_per_page
        self.selection_enabled = select
        self.information_enabled = information
        self.name = name

        # Cluster filtering
        if cluster is not None:
            if isinstance(cluster, str):
                if dataframe is None:
                    raise ValueError("cluster parameter requires a DataFrame when using a column name")
                if cluster not in dataframe.columns:
                    raise ValueError(f"Column '{cluster}' not found in DataFrame")
            elif not isinstance(cluster, dict):
                raise TypeError("cluster must be a string (column name) or dict")
        self.cluster = cluster
        self.cluster_counts = cluster_counts

        # Handle data parameter for info tooltip columns
        if data is not None:
            if isinstance(data, str):
                self.information_fields = [data]
            else:
                self.information_fields = list(data)
        elif dataframe is not None:
            # Auto-detect simple type columns
            self.information_fields = self._auto_detect_info_fields(dataframe, mol_col)
        else:
            self.information_fields = []

        # Auto-detect search fields from DataFrame if not provided
        if search_fields is None and dataframe is not None:
            self.search_fields = self._auto_detect_search_fields(dataframe, mol_col)
        else:
            self.search_fields = search_fields

        # Rendering settings
        self.width = width
        self.height = height
        self.image_format = image_format
        self.atom_label_font_scale = atom_label_font_scale

        # Generate grid name
        if self.name is None:
            self.name = f"molgrid-{uuid.uuid4().hex[:8]}"

        # Initialize selection storage
        MolGrid._selections[self.name] = {}

        # Create widget
        self.widget = MolGridWidget(grid_id=self.name)

        # Observe selection changes
        self.widget.observe(self._on_selection_change, names=["selection"])

        # Observe SMARTS query changes
        self.widget.observe(self._on_smarts_query, names=["smarts_query"])

        # Display widget immediately (critical for model availability)
        # In Jupyter: display widget here so model is available when iframe loads
        # In Marimo: widget is returned from display() method instead
        if not _is_marimo():
            display(self.widget)

    def _auto_detect_search_fields(self, dataframe, mol_col: Optional[str]) -> List[str]:
        """Auto-detect searchable text columns from DataFrame.

        :param dataframe: DataFrame to inspect.
        :param mol_col: Molecule column name to exclude.
        :returns: List of searchable column names.
        """
        search_fields = []
        for col in dataframe.columns:
            # Skip the molecule column
            if col == mol_col:
                continue

            dtype = dataframe[col].dtype
            dtype_str = str(dtype).lower()

            # Skip molecule dtypes (oepandas MoleculeDtype)
            if "molecule" in dtype_str:
                continue

            # Skip numeric dtypes
            if any(t in dtype_str for t in ["int", "float", "double", "decimal"]):
                continue

            # Include string/object columns that likely contain text
            if "object" in dtype_str or "string" in dtype_str or "str" in dtype_str:
                search_fields.append(col)
                continue

            # Also check if column contains string values (fallback for edge cases)
            try:
                first_valid = dataframe[col].dropna().iloc[0] if len(dataframe[col].dropna()) > 0 else None
                if first_valid is not None and isinstance(first_valid, str):
                    search_fields.append(col)
            except (IndexError, KeyError):
                pass

        return search_fields

    def _auto_detect_info_fields(self, dataframe, mol_col: Optional[str]) -> List[str]:
        """Auto-detect simple type columns from DataFrame for info tooltip.

        Includes string, int, and float columns (excludes molecule columns).

        :param dataframe: DataFrame to inspect.
        :param mol_col: Molecule column name to exclude.
        :returns: List of column names with simple types.
        """
        info_fields = []
        for col in dataframe.columns:
            # Skip the molecule column
            if col == mol_col:
                continue

            dtype = dataframe[col].dtype
            dtype_str = str(dtype).lower()

            # Skip molecule dtypes (oepandas MoleculeDtype)
            if "molecule" in dtype_str:
                continue

            # Include numeric types (int, float)
            if any(t in dtype_str for t in ["int", "float", "double", "decimal"]):
                info_fields.append(col)
                continue

            # Include string/object columns
            if "object" in dtype_str or "string" in dtype_str or "str" in dtype_str:
                info_fields.append(col)
                continue

            # Include category dtype
            if "category" in dtype_str:
                info_fields.append(col)
                continue

        return info_fields

    def _on_selection_change(self, change):
        """Handle selection change from widget.

        :param change: Traitlet change dict with 'new' key.
        """
        try:
            selection = json.loads(change["new"])
            MolGrid._selections[self.name] = {int(k): v for k, v in selection.items()}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    def _on_smarts_query(self, change):
        """Handle SMARTS query from widget.

        Performs substructure search and sends matching indices back.

        :param change: Traitlet change dict with 'new' key.
        """
        query = change["new"]
        if not query:
            # Empty query - return all indices
            matches = list(range(len(self._molecules)))
        else:
            matches = self._search_smarts(query)

        # Send results back to widget
        self.widget.smarts_matches = json.dumps(matches)

    def _search_smarts(self, smarts_pattern: str) -> List[int]:
        """Search molecules by SMARTS pattern.

        :param smarts_pattern: SMARTS pattern string.
        :returns: List of indices of matching molecules.
        """
        matches = []
        try:
            ss = oechem.OESubSearch(smarts_pattern)
            if not ss.IsValid():
                return matches

            for idx, mol in enumerate(self._molecules):
                oechem.OEPrepareSearch(mol, ss)
                if ss.SingleMatch(mol):
                    matches.append(idx)
        except Exception:
            # Invalid SMARTS or other error - return empty
            pass

        return matches

    def _get_field_value(self, idx: int, mol, field: str):
        """Get a field value from DataFrame column or molecule property.

        :param idx: Row index in the dataframe.
        :param mol: OpenEye molecule object.
        :param field: Field name to retrieve.
        :returns: Field value or None.
        """
        # Try DataFrame column first
        if self._dataframe is not None and field in self._dataframe.columns:
            return self._dataframe.iloc[idx][field]

        # Fall back to molecule properties
        if field == "Title":
            return mol.GetTitle() or None
        else:
            return oechem.OEGetSDData(mol, field) or None

    def _prepare_data(self) -> List[dict]:
        """Prepare molecule data for template rendering.

        :returns: List of dicts with molecule data for each item.
        """
        data = []
        ctx = CNotebookContext(
            width=self.width,
            height=self.height,
            image_format=self.image_format,
            atom_label_font_scale=self.atom_label_font_scale,
            title=False,
            scope="local",
        )

        for idx, mol in enumerate(self._molecules):
            item = {
                "index": idx,
                "title": None,
                "mol_title": mol.GetTitle() if mol.IsValid() else None,
                "tooltip": {},
                "smiles": oechem.OEMolToSmiles(mol) if mol.IsValid() else "",
                "img": oemol_to_html(mol, ctx=ctx),
            }

            # Extract title
            if self.title is True:
                # Use molecule's built-in title
                item["title"] = mol.GetTitle() if mol.IsValid() else None
            elif self.title:
                # Use specified field name
                item["title"] = self._get_field_value(idx, mol, self.title)

            # Extract tooltip fields
            for field in self.tooltip_fields:
                item["tooltip"][field] = self._get_field_value(idx, mol, field)

            # Extract search fields
            item["search_fields"] = {}
            if self.search_fields:
                for field in self.search_fields:
                    item["search_fields"][field] = self._get_field_value(idx, mol, field)

            # Extract information fields for tooltip
            item["info_fields"] = {}
            if self.information_fields:
                for field in self.information_fields:
                    item["info_fields"][field] = self._get_field_value(idx, mol, field)

            # Extract cluster value
            if self.cluster is not None:
                if isinstance(self.cluster, str):
                    # Column name - get value from DataFrame
                    raw_value = self._dataframe.iloc[idx][self.cluster]
                    if pd.isna(raw_value):
                        item["cluster"] = "Uncategorized"
                    else:
                        item["cluster"] = str(raw_value)
                else:
                    # Dict mapping - use index to look up label
                    item["cluster"] = str(idx)  # Will be mapped in JS

            data.append(item)

        return data

    def _prepare_export_data(self) -> List[dict]:
        """Prepare molecule data for CSV/SMILES export.

        :returns: List of dicts with all exportable data for each molecule.
        """
        export_data = []

        # Determine columns to export
        if self._dataframe is not None:
            columns = [c for c in self._dataframe.columns if c != self._mol_col]
        else:
            columns = []

        for idx, mol in enumerate(self._molecules):
            row = {
                "index": idx,
                "smiles": oechem.OEMolToSmiles(mol) if mol.IsValid() else "",
            }

            # Add DataFrame columns
            if self._dataframe is not None:
                for col in columns:
                    val = self._dataframe.iloc[idx][col]
                    # Convert to string for JSON serialization
                    if val is None or (hasattr(val, '__len__') and len(str(val)) == 0):
                        row[col] = ""
                    else:
                        row[col] = str(val)

            export_data.append(row)

        return export_data

    def to_html(self) -> str:
        """Generate HTML representation of the grid.

        :returns: Complete HTML document as string.
        """
        items = self._prepare_data()
        export_data = self._prepare_export_data()
        grid_id = self.name
        items_per_page = self.n_items_per_page
        total_items = len(items)

        # Prepare export data as JSON for JavaScript
        export_data_js = json.dumps(export_data)
        # Get column names for CSV header
        export_columns = ["smiles"]
        if self._dataframe is not None:
            export_columns.extend([c for c in self._dataframe.columns if c != self._mol_col])
        export_columns_js = json.dumps(export_columns)

        # Prepare cluster data for JavaScript
        cluster_data_js = "null"
        cluster_counts_js = "null"
        cluster_enabled = self.cluster is not None

        if cluster_enabled:
            # Build cluster metadata: {label: [indices], ...}
            cluster_map = {}
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
                info_rows = f'<div class="molgrid-info-tooltip-row"><span class="molgrid-info-tooltip-label">Index:</span><span class="molgrid-info-tooltip-value">{item["index"]}</span></div>'
                if item.get("mol_title"):
                    info_rows += f'<div class="molgrid-info-tooltip-row"><span class="molgrid-info-tooltip-label">Title:</span><span class="molgrid-info-tooltip-value">{escape(str(item["mol_title"]))}</span></div>'
                # Add data fields from info_fields
                for field, value in item.get("info_fields", {}).items():
                    if value is not None:
                        display_value = escape(str(value))
                        info_rows += f'<div class="molgrid-info-tooltip-row"><span class="molgrid-info-tooltip-label">{escape(field)}:</span><span class="molgrid-info-tooltip-value">{display_value}</span></div>'
                info_html = f'''<button class="molgrid-info-btn" type="button">i</button>
                <div class="molgrid-info-tooltip">{info_rows}</div>'''

            tooltip_attr = f'title="{tooltip_str}"' if tooltip_str else ""

            # Build data-cluster attribute if enabled
            cluster_attr = ""
            if cluster_enabled and "cluster" in item:
                cluster_attr = f'data-cluster="{escape(str(item["cluster"]))}"'

            # Build hidden spans for search fields
            search_fields_html = ""
            for field, value in item["search_fields"].items():
                safe_value = escape(str(value)) if value else ""
                search_fields_html += f'<span class="{escape(field)}" style="display:none;">{safe_value}</span>\n                '

            # Keep data-smiles on cell element (critical for selection to work)
            # Add hidden spans for List.js valueNames (index, smiles, title, search fields)
            items_html += f'''
            <li class="molgrid-cell" data-index="{item["index"]}" data-smiles="{escape(item["smiles"])}" {cluster_attr} {tooltip_attr}>
                {checkbox_html}
                {info_html}
                <div class="molgrid-image">{item["img"]}</div>
                {title_display_html}
                <span class="title" style="display:none;">{title_value}</span>
                <span class="index" style="display:none;">{item["index"]}</span>
                <span class="smiles" style="display:none;">{escape(item["smiles"])}</span>
                {search_fields_html}
            </li>
            '''

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

    // Apply SMARTS filter based on matching indices
    function applySmartsFilter(matchIndices) {{
        smartsMatchIndices = new Set(matchIndices);
        molgridList.filter(function(item) {{
            var idx = parseInt(item.values().index, 10);
            return smartsMatchIndices.has(idx);
        }});
        molgridList.i = 1;  // Reset to first page
        updateShowingInfo();
    }}

    // Clear SMARTS filter
    function clearSmartsFilter() {{
        smartsMatchIndices = null;
        molgridList.filter();  // Clear filter
        molgridList.i = 1;
        updateShowingInfo();
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
        if (event.data && event.data.gridId === gridId && event.data.type === "MOLGRID_SMARTS_RESULTS") {{
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

    // Get data for export (selected or all)
    function getExportRows() {{
        var indices = selectedIndices.size > 0
            ? Array.from(selectedIndices).sort(function(a, b) {{ return a - b; }})
            : getMatchingIndices();
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
                Showing <span class="showing-start">1</span>-<span class="showing-end">{min(items_per_page, total_items)}</span> of <span class="showing-total">{total_items}</span> molecules
            </div>
            <div class="molgrid-actions">
                <button class="molgrid-actions-btn" title="Actions">&#8943;</button>
                <div class="molgrid-dropdown">
                    <button class="molgrid-dropdown-item" data-action="select-all">Select All</button>
                    <button class="molgrid-dropdown-item" data-action="clear-selection">Clear Selection</button>
                    <button class="molgrid-dropdown-item" data-action="invert-selection">Invert Selection</button>
                    <div class="molgrid-dropdown-divider"></div>
                    <button class="molgrid-dropdown-item" data-action="copy-clipboard">Copy to Clipboard</button>
                    <button class="molgrid-dropdown-item" data-action="save-smiles">Save to SMILES</button>
                    <button class="molgrid-dropdown-item" data-action="save-csv">Save to CSV</button>
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

    def get_selection(self) -> List:
        """Get list of selected molecules.

        :returns: List of selected OEMol objects.
        """
        selection = MolGrid._selections.get(self.name, {})
        return [self._molecules[idx] for idx in sorted(selection.keys())]

    def get_selection_indices(self) -> List[int]:
        """Get indices of selected molecules.

        :returns: List of selected indices.
        """
        return sorted(MolGrid._selections.get(self.name, {}).keys())

    def display(self):
        """Display the grid in the notebook.

        Automatically detects Jupyter vs Marimo environment.
        Note: The widget was already displayed in __init__ to ensure
        the anywidget model is available when the iframe loads.

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
            import marimo as mo
            return mo.vstack([self.widget, mo.Html(iframe_html)])
        else:
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
            return list(MolGrid._selections.get(self.name, {}).keys())

        return get_state
