"""Tests for MolGrid polars integration."""

import pytest

pytest.importorskip("polars")
pytest.importorskip("oepolars")

import cnotebook as _cnotebook  # noqa: E402,F401


def test_polars_series_molgrid():
    """Test that Polars Series.chem.molgrid() works."""
    import polars as pl
    from openeye import oechem

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol1.SetTitle("Ethanol")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    df = pl.DataFrame({"mol": [mol1, mol2], "MW": [46.07, 30.07]})

    grid = df["mol"].chem.molgrid()

    assert grid is not None
    assert len(grid._molecules) == 2


def test_polars_dataframe_molgrid():
    """Test that Polars DataFrame.chem.molgrid() works."""
    import polars as pl
    from openeye import oechem

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pl.DataFrame({
        "mol": [mol1, mol2],
        "Name": ["Ethanol", "Ethane"],
        "MW": [46.07, 30.07]
    })

    grid = df.chem.molgrid(mol_col="mol", title="Name", tooltip_fields=["MW"])

    assert grid is not None
    data = grid._prepare_data()
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == 46.07


def test_polars_selection_frame_stays_polars():
    """Test the accessor hands its own frame over, so selection_frame() is polars."""
    import polars as pl
    from openeye import oechem

    mols = []
    for smiles in ("CCO", "CC", "CCC"):
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pl.DataFrame({
        "mol": mols,
        "Name": ["Ethanol", "Ethane", "Propane"],
        "MW": [46.07, 30.07, 44.10],
    })

    grid = df.chem.molgrid(mol_col="mol", title="Name")
    grid.selection = [2, 0]

    frame = grid.selection_frame()

    # A pandas conversion in the accessor would return a pandas frame from here, and
    # every polars caller would have to convert it back.
    assert isinstance(frame, pl.DataFrame)
    assert frame["Name"].to_list() == ["Ethanol", "Propane"]
    assert frame["MW"].to_list() == [46.07, 44.10]
    assert frame.height == 2
