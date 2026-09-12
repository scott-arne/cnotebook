"""Tests for the C3D 3D molecule viewer class."""

import asyncio
import base64
import json
import stat
import sys

import pytest
from openeye import oechem

from cnotebook import config as cn_config
from cnotebook.core.errors import CNotebookError, CNotebookWarning

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def ethanol_3d() -> oechem.OEMol:
    """Return an ethanol molecule with Omega-generated 3D coordinates."""
    from openeye import oeomega

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("ethanol")

    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    omega.SetStrictStereo(False)
    omega(mol)
    return mol


# ---------------------------------------------------------------------------
# TestC3DImport
# ---------------------------------------------------------------------------


class TestC3DImport:
    """Verify that C3D can be imported from the submodule."""

    def test_all_exports(self):
        """The submodule export should point at the viewer class."""
        import cnotebook.c3d
        from cnotebook.c3d.c3d import C3D as C3DClass

        assert "C3D" in cnotebook.c3d.__all__
        assert cnotebook.c3d.C3D is C3DClass


# ---------------------------------------------------------------------------
# TestC3DConstructor
# ---------------------------------------------------------------------------


class TestC3DConstructor:
    """Verify C3D constructor defaults and custom dimensions."""

    def test_default_dimensions(self):
        """Default width should be 800 and height should be auto (None)."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._width == 800
        assert viewer._height is None

    def test_custom_dimensions(self):
        """Custom width and height should be stored."""
        from cnotebook.c3d import C3D

        viewer = C3D(width=1024, height=768)
        assert viewer._width == 1024
        assert viewer._height == 768

    def test_effective_height_small_molecule(self, ethanol_3d):
        """Small molecules (<=1000 atoms) should default to 300px height."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        assert viewer._effective_height == 300

    def test_effective_height_small_molecule_with_console(self, ethanol_3d):
        """Small molecules with the console visible should get more vertical room."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_ui(sidebar=True, menubar=True, console=True)
        assert viewer._effective_height == 500

    def test_effective_height_explicit_overrides(self, ethanol_3d):
        """Explicit height should override the auto-computed value."""
        from cnotebook.c3d import C3D

        viewer = C3D(height=500)
        viewer.add_molecule(ethanol_3d)
        assert viewer._effective_height == 500

    def test_empty_molecules_list(self):
        """A new viewer should start with no molecules."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._molecules == []

    def test_empty_operations_list(self):
        """A new viewer should start with no operations."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._operations == []

    def test_default_ui_config(self):
        """Default UI config should enable all panels."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._ui == {
            "sidebar": True,
            "menubar": True,
            "console": True,
        }

    def test_default_background_is_none(self):
        """Default background should be None."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._background is None

    def test_default_zoom_to_is_none(self):
        """Default zoom target should be None."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._zoom_to is None

    def test_constructor_theme_parameter(self):
        """Constructor should accept theme parameter."""
        from cnotebook.c3d import C3D

        viewer = C3D(theme="dark")
        assert viewer._theme == "dark"

    def test_constructor_theme_default_auto(self):
        """Constructor should default theme to 'auto'."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._theme == "auto"

    def test_constructor_theme_rejects_invalid(self):
        """Constructor should raise ValueError for invalid theme."""
        from cnotebook.c3d import C3D

        with pytest.raises(ValueError, match="Unknown theme"):
            C3D(theme="blue")


# ---------------------------------------------------------------------------
# TestC3DBuilder
# ---------------------------------------------------------------------------


class TestC3DBuilder:
    """Verify builder methods return self and store data correctly."""

    def test_add_molecule_returns_self(self, ethanol_3d):
        """add_molecule should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_molecule(ethanol_3d)
        assert result is viewer

    def test_add_molecule_stores_molecule_data(self, ethanol_3d):
        """add_molecule should append a MoleculeData to _molecules."""
        from cnotebook.c3d import C3D
        from cnotebook.c3d.convert import MoleculeData

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="test_mol")
        assert len(viewer._molecules) == 1
        assert isinstance(viewer._molecules[0], MoleculeData)
        assert viewer._molecules[0].name == "test_mol"
        assert viewer._molecules[0].format == "sdf"

    def test_add_molecule_disabled_default(self, ethanol_3d):
        """add_molecule should default to disabled=False."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        assert viewer._molecules[0].disabled is False

    def test_add_molecule_disabled_true(self, ethanol_3d):
        """add_molecule with disabled=True should store the flag."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, disabled=True)
        assert viewer._molecules[0].disabled is True

    def test_add_molecule_raises_type_error(self):
        """add_molecule should raise TypeError for non-OEMolBase input."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(TypeError, match="Expected OEMolBase"):
            viewer.add_molecule("not a molecule")

    def test_add_design_unit_raises_type_error(self):
        """add_design_unit should raise TypeError for non-OEDesignUnit input."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(TypeError, match="Expected OEDesignUnit"):
            viewer.add_design_unit("not a design unit")

    def test_add_style_returns_self(self):
        """add_style should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_style("cartoon", {"chain": "A"})
        assert result is viewer

    def test_add_style_preset_mapping(self):
        """A preset name should map to a dict with the preset as key."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("cartoon", {"chain": "A"})

        assert len(viewer._operations) == 1
        entry = viewer._operations[0]
        assert entry["op"] == "style"
        assert entry["selection"] == {"chain": "A"}
        assert entry["style"] == {"cartoon": {}}

    def test_add_style_preset_with_color(self):
        """When color is given with a preset, it should appear in the spec."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("stick", {"chain": "A"}, color="red")

        entry = viewer._operations[0]
        assert entry["style"] == {"stick": {"color": "red"}}

    def test_add_style_dict_passthrough(self):
        """A dict style should be passed through verbatim."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        custom_style = {"cartoon": {"color": "spectrum"}}
        viewer.add_style(custom_style, {"resi": 42})

        entry = viewer._operations[0]
        assert entry["style"] == {"cartoon": {"color": "spectrum"}}

    def test_add_style_invalid_preset_raises_value_error(self):
        """An unrecognised preset name should raise ValueError."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown style preset"):
            viewer.add_style("ribbon")

    def test_add_style_no_selection(self):
        """add_style with no selection should store None selection."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("stick")

        assert len(viewer._operations) == 1
        entry = viewer._operations[0]
        assert entry["op"] == "style"
        assert entry["selection"] is None
        assert entry["style"] == {"stick": {}}

    def test_add_style_string_selection(self):
        """add_style with a string selection should store the string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("cartoon", "chain A")

        entry = viewer._operations[0]
        assert entry["selection"] == "chain A"
        assert entry["style"] == {"cartoon": {}}

    def test_add_style_entry_name_selection(self):
        """add_style with a molecule name should store it as a string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("sphere", "benzene")

        entry = viewer._operations[0]
        assert entry["selection"] == "benzene"

    def test_remove_style_preset_mapping(self):
        """remove_style should store a removal operation for a preset."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.remove_style("cartoon", {"chain": "A"})

        assert result is viewer
        assert len(viewer._operations) == 1
        entry = viewer._operations[0]
        assert entry["op"] == "remove_style"
        assert entry["selection"] == {"chain": "A"}
        assert entry["style"] == {"cartoon": {}}

    def test_remove_style_dict_passthrough(self):
        """remove_style should accept raw 3Dmol.js style dictionaries."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.remove_style({"stick": {}, "sphere": {}}, "ligand")

        entry = viewer._operations[0]
        assert entry["op"] == "remove_style"
        assert entry["selection"] == "ligand"
        assert entry["style"] == {"stick": {}, "sphere": {}}

    def test_remove_style_invalid_preset_raises_value_error(self):
        """remove_style should validate presets the same way add_style does."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown style preset"):
            viewer.remove_style("ribbon")

    def test_show_style_is_add_style_alias(self):
        """show_style should behave like add_style."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.show_style("stick", "chain A", color="red")

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "style",
                "selection": "chain A",
                "style": {"stick": {"color": "red"}},
            }
        ]

    def test_hide_style_is_remove_style_alias(self):
        """hide_style should behave like remove_style."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.hide_style("stick", "chain A")

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "remove_style",
                "selection": "chain A",
                "style": {"stick": {}},
            }
        ]

    def test_show_polar_hydrogens_adds_style_to_polar_hydrogen_selection(self):
        """show_polar_hydrogens should style the polar_hydrogen selection."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.show_polar_hydrogens("stick")

        assert result is viewer
        assert viewer._operations == [
            {"op": "style", "selection": "polar_hydrogen", "style": {"stick": {}}}
        ]

    def test_hide_nonpolar_hydrogens_removes_everything_by_default(self):
        """hide_nonpolar_hydrogens should clear all styles by default."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.hide_nonpolar_hydrogens()

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "remove_style",
                "selection": "nonpolar_hydrogen",
                "style": {"everything": {}},
            }
        ]

    def test_hide_nonpolar_hydrogens_removes_specific_style(self):
        """hide_nonpolar_hydrogens should remove a specific style when given."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.hide_nonpolar_hydrogens("stick")

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "remove_style",
                "selection": "nonpolar_hydrogen",
                "style": {"stick": {}},
            }
        ]

    def test_add_surface_appends_ordered_operation(self):
        """add_surface should append a scene operation."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_surface(
            "complex",
            name="complex_surface",
            type="sasa",
            color="#111111",
            opacity=0.4,
            mode="wireframe",
        )

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "add_surface",
                "selection": "complex",
                "name": "complex_surface",
                "type": "sasa",
                "color": "#111111",
                "opacity": 0.4,
                "mode": "wireframe",
            }
        ]

    def test_remove_surface_appends_ordered_operation(self):
        """remove_surface should append a delete operation."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.remove_surface("complex_surface")

        assert result is viewer
        assert viewer._operations == [
            {"op": "remove_surface", "name": "complex_surface"}
        ]

    def test_add_map_path_appends_ordered_operation(self, tmp_path):
        """add_map should convert path inputs into operation payloads."""
        from cnotebook.c3d import C3D

        path = tmp_path / "density.ccp4"
        path.write_bytes(b"\x01\x02\x03")

        viewer = C3D()
        result = viewer.add_map(path, name="density", color="#ABCDEF", opacity=0.5, show_box=True)

        assert result is viewer
        assert viewer._operations == [
            {
                "op": "add_map",
                "name": "density",
                "format": "ccp4",
                "encoding": "base64",
                "data": "AQID",
                "color": "#ABCDEF",
                "opacity": 0.5,
                "showBoundingBox": True,
            }
        ]

    def test_remove_map_appends_ordered_operation(self):
        """remove_map should append a delete operation."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.remove_map("density")

        assert result is viewer
        assert viewer._operations == [{"op": "remove_map", "name": "density"}]

    def test_add_isosurface_appends_ordered_operation(self, tmp_path):
        """add_isosurface should target a previously added map."""
        from cnotebook.c3d import C3D

        path = tmp_path / "density.ccp4"
        path.write_bytes(b"\x01\x02\x03")

        viewer = C3D()
        viewer.add_map(path, name="density")
        result = viewer.add_isosurface(
            "density",
            name="mesh",
            level=None,
            selection="ligand",
            buffer=2.0,
            carve=1.0,
            representation="surface",
            color="#123456",
            opacity=0.25,
        )

        assert result is viewer
        assert viewer._operations[-1] == {
            "op": "add_isosurface",
            "mapName": "density",
            "name": "mesh",
            "level": None,
            "selection": "ligand",
            "buffer": 2.0,
            "carve": 1.0,
            "representation": "surface",
            "color": "#123456",
            "opacity": 0.25,
        }

    def test_remove_isosurface_appends_ordered_operation(self):
        """remove_isosurface should append a delete operation."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.remove_isosurface("mesh")

        assert result is viewer
        assert viewer._operations == [{"op": "remove_isosurface", "name": "mesh"}]

    def test_add_surface_rejects_unknown_type(self):
        """add_surface should validate surface type."""
        from cnotebook.c3d import C3D

        with pytest.raises(ValueError, match="Unknown surface type"):
            C3D().add_surface("complex", type="mesh")

    def test_add_surface_rejects_unknown_mode(self):
        """add_surface should validate surface mode."""
        from cnotebook.c3d import C3D

        with pytest.raises(ValueError, match="Unknown surface mode"):
            C3D().add_surface("complex", mode="solid")

    def test_add_isosurface_rejects_unknown_map(self):
        """add_isosurface should validate active map names."""
        from cnotebook.c3d import C3D

        with pytest.raises(ValueError, match='Map "missing" has not been added'):
            C3D().add_isosurface("missing", name="mesh")

    def test_add_isosurface_rejects_unknown_representation(self, tmp_path):
        """add_isosurface should validate representation names."""
        from cnotebook.c3d import C3D

        path = tmp_path / "density.ccp4"
        path.write_bytes(b"\x01\x02\x03")

        viewer = C3D().add_map(path, name="density")
        with pytest.raises(ValueError, match="Unknown isosurface representation"):
            viewer.add_isosurface("density", name="mesh", representation="volume")

    def test_set_ui_returns_self(self):
        """set_ui should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.set_ui(sidebar=False, menubar=True, terminal=False)
        assert result is viewer

    def test_set_ui_stores_config(self):
        """set_ui should store the provided configuration."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_ui(sidebar=False, menubar=True, terminal=False)
        assert viewer._ui == {
            "sidebar": False,
            "menubar": True,
            "console": False,
        }

    def test_set_ui_accepts_console_name(self):
        """set_ui should expose console as the public command panel name."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_ui(sidebar=False, menubar=True, console=False)
        assert viewer._ui == {
            "sidebar": False,
            "menubar": True,
            "console": False,
        }

    def test_set_background_returns_self(self):
        """set_background should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.set_background("#000000")
        assert result is viewer

    def test_set_background_stores_color(self):
        """set_background should store the colour string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_background("white")
        assert viewer._background == "white"

    def test_set_theme_returns_self(self):
        """set_theme should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.set_theme("dark")
        assert result is viewer

    def test_set_theme_stores_value(self):
        """set_theme should store the theme string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_theme("dark")
        assert viewer._theme == "dark"

    def test_set_theme_raises_on_invalid(self):
        """set_theme should raise ValueError for unknown themes."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown theme"):
            viewer.set_theme("blue")

    def test_set_theme_accepts_auto(self):
        """set_theme should accept 'auto'."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_theme("auto")
        assert viewer._theme == "auto"

    def test_zoom_to_returns_self(self):
        """zoom_to should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.zoom_to({"chain": "A"})
        assert result is viewer

    def test_zoom_to_stores_selection(self):
        """zoom_to should store the selection dict."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.zoom_to({"resi": 42})
        assert viewer._zoom_to == {"resi": 42}

    def test_zoom_to_string_selection(self):
        """zoom_to should accept a string selection expression."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.zoom_to("resn 502")
        assert viewer._zoom_to == "resn 502"

    def test_zoom_to_none_for_fit_all(self):
        """zoom_to(None) should store None for fitting all molecules."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.zoom_to(None)
        assert viewer._zoom_to is None

    def test_orient_returns_self(self):
        """orient should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.orient()
        assert result is viewer

    def test_orient_default_true(self):
        """orient() with no args should store True."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.orient()
        assert viewer._orient is True

    def test_orient_with_selection_dict(self):
        """orient should accept a selection dict."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.orient({"chain": "A"})
        assert viewer._orient == {"chain": "A"}

    def test_orient_with_selection_string(self):
        """orient should accept a string selection expression."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.orient("chain A")
        assert viewer._orient == "chain A"

    def test_set_preset_returns_self(self):
        """set_preset should return self for method chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.set_preset("simple")
        assert result is viewer

    def test_set_preset_stores_name(self):
        """set_preset should store the lowercase preset name as an operation."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_preset("Sites")
        assert viewer._operations[-1] == {"op": "preset", "name": "sites"}

    def test_set_preset_all_valid_names(self):
        """All three view presets should be accepted."""
        from cnotebook.c3d import C3D

        for name in ("simple", "sites", "ball-and-stick"):
            viewer = C3D()
            viewer.set_preset(name)
            assert viewer._operations[-1] == {"op": "preset", "name": name}

    def test_set_preset_raises_on_unknown(self):
        """set_preset should raise ValueError for unknown preset names."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown view preset"):
            viewer.set_preset("nonexistent")

    def test_full_method_chaining(self, ethanol_3d):
        """All builder methods should be chainable in a single expression."""
        from cnotebook.c3d import C3D

        viewer = (
            C3D(width=1024, height=768)
            .add_molecule(ethanol_3d, name="ethanol")
            .add_style("cartoon", "chain A", color="blue")
            .add_style("stick")
            .set_ui(sidebar=False)
            .set_background("#ffffff")
            .zoom_to({"chain": "A"})
        )

        assert isinstance(viewer, C3D)
        assert len(viewer._molecules) == 1
        assert len(viewer._operations) == 2
        assert viewer._ui["sidebar"] is False
        assert viewer._background == "#ffffff"
        assert viewer._zoom_to == {"chain": "A"}


