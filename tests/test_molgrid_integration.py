"""Integration tests for MolGrid."""

import pytest
from openeye import oechem


def create_test_molecules():
    """Create a set of test molecules.

    :returns: List of OEGraphMol objects with titles and SD data set.
    """
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


def test_full_workflow():
    """Test complete MolGrid workflow."""
    from cnotebook import MolGrid

    mols = create_test_molecules()

    # Create grid with correct parameter name (select, not selection)
    grid = MolGrid(
        mols,
        title_field="Title",
        tooltip_fields=["SMILES"],
        n_items_per_page=3,
        select=True,
    )

    # Generate HTML
    html = grid.to_html()
    assert "Ethanol" in html
    assert "Benzene" in html
    assert "pagination" in html.lower()

    # Test SMARTS search
    matches = grid._search_smarts("c1ccccc1")  # Aromatic ring
    assert len(matches) >= 3  # Benzene, Acetaminophen, Ibuprofen


def test_smarts_highlighting_quality():
    """Test that SMARTS search returns valid results."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccc(O)cc1")  # Phenol

    grid = MolGrid([mol], image_format="svg")
    matches = grid._search_smarts("[OH]")

    assert 0 in matches


def test_empty_grid():
    """Test MolGrid with no molecules."""
    from cnotebook import MolGrid

    grid = MolGrid([])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_invalid_molecules():
    """Test MolGrid handles invalid molecules gracefully."""
    from cnotebook import MolGrid

    valid = oechem.OEGraphMol()
    oechem.OESmilesToMol(valid, "CCO")

    invalid = oechem.OEGraphMol()  # Empty/invalid

    grid = MolGrid([valid, invalid])
    html = grid.to_html()

    # Should render without crashing
    assert "molgrid" in html.lower()


def test_multiple_smarts_searches():
    """Test sequential SMARTS searches work correctly."""
    from cnotebook import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols)

    # First search for hydroxyl group
    results1 = grid._search_smarts("[OH]")
    assert len(results1) >= 2  # Ethanol, Acetaminophen, Ibuprofen (carboxylic)

    # Second search for aromatic ring
    results2 = grid._search_smarts("c1ccccc1")
    assert len(results2) >= 3

    # Third search for carboxylic acid
    results3 = grid._search_smarts("C(=O)O")
    assert len(results3) >= 2  # Acetic Acid, Ibuprofen


def test_selection_workflow():
    """Test complete selection workflow."""
    from cnotebook import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols, name="integration-test-grid", select=True)

    # Simulate selection via widget
    grid.widget.selection = '{"0": "CCO", "2": "c1ccccc1"}'

    # Get selected molecules
    selected = grid.get_selection()
    assert len(selected) == 2

    # Get selected indices
    indices = grid.get_selection_indices()
    assert indices == [0, 2]


def test_custom_rendering_parameters():
    """Test grid with custom rendering parameters."""
    from cnotebook import MolGrid

    mols = create_test_molecules()

    grid = MolGrid(
        mols,
        width=200,
        height=150,
        image_format="svg",
        n_items_per_page=2,
    )

    assert grid.width == 200
    assert grid.height == 150
    assert grid.image_format == "svg"
    assert grid.n_items_per_page == 2

    html = grid.to_html()
    assert "<svg" in html.lower() or "data:image" in html


def test_tooltip_data_extraction():
    """Test that tooltip fields are correctly extracted."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    oechem.OESetSDData(mol, "MW", "46.07")
    oechem.OESetSDData(mol, "Formula", "C2H6O")

    grid = MolGrid([mol], tooltip_fields=["MW", "Formula"])
    data = grid._prepare_data()

    assert data[0]["tooltip"]["MW"] == "46.07"
    assert data[0]["tooltip"]["Formula"] == "C2H6O"


def test_grid_unique_naming():
    """Test that grids get unique names when not specified."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid1 = MolGrid([mol])
    grid2 = MolGrid([mol])

    assert grid1.name != grid2.name
    assert "molgrid-" in grid1.name
    assert "molgrid-" in grid2.name


def test_export_data_preparation():
    """Test that export data is correctly prepared."""
    from cnotebook import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols)
    export_data = grid._prepare_export_data()

    assert len(export_data) == 5
    assert export_data[0]["smiles"] == "CCO"
    assert export_data[0]["index"] == 0


def test_html_contains_all_menu_actions():
    """Test that HTML contains all action menu items."""
    from cnotebook import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols)
    html = grid.to_html()

    # Check for all action buttons
    assert "select-all" in html
    assert "clear-selection" in html
    assert "invert-selection" in html
    assert "copy-clipboard" in html
    assert "save-smiles" in html
    assert "save-csv" in html


def test_responsive_css_present():
    """Test that responsive CSS is included in HTML."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])
    html = grid.to_html()

    # Check for media queries
    assert "@media" in html


def test_search_fields_in_html():
    """Test that search fields are properly embedded in HTML."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    oechem.OESetSDData(mol, "Category", "Alcohol")

    grid = MolGrid([mol], search_fields=["Category"])
    html = grid.to_html()

    # Search fields should be embedded as JSON
    assert "searchFields" in html
    assert "Category" in html


def test_smarts_query_widget_integration():
    """Test SMARTS query through widget integration."""
    from cnotebook import MolGrid
    import json

    mols = create_test_molecules()
    grid = MolGrid(mols)

    # Simulate SMARTS query via widget
    grid._on_smarts_query({"new": "[OH]"})

    matches = json.loads(grid.widget.smarts_matches)
    assert isinstance(matches, list)
    assert len(matches) >= 2  # At least Ethanol and Acetaminophen


def test_smarts_query_empty_clears_filter():
    """Test that empty SMARTS query returns all molecules."""
    from cnotebook import MolGrid
    import json

    mols = create_test_molecules()
    grid = MolGrid(mols)

    # First filter with SMARTS
    grid._on_smarts_query({"new": "[OH]"})
    filtered = json.loads(grid.widget.smarts_matches)
    assert len(filtered) < 5

    # Then clear filter
    grid._on_smarts_query({"new": ""})
    all_matches = json.loads(grid.widget.smarts_matches)
    assert len(all_matches) == 5


def test_multiple_grid_instances():
    """Test multiple grid instances don't interfere."""
    from cnotebook import MolGrid

    mols1 = create_test_molecules()[:2]
    mols2 = create_test_molecules()[2:]

    grid1 = MolGrid(mols1, name="grid1")
    grid2 = MolGrid(mols2, name="grid2")

    # Set different selections
    grid1.widget.selection = '{"0": "CCO"}'
    grid2.widget.selection = '{"0": "benzene"}'

    # Verify isolation
    assert grid1.get_selection_indices() == [0]
    assert grid2.get_selection_indices() == [0]
    assert grid1.get_selection()[0].GetTitle() == "Ethanol"
    assert grid2.get_selection()[0].GetTitle() == "Benzene"


def test_large_dataset_performance():
    """Test MolGrid handles larger datasets."""
    from cnotebook import MolGrid

    mols = []
    for i in range(50):
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, f"C{'C' * (i % 10)}")
        mol.SetTitle(f"Mol_{i}")
        mols.append(mol)

    grid = MolGrid(mols, n_items_per_page=10)

    # Should complete without timeout
    html = grid.to_html()
    assert "molgrid" in html.lower()

    # Test SMARTS search on larger set
    matches = grid._search_smarts("CC")
    assert len(matches) > 0
