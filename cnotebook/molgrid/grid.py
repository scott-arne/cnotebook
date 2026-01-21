"""MolGrid class for displaying molecules in an interactive grid."""

from typing import Iterable, Optional, List


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
        self.width = width
        self.height = height
        self.image_format = image_format
        self.selection_enabled = selection
        self.search_fields = search_fields
        self.name = name