# ---------------------------------------------------------------------------
# TestC3DMapConversion
# ---------------------------------------------------------------------------


class TestC3DMapConversion:
    """Verify map conversion helpers used by C3D."""

    def test_convert_map_path_binary_ccp4(self, tmp_path):
        """Binary map paths should be base64 encoded."""
        from cnotebook.c3d.convert import convert_map

        path = tmp_path / "density.ccp4"
        path.write_bytes(b"\x01\x02\x03\x04")

        data = convert_map(path, name="2Fo-Fc")

        assert data.name == "2Fo-Fc"
        assert data.format == "ccp4"
        assert data.encoding == "base64"
        assert data.data == "AQIDBA=="

    def test_convert_map_path_text_cube(self, tmp_path):
        """Cube files should be embedded as text."""
        from cnotebook.c3d.convert import convert_map

        path = tmp_path / "density.cube"
        path.write_text("cube text\n", encoding="utf-8")

        data = convert_map(path)

        assert data.name == "density"
        assert data.format == "cube"
        assert data.encoding == "text"
        assert data.data == "cube text\n"

    def test_convert_map_missing_path_raises_file_not_found(self, tmp_path):
        """Missing map paths should fail before HTML generation."""
        from cnotebook.c3d.convert import convert_map

        with pytest.raises(FileNotFoundError):
            convert_map(tmp_path / "missing.ccp4")

    def test_convert_map_unsupported_extension_raises_value_error(self, tmp_path):
        """Unsupported map extensions should raise ValueError."""
        from cnotebook.c3d.convert import convert_map

        path = tmp_path / "density.dx"
        path.write_text("not supported", encoding="utf-8")

        with pytest.raises(ValueError, match="Unsupported map format"):
            convert_map(path)

    def test_convert_map_oescalar_grid_uses_title(self):
        """OEScalarGrid inputs should be written as embedded CCP4 data."""
        from openeye import oegrid

        from cnotebook.c3d.convert import convert_map

        grid = oegrid.OEScalarGrid()
        assert grid.SetDim(2, 2, 2)
        assert grid.SetMid(0.0, 0.0, 0.0)
        assert grid.SetSpacing(1.0)
        assert grid.SetTitle("grid-title")
        for ix in range(2):
            for iy in range(2):
                for iz in range(2):
                    grid.SetValue(ix, iy, iz, float(ix + iy + iz))

        data = convert_map(grid)

        assert data.name == "grid-title"
        assert data.format == "ccp4"
        assert data.encoding == "base64"
        assert len(data.data) > 0


