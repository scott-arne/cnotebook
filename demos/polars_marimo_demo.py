import marimo

__generated_with = "0.19.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import cnotebook
    from cnotebook import molgrid
    import polars as pl
    import oepolars as oeplr
    from pathlib import Path
    from openeye import oechem, oedepict

    DEMO_DIRECTORY = Path(__file__).parent
    return DEMO_DIRECTORY, cnotebook, mo, molgrid, oechem, oedepict, oeplr, pl


@app.cell
def _(mo):
    mo.md(r"""
    # Basic Usage

    **Rendering Basic Molecules**

    Let's start with just viewing any object that derives from```oechem.OEMolBase``` (scroll further if you are looking for Polars examples).
    """)
    return


@app.cell
def _(oechem):
    pyrimidine = oechem.OEGraphMol()
    oechem.OESmilesToMol(pyrimidine, "n1cnccc1")
    pyrimidine
    return (pyrimidine,)


@app.cell
def _(mo):
    mo.md(r"""
    How did this happen? When Marimo encounters the bare mol statement, it tries to display the molecule in any way it knows how. Usually this will just be an obscure string representation of a molecule that OpenEye provides: `oechem.OEGraphMol; proxy of ....` However, CNotebook has informed Marimo on how to display molecules, so we see an image rather than that obscure string representation.

    **Rendering OE2DMolDisplay Objects**

    The same works with OE2DMolDisplay objects, which can include advanced rendering. For example, adding atom indices to the depiction of the molecule that we just created:
    """)
    return


@app.cell
def _(oechem, oedepict, pyrimidine):
    # Prepare the molecule for depiction
    oedepict.OEPrepareDepiction(pyrimidine)

    # Set the depiction options
    _opts = oedepict.OE2DMolDisplayOptions(250, 250, oedepict.OEScale_AutoScale)
    _opts.SetAtomPropertyFunctor(oedepict.OEDisplayAtomIdx())
    _opts.SetAtomPropLabelFont(oedepict.OEFont(oechem.OEDarkGreen))

    # Create the display object
    _disp = oedepict.OE2DMolDisplay(pyrimidine, _opts)

    # Display the molecule
    _disp
    return


@app.cell
def _(mo):
    mo.md(r"""
    Another popular example is to add SMARTS substructure highlighting.
    """)
    return


@app.cell
def _(oechem, oedepict, pyrimidine):
    # Prepare the molecule for depiction
    oedepict.OEPrepareDepiction(pyrimidine)

    # Highlight the aromatic N-C-N in the molecule
    _subs = oechem.OESubSearch("ncn")

    _opts = oedepict.OE2DMolDisplayOptions(250, 250, oedepict.OEScale_AutoScale)
    _opts.SetAtomPropertyFunctor(oedepict.OEDisplayAtomIdx())
    _opts.SetAtomPropLabelFont(oedepict.OEFont(oechem.OEDarkGreen))
    _disp = oedepict.OE2DMolDisplay(pyrimidine, _opts)

    # Highlight all the matches in the molecule
    for _match in _subs.Match(pyrimidine, True):
        oedepict.OEAddHighlighting(
            _disp,
            oechem.OEColor(oechem.OELightBlue),
            oedepict.OEHighlightStyle_Stick,
            _match
        )

    # Display the molecule
    _disp
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Displaying Grids of Molecules

    Sometimes you want to see several molecules in an interactive grid. Use `molgrid` for this:

    ```python
    from cnotebook import molgrid

    grid = molgrid(molecules)
    grid.display()

    # Later, retrieve selected molecules
    selected = grid.get_selection()
    ```

    MolGrid provides an interactive grid with:
    * Pagination for large datasets
    * Row selection
    * Search/filtering
    * Export functionality
    """)
    return


@app.cell
def _(molgrid, oechem):
    # Create some sample molecules
    example_mols = []
    for _i, _smi in enumerate(["n1cnccc1", "c1ccccc1", "CCO", "C(=O)O", "CCCC"]):
        _mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(_mol, _smi)

        # We can title them too!
        _mol.SetTitle(f'Molecule {_i+1}')

        example_mols.append(_mol)

    # Render into an interactive grid
    grid = molgrid(example_mols)
    grid.display()
    return (example_mols, grid)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Advanced: Changing the Rendering Options

    Basic rendering of molecules within Jupyter Notebooks is controlled by a global context. For simplicity, modifying the global context affects the display of molecules both in Marimo (i.e., when you display molecules as above) and in Polars, which has not yet been introduced.
    """)
    return


@app.cell
def _(cnotebook, example_mols):
    ctx = cnotebook.cnotebook_context.get()
    ctx.height = 50
    ctx.width = 50

    # Display the original molecule again (but tiny)
    example_mols[0]
    return (ctx,)


