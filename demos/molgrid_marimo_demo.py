"""MolGrid Demo - Marimo Notebook

This notebook demonstrates the MolGrid interactive molecule grid visualization component.

MolGrid provides an interactive grid for browsing, searching, and selecting molecules
with features including:

- Pagination for large datasets
- Text search by molecular properties
- SMARTS substructure filtering
- Selection with export to SMILES/CSV
- Info tooltips with molecular data
- Full DataFrame integration

Run with: marimo run molgrid_marimo_demo.py
"""

import marimo

__generated_with = "0.10.0"
app = marimo.App(width="medium")


@app.cell
def setup():
    """Import required packages."""
    import marimo as mo
    import cnotebook
    from cnotebook import MolGrid, molgrid
    from openeye import oechem
    import pandas as pd
    import oepandas as oepd

    return MolGrid, cnotebook, mo, molgrid, oechem, oepd, pd


@app.cell
def intro(mo):
    """Introduction."""
    mo.md(
        """
        # MolGrid Demo - Marimo

        This notebook demonstrates the MolGrid interactive molecule grid visualization
        component in a Marimo environment.

        **Features:**
        - Pagination for large datasets
        - Text search by molecular properties
        - SMARTS substructure filtering
        - Selection with export to SMILES/CSV
        - Info tooltips with molecular data
        - Full DataFrame integration
        """
    )
    return


@app.cell
def create_molecules(oechem):
    """Create test molecules."""
    smiles_data = [
        ("CCO", "Ethanol"),
        ("CC(=O)O", "Acetic Acid"),
        ("c1ccccc1", "Benzene"),
        ("CC(=O)Nc1ccc(O)cc1", "Acetaminophen"),
        ("CC(C)Cc1ccc(C(C)C(=O)O)cc1", "Ibuprofen"),
        ("CN1C=NC2=C1C(=O)N(C(=O)N2C)C", "Caffeine"),
        ("CC(=O)OC1=CC=CC=C1C(=O)O", "Aspirin"),
        ("CN1CCC[C@H]1c2cccnc2", "Nicotine"),
        ("CC12CCC3C(C1CCC2O)CCC4=CC(=O)CCC34C", "Testosterone"),
        ("CC(=O)OCC(=O)[C@@]1(CC[C@@H]2[C@@]1(CC[C@H]3[C@H]2CCC4=CC(=O)CC[C@]34C)C)O", "Cortisone"),
        ("C1=CC=C(C=C1)C(C2=CC=CC=C2)N3C=CN=C3", "Clotrimazole"),
        ("CC1=C(C(=O)N(N1C)C2=CC=CC=C2)N(C)CS(=O)(=O)O", "Metamizole"),
    ]

    molecules = []
    for smi, name in smiles_data:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smi)
        mol.SetTitle(name)
        oechem.OESetSDData(mol, "MW", f"{oechem.OECalculateMolecularWeight(mol):.2f}")
        oechem.OESetSDData(mol, "Formula", oechem.OEMolecularFormula(mol))
        molecules.append(mol)

    return molecules, smiles_data


@app.cell
def basic_usage_header(mo):
    """Basic usage header."""
    mo.md(
        """
        ## Basic Usage

        The simplest way to use MolGrid is to pass a list of OpenEye molecule objects.
        """
    )
    return


@app.cell
def basic_grid(MolGrid, molecules):
    """Create a basic grid."""
    grid = MolGrid(molecules, n_items_per_page=6)
    return grid,


@app.cell
def display_basic_grid(grid):
    """Display the basic grid."""
    grid.display()


@app.cell
def customization_header(mo):
    """Customization header."""
    mo.md(
        """
        ## Customizing the Display

        ### Image Size and Format

        Customize molecule image dimensions and format using the width, height, and
        image_format parameters.
        """
    )
    return


@app.cell
def custom_grid(MolGrid, molecules):
    """Create a customized grid."""
    custom_grid = MolGrid(
        molecules,
        width=150,
        height=150,
        image_format="svg",
        n_items_per_page=8,
        title_field="Title",
    )
    return custom_grid,


