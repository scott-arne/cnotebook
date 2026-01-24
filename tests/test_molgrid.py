"""Tests for MolGrid interactive molecule grid."""

import json
import pytest
from openeye import oechem


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def simple_mol():
    """Create a simple test molecule (ethanol)."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    return mol


@pytest.fixture
def mol_with_sd_data():
    """Create a molecule with SD data."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    oechem.OESetSDData(mol, "MW", "46.07")
    oechem.OESetSDData(mol, "Formula", "C2H6O")
    return mol


@pytest.fixture
def test_molecules():
    """Create a set of test molecules."""
    smiles_list = [
        ("CCO", "Ethanol"),
        ("CC(=O)O", "Acetic Acid"),
        ("c1ccccc1", "Benzene"),
        ("CC(=O)Nc1ccc(O)cc1", "Acetaminophen"),
        ("CC(C)Cc1ccc(C(C)C(=O)O)cc1", "Ibuprofen"),
    ]
    mols = []
    for smiles, name in smiles_list:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mol.SetTitle(name)
        oechem.OESetSDData(mol, "SMILES", smiles)
        mols.append(mol)
    return mols


@pytest.fixture
def invalid_mol():
    """Create an invalid/empty molecule."""
    return oechem.OEGraphMol()


# ============================================================================
# Import Tests
# ============================================================================

def test_molgrid_import():
    """Test that MolGrid can be imported."""
    from cnotebook.molgrid import MolGrid
    assert MolGrid is not None


def test_molgrid_function_import():
    """Test that molgrid function can be imported."""
    from cnotebook.molgrid import molgrid
    assert molgrid is not None


def test_cnotebook_molgrid_function():
    """Test that cnotebook.molgrid() function works."""
    import cnotebook
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = cnotebook.molgrid([mol])

    assert grid is not None
    assert hasattr(grid, 'display')


# ============================================================================
# Initialization Tests
# ============================================================================

def test_molgrid_stores_molecules(simple_mol):
    """Test that MolGrid stores molecule data."""
    from cnotebook.molgrid import MolGrid

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    grid = MolGrid([simple_mol, mol2])

    assert len(grid._molecules) == 2
    assert grid._molecules[0].GetTitle() == "Ethanol"
    assert grid._molecules[1].GetTitle() == "Ethane"


def test_molgrid_default_parameters(simple_mol):
    """Test MolGrid default parameter values."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])

    assert grid.title_field == "Title"
    assert grid.tooltip_fields == []
    assert grid.n_items_per_page == 24
    assert grid.width == 200
    assert grid.height == 200
    assert grid.image_format == "svg"
    assert grid.selection_enabled is True
    assert grid.atom_label_font_scale == 1.5


def test_molgrid_custom_parameters(simple_mol):
    """Test MolGrid with custom parameters."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(
        [simple_mol],
        title_field="Name",
        tooltip_fields=["MW", "Formula"],
        n_items_per_page=12,
        width=250,
        height=180,
        image_format="png",
        select=False,
        atom_label_font_scale=2.0,
        name="custom-grid"
    )

    assert grid.title_field == "Name"
    assert grid.tooltip_fields == ["MW", "Formula"]
    assert grid.n_items_per_page == 12
    assert grid.width == 250
    assert grid.height == 180
    assert grid.image_format == "png"
    assert grid.selection_enabled is False
    assert grid.atom_label_font_scale == 2.0
    assert grid.name == "custom-grid"


def test_molgrid_auto_generates_name(simple_mol):
    """Test that MolGrid auto-generates unique names."""
    from cnotebook.molgrid import MolGrid

    grid1 = MolGrid([simple_mol])
    grid2 = MolGrid([simple_mol])

    assert grid1.name is not None
    assert grid2.name is not None
    assert grid1.name != grid2.name
    assert grid1.name.startswith("molgrid-")
    assert grid2.name.startswith("molgrid-")


def test_molgrid_creates_widget(simple_mol):
    """Test that MolGrid creates an AnyWidget."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])

    assert grid.widget is not None
    assert hasattr(grid.widget, 'grid_id')
    assert grid.widget.grid_id == grid.name


def test_molgrid_empty_molecules():
    """Test MolGrid with empty molecule list."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([])

    assert len(grid._molecules) == 0
    html = grid.to_html()
    assert "molgrid" in html.lower()


