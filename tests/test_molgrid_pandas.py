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


def test_dataframe_molgrid_auto_detect_search_fields():
    """Test that string columns are auto-detected as search fields."""
    import pandas as pd
    from openeye import oechem
    import oepandas as oepd
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": ["Ethanol", "Ethane"],
        "Category": ["Alcohol", "Alkane"],
        "MW": [46.07, 30.07],
    })

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")

    # Should auto-detect Name and Category as string columns
    assert grid.search_fields is not None
    assert "Name" in grid.search_fields
    assert "Category" in grid.search_fields
    # MW is float, should not be in search_fields
    assert "MW" not in grid.search_fields
    # Molecule column should be excluded
    assert "Molecule" not in grid.search_fields


def test_dataframe_molgrid_auto_detect_str_dtype():
    """Test auto-detection with pandas string dtype."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": pd.array(["Ethanol", "Ethane"], dtype="string"),
        "MW": [46.07, 30.07],
    })

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")

    # Should detect 'string' dtype as searchable
    assert "Name" in grid.search_fields


def test_dataframe_molgrid_explicit_search_fields_override():
    """Test that explicit search_fields overrides auto-detection."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["Ethanol"],
        "Category": ["Alcohol"],
    })

    # Explicitly set only "Category" as search field
    grid = MolGrid([mol], dataframe=df, mol_col="Molecule", search_fields=["Category"])

    assert grid.search_fields == ["Category"]
    assert "Name" not in grid.search_fields


def test_dataframe_molgrid_no_string_columns():
    """Test auto-detection with no string columns."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "MW": [46.07],
        "NumAtoms": [9],
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")

    # Should have empty search_fields since no string columns
    assert grid.search_fields == []


def test_dataframe_molgrid_export_data_includes_columns():
    """Test that export data includes DataFrame columns."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": ["Ethanol", "Ethane"],
        "MW": [46.07, 30.07],
    })

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")
    export_data = grid._prepare_export_data()

    assert len(export_data) == 2
    assert export_data[0]["smiles"] == "CCO"
    assert export_data[0]["Name"] == "Ethanol"
    assert export_data[0]["MW"] == "46.07"
    # Molecule column should be excluded
    assert "Molecule" not in export_data[0]


def test_dataframe_molgrid_get_field_value_from_dataframe():
    """Test _get_field_value retrieves from DataFrame."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("MolTitle")  # Different from DataFrame

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["DFName"],
        "Title": ["DFTitle"],
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")

    # DataFrame column takes precedence
    assert grid._get_field_value(0, mol, "Name") == "DFName"
    assert grid._get_field_value(0, mol, "Title") == "DFTitle"


def test_dataframe_molgrid_fallback_to_molecule_property():
    """Test _get_field_value falls back to molecule property."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("MolTitle")
    oechem.OESetSDData(mol, "CustomProp", "CustomValue")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["DFName"],
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")

    # CustomProp not in DataFrame, should fall back to SD data
    assert grid._get_field_value(0, mol, "CustomProp") == "CustomValue"


def test_dataframe_molgrid_search_fields_extracted():
    """Test that search fields are extracted in _prepare_data."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["Ethanol"],
        "Category": ["Alcohol"],
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")
    data = grid._prepare_data()

    assert "search_fields" in data[0]
    assert data[0]["search_fields"]["Name"] == "Ethanol"
    assert data[0]["search_fields"]["Category"] == "Alcohol"


def test_dataframe_molgrid_html_contains_search_field_values():
    """Test that HTML contains search field values for List.js."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["Ethanol"],
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")
    html = grid.to_html()

    # Search field value should be in HTML (hidden span for List.js)
    assert "Ethanol" in html
    assert 'class="Name"' in html


def test_dataframe_molgrid_empty_dataframe():
    """Test MolGrid with empty DataFrame."""
    import pandas as pd
    from cnotebook.molgrid import MolGrid

    df = pd.DataFrame({"Molecule": [], "Name": []})

    grid = MolGrid([], dataframe=df, mol_col="Molecule")

    assert len(grid._molecules) == 0
    html = grid.to_html()
    assert "molgrid" in html.lower()


def test_dataframe_molgrid_with_none_values():
    """Test MolGrid handles None/NaN values in DataFrame."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": ["Ethanol", None],  # One None value
    })

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")
    data = grid._prepare_data()

    # Should handle None gracefully
    assert data[0]["search_fields"]["Name"] == "Ethanol"
    # None should be handled (converted to None or empty)


def test_dataframe_molgrid_skips_molecule_dtype():
    """Test that MoleculeDtype columns are excluded from search fields."""
    import pandas as pd
    from openeye import oechem
    import oepandas as oepd
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["Ethanol"],
    })
    df["Molecule"] = df["Molecule"].astype(oepd.MoleculeDtype())

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")

    # Molecule column should be excluded even if it's object dtype
    assert "Molecule" not in grid.search_fields
    assert "Name" in grid.search_fields


def test_dataframe_molgrid_export_empty_string_values():
    """Test _prepare_export_data handles empty string values."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": ["Ethanol", ""],  # Empty string value
        "Category": [None, "Alkane"],  # None value
    })

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")
    export_data = grid._prepare_export_data()

    # Empty string should be preserved or converted appropriately
    assert export_data[0]["Name"] == "Ethanol"
    # The export should not crash on empty/None values
    assert len(export_data) == 2


def test_dataframe_molgrid_category_dtype_fallback():
    """Test auto-detection falls back to checking actual values for category dtype."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")

    df = pd.DataFrame({
        "Molecule": [mol1, mol2],
        "Name": ["Ethanol", "Ethane"],
    })
    # Convert to category dtype - this may trigger the fallback branch
    df["Name"] = df["Name"].astype("category")

    grid = MolGrid([mol1, mol2], dataframe=df, mol_col="Molecule")

    # Category dtype with string values should be detected
    # (either by dtype name or fallback to value checking)
    assert "Name" in grid.search_fields


def test_dataframe_molgrid_integer_column_excluded():
    """Test that integer columns are excluded from search fields."""
    import pandas as pd
    from openeye import oechem
    from cnotebook.molgrid import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({
        "Molecule": [mol],
        "Name": ["Ethanol"],
        "AtomCount": [9],
        "Index": pd.array([1], dtype="int32"),
    })

    grid = MolGrid([mol], dataframe=df, mol_col="Molecule")

    # Integer columns should be excluded
    assert "AtomCount" not in grid.search_fields
    assert "Index" not in grid.search_fields
    # String column should be included
    assert "Name" in grid.search_fields
