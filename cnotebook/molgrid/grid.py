"""MolGrid class for displaying molecules in an interactive grid."""

import uuid
from pathlib import Path
from typing import Iterable, Optional, List

from jinja2 import Environment, FileSystemLoader
from openeye import oechem

from cnotebook import cnotebook_context
from cnotebook.render import oemol_to_html

# Template directory and Jinja2 environment
_template_dir = Path(__file__).parent / "templates"
_env = Environment(loader=FileSystemLoader(str(_template_dir)))


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
