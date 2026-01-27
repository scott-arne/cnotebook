molgrid
=======

.. automodule:: cnotebook.grid
   :members:
   :undoc-members:
   :show-inheritance:

MolGrid Class
-------------

.. autoclass:: cnotebook.grid.MolGrid
   :members:
   :special-members: __init__

molgrid Function
----------------

.. autofunction:: cnotebook.grid.molgrid

Usage Examples
--------------

Basic Grid
^^^^^^^^^^

.. code-block:: python

    from cnotebook import MolGrid
    from openeye import oechem

    molecules = []
    for smi in ["CCO", "c1ccccc1"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smi)
        molecules.append(mol)

    grid = MolGrid(molecules)
    grid.display()

Grid with DataFrame
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import pandas as pd
    from cnotebook import MolGrid

    grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
        data=["Name", "MW"],
    )
    grid.display()

Retrieving Selections
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    selected = grid.get_selection()
    indices = grid.get_selection_indices()
