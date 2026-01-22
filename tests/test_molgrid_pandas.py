"""Tests for MolGrid pandas integration."""

import pytest

pytest.importorskip("pandas")
pytest.importorskip("oepandas")


def test_series_molgrid():
    """Test that Series.chem.molgrid() works."""
    import pandas as pd
    from openeye import oechem
    import oepandas as oepd
    import cnotebook

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol1.SetTitle("Ethanol")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    df = pd.DataFrame({"mol": [mol1, mol2], "MW": [46.07, 30.07]})
    df["mol"] = df["mol"].astype(oepd.MoleculeDtype())

    grid = df["mol"].chem.molgrid()

    assert grid is not None
    assert len(grid._molecules) == 2


def test_dataframe_molgrid():
    """Test that DataFrame.chem.molgrid() works."""
    import pandas as pd
    from openeye import oechem
    import oepandas as oepd
    import cnotebook

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol1.SetTitle("Ethanol")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    df = pd.DataFrame({"mol": [mol1, mol2], "Name": ["Ethanol", "Ethane"], "MW": [46.07, 30.07]})
    df["mol"] = df["mol"].astype(oepd.MoleculeDtype())

    grid = df.chem.molgrid(mol_col="mol", title_field="Name", tooltip_fields=["MW"])

    assert grid is not None
    data = grid._prepare_data()
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == 46.07
