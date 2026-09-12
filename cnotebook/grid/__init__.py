"""Interactive molecule grid for Jupyter and Marimo notebooks."""

from collections.abc import Hashable, Iterable, Mapping, Sequence

from cnotebook.config import UNSET
from cnotebook.grid.grid import (
    BEST_FIT_ORIENTATION,
    DEFAULT_ATOM_LABEL_FONT_SCALE,
    DEFAULT_STRUCTURE_SCALE,
    MolGrid,
)


def molgrid(
    mols: Iterable,
    *,
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
    sort_by: str | tuple | None = None,
    badges: Sequence[str] | None = None,
    static_max_items: int = 2000,
) -> MolGrid:
    """Create an interactive molecule grid.

    :param mols: Iterable of OpenEye molecule objects.
    :param title: Title display mode. True uses molecule's title, a string
        specifies a field name, None/False hides titles.
    :param tooltip_fields: List of fields for tooltip.
    :param n_items_per_page: Molecules per page. Defaults to the configured
        ``molgrid.n_items_per_page``.
    :param width: Image width in pixels. Defaults to the configured
        ``molgrid.width``.
    :param height: Image height in pixels. Defaults to the configured
        ``molgrid.height``.
    :param min_width: Minimum image width in pixels.
    :param min_height: Minimum image height in pixels.
    :param max_width: Maximum image width in pixels, or None for no limit.
    :param max_height: Maximum image height in pixels, or None for no limit.
    :param structure_scale: Scale factor applied to OpenEye's default structure
        scale. Defaults to the standard CNotebook molecule scale factor so grid
        depictions match single-molecule depictions when no shrink-to-fit is
        needed. Ignored when ``auto_scale`` is ``True``.
    :param auto_scale: When ``True``, size structures to fill each grid card
        (OpenEye AutoScale) instead of using ``structure_scale``.
    :param atom_label_font_scale: Scale factor for atom labels.
    :param title_font_scale: Scale factor for title font.
    :param image_format: ``"svg"`` or ``"png"``. Defaults to the configured
        ``molgrid.image_format``.
    :param bond_width_scaling: Whether MolGrid should reduce bond widths when
        a molecule is shrunk below the baseline structure scale.
    :param render_title: Whether to draw titles inside molecule images.
        Card labels remain controlled by the ``title`` parameter.
    :param depict_orientation: Preferred 2D depiction orientation for grid
        renderings. Defaults to :data:`BEST_FIT_ORIENTATION`, which prepares
        each molecule in whichever orientation renders largest in the card.
    :param max_heavy_atoms: Maximum heavy atom count to render, or None to disable.
    :param select: Enable selection checkboxes.
    :param information: Enable info button with hover tooltip.
    :param data: Column(s) to display in info tooltip. If None, auto-detects
        simple types (string, int, float) from DataFrame.
    :param search_fields: Fields for text search.
    :param name: Grid identifier.
    :param cluster: Cluster labels as a DataFrame column name, a per-molecule
        sequence of labels, or an ``{index: label}`` mapping. None disables
        cluster filtering.
    :param cluster_counts: Show molecule count next to each cluster label
        in the dropdown.
    :param theme: ``"auto"``, ``"light"`` or ``"dark"``. Defaults to the
        configured ``molgrid.theme``.
    :param sort_by: Initial sort field, or ``(field, descending)``.
    :param badges: Fields shown as chips on each card.
    :param static_max_items: Static HTML export warns above this many molecules.
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
        auto_scale=auto_scale,
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
        theme=theme,
        sort_by=sort_by,
        badges=badges,
        static_max_items=static_max_items,
    )


__all__ = ["BEST_FIT_ORIENTATION", "MolGrid", "molgrid"]
