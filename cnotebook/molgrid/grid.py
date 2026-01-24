"""MolGrid class for displaying molecules in an interactive grid."""

import json
import sys
import uuid
from html import escape
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import anywidget
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
    """Widget for MolGrid selection sync."""

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
/* MolGrid Container */
.molgrid-container {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    color: #333;
    max-width: 100%;
    margin: 0 auto;
    padding: 10px;
    box-sizing: border-box;
}

/* Toolbar */
.molgrid-toolbar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 15px;
    padding: 10px;
    margin-bottom: 15px;
    background: #f8f9fa;
    border-radius: 6px;
    border: 1px solid #e9ecef;
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
'''


class MolGrid:
    """Interactive molecule grid widget.

    :param mols: Iterable of OpenEye molecule objects.
    :param dataframe: Optional DataFrame with molecule data.
    :param mol_col: Column name containing molecules (if using DataFrame).
    :param title_field: Molecule field to display as title (None to hide).
    :param tooltip_fields: List of fields for tooltip display.
    :param n_items_per_page: Number of molecules per page.
    :param width: Image width in pixels.
    :param height: Image height in pixels.
    :param atom_label_font_scale: Scale factor for atom labels.
    :param image_format: Image format ("svg" or "png").
    :param select: Enable selection checkboxes.
    :param search_fields: Fields for text search.
    :param name: Grid identifier.
    """

    # Class-level selection storage
    _selections: Dict[str, Dict[int, str]] = {}

    def __init__(
        self,
        mols: Iterable,
        *,
        dataframe=None,
        mol_col: Optional[str] = None,
        title_field: Optional[str] = "Title",
        tooltip_fields: Optional[List[str]] = None,
        n_items_per_page: int = 24,
        width: int = 200,
        height: int = 200,
        atom_label_font_scale: float = 1.5,
        image_format: str = "svg",
        select: bool = True,
        search_fields: Optional[List[str]] = None,
        name: Optional[str] = None,
    ):
        self._molecules = list(mols)
        self._dataframe = dataframe
        self._mol_col = mol_col
        self.title_field = title_field
        self.tooltip_fields = tooltip_fields or []
        self.n_items_per_page = n_items_per_page
        self.selection_enabled = select
        self.name = name

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
            scope="local",
        )

        for idx, mol in enumerate(self._molecules):
            item = {
                "index": idx,
                "title": None,
                "tooltip": {},
                "smiles": oechem.OEMolToSmiles(mol) if mol.IsValid() else "",
                "img": oemol_to_html(mol, ctx=ctx),
            }

            # Extract title
            if self.title_field:
                item["title"] = self._get_field_value(idx, mol, self.title_field)

            # Extract tooltip fields
            for field in self.tooltip_fields:
                item["tooltip"][field] = self._get_field_value(idx, mol, field)

            # Extract search fields
            item["search_fields"] = {}
            if self.search_fields:
                for field in self.search_fields:
                    item["search_fields"][field] = self._get_field_value(idx, mol, field)

            data.append(item)

        return data

    def to_html(self) -> str:
        """Generate HTML representation of the grid.

        :returns: Complete HTML document as string.
        """
        items = self._prepare_data()
        grid_id = self.name
        items_per_page = self.n_items_per_page
        total_items = len(items)

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

            tooltip_attr = f'title="{tooltip_str}"' if tooltip_str else ""

            # Build hidden spans for search fields
            search_fields_html = ""
            for field, value in item["search_fields"].items():
                safe_value = escape(str(value)) if value else ""
                search_fields_html += f'<span class="{escape(field)}" style="display:none;">{safe_value}</span>\n                '

            # Keep data-smiles on cell element (critical for selection to work)
            # Add hidden spans for List.js valueNames (index, smiles, title, search fields)
            items_html += f'''
            <li class="molgrid-cell" data-index="{item["index"]}" data-smiles="{escape(item["smiles"])}" {tooltip_attr}>
                {checkbox_html}
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
        js = f'''
(function() {{
    var gridId = "{grid_id}";
    var itemsPerPage = {items_per_page};
    var searchFields = {search_fields_js};
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
        if (cell && !e.target.classList.contains("molgrid-checkbox")) {{
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