@app.cell
def display_custom_grid(custom_grid):
    """Display customized grid."""
    custom_grid.display()


@app.cell
def search_header(mo):
    """Search and filtering header."""
    mo.md(
        """
        ## Search and Filtering

        MolGrid provides two search modes:

        1. **Properties Mode**: Text search across molecule titles and properties
        2. **SMARTS Mode**: Substructure filtering using SMARTS patterns

        Use the toggle switch in the toolbar to switch between modes.

        **Try searching for:**
        - Properties mode: "acid" or "caffeine"
        - SMARTS mode: "c1ccccc1" (aromatic ring) or "[OH]" (hydroxyl group)
        """
    )
    return


@app.cell
def search_grid(MolGrid, molecules):
    """Create a grid for search demonstration."""
    search_grid = MolGrid(molecules, n_items_per_page=8)
    return search_grid,


@app.cell
def display_search_grid(search_grid):
    """Display search grid."""
    search_grid.display()


@app.cell
def selection_header(mo):
    """Selection header."""
    mo.md(
        """
        ## Selection

        Selection is enabled by default. Click on molecules or use the checkbox to select them.

        The "..." menu in the toolbar provides selection actions:
        - **Select All**: Select all visible (filtered) molecules
        - **Clear Selection**: Deselect all molecules
        - **Invert Selection**: Toggle selection state
        - **Copy to Clipboard**: Copy selected molecules as CSV
        - **Save to SMILES**: Download as .smi file
        - **Save to CSV**: Download as .csv file
        """
    )
    return


@app.cell
def selection_grid(MolGrid, molecules):
    """Create a grid for selection demonstration."""
    selection_grid = MolGrid(molecules, select=True, name="selection-demo")
    return selection_grid,


@app.cell
def display_selection_grid(selection_grid):
    """Display selection grid."""
    selection_grid.display()


@app.cell
def get_selection(mo, selection_grid):
    """Display selected molecules."""
    selected_mols = selection_grid.get_selection()
    indices = selection_grid.get_selection_indices()

    if selected_mols:
        names = [mol.GetTitle() for mol in selected_mols]
        mo.md(
            f"""
            ### Selected Molecules

            **Count:** {len(selected_mols)}

            **Names:** {', '.join(names)}

            **Indices:** {indices}
            """
        )
    else:
        mo.md("*No molecules selected. Click on molecules in the grid above to select them.*")
    return indices, selected_mols


@app.cell
def info_button_header(mo):
    """Info button header."""
    mo.md(
        """
        ## Info Button and Tooltips

        Each molecule cell has an info button ("i") in the top-right corner.

        - **Hover** over the "i" to see the tooltip
        - **Click** the "i" to pin the tooltip open (useful for comparing molecules)
        - **Click again** to unpin

        The info button shows:
        - Index (always)
        - Title (if available)
        - Any columns specified via the `data` parameter
        """
    )
    return


@app.cell
def info_grid(MolGrid, molecules):
    """Create a grid with info fields."""
    info_grid = MolGrid(
        molecules,
        data=["MW", "Formula"],
        n_items_per_page=6,
    )
    return info_grid,


@app.cell
def display_info_grid(info_grid):
    """Display info grid."""
    info_grid.display()


@app.cell
def dataframe_header(mo):
    """DataFrame integration header."""
    mo.md(
        """
        ## DataFrame Integration

        MolGrid integrates seamlessly with Pandas DataFrames containing molecule columns.
        When using a DataFrame, MolGrid automatically detects:
        - String columns for text search
        - All simple type columns for info tooltips
        """
    )
    return


