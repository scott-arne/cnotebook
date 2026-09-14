molgrid
=======

.. automodule:: cnotebook.grid
   :members:
   :undoc-members:
   :show-inheritance:
   :special-members: __init__

.. py:data:: BEST_FIT_ORIENTATION
   :value: -1

   Sentinel for the ``depict_orientation`` parameter of :class:`~cnotebook.grid.MolGrid`
   and :func:`~cnotebook.grid.molgrid`: each molecule is prepared in whichever of OpenEye's
   default and horizontal orientations renders largest in its card. Real
   ``OEDepictOrientation`` values are positive, so the sentinel cannot collide with one.
   Also available as ``cnotebook.BEST_FIT_ORIENTATION``.

Live Widget
-----------

``MolGrid.display()`` shows a :class:`~cnotebook.grid.widget.MolGridWidget` unless static
output is requested, and ``MolGrid.widget`` returns it.

.. autoclass:: cnotebook.grid.widget.MolGridWidget
   :members: attach_observer, close
   :exclude-members: __init__

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
