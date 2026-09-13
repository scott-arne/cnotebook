# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "marimo>=0.19.11",
# ]
# ///

import marimo

__generated_with = "0.19.11"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    from cnotebook import C3D
    from pathlib import Path
    from openeye import oechem

    EXAMPLES_DIRECTORY = Path(__file__).parent.parent
    return C3D, EXAMPLES_DIRECTORY, mo, oechem


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    # Interactive 3D Viewer

    ```C3D``` builds a 3D scene and displays it as a live widget. In Marimo the widget is
    wrapped in ```mo.ui.anywidget``` for you, so ```viewer.display()``` returns something the
    cell can render and the rest of the notebook can drive from Python.

    ## Table of Contents

    - [Building the Viewer](#building-the-viewer)
    - [Atom Picks](#atom-picks)
    - [Terminal Commands](#terminal-commands)
    - [Saving a Static Copy](#saving-a-static-copy)
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Building the Viewer

    The scene is assembled with chained builder calls and shown with ```display()```. Once the
    widget exists the builder methods refuse to run, so everything the scene needs is set up
    before it is displayed.
    """)
    return


@app.cell
def _(EXAMPLES_DIRECTORY, oechem):
    design_unit_path = EXAMPLES_DIRECTORY / "assets" / "spruce_9Q03_ABC__DU__A1CM7_C-502.oedu"

    du = oechem.OEDesignUnit()
    if not design_unit_path.exists() or not oechem.OEReadDesignUnit(str(design_unit_path), du):
        du = None
    return design_unit_path, du


@app.cell
def _(mo):
    # Picks arrive from the browser, so the callback writes to state and the cell that
    # reads the state re-runs on its own
    get_pick, set_pick = mo.state(None)
    return get_pick, set_pick


@app.cell
def _(C3D, design_unit_path, du, mo, set_pick):
    mo.stop(
        du is None,
        mo.md(f"""
        Design unit ```{design_unit_path.name}``` was not found, so there is nothing to show.
        The rest of this notebook needs it.
        """),
    )

    viewer = (
        C3D(width=700, height=450)
        .add_design_unit(du, name="complex")
        .set_preset("sites")
        .set_ui(sidebar=True, menubar=True, console=True)
        .zoom_to("resn 502")
    )

    # Register the callback before displaying; this creates the widget and freezes the
    # builder, so every builder call has to come before it
    viewer.on_pick(lambda pick: set_pick(pick))

    viewer.display()
    return (viewer,)


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Atom Picks

    ```on_pick``` is called with a ```PickEvent``` for every atom clicked in the viewer, and
    ```viewer.picked``` always holds the most recent one. Click an atom above.
    """)
    return


@app.cell
def _(get_pick, mo):
    _pick = get_pick()

    if _pick is None:
        mo.output.append(mo.md("*No atom picked yet. Click an atom in the viewer above.*"))
    else:
        _atom = _pick.atom
        mo.output.append(mo.md(f"""
        **Pick {_pick.seq}:** {_atom.get('resn')}{_atom.get('resi')}
        atom {_atom.get('atom')} ({_atom.get('elem')}) in chain {_atom.get('chain')}
        """))
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    ## Terminal Commands

    ```execute``` queues any GUI terminal command on the live widget and returns a handle that
    settles when the front end reports the result. It needs the viewer to be on screen, which is
    why it lives in its own cell behind a button: awaiting it before the widget has connected
    would simply wait.
    """)
    return


@app.cell
def _(mo):
    zoom_button = mo.ui.run_button(label="Run: zoom resn 502")
    zoom_button
    return (zoom_button,)


@app.cell
async def _(mo, viewer, zoom_button):
    mo.stop(not zoom_button.value, mo.md("*Press the button to zoom the viewer to the ligand.*"))

    _result = await viewer.execute("zoom resn 502")

    # output is the terminal's lines, so join them; an indented fence inside a
    # triple-quoted mo.md would be dedented into the surrounding markdown
    _lines = "\n".join(_result.output) or "(no output)"

    mo.md(f"Command accepted: **{_result.ok}**\n\n```\n{_lines}\n```")
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md(r"""
    The camera is reported a short moment after it stops moving, so ```save_view("site")```
    belongs in a later cell than the ```execute``` that moved it. ```restore_view(name)``` puts
    the camera back, and ```await viewer.screenshot()``` returns the current frame as PNG bytes.

    ## Saving a Static Copy

    ```viewer.to_html()``` renders the scene as a self-contained document and
    ```viewer.save(path)``` writes it out. Neither needs a kernel to open afterwards, which
    makes them the way to share a viewer with someone who only has the file.
    """)
    return


@app.cell
def _(mo, viewer):
    mo.md(f"""
    The standalone document is {len(viewer.to_html()) // 1024} KB. Write it out with
    ```viewer.save('complex.html')```.
    """)
    return


if __name__ == "__main__":
    app.run()
