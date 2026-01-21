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