@app.cell
def _(ctx, example_mols):
    # Restore the settings
    ctx.reset()

    # Show the molecule again to prove the settings have been restored
    example_mols[0]
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    By default, molecules scale with their size, meaning a really big molecule could take up the entire page. If you set a maximum height or width, you can prevent this (and the atom sizes / bond widths will scale with your molecule).
    """)
    return


@app.cell
def _(ctx, oechem):
    # Create a very long molecule - by default this much too large to render in a normal cell
    _long_mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(_long_mol, "CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC")

    # Change the max_width so that it fits comfortably in this notebook
    ctx.max_width = 400

    _long_mol
    return


@app.cell
def _(ctx):
    # Reset our context so we don't affect the rest of the notebook
    ctx.reset()
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Polars Usage

    Similar to the simple examples above, the idea was to develop something that "just works" in a Notebook. Most of the
    time you just don't want to have to think about it.

    **Key Difference from Pandas**: Polars DataFrames are immutable. Operations that modify the DataFrame return a new
    DataFrame rather than modifying the original in place. This is a fundamental difference from Pandas.

    Let's create a sample DataFrame with no molecule objects:
    """)
    return


@app.cell
def _(pl):
    df = pl.DataFrame({
        "Name": ["Benzene", "Pyridine", "Pyrimidine"],
        "Molecule": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
    })

    # Display it
    df
    return (df,)


@app.cell
def _(mo):
    mo.md(r"""
    Now let's convert the SMILES to molecules. This is easy with a transparent extension added to Polars by the ```OEPolars``` package.

    **Note**: Unlike Pandas, Polars returns a new DataFrame instead of modifying in place:
    """)
    return


@app.cell
def _(df):
    # Convert the Polars series to molecules
    # This returns a new DataFrame (Polars is immutable)
    df_mol = df.chem.as_molecule("Molecule")

    # Display it
    df_mol
    return (df_mol,)


@app.cell
def _(mo):
    mo.md(r"""
    Take a look at the **dtypes** (datatypes) for the columns. You'll see that the ```Molecule``` column has dtype ```molecule```, which means that we can perform chemistry-aware operations on the column. Pretty snazzy.
    """)
    return


@app.cell
def _(df_mol):
    print(df_mol.dtypes)
    return


@app.cell
def _(df_mol, oechem, pl):
    # Count the number of heavy atoms
    df_with_count = df_mol.with_columns(
        pl.col("Molecule").map_elements(
            lambda x: oechem.OECount(x, oechem.OEIsHeavy()),
            return_dtype=pl.Int64
        ).alias("Heavy Atom Count")
    )

    # Display it
    df_with_count
    return (df_with_count,)


@app.cell
def _(mo):
    mo.md(r"""
    ## Substructure Highlighting

    We can easily highlight substructures. With Polars, we need to keep a reference to the series we want to modify:
    """)
    return


@app.cell
def _(df_with_count):
    # Get the molecule series and highlight aromatic N-C-N bonds
    mol_series = df_with_count.get_column("Molecule")
    mol_series.chem.highlight("ncn")

    # Display it - the highlighting is stored in the series metadata
    df_with_count
    return (mol_series,)


@app.cell
def _(df_with_count):
    # Remove the highlighting (also removes any other display callbacks)
    df_with_count.chem.reset_depictions()

    # Display it
    df_with_count
    return


@app.cell
def _(mo):
    mo.md(r"""
    You can also highlight based on another column. This is useful if you have different SMARTS patterns that you'd like to highlight in each molecule.
    """)
    return


@app.cell
def _(df_with_count, pl):
    # Add a SMARTS column with patterns
    df_with_smarts = df_with_count.with_columns(
        pl.lit(["cc", "cnc", "ncn"]).alias("SMARTS")
    )
    df_with_smarts.head()
    return (df_with_smarts,)


@app.cell
def _(mo):
    mo.md(r"""
    Let's highlight those patterns. Note that ```highlight_using_column``` returns a new DataFrame with the highlighted column:
    """)
    return


@app.cell
def _(df_with_smarts):
    df_highlighted = df_with_smarts.chem.highlight_using_column("Molecule", "SMARTS")
    df_highlighted
    return (df_highlighted,)


@app.cell
def _(mo):
    mo.md(r"""
    Note that ```highlight_using_column``` produces a different kind of output column where the elements are no longer molecules (they are in fact ```oedepict.OE2DMolDisplay``` objects). This is required to enable highlighting different substructures on a per-cell basis, versus highlighting the same substructure for an entire column. You can always check the datatypes:
    """)
    return


@app.cell
def _(df_highlighted):
    print(df_highlighted.dtypes)
    return


