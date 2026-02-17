"""Tests for the C3D 3D molecule viewer class."""

import json

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

    def test_import_from_submodule(self):
        """C3D should be importable from cnotebook.c3d."""
        from cnotebook.c3d import C3D

        assert C3D is not None

    def test_import_c3d_class(self):
        """C3D should be the class itself, not a module."""
        from cnotebook.c3d import C3D

        assert callable(C3D)

    def test_all_exports(self):
        """__all__ should list C3D."""
        import cnotebook.c3d

        assert "C3D" in cnotebook.c3d.__all__


# ---------------------------------------------------------------------------
# TestC3DConstructor
# ---------------------------------------------------------------------------


class TestC3DConstructor:
    """Verify C3D constructor defaults and custom dimensions."""

    def test_default_dimensions(self):
        """Default width should be 800 and height 600."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._width == 800
        assert viewer._height == 600

    def test_custom_dimensions(self):
        """Custom width and height should be stored."""
        from cnotebook.c3d import C3D

        viewer = C3D(width=1024, height=768)
        assert viewer._width == 1024
        assert viewer._height == 768

    def test_empty_molecules_list(self):
        """A new viewer should start with no molecules."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._molecules == []

    def test_empty_styles_list(self):
        """A new viewer should start with no styles."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._styles == []

    def test_default_ui_config(self):
        """Default UI config should enable all panels."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        assert viewer._ui == {
            "sidebar": True,
            "menubar": True,
            "terminal": True,
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
        result = viewer.add_style({"chain": "A"}, "cartoon")
        assert result is viewer

    def test_add_style_preset_mapping(self):
        """A preset name should map to a dict with the preset as key."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style({"chain": "A"}, "cartoon")

        assert len(viewer._styles) == 1
        entry = viewer._styles[0]
        assert entry["selection"] == {"chain": "A"}
        assert entry["style"] == {"cartoon": {}}

    def test_add_style_preset_with_color(self):
        """When color is given with a preset, it should appear in the spec."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style({"chain": "A"}, "stick", color="red")

        entry = viewer._styles[0]
        assert entry["style"] == {"stick": {"color": "red"}}

    def test_add_style_dict_passthrough(self):
        """A dict style should be passed through verbatim."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        custom_style = {"cartoon": {"color": "spectrum"}}
        viewer.add_style({"resi": 42}, custom_style)

        entry = viewer._styles[0]
        assert entry["style"] == {"cartoon": {"color": "spectrum"}}

    def test_add_style_invalid_preset_raises_value_error(self):
        """An unrecognised preset name should raise ValueError."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        with pytest.raises(ValueError, match="Unknown style preset"):
            viewer.add_style({}, "ribbon")

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
            "terminal": False,
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

    def test_zoom_to_none_for_fit_all(self):
        """zoom_to(None) should store None for fitting all molecules."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.zoom_to(None)
        assert viewer._zoom_to is None

    def test_full_method_chaining(self, ethanol_3d):
        """All builder methods should be chainable in a single expression."""
        from cnotebook.c3d import C3D

        viewer = (
            C3D(width=1024, height=768)
            .add_molecule(ethanol_3d, name="ethanol")
            .add_style({"chain": "A"}, "cartoon", color="blue")
            .add_style({}, "stick")
            .set_ui(sidebar=False)
            .set_background("#ffffff")
            .zoom_to({"chain": "A"})
        )

        assert isinstance(viewer, C3D)
        assert len(viewer._molecules) == 1
        assert len(viewer._styles) == 2
        assert viewer._ui["sidebar"] is False
        assert viewer._background == "#ffffff"
        assert viewer._zoom_to == {"chain": "A"}


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
        assert "styles" in payload
        assert "ui" in payload
        assert "background" in payload
        assert "zoomTo" in payload

    def test_ui_defaults(self, ethanol_3d):
        """Default UI config should have all panels enabled."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": True,
            "menubar": True,
            "terminal": True,
        }

    def test_payload_is_json_serializable(self, ethanol_3d):
        """The entire payload should be serializable with json.dumps."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d, name="ethanol")
        viewer.add_style({"chain": "A"}, "cartoon", color="red")
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

    def test_background_default_is_none(self, ethanol_3d):
        """Default background should be None in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["background"] is None

    def test_zoom_to_default_is_none(self, ethanol_3d):
        """Default zoomTo should be None in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["zoomTo"] is None


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
