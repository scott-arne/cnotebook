pandas_ext
==========

.. automodule:: cnotebook.pandas_ext
   :members:
   :undoc-members:
   :show-inheritance:

Pandas DataFrame Accessor
-------------------------

The ``chem`` accessor provides chemistry-aware operations on Pandas DataFrames
and Series containing molecule columns. CNotebook also treats OEPandas
``QueryDtype`` columns as depictable query molecule columns.

Usage
-----

.. code-block:: python

    import cnotebook
    import pandas as pd
    import oepandas as oepd

    # The accessor is automatically registered when cnotebook is imported
    df = pd.DataFrame({"SMILES": ["Oc1ccccc1", "COc1ccccc1"]})

    # Convert SMILES to molecules
    df.chem.as_molecule("SMILES", inplace=True)

    # Query columns render with the same formatter
    queries = pd.DataFrame({"Query": ["[#6]-[#8]"]})
    queries.chem.as_query("Query", inplace=True)

    # Highlight substructures
    df.SMILES.chem.highlight("c1ccccc1")

    # Align depictions to the first molecule; the report says how many rows aligned
    report = df.SMILES.chem.align_depictions("first")
    report = df.SMILES.chem.alignment_report   # the same report, later

    # Create MolGrid; frame= adds the frame's other columns to the cards
    grid = df.SMILES.chem.molgrid(frame=df)

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

.. py:method:: DataFrame.chem.set_render_options(molecule_columns=None, **kwargs)

   Set CNotebook rendering options for molecule or query columns.

Series Methods
--------------

.. py:method:: Series.chem.highlight(smarts)

   Highlight a SMARTS pattern in the molecule column.

.. py:method:: Series.chem.align_depictions(reference)

   Align molecule depictions to a reference (a molecule, SMARTS, or ``"first"``).

   :returns: An :class:`~cnotebook.core.columnops.AlignmentReport`

.. py:attribute:: Series.chem.alignment_report

   The :class:`~cnotebook.core.columnops.AlignmentReport` of the last alignment of this
   Series, or ``None`` when none has run.

.. py:method:: Series.chem.set_render_options(**kwargs)

   Set CNotebook rendering options for a molecule or query Series.

.. py:method:: Series.chem.molgrid(frame=None, **kwargs)

   Create a MolGrid from the Series. Pass the Series' frame as ``frame`` to include its
   other columns in the cards; the frame is no longer discovered automatically.
