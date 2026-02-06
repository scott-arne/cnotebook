"""Interactive molecule grid for Jupyter and Marimo notebooks."""

from cnotebook.grid.grid import MolGrid
from typing import Dict, Iterable, List, Optional, Union


def molgrid(
    mols: Iterable,
    *,
    title: Union[bool, str, None] = True,
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
    cluster: Optional[Union[str, Dict]] = None,
    cluster_counts: bool = True,
) -> MolGrid:
    """Create an interactive molecule grid.

    :param mols: Iterable of OpenEye molecule objects.
    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
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
    :param cluster: Cluster filtering mode. A string specifies a DataFrame
        column name containing cluster labels. A dict maps values to display
        labels. None disables cluster filtering.
    :param cluster_counts: Show molecule count next to each cluster label
        in the dropdown.
    :returns: MolGrid instance.
    """
    return MolGrid(
        mols,
        title=title,
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
        cluster=cluster,
        cluster_counts=cluster_counts,
    )


__all__ = ["MolGrid", "molgrid"]
