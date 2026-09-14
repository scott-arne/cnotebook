polars_ext
==========

.. automodule:: cnotebook.polars_ext
   :members:
   :undoc-members:
   :show-inheritance:

Polars DataFrame Accessor
-------------------------

The ``chem`` accessor provides chemistry-aware operations on Polars DataFrames
and Series containing molecule columns. Install ``oepolars>=0.4.0`` to use the
current CNotebook-supported Polars extension types.

Usage
-----

.. code-block:: python

    import cnotebook
    import polars as pl
    import oepolars as oeplr

    # The accessor is automatically registered when cnotebook is imported
    df = pl.DataFrame({"smiles": ["Oc1ccccc1", "COc1ccccc1"]})

    # Convert SMILES to molecules
    df = df.chem.as_molecule("smiles")

    # Highlight substructures; polars frames are immutable, so keep the result
    df = df.chem.highlight("smiles", "c1ccccc1")

    # Align depictions to the first molecule and inspect the outcome
    df = df.chem.align_depictions("smiles", "first")
    report = df.chem.alignment_report("smiles")

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

.. py:method:: DataFrame.chem.highlight(column, smarts)
   :no-index:

   Highlight a SMARTS pattern in a molecule column.

   :returns: New DataFrame with the highlight applied

.. py:method:: DataFrame.chem.align_depictions(column, reference)
   :no-index:

   Align the depictions of a molecule column to a reference (a molecule, SMARTS, or ``"first"``).

   :returns: New DataFrame with aligned depictions

.. py:method:: DataFrame.chem.alignment_report(column)
   :no-index:

   The :class:`~cnotebook.core.columnops.AlignmentReport` of the last alignment of
   *column*, or ``None`` when none has run.

Series Methods
--------------

The Series accessor offers ``align_depictions``, ``recalculate_depiction_coordinates`` and
``molgrid``; highlighting is a DataFrame method. Every Series method returns a new Series.

.. py:method:: Series.chem.align_depictions(reference)
   :no-index:

   Align molecule depictions to a reference.

   :returns: New Series with aligned depictions
