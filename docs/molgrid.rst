MolGrid: Interactive Molecule Grids
====================================

MolGrid provides an interactive grid visualization for browsing, searching, and
selecting molecules. It is designed for exploring large molecular datasets with
powerful filtering and selection capabilities.

Overview
--------

Key features of MolGrid:

- **Pagination**: Navigate large datasets with configurable items per page
- **Text Search**: Filter by molecule titles and properties
- **SMARTS Search**: Substructure filtering using SMARTS patterns
- **Selection**: Select molecules with checkboxes or click-to-select
- **Export**: Export selected molecules to SMILES or CSV files
- **Info Tooltips**: View molecular data with click-to-pin tooltips
- **DataFrame Integration**: Automatic field detection from DataFrames

Basic Usage
-----------

Creating a Simple Grid
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from cnotebook import MolGrid
    from openeye import oechem

    # Create molecules
    molecules = []
    for smi in ["CCO", "c1ccccc1", "CC(=O)O"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smi)
        molecules.append(mol)

    # Create and display grid
    grid = MolGrid(molecules)
    grid.display()

Using the Convenience Function
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    from cnotebook import molgrid

    grid = molgrid(molecules, n_items_per_page=12)
    grid.display()

Customizing the Display
-----------------------

Image Settings
^^^^^^^^^^^^^^

Control the size and format of molecule images:

.. code-block:: python

    grid = MolGrid(
        molecules,
        width=150,           # Image width in pixels
        height=150,          # Image height in pixels
        image_format="svg",  # "svg" or "png"
        atom_label_font_scale=1.5,  # Scale factor for atom labels
    )

Pagination
^^^^^^^^^^

Control how many molecules appear per page:

.. code-block:: python

    grid = MolGrid(
        molecules,
        n_items_per_page=24,  # Molecules per page (default: 24)
    )

Title Display
^^^^^^^^^^^^^

Control molecule title display:

.. code-block:: python

    # Show titles from molecule's Title field
    grid = MolGrid(molecules, title_field="Title")

    # Show titles from SD data field
    grid = MolGrid(molecules, title_field="Name")

    # Hide titles
    grid = MolGrid(molecules, title_field=None)

Search and Filtering
--------------------

MolGrid provides two search modes accessible via the toggle in the toolbar:

Properties Mode (Text Search)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Search across molecule titles and configured search fields:

.. code-block:: python

    # Configure which fields are searchable
    grid = MolGrid(
        molecules,
        search_fields=["Name", "Category"],
    )

When using a DataFrame, string columns are automatically detected as searchable.

SMARTS Mode (Substructure Search)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Filter molecules by SMARTS substructure patterns. Switch to SMARTS mode using
the toggle in the toolbar, then enter a SMARTS pattern.

Common SMARTS patterns:

- ``c1ccccc1`` - Aromatic 6-membered ring
- ``[OH]`` - Hydroxyl group
- ``C(=O)O`` - Carboxylic acid
- ``[NX3]`` - Any nitrogen with 3 connections
- ``[#6][#6]`` - Carbon-carbon bond

Selection
---------

Enabling Selection
^^^^^^^^^^^^^^^^^^

Selection is enabled by default:

.. code-block:: python

    grid = MolGrid(molecules, select=True)   # Enabled (default)
    grid = MolGrid(molecules, select=False)  # Disabled

Selection Methods
^^^^^^^^^^^^^^^^^

Multiple ways to select molecules:

1. **Click on a molecule** to toggle its selection
2. **Click the checkbox** in the top-left corner
3. **Use the Actions menu** ("..." button):

   - Select All: Select all visible molecules
   - Clear Selection: Deselect all molecules
   - Invert Selection: Toggle selection state of all visible molecules

Retrieving Selections
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # Get selected molecule objects
    selected_mols = grid.get_selection()
    for mol in selected_mols:
        print(mol.GetTitle())

    # Get selected indices
    indices = grid.get_selection_indices()
    print(f"Selected indices: {indices}")

Exporting Selections
^^^^^^^^^^^^^^^^^^^^

Use the Actions menu to export selected molecules:

- **Copy to Clipboard**: Copy as CSV to clipboard
- **Save to SMILES**: Download as .smi file
- **Save to CSV**: Download as .csv file with all data columns

Info Button and Tooltips
------------------------

Each molecule cell has an info button ("i") in the top-right corner.

Viewing Information
^^^^^^^^^^^^^^^^^^^

- **Hover** over the "i" to see the tooltip
- **Click** the "i" to pin the tooltip open
- **Click again** to unpin

This allows comparing data across multiple molecules by pinning multiple tooltips.

Configuring Displayed Data
^^^^^^^^^^^^^^^^^^^^^^^^^^

Control what appears in the info tooltip using the ``data`` parameter:

.. code-block:: python

    # Display specific fields
    grid = MolGrid(molecules, data=["MW", "LogP"])

    # Display a single field (can use string instead of list)
    grid = MolGrid(molecules, data="Name")

    # Auto-detect from DataFrame (default when data=None)
    grid = MolGrid(
        molecules,
        dataframe=df,
        mol_col="Molecule",
        data=None,  # Auto-detects string/int/float columns
    )

The tooltip always displays:

1. **Index**: The molecule's position in the grid
2. **Title**: The molecule's title (if set)
3. **Data fields**: Additional fields from the ``data`` parameter

Disabling the Info Button
^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    grid = MolGrid(molecules, information=False)

DataFrame Integration
---------------------

Creating a Grid from a DataFrame
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import pandas as pd
    from cnotebook import MolGrid

    # Assuming df has a "Molecule" column with OEMol objects
    grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
    )
    grid.display()

