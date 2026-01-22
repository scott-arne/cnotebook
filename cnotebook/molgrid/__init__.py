"""Interactive molecule grid for Jupyter and Marimo notebooks."""

from cnotebook.molgrid.grid import MolGrid
from typing import Iterable, Optional, List


def molgrid(
    mols: Iterable,
    *,
    title_field: Optional[str] = "Title",
    tooltip_fields: Optional[List[str]] = None,
    n_items_per_page: int = 24,
    width: Optional[int] = None,
    height: Optional[int] = None,
    image_format: Optional[str] = None,
    selection: bool = True,
    search_fields: Optional[List[str]] = None,
    name: Optional[str] = None,
) -> MolGrid:
    """Create an interactive molecule grid.

    :param mols: Iterable of OpenEye molecule objects.
    :param title_field: Molecule field for title (None to hide).
    :param tooltip_fields: List of fields for tooltip.
    :param n_items_per_page: Molecules per page.
    :param width: Image width in pixels.
    :param height: Image height in pixels.
    :param image_format: "svg" or "png".
    :param selection: Enable selection checkboxes.
    :param search_fields: Fields for text search.
    :param name: Grid identifier.
    :returns: MolGrid instance.
    """
    return MolGrid(
        mols,
        title_field=title_field,
        tooltip_fields=tooltip_fields,
        n_items_per_page=n_items_per_page,
        width=width,
        height=height,
        image_format=image_format,
        selection=selection,
        search_fields=search_fields,
        name=name,
    )


__all__ = ["MolGrid", "molgrid"]
