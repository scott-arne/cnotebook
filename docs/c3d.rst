C3D Interactive 3D Viewer
=========================

C3D provides an interactive 3D molecule viewer for Jupyter and Marimo notebooks,
powered by `3Dmol.js <https://3dmol.csb.pitt.edu/>`_. It generates self-contained
HTML with no external network requests, making it suitable for offline use and
secure environments.

The viewer includes a built-in GUI with a sidebar for toggling molecule visibility,
a menubar with view controls, and a console for executing 3Dmol.js commands
interactively.

Quick Start
-----------

.. code-block:: python

    from cnotebook.c3d import C3D
    from openeye import oechem

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1 benzene")  # SMILES with optional title

    viewer = C3D().add_molecule(mol)
    viewer.display()

You'll see the following warning ``Molecule 'benzene' lacks 3D coordinates; generating with OEOmega."`` This is normal,
since the molecule converted from SMILES contains no 3D coordinates but you're trying to display it in 3D.

.. iframe:: _static/c3d-benzene.html

C3D is also available at the top level when its dependencies are present:

.. code-block:: python

    import cnotebook

    # ... code that loads a molecule ...
    viewer = cnotebook.C3D().add_molecule(mol)
    viewer.display()

Adding Molecules
----------------

Use ``add_molecule`` to add OpenEye molecules. If the molecule lacks 3D
coordinates, CNotebook will automatically generate them using Omega.

.. code-block:: python

    # Read two molecules from the example notebooks
    mol1 = oechem.OEGraphMol()
    mol2 = oechem.OEGraphMol()

    with oechem.oemolistream("examples/assets/5FQD_ligand.sdf") as ifs:
        oechem.OEReadMolecule(ifs, mol1)

    with oechem.oemolistream("examples/assets/6XK9_ligand.sdf") as ifs:
        oechem.OEReadMolecule(ifs, mol2)

    # View them both as sticks
    viewer = (
        C3D()
        .add_molecule(mol1)
        .add_molecule(mol2)
        .add_style("stick")
    )
    viewer.display()

Note that adding two molecules automatically displays the sidebar. The names of
each entry on the sidebar are taken from the molecule titles. If you want to
custom names, use the ``name`` parameter on ``add_molecule`` and provide your
own name.

.. iframe:: _static/c3d-two-mols.html

Adding Design Units
-------------------

Design units (protein-ligand complexes) are added with ``add_design_unit``.
The full complex is extracted and written as PDB format for 3Dmol.js.

.. code-block:: python

    from openeye import oechem
    from cnotebook.c3d import C3D

    du = oechem.OEDesignUnit()
    oechem.OEReadDesignUnit("examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu", du)

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .set_preset("sites")
        .orient("resi 502")
    )
    viewer.display()

Note that ``orient`` will orient the molecule based on it's principal components and zoom to it. It
does not guarantee that no residues will be in the way.

.. iframe:: _static/c3d-design-unit.html

Disabled Molecules
------------------

Molecules and design units can be loaded in a disabled state using the
``disabled`` parameter. Disabled entries are not displayed when the viewer starts,
but can be toggled on via the sidebar.

.. code-block:: python

    # ... load two molecules 'mol' and 'ref'
    viewer = (
        C3D()
        .add_molecule(mol, name="active")
        .add_molecule(ref, name="reference", disabled=True)
    )
    viewer.display()

View Presets
------------

Presets are compound styles defined in the GUI that combine multiple
representations into a common visualization. When a preset is set, it replaces
any styles added via ``add_style``.

Available presets:

- ``"simple"`` -- Element-coloured cartoon with per-chain carbons and sticks
  for ligands.
- ``"sites"`` -- Like *simple*, plus stick representation for residues within
  5 angstroms of ligands.
- ``"ball-and-stick"`` -- Ball-and-stick for ligands only.

.. code-block:: python

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .set_preset("sites")
    )
    viewer.display()

Custom Styles
-------------

For finer control, add individual 3Dmol.js styles with ``add_style``:

.. code-block:: python

    viewer = (
        C3D()
        .add_molecule(mol)
        .add_style("cartoon", {"chain": "A"}, color="blue")
        .add_style("stick")
        .remove_style("stick", "not ligand")
    )
    viewer.display()

Style presets: ``cartoon``, ``stick``, ``sphere``, ``line``, ``cross``, ``surface``.

``show_style`` is a synonym for ``add_style``. ``hide_style`` is a synonym for
``remove_style``.

For hydrogen display cleanup, ``show_polar_hydrogens(rep)`` applies *rep* to
``polar_hydrogen`` and ``hide_nonpolar_hydrogens()`` removes all styles from
``nonpolar_hydrogen``. Pass a representation name to
``hide_nonpolar_hydrogens(rep)`` to remove only that representation.

You can also pass a raw 3Dmol.js style dict for full control:

.. code-block:: python

    viewer.add_style({"cartoon": {"color": "spectrum"}}, {"resi": 42})

Surfaces, Maps, and Isosurfaces
-------------------------------