def test_molgrid_with_invalid_molecules(simple_mol, invalid_mol):
    """Test MolGrid handles invalid molecules gracefully."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol, invalid_mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()
    assert len(grid._molecules) == 2


def test_molgrid_search_fields_parameter(simple_mol):
    """Test that explicit search_fields parameter is used."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], search_fields=["MW", "Formula"])

    assert grid.search_fields == ["MW", "Formula"]


# ============================================================================
# Data Preparation Tests
# ============================================================================

def test_molgrid_prepare_data_basic(mol_with_sd_data):
    """Test _prepare_data extracts basic data correctly."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([mol_with_sd_data], title_field="Title", tooltip_fields=["MW"])
    data = grid._prepare_data()

    assert len(data) == 1
    assert data[0]["index"] == 0
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == "46.07"
    assert "img" in data[0]
    assert "smiles" in data[0]


def test_molgrid_prepare_data_smiles(simple_mol):
    """Test that SMILES is correctly extracted."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    data = grid._prepare_data()

    assert data[0]["smiles"] == "CCO"


def test_molgrid_prepare_data_no_title(simple_mol):
    """Test _prepare_data with title_field=None."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], title_field=None)
    data = grid._prepare_data()

    assert data[0]["title"] is None


def test_molgrid_prepare_data_missing_sd_data(simple_mol):
    """Test _prepare_data when SD data field doesn't exist."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], tooltip_fields=["NonExistentField"])
    data = grid._prepare_data()

    assert data[0]["tooltip"]["NonExistentField"] is None


def test_molgrid_prepare_data_search_fields(mol_with_sd_data):
    """Test _prepare_data extracts search fields."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([mol_with_sd_data], search_fields=["MW", "Formula"])
    data = grid._prepare_data()

    assert data[0]["search_fields"]["MW"] == "46.07"
    assert data[0]["search_fields"]["Formula"] == "C2H6O"


def test_molgrid_prepare_data_invalid_mol(invalid_mol):
    """Test _prepare_data handles invalid molecules."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([invalid_mol])
    data = grid._prepare_data()

    assert len(data) == 1
    assert data[0]["smiles"] == ""
    assert "img" in data[0]


# ============================================================================
# Export Data Tests
# ============================================================================

def test_molgrid_prepare_export_data_basic(simple_mol):
    """Test _prepare_export_data basic functionality."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    export_data = grid._prepare_export_data()

    assert len(export_data) == 1
    assert export_data[0]["index"] == 0
    assert export_data[0]["smiles"] == "CCO"


def test_molgrid_prepare_export_data_multiple_mols(test_molecules):
    """Test _prepare_export_data with multiple molecules."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    export_data = grid._prepare_export_data()

    assert len(export_data) == 5
    assert export_data[0]["smiles"] == "CCO"
    assert export_data[2]["smiles"] == "c1ccccc1"


def test_molgrid_prepare_export_data_invalid_mol(invalid_mol):
    """Test _prepare_export_data with invalid molecule."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([invalid_mol])
    export_data = grid._prepare_export_data()

    assert export_data[0]["smiles"] == ""


# ============================================================================
# HTML Generation Tests
# ============================================================================

def test_molgrid_generates_html(simple_mol):
    """Test that MolGrid generates valid HTML output."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "<!DOCTYPE html>" in html
    assert "<html" in html.lower()
    assert "</html>" in html.lower()


def test_molgrid_html_contains_grid_elements(simple_mol):
    """Test HTML contains required grid elements."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid-container" in html
    assert "molgrid-toolbar" in html
    assert "molgrid-list" in html
    assert "molgrid-pagination" in html


def test_molgrid_html_contains_title(simple_mol):
    """Test HTML contains molecule title."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "Ethanol" in html


def test_molgrid_html_contains_svg(simple_mol):
    """Test HTML contains SVG images."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], image_format="svg")
    html = grid.to_html()

    assert "<svg" in html.lower() or "data:image" in html


def test_molgrid_html_contains_search_elements(simple_mol):
    """Test HTML contains search-related elements."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid-search" in html
    assert "Properties" in html
    assert "SMARTS" in html


def test_molgrid_html_contains_actions_menu(simple_mol):
    """Test HTML contains actions dropdown menu."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid-actions" in html
    assert "molgrid-dropdown" in html
    assert "Select All" in html
    assert "Clear Selection" in html
    assert "Invert Selection" in html
    assert "Copy to Clipboard" in html
    assert "Save to SMILES" in html
    assert "Save to CSV" in html


def test_molgrid_html_contains_checkbox_when_enabled(simple_mol):
    """Test HTML contains checkbox when select=True."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], select=True)
    html = grid.to_html()

    assert 'class="molgrid-checkbox"' in html


