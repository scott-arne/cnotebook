"""Declarative vocabulary for the rendering engine.

Single source of truth for the option names, enums, and defaults shared by
cnotebook's validation and oefastapi's /capabilities endpoints.
"""

from __future__ import annotations

STYLE_PRESETS: dict[str, str] = {
    "cartoon": "cartoon",
    "stick": "stick",
    "sphere": "sphere",
    "line": "line",
    "cross": "cross",
    "surface": "surface",
}

VIEW_PRESETS: tuple[str, ...] = ("simple", "sites", "ball-and-stick")
SURFACE_TYPES: tuple[str, ...] = ("molecular", "sasa")
SURFACE_MODES: tuple[str, ...] = ("surface", "wireframe")
ISOSURFACE_REPRESENTATIONS: tuple[str, ...] = ("mesh", "surface")

MOLECULE_FORMATS: tuple[str, ...] = (
    "smiles", "sdf", "mol", "mol2", "pdb", "inchi", "oeb", "oedu",
)
BINARY_MOLECULE_FORMATS: frozenset[str] = frozenset({"oeb", "oedu"})

BINARY_MAP_FORMATS: frozenset[str] = frozenset({"ccp4", "map", "mrc"})
TEXT_MAP_FORMATS: frozenset[str] = frozenset({"cube"})
MAP_FORMATS: tuple[str, ...] = tuple(sorted(BINARY_MAP_FORMATS | TEXT_MAP_FORMATS))

IMAGE_FORMATS: tuple[str, ...] = ("png", "svg")

DEFAULTS: dict[str, object] = {
    "image_format": "png",
    "max_heavy_atoms": 100,
    "structure_scale_factor": 0.6,
    "title": True,
    "viewer_width": 800,
    "theme": "auto",
    "surface_color": "#FFFFFF",
    "surface_opacity": 0.75,
    "isosurface_color": "#0000FF",
    "isosurface_opacity": 0.75,
    "isosurface_representation": "mesh",
}
