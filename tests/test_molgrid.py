"""Tests for MolGrid interactive molecule grid."""


def test_molgrid_import():
    """Test that MolGrid can be imported."""
    from cnotebook.molgrid import MolGrid
    assert MolGrid is not None


def test_molgrid_stores_molecules():
    """Test that MolGrid stores molecule data."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol1.SetTitle("Ethanol")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    grid = MolGrid([mol1, mol2])

    assert len(grid._molecules) == 2
    assert grid._molecules[0].GetTitle() == "Ethanol"


def test_molgrid_extracts_data():
    """Test that MolGrid extracts molecule data for display."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    oechem.OESetSDData(mol, "MW", "46.07")

    grid = MolGrid([mol], title_field="Title", tooltip_fields=["MW"])
    data = grid._prepare_data()

    assert len(data) == 1
    assert data[0]["index"] == 0
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == "46.07"


def test_molgrid_renders_images():
    """Test that MolGrid renders molecule images."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol], width=150, height=100, image_format="svg")
    data = grid._prepare_data()

    assert "img" in data[0]
    assert "<svg" in data[0]["img"] or "data:image" in data[0]["img"]


def test_molgrid_generates_html():
    """Test that MolGrid generates HTML output."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")

    grid = MolGrid([mol])
    html = grid.to_html()

    assert "<html" in html.lower()
    assert "molgrid" in html.lower()
    assert "Ethanol" in html


def test_molgrid_creates_widget():
    """Test that MolGrid creates an AnyWidget."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])

    assert grid.widget is not None
    assert hasattr(grid.widget, 'grid_id')


def test_molgrid_smarts_search():
    """Test that MolGrid performs SMARTS search with highlighting."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")  # Has OH
    mol1.SetTitle("Ethanol")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")  # No OH
    mol2.SetTitle("Ethane")

    grid = MolGrid([mol1, mol2])
    results = grid._process_smarts_search("[OH]")

    assert "matches" in results
    assert len(results["matches"]) == 1
    assert 0 in results["matches"]  # Ethanol matches
    assert "img" in results["matches"][0]


def test_molgrid_invalid_smarts():
    """Test that MolGrid handles invalid SMARTS gracefully."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])
    results = grid._process_smarts_search("invalid[[[smarts")

    assert "error" in results


def test_molgrid_selection():
    """Test that MolGrid tracks selection state."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    grid = MolGrid([mol1, mol2], name="test-grid")

    # Simulate selection via widget
    grid.widget.selection = '{"0": "CCO"}'

    selection = grid.get_selection()
    assert len(selection) == 1

    indices = grid.get_selection_indices()
    assert indices == [0]


def test_molgrid_display_returns_html():
    """Test that display() returns displayable output."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])
    result = grid.display()

    # Should return something displayable
    assert result is not None


def test_molgrid_filter():
    """Test that MolGrid can filter by mask."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    mol3 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol3, "C")

    grid = MolGrid([mol1, mol2, mol3])
    grid.filter([True, False, True])

    assert grid.widget.filter_mask == [True, False, True]


def test_molgrid_filter_by_index():
    """Test that MolGrid can filter by indices."""
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    mol3 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol3, "C")

    grid = MolGrid([mol1, mol2, mol3])
    grid.filter_by_index([0, 2])

    assert grid.widget.filter_mask == [True, False, True]