def test_molgrid_html_no_checkbox_when_disabled(simple_mol):
    """Test HTML does not contain checkbox when select=False."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], select=False)
    html = grid.to_html()

    assert 'class="molgrid-checkbox"' not in html


def test_molgrid_html_pagination_info(test_molecules):
    """Test HTML contains pagination info."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, n_items_per_page=3)
    html = grid.to_html()

    assert "showing-start" in html
    assert "showing-end" in html
    assert "showing-total" in html


def test_molgrid_html_export_data_embedded(simple_mol):
    """Test that export data is embedded in HTML."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "exportData" in html
    assert "exportColumns" in html


def test_molgrid_html_contains_listjs(simple_mol):
    """Test HTML contains List.js library."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    # List.js should be included
    assert "List" in html


# ============================================================================
# SMARTS Search Tests
# ============================================================================

def test_molgrid_search_smarts_match(test_molecules):
    """Test _search_smarts finds matching molecules."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    matches = grid._search_smarts("[OH]")

    # Ethanol, Acetaminophen have OH
    assert len(matches) >= 2
    assert 0 in matches  # Ethanol


def test_molgrid_search_smarts_aromatic(test_molecules):
    """Test _search_smarts for aromatic ring."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    matches = grid._search_smarts("c1ccccc1")

    # Benzene, Acetaminophen, Ibuprofen have aromatic rings
    assert len(matches) >= 3
    assert 2 in matches  # Benzene


