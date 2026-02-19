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

        assert len(viewer._styles) == 1
        entry = viewer._styles[0]
        assert entry["selection"] == {"chain": "A"}
        assert entry["style"] == {"cartoon": {}}

    def test_add_style_preset_with_color(self):
        """When color is given with a preset, it should appear in the spec."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("stick", {"chain": "A"}, color="red")

        entry = viewer._styles[0]
        assert entry["style"] == {"stick": {"color": "red"}}

    def test_add_style_dict_passthrough(self):
        """A dict style should be passed through verbatim."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        custom_style = {"cartoon": {"color": "spectrum"}}
        viewer.add_style(custom_style, {"resi": 42})

        entry = viewer._styles[0]
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

        assert len(viewer._styles) == 1
        entry = viewer._styles[0]
        assert entry["selection"] is None
        assert entry["style"] == {"stick": {}}

    def test_add_style_string_selection(self):
        """add_style with a string selection should store the string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("cartoon", "chain A")

        entry = viewer._styles[0]
        assert entry["selection"] == "chain A"
        assert entry["style"] == {"cartoon": {}}

    def test_add_style_entry_name_selection(self):
        """add_style with a molecule name should store it as a string."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_style("sphere", "benzene")

        entry = viewer._styles[0]
        assert entry["selection"] == "benzene"

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
        """set_preset should store the lowercase preset name."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.set_preset("Sites")
        assert viewer._preset == "sites"

    def test_set_preset_all_valid_names(self):
        """All three view presets should be accepted."""
        from cnotebook.c3d import C3D

        for name in ("simple", "sites", "ball-and-stick"):
            viewer = C3D()
            viewer.set_preset(name)
            assert viewer._preset == name

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
        assert "preset" in payload
        assert "ui" in payload
        assert "theme" in payload
        assert "background" in payload
        assert "zoomTo" in payload
        assert "orient" in payload

    def test_preset_in_payload(self, ethanol_3d):
        """Payload should include preset when set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_preset("sites")
        payload = viewer._build_init_payload()
        assert payload["preset"] == "sites"

    def test_preset_default_none(self, ethanol_3d):
        """Payload preset should be None when not set."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()
        assert payload["preset"] is None

    def test_ui_defaults_single_molecule(self, ethanol_3d):
        """Single molecule should default to no GUI panels."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["ui"] == {
            "sidebar": False,
            "menubar": False,
            "terminal": False,
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
            "terminal": False,
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
            "terminal": True,
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
            "terminal": True,
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

    def test_theme_default_light_in_payload(self, ethanol_3d):
        """Default theme should be 'light' in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        payload = viewer._build_init_payload()

        assert payload["theme"] == "light"

    def test_theme_dark_in_payload(self, ethanol_3d):
        """set_theme('dark') should appear in payload."""
        from cnotebook.c3d import C3D

        viewer = C3D()
        viewer.add_molecule(ethanol_3d)
        viewer.set_theme("dark")
        payload = viewer._build_init_payload()

        assert payload["theme"] == "dark"

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
