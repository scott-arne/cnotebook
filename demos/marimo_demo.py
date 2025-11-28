import marimo

__generated_with = "0.14.15"
app = marimo.App(width="medium")


@app.cell
def _():
    import cnotebook
    from openeye import oechem
    return (oechem,)


@app.cell
def _(oechem):
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    mol
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