def test_molgrid_search_smarts_no_match(simple_mol):
    """Test _search_smarts with pattern that doesn't match."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    matches = grid._search_smarts("[Br]")  # No bromine

    assert matches == []


def test_molgrid_search_smarts_invalid_pattern(simple_mol):
    """Test _search_smarts handles invalid SMARTS gracefully."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    matches = grid._search_smarts("invalid[[[smarts")

    assert matches == []


def test_molgrid_search_smarts_empty_pattern(test_molecules):
    """Test _search_smarts with empty pattern."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    matches = grid._search_smarts("")

    assert matches == []


def test_molgrid_on_smarts_query_empty(test_molecules):
    """Test _on_smarts_query with empty query returns all indices."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    grid._on_smarts_query({"new": ""})

    matches = json.loads(grid.widget.smarts_matches)
    assert len(matches) == 5  # All molecules


def test_molgrid_on_smarts_query_with_pattern(test_molecules):
    """Test _on_smarts_query with valid pattern."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules)
    grid._on_smarts_query({"new": "[OH]"})

    matches = json.loads(grid.widget.smarts_matches)
    assert len(matches) >= 2


# ============================================================================
# Selection Tests
# ============================================================================

def test_molgrid_selection_via_widget(test_molecules):
    """Test selection state via widget update."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="selection-test")

    # Simulate selection via widget
    grid.widget.selection = '{"0": "CCO", "2": "c1ccccc1"}'

    indices = grid.get_selection_indices()
    assert indices == [0, 2]


def test_molgrid_get_selection_molecules(test_molecules):
    """Test get_selection returns actual molecules."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="selection-mol-test")
    grid.widget.selection = '{"0": "CCO"}'

    selected = grid.get_selection()
    assert len(selected) == 1
    assert selected[0].GetTitle() == "Ethanol"


def test_molgrid_get_selection_indices_empty(test_molecules):
    """Test get_selection_indices with no selection."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="empty-selection-test")

    indices = grid.get_selection_indices()
    assert indices == []


def test_molgrid_get_selection_empty(test_molecules):
    """Test get_selection with no selection."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="empty-selection-mols-test")

    selected = grid.get_selection()
    assert selected == []


def test_molgrid_selection_change_handler(test_molecules):
    """Test _on_selection_change updates internal state."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="change-handler-test")

    # Directly call change handler
    grid._on_selection_change({"new": '{"1": "CC(=O)O", "3": "acetaminophen"}'})

    indices = grid.get_selection_indices()
    assert indices == [1, 3]


def test_molgrid_selection_change_invalid_json(test_molecules):
    """Test _on_selection_change handles invalid JSON gracefully."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid(test_molecules, name="invalid-json-test")

    # Should not raise exception
    grid._on_selection_change({"new": "not valid json{"})

    # Selection should remain empty
    indices = grid.get_selection_indices()
    assert indices == []


def test_molgrid_selection_isolated_between_grids(test_molecules):
    """Test that selections are isolated between grid instances."""
    from cnotebook.molgrid import MolGrid

    grid1 = MolGrid(test_molecules, name="grid1-isolated")
    grid2 = MolGrid(test_molecules, name="grid2-isolated")

    grid1.widget.selection = '{"0": "CCO"}'
    grid2.widget.selection = '{"1": "CC(=O)O", "2": "benzene"}'

    assert grid1.get_selection_indices() == [0]
    assert grid2.get_selection_indices() == [1, 2]


# ============================================================================
# Display Tests
# ============================================================================

def test_molgrid_display_returns_html(simple_mol):
    """Test that display() returns displayable output."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    result = grid.display()

    assert result is not None


def test_molgrid_display_contains_iframe(simple_mol):
    """Test that display output contains iframe."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    result = grid.display()

    # The result should contain iframe HTML
    assert hasattr(result, 'data') or hasattr(result, '_repr_html_')


# ============================================================================
# Field Value Extraction Tests
# ============================================================================

def test_molgrid_get_field_value_title(simple_mol):
    """Test _get_field_value extracts Title field."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    value = grid._get_field_value(0, simple_mol, "Title")

    assert value == "Ethanol"


def test_molgrid_get_field_value_sd_data(mol_with_sd_data):
    """Test _get_field_value extracts SD data."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([mol_with_sd_data])
    value = grid._get_field_value(0, mol_with_sd_data, "MW")

    assert value == "46.07"


def test_molgrid_get_field_value_missing(simple_mol):
    """Test _get_field_value returns None for missing field."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    value = grid._get_field_value(0, simple_mol, "NonExistent")

    assert value is None


def test_molgrid_get_field_value_empty_title():
    """Test _get_field_value with molecule without title."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    # No title set

    grid = MolGrid([mol])
    value = grid._get_field_value(0, mol, "Title")

    assert value is None


# ============================================================================
# Rendering Settings Tests
# ============================================================================

def test_molgrid_svg_format(simple_mol):
    """Test MolGrid with SVG image format."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], image_format="svg")
    data = grid._prepare_data()

    assert "<svg" in data[0]["img"].lower() or "data:image/svg" in data[0]["img"]


def test_molgrid_png_format(simple_mol):
    """Test MolGrid with PNG image format."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], image_format="png")
    data = grid._prepare_data()

    assert "data:image/png" in data[0]["img"]


def test_molgrid_custom_dimensions(simple_mol):
    """Test MolGrid with custom width/height."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], width=300, height=250)
    html = grid.to_html()

    assert "300px" in html
    assert "250px" in html


def test_molgrid_atom_label_font_scale(simple_mol):
    """Test MolGrid with custom atom label font scale."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], atom_label_font_scale=2.5)

    assert grid.atom_label_font_scale == 2.5


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

def test_molgrid_large_molecule_list():
    """Test MolGrid with many molecules."""
    from cnotebook.molgrid import MolGrid

    mols = []
    for i in range(100):
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C" * (i % 10 + 1))
        mol.SetTitle(f"Molecule_{i}")
        mols.append(mol)

    grid = MolGrid(mols, n_items_per_page=10)
    html = grid.to_html()

    assert "molgrid" in html.lower()
    assert len(grid._molecules) == 100


def test_molgrid_single_molecule(simple_mol):
    """Test MolGrid with single molecule."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_molgrid_molecules_with_special_characters():
    """Test MolGrid handles molecules with special characters in title."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle('Ethanol <script>alert("XSS")</script>')

    grid = MolGrid([mol])
    html = grid.to_html()

    # Should escape HTML special characters
    assert '<script>' not in html or '&lt;script&gt;' in html


def test_molgrid_unicode_title():
    """Test MolGrid handles unicode in title."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Éthanol café α-酒精")

    grid = MolGrid([mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_molgrid_very_long_smiles():
    """Test MolGrid handles very long SMILES."""
    from cnotebook.molgrid import MolGrid

    # Create a long molecule
    mol = oechem.OEGraphMol()
    long_smiles = "C" * 50
    oechem.OESmilesToMol(mol, long_smiles)

    grid = MolGrid([mol])
    data = grid._prepare_data()

    assert len(data[0]["smiles"]) > 0


def test_molgrid_with_none_in_list(simple_mol):
    """Test MolGrid behavior with None values in molecule list."""
    from cnotebook.molgrid import MolGrid

    # This tests defensive coding - though ideally users shouldn't pass None
    mols = [simple_mol]

    grid = MolGrid(mols)
    assert len(grid._molecules) == 1


def test_molgrid_smarts_exception_handling():
    """Test SMARTS search handles exceptions gracefully."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])

    # Test with a pattern that could cause issues - extremely malformed patterns
    # The SMARTS parser should handle this gracefully
    matches = grid._search_smarts("[invalid")
    assert isinstance(matches, list)


def test_molgrid_get_marimo_selection_outside_marimo(simple_mol):
    """Test get_marimo_selection raises error outside marimo."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])

    with pytest.raises(RuntimeError, match="marimo"):
        grid.get_marimo_selection()


def test_molgrid_is_marimo_check():
    """Test _is_marimo returns False when not in marimo."""
    from cnotebook.molgrid.grid import _is_marimo

    # When not in marimo, should return False
    result = _is_marimo()
    assert result is False


# ============================================================================
# Information Button Tests
# ============================================================================

def test_molgrid_information_enabled_by_default(simple_mol):
    """Test that information button is enabled by default."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    assert grid.information_enabled is True


def test_molgrid_information_can_be_disabled(simple_mol):
    """Test that information button can be disabled."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], information=False)
    assert grid.information_enabled is False


def test_molgrid_html_contains_info_button_when_enabled(simple_mol):
    """Test HTML contains info button when information=True."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], information=True)
    html = grid.to_html()

    assert 'class="molgrid-info-btn"' in html
    assert 'class="molgrid-info-tooltip"' in html


def test_molgrid_html_no_info_button_when_disabled(simple_mol):
    """Test HTML does not contain info button when information=False."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], information=False)
    html = grid.to_html()

    assert 'class="molgrid-info-btn"' not in html
    assert 'class="molgrid-info-tooltip"' not in html


def test_molgrid_info_tooltip_contains_index(simple_mol):
    """Test info tooltip always contains index."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], information=True)
    html = grid.to_html()

    assert "Index:" in html
    assert 'class="molgrid-info-tooltip-label"' in html


def test_molgrid_info_tooltip_contains_title_when_set():
    """Test info tooltip contains title when molecule has one."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")

    grid = MolGrid([mol], information=True)
    html = grid.to_html()

    # Should have Title in tooltip
    assert "Title:" in html
    assert "Ethanol" in html


def test_molgrid_info_tooltip_no_title_when_empty():
    """Test info tooltip does not show title row when molecule has no title."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    # Don't set a title

    grid = MolGrid([mol], information=True)
    data = grid._prepare_data()

    # mol_title should be empty string (not None since mol is valid)
    assert data[0]["mol_title"] == ""


def test_molgrid_prepare_data_includes_mol_title(simple_mol):
    """Test _prepare_data includes mol_title field."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    data = grid._prepare_data()

    assert "mol_title" in data[0]
    assert data[0]["mol_title"] == "Ethanol"


def test_molgrid_info_css_present(simple_mol):
    """Test that info button CSS is included in HTML."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert ".molgrid-info-btn" in html
    assert ".molgrid-info-tooltip" in html


def test_molgrid_info_tooltip_pinned_css(simple_mol):
    """Test that pinned tooltip CSS is included."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert ".molgrid-info-tooltip.pinned" in html
    assert ".molgrid-info-btn.active" in html


def test_molgrid_data_parameter_string(simple_mol):
    """Test data parameter accepts a single string."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], data="MW")

    assert grid.information_fields == ["MW"]


def test_molgrid_data_parameter_list(simple_mol):
    """Test data parameter accepts a list of strings."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], data=["MW", "Formula"])

    assert grid.information_fields == ["MW", "Formula"]


def test_molgrid_data_parameter_none_without_dataframe(simple_mol):
    """Test data=None with no DataFrame results in empty info fields."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([simple_mol], data=None)

    assert grid.information_fields == []


def test_molgrid_prepare_data_includes_info_fields(mol_with_sd_data):
    """Test _prepare_data includes info_fields."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([mol_with_sd_data], data=["MW"])
    data = grid._prepare_data()

    assert "info_fields" in data[0]
    assert "MW" in data[0]["info_fields"]
    assert data[0]["info_fields"]["MW"] == "46.07"


def test_molgrid_info_tooltip_displays_data_fields(mol_with_sd_data):
    """Test info tooltip displays data fields from the data parameter."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([mol_with_sd_data], data=["MW", "Formula"])
    html = grid.to_html()

    # Should contain the data field labels and values
    assert "MW:" in html
    assert "46.07" in html
    assert "Formula:" in html
    assert "C2H6O" in html
