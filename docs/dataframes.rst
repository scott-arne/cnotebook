DataFrame Integration
=====================

CNotebook provides seamless integration with Pandas and Polars DataFrames through
the ``chem`` accessor, enabling chemistry-aware operations on molecular data.

Pandas Integration
------------------

Prerequisites
^^^^^^^^^^^^^

.. code-block:: bash

    pip install pandas oepandas

Creating Molecule Columns
^^^^^^^^^^^^^^^^^^^^^^^^^

Convert SMILES strings to molecule objects:

.. code-block:: python

    import cnotebook
    import oepandas as oepd
    import pandas as pd

    df = pd.DataFrame({
        "Name": ["Benzene", "Pyridine", "Pyrimidine"],
        "Molecule": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
    })

    # Convert SMILES column to molecules (in place)
    df.chem.as_molecule("Molecule", inplace=True)

    # Display the DataFrame
    df

DataFrame Display
^^^^^^^^^^^^^^^^^

Molecule columns automatically render as chemical structures when displaying
the DataFrame:

.. code-block:: python

    df  # Molecules display as structures in Jupyter/Marimo

Substructure Highlighting
^^^^^^^^^^^^^^^^^^^^^^^^^

Highlight substructures in molecule columns:

.. code-block:: python

    # Highlight a single pattern
    df.SMILES.chem.highlight("c1ccccc1")  # Highlight aromatic rings

    # Highlight different patterns per row
    df["Pattern"] = ["cc", "cnc", "ncn"]
    df.chem.highlight_using_column("SMILES", "Pattern", inplace=True)

Molecular Alignment
^^^^^^^^^^^^^^^^^^^

Align molecule depictions for visual comparison:

.. code-block:: python

    # Align to first molecule
    df.SMILES.chem.align_depictions("first")

    # Align to a reference molecule
    ref = oechem.OEGraphMol()
    oechem.OESmilesToMol(ref, "c1ccccc1")
    df.SMILES.chem.align_depictions(ref)

    # Align to maximum common substructure
    df.SMILES.chem.align_depictions("mcs")

Fingerprint Similarity
^^^^^^^^^^^^^^^^^^^^^^

Color molecules by similarity to a reference:

.. code-block:: python

    reference = oechem.OEGraphMol()
    oechem.OESmilesToMol(reference, "c1ccc(N)cc1")

    df.chem.fingerprint_similarity("SMILES", reference, inplace=True)

Polars Integration
------------------

Prerequisites
^^^^^^^^^^^^^

.. code-block:: bash

    pip install polars oepolars

Creating Molecule Columns
^^^^^^^^^^^^^^^^^^^^^^^^^

Convert SMILES strings to molecule objects:

.. code-block:: python

    import cnotebook
    import oepolars as oeplr
    import polars as pl

    df = pl.DataFrame({
        "Name": ["Benzene", "Pyridine", "Pyrimidine"],
        "smiles": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
    })

    # Convert SMILES column to molecules
    df = df.chem.as_molecule("smiles")

Reading Molecule Files
^^^^^^^^^^^^^^^^^^^^^^

Read molecules directly from files:

.. code-block:: python

    # Read from SMILES file
    df = oeplr.read_smi("molecules.smi")

    # Read from SDF file
    df = oeplr.read_sdf("molecules.sdf")

DataFrame Display
^^^^^^^^^^^^^^^^^

Molecule columns automatically render as chemical structures:

.. code-block:: python

    df  # Molecules display as structures in Jupyter/Marimo

Substructure Highlighting
^^^^^^^^^^^^^^^^^^^^^^^^^

Highlight substructures in molecule columns:

.. code-block:: python

    # Highlight a single pattern
    df.get_column("smiles").chem.highlight("c1ccccc1")

    # Highlight different patterns per row
    df = df.with_columns(pl.lit(["cc", "cnc", "ncn"]).alias("Pattern"))
    df = df.chem.highlight_using_column("smiles", "Pattern")

Molecular Alignment
^^^^^^^^^^^^^^^^^^^

Align molecule depictions:

.. code-block:: python

    # Align to first molecule
    df.get_column("smiles").chem.align_depictions("first")

    # Align to a reference molecule
    df.get_column("smiles").chem.align_depictions(ref)

Fingerprint Similarity
^^^^^^^^^^^^^^^^^^^^^^

Color molecules by similarity:

.. code-block:: python

    reference = oechem.OEGraphMol()
    oechem.OESmilesToMol(reference, "c1ccc(N)cc1")

    df = df.chem.fingerprint_similarity("smiles", reference)

MolGrid from DataFrames
-----------------------

Create interactive molecule grids from DataFrames:

**Pandas:**

.. code-block:: python

    from cnotebook import MolGrid

    grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
    )
    grid.display()

    # Or use the accessor
    grid = df["Molecule"].chem.molgrid()
    grid.display()

**Polars:**

.. code-block:: python

    grid = MolGrid(
        df["smiles"].to_list(),
        dataframe=df.to_pandas(),  # Convert for DataFrame features
        mol_col="smiles",
    )
    grid.display()

See the :doc:`molgrid` documentation for more details on MolGrid features.

Best Practices
--------------

1. **Memory Management**: For large datasets, consider using molecule indices
   rather than storing full molecule objects in memory.

2. **Performance**: Use PNG format for faster rendering of large DataFrames.
   SVG provides better quality but may be slower for many molecules.

3. **Column Naming**: Use descriptive column names and avoid conflicts with
   reserved names like "Molecule" when possible.

4. **Lazy Evaluation**: When using Polars, take advantage of lazy evaluation
   for complex operations on large datasets.
