C3D Interactive 3D Viewer
=========================

C3D provides an interactive 3D molecule viewer for Jupyter and Marimo notebooks,
powered by `3Dmol.js <https://3dmol.csb.pitt.edu/>`_. It generates self-contained
HTML with no external network requests, making it suitable for offline use and
secure environments.

The viewer includes a built-in GUI with a sidebar for toggling molecule visibility,
a menubar with view controls, and a terminal for executing 3Dmol.js commands
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
        .add_style({"chain": "A"}, "cartoon", color="blue")
        .add_style({}, "stick")
    )
    viewer.display()

Style presets: ``cartoon``, ``stick``, ``sphere``, ``line``, ``cross``, ``surface``.

You can also pass a raw 3Dmol.js style dict for full control:

.. code-block:: python

    viewer.add_style({"resi": 42}, {"cartoon": {"color": "spectrum"}})

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
        .set_ui(sidebar=True, menubar=True, terminal=False)
    )
    viewer.display()

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
        .add_style({"chain": "A"}, "cartoon", color="blue")
        .set_preset("sites")
        .set_ui(sidebar=True, menubar=True, terminal=False)
        .set_background("#ffffff")
        .zoom_to("resn 502")
    )
    viewer.display()

HTML Export
-----------

Use ``to_html()`` to get the raw HTML string for embedding or saving:

.. code-block:: python

    html = viewer.to_html()
    with open("viewer.html", "w") as f:
        f.write(html)

The generated HTML is fully self-contained with all JavaScript and CSS inlined.
