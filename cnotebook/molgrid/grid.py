"""MolGrid class for displaying molecules in an interactive grid."""

import json
import sys
import uuid
from functools import partial
from html import escape
from pathlib import Path
from typing import Iterable, Optional, List

from jinja2 import Environment, FileSystemLoader
from openeye import oechem, oedepict

from cnotebook import cnotebook_context
from cnotebook.render import oemol_to_html
from cnotebook.molgrid.widget import MolGridWidget
from cnotebook.molgrid.select import register
from cnotebook.helpers import create_structure_highlighter

# Template directory and Jinja2 environment
_template_dir = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_template_dir)))


def _is_marimo() -> bool:
    """Check if running in marimo environment."""
    return "marimo" in sys.modules


class MolGrid:
    """Interactive molecule grid widget.

    :param mols: Iterable of OpenEye molecule objects.
    :param title_field: Molecule field to display as title (None to hide).
    :param tooltip_fields: List of fields for tooltip display.
    :param n_items_per_page: Number of molecules per page.
    :param n_cols: Number of columns (auto-calculated if None).
    :param width: Image width in pixels.
    :param height: Image height in pixels.
    :param image_format: Image format ("svg" or "png").
    :param selection: Enable selection checkboxes.
    :param search_fields: Fields for text search.
    :param name: Grid identifier.
    """

    def __init__(
        self,
        mols: Iterable,
        *,
        title_field: Optional[str] = "Title",
        tooltip_fields: Optional[List[str]] = None,
        n_items_per_page: int = 24,
        n_cols: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        image_format: Optional[str] = None,
        selection: bool = True,
        search_fields: Optional[List[str]] = None,
        name: Optional[str] = None,
    ):
        self._molecules = list(mols)
        self.title_field = title_field
        self.tooltip_fields = tooltip_fields or []
        self.n_items_per_page = n_items_per_page
        self.n_cols = n_cols
        self.selection_enabled = selection
        self.search_fields = search_fields
        self.name = name

        # Resolve rendering settings from context
        ctx = cnotebook_context.get()
        self.width = width if width is not None else ctx.width
        self.height = height if height is not None else ctx.height
        self.image_format = image_format if image_format is not None else ctx.image_format

        # Create widget
        if self.name is None:
            self.name = f"molgrid-{uuid.uuid4().hex[:8]}"
        self.widget = MolGridWidget(grid_id=self.name)

        # Observe search changes
        self.widget.observe(self._on_search_change, names=['search_query', 'search_mode'])

        # Register selection tracking
        register._init_grid(self.name)
        selection_handler = partial(register.selection_updated, self.name)
        self.widget.observe(selection_handler, names=["selection"])

    def _prepare_data(self) -> List[dict]:
        """Prepare molecule data for template rendering.

        :returns: List of dicts with molecule data for each item.
        """
        data = []
        ctx = cnotebook_context.get().copy()
        ctx.width = self.width
        ctx.height = self.height
        ctx.image_format = self.image_format

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
                if self.title_field == "Title":
                    item["title"] = mol.GetTitle() or None
                else:
                    item["title"] = oechem.OEGetSDData(mol, self.title_field) or None

            # Extract tooltip fields
            for field in self.tooltip_fields:
                if field == "Title":
                    item["tooltip"][field] = mol.GetTitle()
                else:
                    item["tooltip"][field] = oechem.OEGetSDData(mol, field)

            data.append(item)

        return data

    def to_html(self) -> str:
        """Generate HTML representation of the grid.

        :returns: Complete HTML document as string.
        """
        # Generate grid name if not set
        if not self.name:
            self.name = f"molgrid-{uuid.uuid4().hex[:8]}"

        # Prepare molecule data
        items = self._prepare_data()

        # Determine search fields
        search_fields = self.search_fields or []

        # Load CSS
        css_path = _template_dir / "css" / "styles.css"
        css = css_path.read_text()

        # Render JS template
        js_template = _env.get_template("js/main.js")
        js = js_template.render(
            grid_id=self.name,
            n_items_per_page=self.n_items_per_page,
            search_fields=search_fields,
        )

        # Render main template
        template = _env.get_template("grid.html")
        html = template.render(
            grid_id=self.name,
            items=items,
            title_field=self.title_field,
            tooltip_fields=self.tooltip_fields,
            n_items_per_page=self.n_items_per_page,
            total_count=len(items),
            selection=self.selection_enabled,
            css=css,
            js=js,
            search_fields=search_fields,
        )

        return html

    def _on_search_change(self, change):
        """Handle search query changes from JavaScript.

        :param change: Traitlet change dict.
        """
        if self.widget.search_mode == "smarts" and self.widget.search_query.strip():
            self.widget.is_searching = True
            try:
                results = self._process_smarts_search(self.widget.search_query)
                self.widget.search_results = json.dumps(results)
            finally:
                self.widget.is_searching = False

    def _render_molecule_with_highlight(self, mol, smarts_pattern: str) -> str:
        """Render molecule with SMARTS match highlighted.

        :param mol: OpenEye molecule object.
        :param smarts_pattern: SMARTS pattern to highlight.
        :returns: HTML string with highlighted molecule image.
        """
        ctx = cnotebook_context.get().copy()
        ctx.width = self.width
        ctx.height = self.height
        ctx.image_format = self.image_format

        if smarts_pattern:
            highlighter = create_structure_highlighter(
                query=smarts_pattern,
                color=oechem.OEBlueTint,
                style=oedepict.OEHighlightStyle_BallAndStick,
            )
            ctx.add_callback(highlighter)

        return oemol_to_html(mol, ctx=ctx)

    def _process_smarts_search(self, pattern: str) -> dict:
        """Process SMARTS search and return results with highlighted SVGs.

        :param pattern: SMARTS pattern to search for.
        :returns: Dict with matches and highlighted images, or error.
        """
        ss = oechem.OESubSearch(pattern)
        if not ss.IsValid():
            return {"error": f"Invalid SMARTS pattern: {pattern}"}

        results = {"matches": {}, "count": 0}

        for idx, mol in enumerate(self._molecules):
            if not mol.IsValid():
                continue

            oechem.OEPrepareSearch(mol, ss)
            if ss.SingleMatch(mol):
                results["matches"][idx] = {
                    "matched": True,
                    "img": self._render_molecule_with_highlight(mol, pattern),
                }

        results["count"] = len(results["matches"])
        return results

    def get_selection(self) -> List:
        """Get list of selected molecules.

        :returns: List of selected OEMol objects.
        """
        selection = register.get_selection(self.name)
        return [self._molecules[idx] for idx in sorted(selection.keys())]

    def get_selection_indices(self) -> List[int]:
        """Get indices of selected molecules.

        :returns: List of selected indices.
        """
        return sorted(register.get_selection(self.name).keys())

    def display(self):
        """Display the grid in the notebook.

        Automatically detects Jupyter vs Marimo environment.

        :returns: Displayable widget/HTML object.
        """
        html_content = self.to_html()

        # Create iframe wrapper
        iframe_html = f'''<iframe
            class="molgrid-iframe"
            style="width: 100%; min-height: 500px; border: none;"
            srcdoc="{escape(html_content)}"
        ></iframe>'''

        if _is_marimo():
            import marimo as mo
            return mo.vstack([self.widget, mo.Html(iframe_html)])
        else:
            from IPython.display import display, HTML
            display(self.widget)
            return HTML(iframe_html)

    def get_marimo_selection(self):
        """Get marimo reactive state for selection.

        Only available in marimo environment.

        :returns: State getter function.
        :raises RuntimeError: If not in marimo environment.
        """
        if not _is_marimo():
            raise RuntimeError("This method is only available in a marimo notebook.")

        import marimo as mo
        import ast

        get_state, set_state = mo.state([])

        def _on_change(change):
            try:
                sel = ast.literal_eval(change["new"])
                set_state(list(sel.keys()))
            except (ValueError, SyntaxError):
                pass

        if not getattr(self.widget, "_marimo_hooked", False):
            self.widget.observe(_on_change, names=["selection"])
            self.widget._marimo_hooked = True

        return get_state

    def filter(self, mask: List[bool]):
        """Filter the grid using a boolean mask.

        :param mask: Boolean list, True to show, False to hide.
        """
        self.widget.filter_mask = list(mask)

    def filter_by_index(self, indices: List[int]):
        """Filter the grid to show only specified indices.

        :param indices: List of indices to show.
        """
        indices_set = set(indices)
        mask = [i in indices_set for i in range(len(self._molecules))]
        self.filter(mask)
