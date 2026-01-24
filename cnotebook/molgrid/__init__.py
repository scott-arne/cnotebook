"""Interactive molecule grid for Jupyter and Marimo notebooks."""

from cnotebook.molgrid.grid import MolGrid
from typing import Iterable, List, Optional, Union


def molgrid(
    mols: Iterable,
    *,
    title_field: Optional[str] = "Title",
    tooltip_fields: Optional[List[str]] = None,
    n_items_per_page: int = 24,
    width: int = 200,
    height: int = 200,
    image_format: str = "svg",
    select: bool = True,
    information: bool = True,
    data: Optional[Union[str, List[str]]] = None,
    search_fields: Optional[List[str]] = None,
    name: Optional[str] = None,
) -> MolGrid:
    """Create an interactive molecule grid.

    :param mols: Iterable of OpenEye molecule objects.
    :param title_field: Molecule field for title (None to hide).
    :param tooltip_fields: List of fields for tooltip.
    :param n_items_per_page: Molecules per page.
    :param width: Image width in pixels (default 200).
    :param height: Image height in pixels (default 200).
    :param image_format: "svg" or "png" (default "svg").
    :param select: Enable selection checkboxes.
    :param information: Enable info button with hover tooltip.
    :param data: Column(s) to display in info tooltip. If None, auto-detects
        simple types (string, int, float) from DataFrame.
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
        select=select,
        information=information,
        data=data,
        search_fields=search_fields,
        name=name,
    )


__all__ = ["MolGrid", "molgrid"]