# ---------------------------------------------------------------------------
# TestC3DPayload
# ---------------------------------------------------------------------------


class TestC3DPayload:
    """Verify the _build_init_payload method."""

    def test_payload_structure(self, ethanol_3d):
        """Payload should contain all required top-level keys."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert "molecules" in payload
        assert "operations" in payload
        assert "ui" in payload
        assert "theme" in payload
        assert "background" in payload
        assert "zoomTo" in payload
        assert "orient" in payload

    def test_preset_in_payload(self, ethanol_3d):
        """Payload should include preset operation when set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_preset("sites")
        payload = viewer._build_init_payload()
        assert payload["operations"][-1] == {"op": "preset", "name": "sites"}

    def test_empty_operations_default(self, ethanol_3d):
        """Payload operations should be empty when nothing is set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()
        assert payload["operations"] == []

    def test_scene_operations_are_json_serializable(self, ethanol_3d, tmp_path):
        """Surface, map, and isosurface operations should serialize cleanly."""
        from cnotebook.c3d import C3D

        path = tmp_path / "density.ccp4"
        path.write_bytes(b"\x01\x02\x03")

        viewer = (
            C3D()
            .add_molecule(ethanol_3d, name="ligand")
            .add_surface("ligand", name="ligand_surface")
            .add_map(path, name="density")
            .add_isosurface("density", name="mesh", level=None)
            .remove_surface("ligand_surface")
        )

        payload = viewer._build_init_payload()
        serialized = json.dumps(payload)
        deserialized = json.loads(serialized)

        assert deserialized["operations"][-4:] == [
            {
                "op": "add_surface",
                "selection": "ligand",
                "name": "ligand_surface",
                "type": "molecular",
                "color": "#FFFFFF",
                "opacity": 0.75,
                "mode": "surface",
            },
            {
                "op": "add_map",
                "name": "density",
                "format": "ccp4",
                "encoding": "base64",
                "data": "AQID",
                "color": "#38BDF8",
                "opacity": 1.0,
                "showBoundingBox": False,
            },
            {
                "op": "add_isosurface",
                "mapName": "density",
                "name": "mesh",
                "level": None,
                "selection": None,
                "buffer": None,
                "carve": None,
                "representation": "mesh",
                "color": "#0000FF",
                "opacity": 0.75,
            },
            {"op": "remove_surface", "name": "ligand_surface"},
        ]

    def test_ui_defaults_single_molecule(self, ethanol_3d):
        """Single molecule should default to no GUI panels."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": False,
            "menubar": False,
            "console": False,
        }

    def test_ui_defaults_two_molecules(self, ethanol_3d):
        """Two molecules should default to sidebar only."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="mol1")
        viewer.add_molecule(ethanol_3d, name="mol2")
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": True,
            "menubar": False,
            "console": False,
        }

    def test_ui_defaults_three_molecules(self, ethanol_3d):
        """Three or more molecules should default to full GUI."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="mol1")
        viewer.add_molecule(ethanol_3d, name="mol2")
        viewer.add_molecule(ethanol_3d, name="mol3")
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": True,
            "menubar": True,
            "console": True,
        }

    def test_explicit_set_ui_overrides_defaults(self, ethanol_3d):
        """Explicit set_ui should override smart defaults."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_ui(sidebar=True, menubar=True, terminal=True)
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": True,
            "menubar": True,
            "console": True,
        }

    def test_payload_is_json_serializable(self, ethanol_3d):
        """The entire payload should be serializable with json.dumps."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="ethanol")
        viewer.add_style("cartoon", "chain A", color="red")
        viewer.set_background("white")
        viewer.zoom_to({"resi": 1})
        payload = viewer._build_init_payload()

        # Should not raise
        serialized = json.dumps(payload)
        assert isinstance(serialized, str)

        # Round-trip should match
        deserialized = json.loads(serialized)
        assert deserialized == payload

    def test_molecule_entries_in_payload(self, ethanol_3d):
        """Each molecule entry should have name, data, and format keys."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="ethanol")
        payload = viewer._build_init_payload()

        assert len(payload["molecules"]) == 1
        mol_entry = payload["molecules"][0]
        assert mol_entry["name"] == "ethanol"
        assert "data" in mol_entry
        assert mol_entry["format"] == "sdf"
        assert mol_entry["disabled"] is False

    def test_disabled_molecule_in_payload(self, ethanol_3d):
        """A disabled molecule should have disabled=True in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="hidden", disabled=True)
        payload = viewer._build_init_payload()

        mol_entry = payload["molecules"][0]
        assert mol_entry["disabled"] is True

    def test_background_default_none_in_payload(self, ethanol_3d):
        """Default background should be None in payload (theme controls it)."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["background"] is None

    def test_explicit_background_in_payload(self, ethanol_3d):
        """Explicit set_background should appear in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_background("#ff0000")
        payload = viewer._build_init_payload()

        assert payload["background"] == "#ff0000"

    def test_theme_default_auto_in_payload(self, ethanol_3d):
        """Default theme should be 'auto' in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["theme"] == "auto"

    def test_theme_dark_in_payload(self, ethanol_3d):
        """set_theme('dark') should appear in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_theme("dark")
        payload = viewer._build_init_payload()

        assert payload["theme"] == "dark"

    def test_theme_auto_in_payload(self, ethanol_3d):
        """set_theme('auto') should appear in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_theme("auto")
        payload = viewer._build_init_payload()

        assert payload["theme"] == "auto"

    def test_zoom_to_default_is_none(self, ethanol_3d):
        """Default zoomTo should be None in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["zoomTo"] is None

    def test_zoom_to_string_in_payload(self, ethanol_3d):
        """String zoomTo should be passed through in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.zoom_to("resn 502")
        payload = viewer._build_init_payload()

        assert payload["zoomTo"] == "resn 502"

    def test_orient_implicit_default(self, ethanol_3d):
        """Orient should default to True when neither orient nor zoom_to is set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["orient"] is True

    def test_orient_suppressed_by_zoom_to(self, ethanol_3d):
        """Implicit orient should be None when zoom_to is set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.zoom_to({"chain": "A"})
        payload = viewer._build_init_payload()

        assert payload["orient"] is None

    def test_orient_explicit_true_in_payload(self, ethanol_3d):
        """Explicit orient() should produce True in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.orient()
        payload = viewer._build_init_payload()

        assert payload["orient"] is True

    def test_orient_selection_in_payload(self, ethanol_3d):
        """orient with a selection should pass it through in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.orient({"chain": "A"})
        payload = viewer._build_init_payload()

        assert payload["orient"] == {"chain": "A"}

    def test_orient_string_in_payload(self, ethanol_3d):
        """orient with a string selection should pass it through."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.orient("chain A")
        payload = viewer._build_init_payload()

        assert payload["orient"] == "chain A"


