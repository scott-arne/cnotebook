import marimo

__generated_with = "0.19.2"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import cnotebook
    import pandas as pd
    from openeye import oechem, oedepict

    cnotebook.enable_debugging()
    return cnotebook, mo, oechem, oedepict, pd


@app.cell
def _(mo):
    mo.md(r"""
    # Basic Usage

    **Rendering Basic Molecules**

    Let's start with just viewing any object that derives from```oechem.OEMolBase``` (scroll further if you are looking for Pandas examples).
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
    ## Displaying Grids of Molecule

    Sometimes you want to see several molecules in a grid. There is a convenient function to do this:

    ```python
    cnotebook.render_molecule_grid(
        mols,

        # All of these parameters are optional

        scale=0.5,
        nrows=None,
        ncols=None,
        max_width=1200,
        max_columns=100,
        align=None,
        smarts=None,
        color=oechem.OEColor(oechem.OELightBlue),
        style=oedepict.OEHighlightStyle_Stick
    )
    ```

    Where:

    * *mols*: One or more OpenEye molecule objects
    * *scale*: (Optional) Image scale within grid
    * *nrows*: (Optional) Number of rows
    * *ncols*: (Optional) Number of columns
    * *max_width*: (Optional) Maximum width of the image
    * *max_columns*: (Optional) Maximum number of molecule columns
    * *align*: (Optional) Set to True to align everything to the first molecule, or provide a reference OpenEye molecule
    * *smarts*: (Optional) SMARTS highlighting (currently only supports a single highlight)
    * *color*: (Optional) SMARTS highlighting color
    * *style*: (Optional) SMARTS highlighting style

    A few things to note:

    * You cannot supply both ```nrows``` and ```ncols```.
    * When ```nrows``` and ```ncols``` are None (default), the optimal number of rows and columns is calculated by the
      maximum molecule image width and ```max_width```. Specifying a custom number of rows / columns will override
      the maximum width.
    """)
    return


@app.cell
def _(cnotebook, oechem):
    # Create some sample molecules
    example_mols = []
    for _i, _smi in enumerate(["n1cnccc1", "c1ccccc1", "CCOH", "C(=O)OH", "CCCC"]):
        _mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(_mol, _smi)

        # We can title them too!
        _mol.SetTitle(f'Molecule {_i+1}')

        example_mols.append(_mol)

    # Render into a grid
    cnotebook.render_molecule_grid(example_mols, scale=1.0, smarts="ncn")
    return (example_mols,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Advanced: Changing the Rendering Options

    Basic rendering of molecules within Jupyter Notebooks is controlled by a global context. For simplicity, modifying the global context affects the display of molecules both in Marimo (i.e., when you display molecules as above) and in Pandas, which has not yet been introduced.
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
    # Pandas Usage

    Similar to the simple examples above, the idea was to develop something that "just works" in a Notebook. Most of the
    time you just don't want to have to think about it.

    Let's create a sample DataFrame with no molecule objects:
    """)
    return


@app.cell
def _(pd):
    data = [
        {"Name": "Benzene", "Molecule": "c1ccccc1"},
        {"Name": "Pyridine", "Molecule": "c1cnccc1"},
        {"Name": "Pyrimidine", "Molecule": "n1cnccc1"}
    ]

    # Create the DataFrame
    df = pd.DataFrame(data)

    # Display it
    df
    return (df,)


@app.cell
def _(mo):
    mo.md(r"""
    Now let's convert the SMILES to molecules. This is easy with a transparent extension added to Pandas by the ```OEPandas``` package:
    """)
    return


@app.cell
def _(df):
    # Convert the Pandas series to molecules
    # This can also take a list of columns to convert to molecule as well
    df.as_molecule("Molecule", inplace=True)

    # Display it
    df
    return


@app.cell
def _(mo):
    mo.md(r"""
    Take a look at the **dtypes** (datatypes) for the columns. You'll see that the ```Molecule``` column has dtype ```molecule```, which means that we can perform chemistry-aware operations on the column. Pretty snazzy.
    """)
    return


@app.cell
def _(df):
    print(df.dtypes)
    return


@app.cell
def _(df, oechem):
    # Count the number of heavy atoms
    df["Heavy Atom Count"] = df.Molecule.apply(lambda x: oechem.OECount(x, oechem.OEIsHeavy()))

    # Display it
    df
    return


@app.cell
def _(mo):
    mo.md(r"""
    ## Substructure Highlighting

    We can easily highlight substructures:
    """)
    return


@app.cell
def _(df):
    # Highlight aromatic N-C-N bonds
    df.Molecule.highlight("ncn")

    # Display it
    df
    return


@app.cell
def _(df, mo):
    mo.Html(df._mime_()[1])
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
