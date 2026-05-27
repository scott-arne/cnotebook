"""Interactive molecule grid for Jupyter and Marimo notebooks."""

from cnotebook.grid.grid import DEFAULT_ATOM_LABEL_FONT_SCALE, DEFAULT_STRUCTURE_SCALE, MolGrid
from typing import Dict, Iterable, List, Optional, Union
from openeye import oedepict  # type: ignore[import-untyped]


def molgrid(
    mols: Iterable,
    *,
    title: Union[bool, str, None] = True,
    tooltip_fields: Optional[List[str]] = None,
    n_items_per_page: int = 24,
    width: int = 260,
    height: int = 240,
    min_width: Optional[float] = 260.0,
    min_height: Optional[float] = 240.0,
    max_width: Optional[float] = None,
    max_height: Optional[float] = None,
    structure_scale: float = DEFAULT_STRUCTURE_SCALE,
    atom_label_font_scale: float = DEFAULT_ATOM_LABEL_FONT_SCALE,
    title_font_scale: float = 1.0,
    image_format: str = "svg",
    bond_width_scaling: bool = True,
    render_title: bool = False,
    depict_orientation: int = oedepict.OEDepictOrientation_Default,
    max_heavy_atoms: Optional[int] = 100,
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
    :param width: Image width in pixels (default 260).
    :param height: Image height in pixels (default 240).
    :param min_width: Minimum image width in pixels.
    :param min_height: Minimum image height in pixels.
    :param max_width: Maximum image width in pixels, or None for no limit.
    :param max_height: Maximum image height in pixels, or None for no limit.
    :param structure_scale: Scale factor for structure rendering. Defaults to
        the standard CNotebook molecule scale so grid depictions match
        single-molecule depictions when no shrink-to-fit is needed.
    :param atom_label_font_scale: Scale factor for atom labels.
    :param title_font_scale: Scale factor for title font.
    :param image_format: "svg" or "png" (default "svg").
    :param bond_width_scaling: Whether MolGrid should reduce bond widths when
        a molecule is shrunk below the baseline structure scale.
    :param render_title: Whether to draw titles inside molecule images.
        Card labels remain controlled by the ``title`` parameter.
    :param depict_orientation: Preferred 2D depiction orientation for grid
        renderings.
    :param max_heavy_atoms: Maximum heavy atom count to render, or None to disable.
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
        min_width=min_width,
        min_height=min_height,
        max_width=max_width,
        max_height=max_height,
        structure_scale=structure_scale,
        atom_label_font_scale=atom_label_font_scale,
        title_font_scale=title_font_scale,
        image_format=image_format,
        bond_width_scaling=bond_width_scaling,
        render_title=render_title,
        depict_orientation=depict_orientation,
        max_heavy_atoms=max_heavy_atoms,
        select=select,
        information=information,
        data=data,
        search_fields=search_fields,
        name=name,
        cluster=cluster,
        cluster_counts=cluster_counts,
    )


__all__ = ["MolGrid", "molgrid"]