# ---------------------------------------------------------------------------
# TestC3DToHtml
# ---------------------------------------------------------------------------


class TestC3DToHtml:
    """Verify the to_html HTML generation method."""

    def test_contains_3dmol_library(self, ethanol_3d):
        """Generated HTML should contain the 3Dmol.js library content."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert "$3Dmol" in html

    def test_contains_viewer_container(self, ethanol_3d):
        """Generated HTML should contain the viewer-container div."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert "viewer-container" in html

    def test_contains_style_tag(self, ethanol_3d):
        """Generated HTML should contain a <style> block for CSS."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert "<style>" in html

    def test_contains_init_payload(self, ethanol_3d):
        """Generated HTML should contain the __C3D_INIT__ payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert "__C3D_INIT__" in html

    def test_raises_value_error_no_molecules(self):
        """to_html should raise ValueError when no molecules are added."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="No molecules have been added"):
            viewer.to_html()

    def test_no_external_urls(self, ethanol_3d):
        """Generated HTML should not contain external URLs."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert 'src="http' not in html
        assert 'href="http' not in html

    def test_contains_doctype(self, ethanol_3d):
        """Generated HTML should start with a DOCTYPE declaration."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert html.startswith("<!DOCTYPE html>")

    def test_contains_gui_div_ids(self, ethanol_3d):
        """Generated HTML should contain the expected GUI div IDs."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert 'id="app"' in html
        assert 'id="menubar-container"' in html
        assert 'id="sidebar-container"' in html
        assert 'id="terminal-container"' in html

    def test_html_contains_module_script(self, ethanol_3d):
        """Generated HTML should contain a module script for the GUI JS."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        html = viewer.to_html()

        assert '<script type="module">' in html


# ---------------------------------------------------------------------------
# TestIsMarimo
# ---------------------------------------------------------------------------


class TestIsMarimo:
    """Verify the _is_marimo() environment detection helper."""

    def test_is_marimo_not_in_modules(self):
        """_is_marimo() should return False when marimo is not in sys.modules."""
        from unittest.mock import patch

        from cnotebook.c3d.c3d import _is_marimo

        mods = dict(sys.modules)
        mods.pop("marimo", None)
        with patch.dict("sys.modules", mods, clear=True):
            assert _is_marimo() is False

    def test_is_marimo_import_error(self):
        """_is_marimo() should return False when running_in_notebook raises."""
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d.c3d import _is_marimo

        mock_marimo = MagicMock()
        mock_marimo.running_in_notebook.side_effect = AttributeError

        with patch.dict("sys.modules", {"marimo": mock_marimo}):
            assert _is_marimo() is False


# ---------------------------------------------------------------------------
# TestC3DDisplay
# ---------------------------------------------------------------------------


class TestC3DDisplay:
    """Verify the display() method returns the right wrapper."""

    def test_display_returns_jupyter_iframe(self, ethanol_3d):
        """display() should return a _JupyterIFrame when not in marimo."""
        from unittest.mock import patch

        from cnotebook.c3d import C3D
        from cnotebook.c3d.c3d import _JupyterIFrame

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)

        with patch("cnotebook.c3d.c3d._is_marimo", return_value=False):
            result = viewer.display()

        assert isinstance(result, _JupyterIFrame)

    def test_display_returns_marimo_html(self, ethanol_3d):
        """Static display() should return marimo.Html when running in marimo."""
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d import C3D

        mock_mo = MagicMock()
        viewer = C3D()
        viewer.add_molecule(ethanol_3d)

        with patch("cnotebook.c3d.c3d._is_marimo", return_value=True), \
             patch.dict("sys.modules", {"marimo": mock_mo}):
            result = viewer.display(static=True)

        mock_mo.Html.assert_called_once()
        assert result is mock_mo.Html.return_value

    def test_widget_display_is_wrapped_for_marimo(self, ethanol_3d):
        """Widget display() should hand the widget to mo.ui.anywidget in marimo."""
        pytest.importorskip("anywidget")
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d import C3D

        mock_mo = MagicMock()
        viewer = C3D()
        viewer.add_molecule(ethanol_3d)

        with patch("cnotebook.c3d.c3d._is_marimo", return_value=True), \
             patch.dict("sys.modules", {"marimo": mock_mo}):
            result = viewer.display(static=False)

        mock_mo.ui.anywidget.assert_called_once_with(viewer.widget)
        assert result is mock_mo.ui.anywidget.return_value

    def test_jupyter_iframe_repr_html(self):
        """_JupyterIFrame._repr_html_() should return the stored HTML string."""
        from cnotebook.c3d.c3d import _JupyterIFrame

        html = "<iframe>test</iframe>"
        iframe = _JupyterIFrame(html)
        assert iframe._repr_html_() == html


# ---------------------------------------------------------------------------
# TestC3DAddMolecules
# ---------------------------------------------------------------------------


class TestC3DAddMolecules:
    """Verify the add_molecules batch method."""

    def test_invalid_enable_string_raises_value_error(self):
        """add_molecules should raise ValueError for unknown enable strings."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown enable mode"):
            viewer.add_molecules([], enable="none")

    def test_invalid_enable_type_raises_type_error(self):
        """add_molecules should raise TypeError for non-string, non-Sequence enable."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(TypeError, match="enable must be"):
            viewer.add_molecules([], enable=42)

    def test_enable_all(self, ethanol_3d):
        """enable='all' should make all entries visible."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d, ethanol_3d, ethanol_3d], enable="all")
        assert all(m.disabled is False for m in viewer._molecules)

    def test_enable_first(self, ethanol_3d):
        """enable='first' should enable only the first entry."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d, ethanol_3d, ethanol_3d], enable="first")
        assert viewer._molecules[0].disabled is False
        assert viewer._molecules[1].disabled is True
        assert viewer._molecules[2].disabled is True

    def test_enable_sequence(self, ethanol_3d):
        """A Sequence[bool] should map True=enabled, False=disabled."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules(
            [ethanol_3d, ethanol_3d, ethanol_3d],
            enable=[True, False, True],
        )
        assert viewer._molecules[0].disabled is False
        assert viewer._molecules[1].disabled is True
        assert viewer._molecules[2].disabled is False

    def test_enable_sequence_shorter_than_input(self, ethanol_3d):
        """Short Sequence should disable remaining entries."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules(
            [ethanol_3d, ethanol_3d, ethanol_3d],
            enable=[True],
        )
        assert viewer._molecules[0].disabled is False
        assert viewer._molecules[1].disabled is True
        assert viewer._molecules[2].disabled is True

    def test_enable_first_single_element(self, ethanol_3d):
        """enable='first' with a single molecule should enable it."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d], enable="first")
        assert len(viewer._molecules) == 1
        assert viewer._molecules[0].disabled is False

    def test_enable_sequence_longer_than_input(self, ethanol_3d):
        """Extra enable values beyond len(mols) should be silently ignored."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d], enable=[True, False, True])
        assert len(viewer._molecules) == 1
        assert viewer._molecules[0].disabled is False

    def test_prefix_with_titled_molecules(self, ethanol_3d):
        """Prefix should be prepended to existing titles."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d], prefix="Series A - ")
        assert viewer._molecules[0].name == "Series A - ethanol"

    def test_prefix_with_untitled_molecule(self):
        """Untitled molecules with prefix should get 1-based index names."""
        from openeye import oechem, oeomega

        from cnotebook.c3d import C3D

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "C")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CC")
        omega = oeomega.OEOmega()
        omega.SetMaxConfs(1)
        omega.SetStrictStereo(False)
        omega(mol1)
        omega(mol2)

        viewer = C3D()
        viewer.add_molecules([mol1, mol2], prefix="Mol ", enable="all")
        assert viewer._molecules[0].name == "Mol 1"
        assert viewer._molecules[1].name == "Mol 2"

    def test_no_prefix_delegates_naming(self, ethanol_3d):
        """Without prefix, name=None is passed and delegate uses its fallback."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules([ethanol_3d])
        # convert_molecule falls back to mol.GetTitle() which is "ethanol"
        assert viewer._molecules[0].name == "ethanol"

    def test_no_prefix_untitled_molecule(self):
        """Without prefix and no title, delegate falls back to 'molecule'."""
        from openeye import oechem, oeomega

        from cnotebook.c3d import C3D

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "C")
        omega = oeomega.OEOmega()
        omega.SetMaxConfs(1)
        omega.SetStrictStereo(False)
        omega(mol)

        viewer = C3D()
        viewer.add_molecules([mol], enable="all")
        assert viewer._molecules[0].name == "molecule"

    def test_returns_self(self, ethanol_3d):
        """add_molecules should return the C3D instance for chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_molecules([ethanol_3d])
        assert result is viewer

    def test_empty_iterable(self):
        """Empty iterable should be a no-op and return self."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_molecules([])
        assert result is viewer
        assert len(viewer._molecules) == 0

    def test_ui_defaults_with_batch(self, ethanol_3d):
        """Batch-added molecules should count toward UI smart defaults."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules(
            [ethanol_3d, ethanol_3d, ethanol_3d], enable="all"
        )
        payload = viewer._build_init_payload()
        # 3 molecules -> full GUI
        assert payload["ui"]["sidebar"] is True
        assert payload["ui"]["menubar"] is True
        assert payload["ui"]["console"] is True

    def test_composition_with_single_add(self, ethanol_3d):
        """add_molecules should compose with add_molecule."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="solo")
        viewer.add_molecules([ethanol_3d, ethanol_3d], prefix="Batch ", enable="all")
        assert len(viewer._molecules) == 3
        assert viewer._molecules[0].name == "solo"
        assert viewer._molecules[1].name == "Batch ethanol"
        assert viewer._molecules[2].name == "Batch ethanol"

    def test_generator_input(self, ethanol_3d):
        """add_molecules should accept a generator (non-list iterable)."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecules((m for m in [ethanol_3d, ethanol_3d]), enable="all")
        assert len(viewer._molecules) == 2