@app.cell
def _(mo):
    mo.md(r"""
    # Empty Molecules

    Empty molecules render an image in blue text. By default the size is 200x200 px.
    """)
    return


@app.cell
def _(oechem):
    _empty_mol = oechem.OEGraphMol()
    _empty_mol
    return


@app.cell
def _(mo):
    mo.md(r"""
    # Aligned Molecule Depictions

    Sometimes you may have multiple molecules in a DataFrame that you may want to have aligned. There are two options:

    1. Use ```align_depictions``` and you will regenerate the 2D coordinates of the molecules in a column based on a reference.
    2. Use ```highlight``` with a reference, and it will both align and highlight the molecule.

    Let's first take a look at our DataFrame. See how the bicyclic pyrimidine is not always in the same orientation?
    """)
    return


@app.cell
def _(DEMO_DIRECTORY, oeplr):
    egfr_df = oeplr.read_smi(DEMO_DIRECTORY / "assets" / "egfr.smi")
    egfr_df = egfr_df.rename({"Molecule": "Original"})
    egfr_df.head()
    return (egfr_df,)


@app.cell
def _(mo):
    mo.md(r"""
    Let's align based on the following template structure. This template was drawn in ChemDraw and saved as an MDL MOL file. We are going to read it in as an ```OEQMol```, which supports query features.
    """)
    return


@app.cell
def _(DEMO_DIRECTORY, oechem):
    alignment_template = oechem.OEQMol()
    with oechem.oemolistream(str(DEMO_DIRECTORY / "assets" / "egfr_template.mol")) as _ifs:
        oechem.OEReadMDLQueryFile(_ifs, alignment_template)

    # Show the template
    alignment_template
    return (alignment_template,)


@app.cell
def _(mo):
    mo.md(r"""
    Let's take a look at the ```align_depictions``` route, first. We're creating a new column called ```Aligned``` so that we can compare it to the original structure.

    **Note**: With Polars, we need to use ```deepcopy``` to create a copy of the molecules, then align them:
    """)
    return


@app.cell
def _(alignment_template, egfr_df):
    # Create a deep copy of the Original column for alignment
    aligned_series = egfr_df.get_column("Original").chem.deepcopy()
    aligned_series.chem.align_depictions(alignment_template)

    # Add the aligned column to the DataFrame
    egfr_df_aligned = egfr_df.with_columns(aligned_series.alias("Aligned"))
    egfr_df_aligned.head()
    return aligned_series, egfr_df_aligned


@app.cell
def _(mo):
    mo.md(r"""
    Now lets look at the highlight route. Note that we are providing the template to the ```highlight``` function twice, once for actually highlighting the structure and once for aligning the structure. This allows you to align and highlight using different templates if you wish.
    """)
    return


@app.cell
def _(alignment_template, egfr_df_aligned):
    # Create a deep copy for highlighting
    highlighted_series = egfr_df_aligned.get_column("Original").chem.deepcopy()
    highlighted_series.chem.highlight(alignment_template, ref=alignment_template)

    # Add the highlighted column to the DataFrame
    egfr_df_full = egfr_df_aligned.with_columns(highlighted_series.alias("Highlighted"))
    egfr_df_full.head()
    return egfr_df_full, highlighted_series


@app.cell
def _(mo):
    mo.md(r"""
    It should be noted that a column can only be aligned to a single reference (at the moment). Subsequent calls to functions that set an alignment reference will override previous references.

    # Fingerprint Similarity

    You can color the fingerprint similarity between two structures. By default, this uses OpenEye Tree fingerprints of size 4096 with default atom and bond definitions. Note that the resulting columns are ```display``` columns, so they cannot be manipulated as molecules any longer.

    Note that the second argument is optional. If this argument is omitted, then the first valid molecule in the DataFrame will be used as a reference.
    """)
    return


@app.cell
def _(DEMO_DIRECTORY, oechem):
    # Read a reference molecule
    refmol = oechem.OEGraphMol()

    with oechem.oemolistream(str(DEMO_DIRECTORY / "assets" / "egfr.smi")) as ifs:
        oechem.OEReadMolecule(ifs, refmol)
        refmol.SetTitle('')

    # Display it
    refmol
    return (refmol,)


@app.cell
def _(DEMO_DIRECTORY, oeplr, refmol):
    # Re-read the EGFR DataFrame
    egfr_fpsim_df = oeplr.read_smi(str(DEMO_DIRECTORY / "assets" / "egfr.smi"))

    # Calculate fingerprint similarity (returns a new DataFrame)
    egfr_fpsim_df = egfr_fpsim_df.chem.fingerprint_similarity("Molecule", refmol)
    egfr_fpsim_df.head()
    return (egfr_fpsim_df,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
