pandas_ext
==========

.. automodule:: cnotebook.pandas_ext
   :members:
   :undoc-members:
   :show-inheritance:

Pandas DataFrame Accessor
-------------------------

The ``chem`` accessor provides chemistry-aware operations on Pandas DataFrames
and Series containing molecule columns.

Usage
-----

.. code-block:: python

    import cnotebook
    import pandas as pd
    import oepandas as oepd

    # The accessor is automatically registered when cnotebook is imported
    df = pd.DataFrame({"SMILES": ["CCO", "c1ccccc1"]})

    # Convert SMILES to molecules
    df.chem.as_molecule("SMILES", inplace=True)

    # Highlight substructures
    df.SMILES.chem.highlight("c1ccccc1")

    # Align depictions
    df.SMILES.chem.align_depictions("first")

    # Create MolGrid
    grid = df.SMILES.chem.molgrid()

DataFrame Methods
-----------------

.. py:method:: DataFrame.chem.as_molecule(column, inplace=False)

   Convert a SMILES column to molecules.

.. py:method:: DataFrame.chem.highlight_using_column(mol_col, pattern_col, inplace=False)

   Highlight substructures using patterns from another column.

.. py:method:: DataFrame.chem.fingerprint_similarity(mol_col, reference, inplace=False)

   Color molecules by fingerprint similarity to a reference.

.. py:method:: DataFrame.chem.molgrid(**kwargs)

   Create a MolGrid from the DataFrame.

Series Methods
--------------

.. py:method:: Series.chem.highlight(smarts)

   Highlight a SMARTS pattern in the molecule column.

.. py:method:: Series.chem.align_depictions(reference)

   Align molecule depictions to a reference.

.. py:method:: Series.chem.molgrid(**kwargs)

   Create a MolGrid from the Series.