# ---------------------------------------------------------------------------
# TestC3DAddDesignUnits
# ---------------------------------------------------------------------------


class TestC3DAddDesignUnits:
    """Verify the add_design_units batch method."""

    def test_invalid_enable_string_raises_value_error(self):
        """add_design_units should raise ValueError for unknown enable strings."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown enable mode"):
            viewer.add_design_units([], enable="none")

    def test_invalid_enable_type_raises_type_error(self):
        """add_design_units should raise TypeError for non-string, non-Sequence enable."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(TypeError, match="enable must be"):
            viewer.add_design_units([], enable=42)

    def test_returns_self(self):
        """add_design_units should return self for method chaining."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_design_units([])
        assert result is viewer

    def test_empty_iterable(self):
        """Empty iterable should be a no-op and return self."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        result = viewer.add_design_units([])
        assert result is viewer
        assert len(viewer._molecules) == 0

    def test_delegates_to_add_design_unit(self):
        """add_design_units should call add_design_unit for each item."""
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d import C3D

        viewer = C3D()
        du1 = MagicMock()
        du1.GetTitle.return_value = "complex_1"
        du2 = MagicMock()
        du2.GetTitle.return_value = "complex_2"

        with patch.object(viewer, "add_design_unit", return_value=viewer) as mock_add:
            viewer.add_design_units([du1, du2], prefix="DU ", enable="all")

        assert mock_add.call_count == 2
        mock_add.assert_any_call(du1, name="DU complex_1", disabled=False)
        mock_add.assert_any_call(du2, name="DU complex_2", disabled=False)

    def test_enable_first_with_delegation(self):
        """enable='first' should pass disabled=False for first, True for rest."""
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d import C3D

        viewer = C3D()
        du1 = MagicMock()
        du1.GetTitle.return_value = ""
        du2 = MagicMock()
        du2.GetTitle.return_value = ""

        with patch.object(viewer, "add_design_unit", return_value=viewer) as mock_add:
            viewer.add_design_units([du1, du2], prefix="P", enable="first")

        calls = mock_add.call_args_list
        assert calls[0].kwargs["disabled"] is False
        assert calls[1].kwargs["disabled"] is True

    def test_no_prefix_passes_none_name(self):
        """Without prefix, name=None should be passed to add_design_unit."""
        from unittest.mock import MagicMock, patch

        from cnotebook.c3d import C3D

        viewer = C3D()
        du = MagicMock()
        du.GetTitle.return_value = "my_du"

        with patch.object(viewer, "add_design_unit", return_value=viewer) as mock_add:
            viewer.add_design_units([du], enable="all")

        mock_add.assert_called_once_with(du, name=None, disabled=False)


def test_add_molecule_generate_3d_flag(monkeypatch):
    import cnotebook.c3d.c3d as c3d_module
    from cnotebook.c3d import C3D

    seen = {}

    def fake_convert(mol, name=None, disabled=False, *, generate_3d=True):
        seen["generate_3d"] = generate_3d
        from cnotebook.core.convert import MoleculeData
        return MoleculeData(name="x", data="", format="sdf", source_type="molecule")

    monkeypatch.setattr(c3d_module, "convert_molecule", fake_convert)
    C3D().add_molecule(oechem.OEGraphMol(), generate_3d=False)
    assert seen["generate_3d"] is False