Molecular and solvent-accessible surfaces can be added to molecules, design
units, or selections. The surface operations are applied in chain order, like
style operations.

.. code-block:: python

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .set_preset("sites")
        .add_surface("complex", name="complex_surface", type="molecular")
    )
    viewer.display()

Density maps can be embedded from local CCP4/MRC/MAP/CUBE files. The generated
HTML remains self-contained.

.. code-block:: python

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .add_map("density.ccp4", name="2Fo-Fc", show_box=True)
        .add_isosurface("2Fo-Fc", name="density_mesh", level=None)
    )
    viewer.display()

``level=None`` lets the GUI choose a suggested contour level from the map data.
OpenEye ``OEScalarGrid`` objects can also be passed directly to ``add_map``.

.. code-block:: python

    viewer = (
        C3D()
        .add_molecule(mol, name="ligand")
        .add_map(grid, name="site_grid")
        .add_isosurface("site_grid", name="site_surface", representation="surface")
    )

Maps, surfaces, and isosurfaces can be removed in the same ordered chain:

.. code-block:: python

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .add_surface("complex", name="temporary_surface")
        .remove_surface("temporary_surface")
    )

Zoom Targets
------------

The ``zoom_to`` method sets the initial zoom target after loading.

- **String selection** -- Parsed by the GUI's selection engine:

  .. code-block:: python

      viewer.zoom_to("resn 502")
      viewer.zoom_to("chain A")

- **Dict selection** -- Passed directly to 3Dmol.js:

  .. code-block:: python

      viewer.zoom_to({"chain": "A"})

- **None** -- Fit all molecules in view (the default).

UI Configuration
----------------

Control which GUI panels are visible:

.. code-block:: python

    viewer = (
        C3D()
        .add_molecule(mol)
        .set_ui(sidebar=True, menubar=True, console=True)
    )
    viewer.display()

When the console is visible and ``height`` was not set explicitly, C3D uses a
taller default cell height so the molecule viewer is not compressed by the
console. Pass ``height=...`` to :class:`~cnotebook.c3d.C3D` when you want to control the exact
JupyterLab iframe height.

.. iframe:: _static/c3d-full-ui.html

Background Color
----------------

Set the viewer background colour with any CSS colour string:

.. code-block:: python

    viewer.set_background("#ffffff")
    viewer.set_background("white")

Builder API
-----------

All configuration methods return ``self``, enabling fluent method chaining:

.. code-block:: python

    viewer = (
        C3D(width=1024, height=768)
        .add_design_unit(du, name="protein")
        .add_molecule(ligand, name="ligand")
        .add_style("cartoon", {"chain": "A"}, color="blue")
        .set_preset("sites")
        .set_ui(sidebar=True, menubar=True, console=False)
        .set_background("#ffffff")
        .zoom_to("resn 502")
    )
    viewer.display()

Interactive use
---------------

``display()`` shows a live widget by default. Atom picks, the camera view and terminal
commands are all available from Python.

``display()`` returns a displayable object; it does not publish one. The notebook renders
it because it is the value of the cell, so it has to be the cell's last expression: a
statement after it discards the widget, nothing appears, and the interaction that follows
has no front end to reach. Build and display in one cell:

.. code-block:: python

    # Cell 1: build the viewer, register callbacks, display it last
    viewer = C3D().add_design_unit(du, name="complex").set_preset("sites")
    viewer.on_pick(lambda pick: print(pick.atom["resn"], pick.atom["resi"]))
    viewer.display()

Then drive it from later cells, once the viewer above has rendered:

.. code-block:: python

    # Cell 2
    await viewer.execute("zoom resn 502")    # any GUI terminal command

.. code-block:: python

    # Cell 3: run once the camera shows what you want to keep
    viewer.save_view("site")
    png = await viewer.screenshot()          # PNG bytes

``viewer.save("complex.html")`` writes the standalone document at any point; it needs no
kernel to open.

Once a viewer is on screen as a widget the builder methods refuse to run and raise
``CNotebookError``: the widget was initialized from the scene as it stood, and a later
``add_molecule`` would make ``to_html()`` and ``save()`` disagree with what is on screen.
Live changes go through ``execute()``, or build a new ``C3D``.

Picks
^^^^^

``on_pick(callback)`` registers a callback that receives a ``PickEvent`` with ``seq``,
``atom`` (the 3Dmol atom record) and ``modifiers`` (the keyboard modifiers held during
the click). An exception raised by the callback is logged, not propagated.

``viewer.picked`` holds the last ``PickEvent``, or ``None``. Reading it never brings a
widget into being: with no widget there can have been no pick.

The camera
^^^^^^^^^^

``viewer.view`` is a copy of the last view array the front end reported, 3Dmol's
``getView()`` vector ``[x, y, z, zoom, qx, qy, qz, qw]``, or ``None`` if the viewer has
not reported one yet. ``set_view(view)`` points the camera at such an array, and
``save_view(name)`` and ``restore_view(name)`` store and recall them by name.

