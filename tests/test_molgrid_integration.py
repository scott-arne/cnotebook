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
    from cnotebook.molgrid import MolGrid

    mols = create_test_molecules()

    # Create grid
    grid = MolGrid(
        mols,
        title_field="Title",
        tooltip_fields=["SMILES"],
        n_items_per_page=3,
        selection=True,
    )

    # Generate HTML
    html = grid.to_html()
    assert "Ethanol" in html
    assert "Benzene" in html
    assert "pagination" in html.lower()

    # Test SMARTS search
    results = grid._process_smarts_search("c1ccccc1")  # Aromatic ring
    assert results["count"] >= 3  # Benzene, Acetaminophen, Ibuprofen

    # Test filtering
    grid.filter([True, True, False, False, False])
    assert grid.widget.filter_mask == [True, True, False, False, False]


def test_smarts_highlighting_quality():
    """Test that SMARTS highlighting produces valid SVG."""
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccc(O)cc1")  # Phenol

    grid = MolGrid([mol], image_format="svg")
    results = grid._process_smarts_search("[OH]")

    assert 0 in results["matches"]
    img = results["matches"][0]["img"]

    # Should be valid SVG
    assert "<svg" in img.lower() or "data:image" in img


def test_empty_grid():
    """Test MolGrid with no molecules."""
    from cnotebook.molgrid import MolGrid

    grid = MolGrid([])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_invalid_molecules():
    """Test MolGrid handles invalid molecules gracefully."""
    from cnotebook.molgrid import MolGrid

    valid = oechem.OEGraphMol()
    oechem.OESmilesToMol(valid, "CCO")

    invalid = oechem.OEGraphMol()  # Empty/invalid

    grid = MolGrid([valid, invalid])
    html = grid.to_html()

    # Should render without crashing
    assert "molgrid" in html.lower()


def test_multiple_smarts_searches():
    """Test sequential SMARTS searches work correctly."""
    from cnotebook.molgrid import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols)

    # First search for hydroxyl group
    results1 = grid._process_smarts_search("[OH]")
    assert results1["count"] >= 2  # Ethanol, Acetaminophen, Ibuprofen (carboxylic)

    # Second search for aromatic ring
    results2 = grid._process_smarts_search("c1ccccc1")
    assert results2["count"] >= 3

    # Third search for carboxylic acid
    results3 = grid._process_smarts_search("C(=O)O")
    assert results3["count"] >= 2  # Acetic Acid, Ibuprofen


def test_filter_then_clear():
    """Test filtering and clearing filter."""
    from cnotebook.molgrid import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols)

    # Apply filter
    grid.filter([True, False, True, False, True])
    assert grid.widget.filter_mask == [True, False, True, False, True]

    # Clear filter by showing all
    grid.filter([True, True, True, True, True])
    assert grid.widget.filter_mask == [True, True, True, True, True]


def test_selection_workflow():
    """Test complete selection workflow."""
    from cnotebook.molgrid import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols, name="integration-test-grid", selection=True)

    # Simulate selection via widget
    grid.widget.selection = '{"0": "CCO", "2": "c1ccccc1"}'

    # Get selected molecules
    selected = grid.get_selection()
    assert len(selected) == 2

    # Get selected indices
    indices = grid.get_selection_indices()
    assert indices == [0, 2]


def test_filter_by_index_then_select():
    """Test filtering by index then selecting."""
    from cnotebook.molgrid import MolGrid

    mols = create_test_molecules()
    grid = MolGrid(mols, name="filter-select-test")

    # Filter to show only first 3
    grid.filter_by_index([0, 1, 2])
    assert grid.widget.filter_mask == [True, True, True, False, False]

    # Simulate selection
    grid.widget.selection = '{"1": "CC(=O)O"}'

    indices = grid.get_selection_indices()
    assert indices == [1]


def test_custom_rendering_parameters():
    """Test grid with custom rendering parameters."""
    from cnotebook.molgrid import MolGrid

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
    from cnotebook.molgrid import MolGrid

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
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid1 = MolGrid([mol])
    grid2 = MolGrid([mol])

    assert grid1.name != grid2.name
    assert "molgrid-" in grid1.name
    assert "molgrid-" in grid2.name