def test_add_molecules_forwards_generate_3d_false(monkeypatch):
    """add_molecules should forward generate_3d=False to all add_molecule calls."""
    import cnotebook.c3d.c3d as c3d_module
    from cnotebook.c3d import C3D

    calls = []

    def fake_convert(mol, name=None, disabled=False, *, generate_3d=True):
        calls.append({"name": name, "disabled": disabled, "generate_3d": generate_3d})
        from cnotebook.core.convert import MoleculeData
        return MoleculeData(name=name or "x", data="", format="sdf", source_type="molecule")

    monkeypatch.setattr(c3d_module, "convert_molecule", fake_convert)
    
    mol1 = oechem.OEGraphMol()
    mol1.SetTitle("mol1")
    mol2 = oechem.OEGraphMol()
    mol2.SetTitle("mol2")
    
    C3D().add_molecules([mol1, mol2], generate_3d=False)
    
    assert len(calls) == 2
    assert all(call["generate_3d"] is False for call in calls)


def test_add_molecules_defaults_generate_3d_true(monkeypatch):
    """add_molecules should default generate_3d=True when not specified."""
    import cnotebook.c3d.c3d as c3d_module
    from cnotebook.c3d import C3D

    calls = []

    def fake_convert(mol, name=None, disabled=False, *, generate_3d=True):
        calls.append({"name": name, "disabled": disabled, "generate_3d": generate_3d})
        from cnotebook.core.convert import MoleculeData
        return MoleculeData(name=name or "x", data="", format="sdf", source_type="molecule")

    monkeypatch.setattr(c3d_module, "convert_molecule", fake_convert)
    
    mol1 = oechem.OEGraphMol()
    mol1.SetTitle("mol1")
    mol2 = oechem.OEGraphMol()
    mol2.SetTitle("mol2")
    
    C3D().add_molecules([mol1, mol2])

    assert len(calls) == 2
    assert all(call["generate_3d"] is True for call in calls)


# ---------------------------------------------------------------------------
# Interactive API: display modes, commands, views, picks and durable writers
# ---------------------------------------------------------------------------

# 3Dmol's getView() returns [x, y, z, zoom, qx, qy, qz, qw]. C3DWidget.set_view rejects a
# vector of any other shape, so every camera below is a full eight-number view array.
_VIEW_A = [1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0.0, 1.0]
_VIEW_B = [5.0, 6.0, 7.0, 8.0, 0.0, 0.0, 1.0, 0.0]

_PNG_SIGNATURE_BASE64 = "iVBORw0KGgo="  # the eight PNG signature bytes, nothing more


def _explode(*args, **kwargs):
    """Stand in for a filesystem call that fails halfway through a write."""
    raise OSError("disk full")


@pytest.fixture()
def viewer(ethanol_3d):
    """A viewer holding one molecule, shared by the interactive API tests."""
    from cnotebook.c3d import C3D

    return C3D(width=300, height=200).add_molecule(ethanol_3d, name="ethanol")


def test_display_mode_snapshotted_at_construction(ethanol_3d, monkeypatch):
    """A viewer shows the way it did when it was built, whatever the config does later.

    The gate is forced open throughout, so the only thing that can decide between the
    widget and the document is the mode each viewer captured for itself.
    """
    pytest.importorskip("anywidget")
    from cnotebook.c3d import C3D
    from cnotebook.c3d.widget import C3DWidget

    monkeypatch.setattr("cnotebook.c3d.c3d._has_display_frontend", lambda: True)
    monkeypatch.setattr(cn_config, "_CONFIG", None)
    try:
        built_as_widget = C3D().add_molecule(ethanol_3d)
        cn_config.configure(display_mode="static")
        built_as_static = C3D().add_molecule(ethanol_3d)
        assert isinstance(built_as_widget.display(), C3DWidget)
        assert "<iframe" in built_as_static.display()._repr_html_()

        # ... and the same the other way round.
        cn_config.configure(display_mode="widget")
        built_as_widget_again = C3D().add_molecule(ethanol_3d)
        assert "<iframe" in built_as_static.display()._repr_html_()
        assert isinstance(built_as_widget_again.display(), C3DWidget)
    finally:
        cn_config.configure(display_mode="widget")


def test_constructor_defaults_resolve_from_config(monkeypatch):
    from cnotebook.c3d import C3D

    monkeypatch.setattr(cn_config, "_CONFIG", None)
    cn_config.configure(c3d={"width": 512, "theme": "dark"})
    try:
        v = C3D()
        assert v._width == 512 and v._theme == "dark"
        assert C3D(width=64)._width == 64
    finally:
        cn_config.configure(c3d={"width": 800, "theme": "auto"})


def test_widget_display_and_static_display(viewer):
    pytest.importorskip("anywidget")
    from cnotebook.c3d.widget import C3DWidget

    shown = viewer.display(static=False)
    assert isinstance(shown, C3DWidget)
    assert json.loads(shown.payload)["molecules"][0]["name"] == "ethanol"
    assert viewer.widget is shown
    assert "<iframe" in viewer.display(static=True)._repr_html_()


def test_widget_mode_falls_back_without_anywidget(viewer, monkeypatch):
    monkeypatch.setitem(sys.modules, "anywidget", None)
    monkeypatch.setitem(sys.modules, "cnotebook.c3d.widget", None)
    viewer._widget = None
    with pytest.warns(CNotebookWarning, match="anywidget"):
        shown = viewer.display(static=False)
    assert "<iframe" in shown._repr_html_()


def test_widget_mode_without_a_front_end_falls_back_quietly(viewer, recwarn):
    """A script or test run has nowhere to render a widget, and that is not a problem."""
    shown = viewer.display()
    assert "<iframe" in shown._repr_html_()
    assert [w for w in recwarn.list if issubclass(w.category, CNotebookWarning)] == []


def test_display_follows_the_front_end_gate(viewer, monkeypatch):
    """The gate decides display(): the live widget where one can render, else the HTML.

    Without this the gate could be stuck closed and every notebook would quietly get the
    static document instead of an interactive viewer, with nothing failing to say so.
    """
    pytest.importorskip("anywidget")
    from cnotebook.c3d.widget import C3DWidget

    monkeypatch.setattr("cnotebook.c3d.c3d._has_display_frontend", lambda: True)
    assert isinstance(viewer.display(), C3DWidget)
    assert isinstance(viewer.display(static=None), C3DWidget)

    monkeypatch.setattr("cnotebook.c3d.c3d._has_display_frontend", lambda: False)
    assert "<iframe" in viewer.display()._repr_html_()
    # An explicit request still wins: the gate only decides the default.
    assert isinstance(viewer.display(static=False), C3DWidget)


def test_the_front_end_gate_wants_a_kernel_shell_not_merely_a_shell(monkeypatch):
    """Terminal IPython has a shell but no widget manager, so a widget cannot render."""
    from cnotebook.c3d.c3d import _has_display_frontend

    class TerminalInteractiveShell:
        """Stands in for `ipython` at a terminal prompt."""

    class ZMQInteractiveShell:
        """Stands in for the ipykernel shell a notebook front end talks to."""

    class ColabShell(ZMQInteractiveShell):
        """Stands in for a front end that subclasses the kernel shell, as Colab does."""

    monkeypatch.setattr("cnotebook.c3d.c3d._is_marimo", lambda: False)
    monkeypatch.setattr("IPython.core.getipython.get_ipython", lambda: None)
    assert _has_display_frontend() is False
    monkeypatch.setattr("IPython.core.getipython.get_ipython", TerminalInteractiveShell)
    assert _has_display_frontend() is False
    monkeypatch.setattr("IPython.core.getipython.get_ipython", ZMQInteractiveShell)
    assert _has_display_frontend() is True
    monkeypatch.setattr("IPython.core.getipython.get_ipython", ColabShell)
    assert _has_display_frontend() is True
    # IPython is an optional dependency, and its absence is not an error here.
    monkeypatch.setitem(sys.modules, "IPython.core.getipython", None)
    assert _has_display_frontend() is False
    monkeypatch.setattr("cnotebook.c3d.c3d._is_marimo", lambda: True)
    assert _has_display_frontend() is True


