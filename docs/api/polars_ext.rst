polars_ext
==========

.. automodule:: cnotebook.polars_ext
   :members:
   :undoc-members:
   :show-inheritance:

Polars DataFrame Accessor
-------------------------

The ``chem`` accessor provides chemistry-aware operations on Polars DataFrames
and Series containing molecule columns.

Usage
-----

.. code-block:: python

    import cnotebook
    import polars as pl
    import oepolars as oeplr

    # The accessor is automatically registered when cnotebook is imported
    df = pl.DataFrame({"smiles": ["CCO", "c1ccccc1"]})

    # Convert SMILES to molecules
    df = df.chem.as_molecule("smiles")

    # Highlight substructures
    df.get_column("smiles").chem.highlight("c1ccccc1")

    # Align depictions
    df.get_column("smiles").chem.align_depictions("first")

DataFrame Methods
-----------------

.. py:method:: DataFrame.chem.as_molecule(column)
   :no-index:

   Convert a SMILES column to molecules.

   :returns: New DataFrame with molecules

.. py:method:: DataFrame.chem.highlight_using_column(mol_col, pattern_col)
   :no-index:

   Highlight substructures using patterns from another column.

   :returns: New DataFrame with highlighted molecules

.. py:method:: DataFrame.chem.fingerprint_similarity(mol_col, reference)
   :no-index:

   Color molecules by fingerprint similarity to a reference.

   :returns: New DataFrame with similarity coloring

Series Methods
--------------

.. py:method:: Series.chem.highlight(smarts)
   :no-index:

   Highlight a SMARTS pattern in the molecule column.

.. py:method:: Series.chem.align_depictions(reference)
   :no-index:

   Align molecule depictions to a reference.
