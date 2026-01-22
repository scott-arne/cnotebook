"""Tests for MolGrid polars integration."""

import pytest

pytest.importorskip("polars")
pytest.importorskip("oepolars")


def test_polars_series_molgrid():
    """Test that Polars Series.chem.molgrid() works."""
    import polars as pl
    from openeye import oechem
    import oepolars as oepl
    import cnotebook

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
    import oepolars as oepl
    import cnotebook

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pl.DataFrame({
        "mol": [mol1, mol2],
        "Name": ["Ethanol", "Ethane"],
        "MW": [46.07, 30.07]
    })

    grid = df.chem.molgrid(mol_col="mol", title_field="Name", tooltip_fields=["MW"])

    assert grid is not None
    data = grid._prepare_data()
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == 46.07