def test_construction_and_static_output_never_reach_the_widget_module(ethanol_3d, monkeypatch):
    """Only the live widget needs anywidget; building and rendering must not import it."""
    from cnotebook.c3d import C3D

    monkeypatch.setitem(sys.modules, "anywidget", None)
    monkeypatch.setitem(sys.modules, "cnotebook.c3d.widget", None)
    built = C3D(width=300, height=200).add_molecule(ethanol_3d, name="ethanol")
    assert built._widget is None
    assert "<iframe" in built.display(static=True)._repr_html_()


def test_star_import_does_not_need_anywidget(monkeypatch):
    """The lazily resolved widget names must stay out of `from cnotebook.c3d import *`.

    A star import resolves every name in ``__all__``, so listing them there would import
    anywidget and undo the isolation the lazy ``__getattr__`` exists for.
    """
    import cnotebook.c3d

    class _BlockAnywidget:
        """Meta path finder that fails `import anywidget` as a missing install would."""

        def find_spec(self, name, path=None, target=None):
            if name.partition(".")[0] == "anywidget":
                raise ImportError("anywidget is not installed")
            # Any other module is none of this finder's business.

    for imported in [n for n in sys.modules if n.partition(".")[0] == "anywidget"]:
        monkeypatch.delitem(sys.modules, imported)
    monkeypatch.delitem(sys.modules, "cnotebook.c3d.widget", raising=False)
    # The submodule is an attribute of its package too, and a `from ... import widget`
    # would find that instead of trying the blocked import.
    monkeypatch.delattr(cnotebook.c3d, "widget", raising=False)
    monkeypatch.setattr(sys, "meta_path", [_BlockAnywidget(), *sys.meta_path])

    namespace = {}
    exec("from cnotebook.c3d import *", namespace)  # noqa: S102 - the statement under test
    assert namespace["C3D"] is cnotebook.c3d.C3D
    assert "cnotebook.c3d.widget" not in sys.modules

    # The widget names are still exported by name; they just need the install.
    with pytest.raises(ImportError, match="anywidget"):
        namespace["blocked"] = cnotebook.c3d.C3DWidget


def test_execute_views_and_picks(viewer):
    pytest.importorskip("anywidget")
    handle = viewer.execute("zoom resn LIG")
    assert viewer.widget.commands[-1]["command"] == "zoom resn LIG"
    viewer.widget.command_results = [{"id": handle.id, "ok": True, "output": []}]
    assert handle.done
    assert viewer.view is None
    # A browser-originated camera update: the front end writes both traits itself.
    viewer.widget.view = _VIEW_A
    viewer.widget.view_origin = "js"
    assert viewer.view == _VIEW_A
    viewer.save_view("start")
    viewer.set_view(_VIEW_B)
    assert viewer.widget.view == _VIEW_B and viewer.widget.view_origin == "python"
    viewer.restore_view("start")
    assert viewer.widget.view == _VIEW_A and viewer.views == {"start": _VIEW_A}
    picks = []
    viewer.on_pick(picks.append)
    viewer.widget.picked = {"seq": 1, "atom": {"serial": 1}, "modifiers": {}}
    assert picks and viewer.picked is picks[0]
    with pytest.raises(CNotebookError, match="missing"):
        viewer.restore_view("missing")


def test_restore_view_reaches_the_frame_when_the_camera_did_not_move(viewer):
    """traitlets drops an equal-valued assignment, so only the counter carries a restore."""
    pytest.importorskip("anywidget")
    viewer.set_view(_VIEW_A)
    viewer.save_view("start")
    requests = viewer.widget.view_request
    viewer.restore_view("start")
    assert viewer.widget.view == _VIEW_A and viewer.widget.view_request == requests + 1


def test_set_view_rejects_a_bad_camera_before_a_widget_exists(viewer):
    """A rejected camera must not be what brings a live widget into being."""
    pytest.importorskip("anywidget")
    with pytest.raises(ValueError, match="8 numbers"):
        viewer.set_view([1.0, 2.0])
    assert viewer._widget is None
    # Validating first must not consume a one-shot iterable before the widget sees it.
    viewer.set_view(iter(_VIEW_A))
    assert viewer.widget.view == _VIEW_A


def test_saved_views_are_copies(viewer):
    pytest.importorskip("anywidget")
    viewer.set_view(_VIEW_A)
    viewer.save_view("start")
    assert viewer._views["start"] is not viewer.widget.view
    viewer.views["start"][0] = 99.0
    viewer.set_view(_VIEW_B)
    assert viewer.views == {"start": _VIEW_A}
    assert viewer.view == _VIEW_B and viewer.view is not viewer.widget.view


def test_save_view_before_the_viewer_reports_one_is_an_error(viewer):
    with pytest.raises(CNotebookError, match="No view"):
        viewer.save_view("start")
    assert viewer._widget is None


def test_screenshot_and_save_png(viewer, tmp_path):
    pytest.importorskip("anywidget")

    async def scenario():
        task = asyncio.ensure_future(viewer.screenshot())
        await asyncio.sleep(0)
        seq = viewer.widget.screenshot_request
        viewer.widget.screenshot = {"seq": seq, "png_base64": _PNG_SIGNATURE_BASE64}
        return await task

    assert asyncio.run(scenario()).startswith(b"\x89PNG")

    async def save_scenario():
        task = asyncio.ensure_future(viewer.save_png(tmp_path / "shot.png"))
        await asyncio.sleep(0)
        seq = viewer.widget.screenshot_request
        viewer.widget.screenshot = {"seq": seq, "png_base64": _PNG_SIGNATURE_BASE64}
        return await task

    written = asyncio.run(save_scenario())
    assert written == tmp_path / "shot.png"
    assert written.read_bytes().startswith(b"\x89PNG")
    assert list(tmp_path.iterdir()) == [written]

    async def timeout_scenario():
        viewer._screenshot_timeout = 0.01
        return await viewer.screenshot()

    with pytest.raises(CNotebookError, match="Screenshot"):
        asyncio.run(timeout_scenario())
    # A timed out request is cancelled, so nothing is left waiting for an answer.
    assert viewer.widget._screenshot_futures == {}


def test_screenshot_reports_a_front_end_failure(viewer):
    pytest.importorskip("anywidget")

    async def scenario():
        task = asyncio.ensure_future(viewer.screenshot())
        await asyncio.sleep(0)
        seq = viewer.widget.screenshot_request
        viewer.widget.screenshot = {"seq": seq, "error": "canvas is empty"}
        return await task

    with pytest.raises(CNotebookError, match="canvas is empty"):
        asyncio.run(scenario())


def test_save_png_writes_nothing_when_the_answer_is_not_a_png(viewer, tmp_path):
    pytest.importorskip("anywidget")
    target = tmp_path / "shot.png"

    async def scenario():
        task = asyncio.ensure_future(viewer.save_png(target))
        await asyncio.sleep(0)
        seq = viewer.widget.screenshot_request
        encoded = base64.b64encode(b"not a png at all").decode()
        viewer.widget.screenshot = {"seq": seq, "png_base64": encoded}
        return await task

    with pytest.raises(CNotebookError, match="PNG"):
        asyncio.run(scenario())
    assert list(tmp_path.iterdir()) == []


def test_save_png_checks_the_directory_before_waiting_for_the_front_end(viewer, tmp_path):
    pytest.importorskip("anywidget")

    async def scenario():
        return await viewer.save_png(tmp_path / "nope" / "shot.png")

    with pytest.raises(CNotebookError, match="does not exist"):
        asyncio.run(scenario())
    assert viewer.widget.screenshot_request == 0


def test_save_writes_standalone_html(viewer, tmp_path):
    out = viewer.save(tmp_path / "v.html")
    assert out == tmp_path / "v.html"
    assert out.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")
    assert list(tmp_path.iterdir()) == [out]


def test_save_rejects_a_directory_that_does_not_exist(viewer, tmp_path):
    with pytest.raises(CNotebookError, match="does not exist"):
        viewer.save(tmp_path / "nope" / "v.html")