Automatic Field Detection
^^^^^^^^^^^^^^^^^^^^^^^^^

When using a DataFrame, MolGrid automatically detects:

- **Search fields**: String columns for text search
- **Info fields**: All simple type columns (string, int, float) for the info tooltip

.. code-block:: python

    # Check what was auto-detected
    print(f"Search fields: {grid.search_fields}")
    print(f"Info fields: {grid.information_fields}")

Using DataFrame Accessors
^^^^^^^^^^^^^^^^^^^^^^^^^

Create a grid directly from a DataFrame column:

.. code-block:: python

    # From Series
    grid = df["Molecule"].chem.molgrid()

    # From DataFrame with options
    grid = df.chem.molgrid(
        mol_col="Molecule",
        title_field="Name",
        tooltip_fields=["SMILES"],
    )

Complete Example
----------------

.. code-block:: python

    import pandas as pd
    from openeye import oechem
    import oepandas as oepd
    from cnotebook import MolGrid

    # Create sample data
    data = {
        "Name": ["Ethanol", "Benzene", "Aspirin", "Caffeine"],
        "SMILES": ["CCO", "c1ccccc1", "CC(=O)OC1=CC=CC=C1C(=O)O",
                   "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"],
        "Category": ["Alcohol", "Aromatic", "NSAID", "Stimulant"],
        "MW": [46.07, 78.11, 180.16, 194.19],
    }

    df = pd.DataFrame(data)

    # Create molecules
    mols = []
    for _, row in df.iterrows():
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, row["SMILES"])
        mol.SetTitle(row["Name"])
        mols.append(mol)

    df["Molecule"] = mols
    df["Molecule"] = df["Molecule"].astype(oepd.MoleculeDtype())

    # Create comprehensive grid
    grid = MolGrid(
        df["Molecule"].tolist(),
        dataframe=df,
        mol_col="Molecule",
        title_field="Name",
        tooltip_fields=["SMILES"],
        data=["Category", "MW"],
        n_items_per_page=4,
        width=180,
        height=180,
        image_format="svg",
        select=True,
        information=True,
    )

    # Display
    grid.display()

    # Later, retrieve selections
    selected = grid.get_selection()
    print(f"Selected {len(selected)} molecules")

API Reference
-------------

MolGrid Class
^^^^^^^^^^^^^

.. py:class:: MolGrid(mols, *, dataframe=None, mol_col=None, title_field="Title", tooltip_fields=None, n_items_per_page=24, width=200, height=200, atom_label_font_scale=1.5, image_format="svg", select=True, information=True, data=None, search_fields=None, name=None)

   Interactive molecule grid widget.

   :param mols: Iterable of OpenEye molecule objects
   :param dataframe: Optional DataFrame with molecule data
   :param mol_col: Column name containing molecules (required if dataframe is provided)
   :param title_field: Molecule field to display as title, or None to hide
   :param tooltip_fields: List of fields for hover tooltip
   :param n_items_per_page: Number of molecules per page
   :param width: Image width in pixels
   :param height: Image height in pixels
   :param atom_label_font_scale: Scale factor for atom labels
   :param image_format: Image format ("svg" or "png")
   :param select: Enable selection checkboxes
   :param information: Enable info button with tooltip
   :param data: Column(s) to display in info tooltip; auto-detects if None with DataFrame
   :param search_fields: Fields for text search; auto-detects if None with DataFrame
   :param name: Grid identifier for tracking selections

   .. py:method:: display()

      Display the grid in the notebook.

      :returns: HTML object for display

   .. py:method:: to_html()

      Generate HTML representation of the grid.

      :returns: Complete HTML document as string

   .. py:method:: get_selection()

      Get list of selected molecules.

      :returns: List of selected OEMol objects

   .. py:method:: get_selection_indices()

      Get indices of selected molecules.

      :returns: List of selected indices (sorted)

molgrid Function
^^^^^^^^^^^^^^^^

.. py:function:: molgrid(mols, *, title_field="Title", tooltip_fields=None, n_items_per_page=24, width=200, height=200, image_format="svg", select=True, information=True, data=None, search_fields=None, name=None)

   Convenience function to create an interactive molecule grid.

   See :py:class:`MolGrid` for parameter documentation.

   :returns: MolGrid instance
