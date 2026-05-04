"""Tests for the C3D 3D molecule viewer class."""

import json
import sys

import pytest
from openeye import oechem


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
        from cnotebook.c3d.convert import convert_map
        from openeye import oegrid

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
        from unittest.mock import patch, MagicMock
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
        """display() should return marimo.Html when running in marimo."""
        from unittest.mock import patch, MagicMock
        from cnotebook.c3d import C3D

        mock_mo = MagicMock()
        viewer = C3D()
        viewer.add_molecule(ethanol_3d)

        with patch("cnotebook.c3d.c3d._is_marimo", return_value=True), \
             patch.dict("sys.modules", {"marimo": mock_mo}):
            result = viewer.display()

        mock_mo.Html.assert_called_once()
        assert result is mock_mo.Html.return_value

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
        from cnotebook.c3d import C3D
        from openeye import oechem, oeomega

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
        from cnotebook.c3d import C3D
        from openeye import oechem, oeomega

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
        from unittest.mock import patch, MagicMock
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
        from unittest.mock import patch, MagicMock
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
        from unittest.mock import patch, MagicMock
        from cnotebook.c3d import C3D

        viewer = C3D()
        du = MagicMock()
        du.GetTitle.return_value = "my_du"

        with patch.object(viewer, "add_design_unit", return_value=viewer) as mock_add:
            viewer.add_design_units([du], enable="all")

        mock_add.assert_called_once_with(du, name=None, disabled=False)