def test_a_failed_write_leaves_neither_a_partial_file_nor_a_temporary(viewer, tmp_path, monkeypatch):
    """The document is moved into place last, so a failed write keeps the previous one."""
    target = viewer.save(tmp_path / "v.html")
    original = target.read_text(encoding="utf-8")
    monkeypatch.setattr("os.replace", _explode)
    with pytest.raises(OSError, match="disk full"):
        viewer.save(target)
    assert target.read_text(encoding="utf-8") == original
    assert list(tmp_path.iterdir()) == [target]


def test_saved_files_get_ordinary_permissions(viewer, tmp_path):
    """The temporary file is created 0600; the saved document must not inherit that."""
    reference = tmp_path / "reference.html"
    reference.write_text("written the plain way", encoding="utf-8")

    out = viewer.save(tmp_path / "v.html")
    assert out.stat().st_mode == reference.stat().st_mode

    out.chmod(0o640)  # rewriting keeps whatever mode the user chose
    viewer.save(out)
    assert stat.S_IMODE(out.stat().st_mode) == 0o640


def _mutations(viewer, mol):
    """Every builder call that would change what the viewer shows, by category.

    The arguments are deliberately worthless: the lifecycle check runs before any of
    them is looked at, so a frozen viewer must reject the call whatever it was given.
    """
    return {
        "add_molecule": lambda: viewer.add_molecule(mol),
        "add_molecules": lambda: viewer.add_molecules([]),
        "add_design_unit": lambda: viewer.add_design_unit(None),
        "add_design_units": lambda: viewer.add_design_units([]),
        "add_style": lambda: viewer.add_style("stick"),
        "remove_style": lambda: viewer.remove_style("stick"),
        "show_style": lambda: viewer.show_style("stick"),
        "hide_style": lambda: viewer.hide_style("stick"),
        "show_polar_hydrogens": lambda: viewer.show_polar_hydrogens("stick"),
        "hide_nonpolar_hydrogens": lambda: viewer.hide_nonpolar_hydrogens(),
        "add_surface": lambda: viewer.add_surface("all"),
        "remove_surface": lambda: viewer.remove_surface("s"),
        "add_map": lambda: viewer.add_map("nowhere.dx"),
        "remove_map": lambda: viewer.remove_map("m"),
        "add_isosurface": lambda: viewer.add_isosurface("m"),
        "remove_isosurface": lambda: viewer.remove_isosurface("i"),
        "set_color": lambda: viewer.set_color("all", "red"),
        "set_ui": lambda: viewer.set_ui(sidebar=False),
        "set_background": lambda: viewer.set_background("#000000"),
        "set_theme": lambda: viewer.set_theme("dark"),
        "zoom_to": lambda: viewer.zoom_to("all"),
        "orient": lambda: viewer.orient(),
        "set_preset": lambda: viewer.set_preset("simple"),
    }


def test_the_builder_freezes_once_a_widget_exists(viewer, ethanol_3d):
    """The widget is initialized from the payload as it stood, and never re-reads it.

    Accepting a later builder call would leave the widget on screen showing one scene
    while to_html() and save() produced another, with nothing to say they had parted.
    """
    pytest.importorskip("anywidget")
    payload = viewer.widget.payload

    for name, mutate in _mutations(viewer, ethanol_3d).items():
        with pytest.raises(CNotebookError, match="displayed as a widget"):
            mutate()
        assert viewer.widget.payload == payload, name

    # Nothing slipped through: the builder still describes exactly what is on screen.
    assert json.loads(viewer.widget.payload) == viewer._build_init_payload()


def test_static_display_leaves_the_builder_open(viewer, ethanol_3d, tmp_path):
    """Only a widget freezes the viewer; a document is rendered from scratch each time."""
    viewer.display(static=True)
    viewer.to_html()
    viewer.save(tmp_path / "v.html")

    viewer.add_molecule(ethanol_3d, name="second")
    viewer.add_style("stick")
    viewer.set_background("#000000")
    viewer.set_theme("dark")
    viewer.zoom_to("all")

    assert len(viewer._molecules) == 2
    assert viewer._theme == "dark"
    assert viewer._background == "#000000"
    assert "second" in viewer.to_html()


def test_a_closed_viewer_refuses_what_needs_the_front_end(viewer, tmp_path, monkeypatch):
    """Closing is final: the cached widget's comm is gone, so nothing may reuse it."""
    pytest.importorskip("anywidget")
    # display() with no argument has to choose the widget for its check to mean anything.
    monkeypatch.setattr("cnotebook.c3d.c3d._has_display_frontend", lambda: True)
    monkeypatch.setattr(viewer, "_display_mode", "widget")

    viewer.widget.view = _VIEW_A
    viewer.widget.view_origin = "js"
    viewer.save_view("start")
    viewer.widget.picked = {"seq": 1, "atom": {"serial": 1}, "modifiers": {}}
    pick = viewer.picked

    viewer.close()

    refused = [
        lambda: viewer.widget,
        lambda: viewer.display(),
        lambda: viewer.display(static=False),
        lambda: viewer.execute("zoom resn LIG"),
        lambda: viewer.set_view(_VIEW_B),
        lambda: viewer.restore_view("start"),
    ]
    for call in refused:
        with pytest.raises(CNotebookError, match="viewer closed"):
            call()

    async def capture():
        return await viewer.screenshot()

    async def write():
        return await viewer.save_png(tmp_path / "shot.png")

    with pytest.raises(CNotebookError, match="viewer closed"):
        asyncio.run(capture())
    with pytest.raises(CNotebookError, match="viewer closed"):
        asyncio.run(write())
    assert list(tmp_path.iterdir()) == []

    # What needs no front end is untouched, including the state the session produced.
    assert viewer.to_html().startswith("<!DOCTYPE html>")
    assert viewer.save(tmp_path / "v.html").read_text(encoding="utf-8")
    assert "<iframe" in viewer.display(static=True)._repr_html_()
    monkeypatch.setattr("cnotebook.c3d.c3d._has_display_frontend", lambda: False)
    assert "<iframe" in viewer.display()._repr_html_()
    assert viewer.view == _VIEW_A and viewer.views == {"start": _VIEW_A}
    assert viewer.picked is pick
    viewer.close()  # closing twice does nothing


def test_closing_a_viewer_that_was_never_displayed_still_closes_it(ethanol_3d):
    from cnotebook.c3d import C3D

    viewer = C3D(width=300, height=200).add_molecule(ethanol_3d)
    viewer.close()
    assert viewer._widget is None
    assert viewer.to_html().startswith("<!DOCTYPE html>")
    with pytest.raises(CNotebookError, match="viewer closed"):
        viewer.execute("zoom")


def test_set_view_accepts_a_numpy_camera(viewer):
    """The camera a caller saved from numpy must come back through the Python API."""
    pytest.importorskip("anywidget")
    numpy = pytest.importorskip("numpy")
    viewer.set_view(numpy.array(_VIEW_A, dtype=numpy.float32))
    assert viewer.view == _VIEW_A
    viewer.set_view(numpy.array([1, 2, 3, 4, 0, 0, 0, 1], dtype=numpy.int64))
    assert viewer.view == [1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0.0, 1.0]


def test_close_fails_the_commands_the_front_end_can_no_longer_answer(viewer):
    pytest.importorskip("anywidget")
    from cnotebook.c3d import C3D

    handle = viewer.execute("zoom resn LIG")
    viewer.close()
    assert handle.done and handle.result.ok is False
    assert handle.result.output == ["widget closed"]
    viewer.close()  # closing twice, or without a widget, does nothing
    C3D(width=300, height=200).close()


def test_widget_output_is_small(viewer):
    pytest.importorskip("anywidget")
    bundle = viewer.display(static=False)._repr_mimebundle_()
    data = bundle[0] if isinstance(bundle, tuple) else bundle
    assert len(json.dumps(data)) < 20_000