``save_view`` is the one place where the asynchrony is visible. It copies ``viewer.view``
synchronously, and ``viewer.view`` holds whatever the browser last sent: the front end
publishes a camera a short debounce after the camera stops moving, not when the command
that moved it returns. Awaiting ``execute()`` therefore says the command ran, not that its
camera has arrived, and a ``save_view`` on the next line can store the previous camera.
Save the view from a later cell, once the frame shows what you mean to keep:

.. code-block:: python

    # Cell 1: remember where you are, then move
    viewer.save_view("overview")
    await viewer.execute("zoom resn 502")

.. code-block:: python

    # Cell 2: the frame now shows the site, so this stores the site
    viewer.save_view("site")

.. code-block:: python

    # Cell 3: and go back
    viewer.restore_view("overview")

``save_view`` raises ``CNotebookError`` when the viewer has not reported a view at all
yet, which is the state a freshly displayed viewer is in until it is moved: interact with
it, or call ``set_view()`` first, to give it one.

Terminal commands
^^^^^^^^^^^^^^^^^

``execute(command)`` queues any GUI terminal command on the live widget and returns a
``CommandHandle`` that settles, and can be awaited, when the front end reports the
result.

.. code-block:: python

    result = await viewer.execute("zoom resn 502")

``result`` is a ``CommandResult`` with ``ok`` (whether the front end accepted the command)
and ``output`` (the terminal lines it produced). Awaiting the handle guarantees that much
and no more: any camera the command moved is reported separately, so do not read
``viewer.view`` or call ``save_view()`` on the following line and expect the new camera.
A command submitted before the widget is on screen is queued and runs when it connects;
``execute()`` on a closed viewer raises ``CNotebookError`` rather than returning a handle.
When the same viewer is displayed in more than one cell the views mirror each other, but a
command result is pruned once the first view reports it, so a view still working through an
earlier asynchronous command can miss later ones: treat the first view as the authoritative
one.

Measurements, labels and animation
----------------------------------

These are builder methods: they return ``self``, they are applied when the scene is
built, and like every builder method they raise ``CNotebookError`` on a viewer that is
already displayed as a widget.

.. code-block:: python

    viewer = (
        C3D()
        .add_design_unit(du, name="complex")
        .label_residues("resn 502", template="{resn}{resi}")
        .measure_distance("resn 502", "chain A and resi 45", name="contact")
    )
    viewer.display()

``label_residues(selection, template="{resn}{resi}")`` labels every matching atom. The
template accepts the ``{name}``, ``{atom}``, ``{resn}``, ``{resi}``, ``{chain}``,
``{elem}`` and ``{index}`` placeholders.

``measure_distance(selection_a, selection_b, name=None)`` draws a dashed distance between
the centroids of two selections; without a name the viewer numbers the measurement the
way the ``distance`` terminal command does.

Both read their selection as text -- a selection expression such as ``"chain A"`` or an
entry name -- so, unlike ``add_style``, they do not accept a raw 3Dmol.js selection dict.

Conformers are added as one entry whose frames are the conformers, and ``animate`` plays
them:

.. code-block:: python

    viewer = (
        C3D()
        .add_conformers(mcmol, name="poses")
        .animate("poses", interval_ms=200, loop="backAndForth")
    )
    viewer.display()

``add_conformers`` needs a multi-conformer molecule (``OEMCMolBase``) with at least two
conformers. ``animate(entry, interval_ms=100, loop="forward")`` names an entry already
added to the same viewer; ``loop`` is ``"forward"``, ``"backward"`` or ``"backAndForth"``.

HTML Export
-----------

Use ``to_html()`` to get the raw HTML string for embedding or saving:

.. code-block:: python

    html = viewer.to_html()
    with open("viewer.html", "w") as f:
        f.write(html)

The generated HTML is fully self-contained with all JavaScript and CSS inlined.
``viewer.save("viewer.html")`` does the same thing in one call and returns the ``Path``
it wrote.

Display modes
-------------

``display()`` produces a live widget: a small notebook output that keeps the scene in the
kernel and supports picks, terminal commands and the camera API. That needs a running
kernel, and it does not appear in a static render such as GitHub's notebook preview.
Saving JupyterLab widget state re-embeds the viewer assets, so a saved notebook does show
the viewer again.

The static form embeds the whole scene in the output instead, so it survives with no
kernel at all:

.. code-block:: python

    viewer.display(static=True)   # self-contained HTML in the notebook output

.. code-block:: python

    html = viewer.to_html()       # the same document as a string
    viewer.save("viewer.html")    # written to a file

These are three ways to reach the same document, not a sequence: ``display(static=True)``
has to end its cell like any other ``display()`` call.

To make the static form the default for every viewer, set the display mode once:

.. code-block:: python

    import cnotebook

    cnotebook.configure(display_mode="static")

or put it in the configuration file:

.. code-block:: toml

    [display]
    mode = "static"

``CNOTEBOOK_DISPLAY_MODE=static`` in the environment does the same for one session. See
:doc:`configuration` for the rest of the file.