@app.cell
def create_dataframe(oechem, oepd, pd):
    """Create a DataFrame with molecules."""
    df = pd.DataFrame(
        {
            "Name": [
                "Ethanol",
                "Benzene",
                "Acetaminophen",
                "Ibuprofen",
                "Caffeine",
                "Aspirin",
            ],
            "SMILES": [
                "CCO",
                "c1ccccc1",
                "CC(=O)Nc1ccc(O)cc1",
                "CC(C)Cc1ccc(C(C)C(=O)O)cc1",
                "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
                "CC(=O)OC1=CC=CC=C1C(=O)O",
            ],
            "Category": ["Alcohol", "Aromatic", "Analgesic", "NSAID", "Stimulant", "NSAID"],
            "MW": [46.07, 78.11, 151.16, 206.28, 194.19, 180.16],
        }
    )

    # Convert SMILES to molecules
    mols = []
    for _, row in df.iterrows():
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, row["SMILES"])
        mol.SetTitle(row["Name"])
        mols.append(mol)

    df["Molecule"] = mols
    df["Molecule"] = df["Molecule"].astype(oepd.MoleculeDtype())

    return df, mols


@app.cell
def show_dataframe(df, mo):
    """Display the DataFrame."""
    mo.md("### Sample DataFrame")
    return


@app.cell
def display_df(df):
    """Show DataFrame."""
    df


@app.cell
def df_grid(MolGrid, df):
    """Create a grid from DataFrame."""
    df_grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
        data=["Category", "MW"],
        n_items_per_page=6,
    )
    return df_grid,


@app.cell
def display_df_grid(df_grid):
    """Display DataFrame grid."""
    df_grid.display()


@app.cell
def auto_detection(df_grid, mo):
    """Show auto-detected fields."""
    mo.md(
        f"""
        ### Auto-Detected Fields

        **Search Fields:** {df_grid.search_fields}

        **Info Fields:** {df_grid.information_fields}
        """
    )
    return


@app.cell
def complete_example_header(mo):
    """Complete example header."""
    mo.md(
        """
        ## Complete Example

        Here is a comprehensive example combining multiple features.
        """
    )
    return


@app.cell
def complete_grid(MolGrid, df):
    """Create a comprehensive grid."""
    complete_grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
        title_field="Name",
        tooltip_fields=["SMILES"],
        data=["Category", "MW"],
        n_items_per_page=6,
        width=180,
        height=180,
        image_format="svg",
        select=True,
        information=True,
        name="complete-demo",
    )
    return complete_grid,


@app.cell
def display_complete_grid(complete_grid):
    """Display comprehensive grid."""
    complete_grid.display()


@app.cell
def api_reference(mo):
    """API Reference."""
    mo.md(
        """
        ## API Reference

        ### MolGrid Parameters

        | Parameter | Type | Default | Description |
        |-----------|------|---------|-------------|
        | `mols` | Iterable | (required) | OpenEye molecule objects |
        | `dataframe` | DataFrame | None | Optional DataFrame with molecule data |
        | `mol_col` | str | None | Column name containing molecules |
        | `title_field` | str | "Title" | Field to display as title (None to hide) |
        | `tooltip_fields` | List[str] | None | Fields for hover tooltip |
        | `n_items_per_page` | int | 24 | Molecules per page |
        | `width` | int | 200 | Image width in pixels |
        | `height` | int | 200 | Image height in pixels |
        | `atom_label_font_scale` | float | 1.5 | Scale factor for atom labels |
        | `image_format` | str | "svg" | Image format ("svg" or "png") |
        | `select` | bool | True | Enable selection checkboxes |
        | `information` | bool | True | Enable info button |
        | `data` | str/List[str] | None | Columns for info tooltip |
        | `search_fields` | List[str] | None | Fields for text search |
        | `name` | str | None | Grid identifier |

        ### MolGrid Methods

        | Method | Returns | Description |
        |--------|---------|-------------|
        | `display()` | HTML | Display the grid in the notebook |
        | `to_html()` | str | Generate HTML representation |
        | `get_selection()` | List[OEMol] | Get selected molecule objects |
        | `get_selection_indices()` | List[int] | Get indices of selected molecules |
        """
    )
    return


if __name__ == "__main__":
    app.run()
