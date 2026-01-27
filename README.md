# CNotebook

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![OpenEye Toolkits](https://img.shields.io/badge/OpenEye-2025.2.1+-green.svg)](https://www.eyesopen.com/toolkits)


**Author:** Scott Arne Johnson ([scott.arne.johnson@gmail.com](mailto:scott.arne.johnson@gmail.com))

CNotebook provides ergonomic chemistry visualization in Jupyter Notebooks and Marimo with the OpenEye Toolkits. Simply import the package and your molecular data will be automatically rendered as beautiful chemical structures - no additional configuration required.

**Supports both Pandas and Polars DataFrames** - CNotebook auto-detects your environment and works with whichever DataFrame library you prefer.

## Quick Start

### Installation

```bash
pip install cnotebook
```

**Prerequisites:** Requires OpenEye Toolkits to be installed and properly licensed.

**Optional backends:**
- **Pandas**: `pip install pandas oepandas` - For Pandas DataFrame support
- **Polars**: `pip install polars oepolars` - For Polars DataFrame support
- Both can be installed together - CNotebook will work with either or both

### Basic Usage

```python
import cnotebook
from openeye import oechem

# Create a molecule
mol = oechem.OEGraphMol()
oechem.OESmilesToMol(mol, "n1cnccc1")

# Display it - automatically renders as a chemical structure!
mol
```

That's it. CNotebook automatically registers formatters so that OpenEye molecule objects display as chemical structures instead of cryptic text representations.

## Features

### Automatic Rendering
- **Zero Configuration**: Just import and go - molecules automatically render as structures
- **Multiple Formats**: Supports both Jupyter Notebooks and Marimo environments
- **Smart Detection**: Automatically detects your notebook environment and available backends

### Molecule Support
- **OEMol Objects**: Direct rendering of `oechem.OEMolBase` derived objects
- **OE2DMolDisplay**: Advanced rendering with custom depiction options
- **Pandas Integration**: Seamless rendering in DataFrames with OEPandas
- **Polars Integration**: Native Polars DataFrame support with OEPolars

### Visualization Options
- **Multiple Formats**: PNG (default) or SVG output
- **Customizable Sizing**: Configurable width, height, and scaling
- **Substructure Highlighting**: SMARTS pattern highlighting
- **Molecular Alignment**: Align molecules to reference structures

### MolGrid Interactive Visualization
- **Interactive Grid**: Browse, search, and select molecules in paginated grids
- **Text Search**: Filter by molecular properties
- **SMARTS Filtering**: Substructure search with SMARTS patterns
- **Selection Tools**: Select molecules with export to SMILES/CSV
- **Info Tooltips**: Click-to-pin tooltips for comparing molecular data
- **DataFrame Integration**: Automatic column detection for search and display

### DataFrame Integration (Pandas & Polars)
- **DataFrame Rendering**: Automatic molecule column detection and rendering
- **Column Highlighting**: Highlight different patterns per row
- **Alignment Tools**: Align molecular depictions in DataFrames
- **Fingerprint Similarity**: Visual similarity coloring
- **Property Calculation**: Chemistry-aware DataFrame operations

## MolGrid: Interactive Molecule Grids

MolGrid provides an interactive grid for browsing large molecular datasets with powerful search and selection capabilities.

### Quick Example

```python
from cnotebook import MolGrid
from openeye import oechem

# Create molecules
molecules = []
for smi in ["CCO", "c1ccccc1", "CC(=O)O"]:
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smi)
    molecules.append(mol)

# Display interactive grid
grid = MolGrid(molecules)
grid.display()
```

### Key Features

**Search and Filter:**
- Toggle between Properties (text) and SMARTS (substructure) search modes
- Properties mode searches titles and configurable fields
- SMARTS mode filters by substructure patterns

**Selection:**
- Click molecules or checkboxes to select
- Use the "..." menu for Select All, Clear, Invert operations
- Export selections to SMILES or CSV files

**Info Tooltips:**
- Hover over the "i" button to see molecular data
- Click to pin tooltips open for comparing multiple molecules
- Configure displayed fields with the `data` parameter

### DataFrame Integration

```python
import pandas as pd
from cnotebook import MolGrid

# Create grid from DataFrame
grid = MolGrid(
    df["Molecule"].tolist(),
    dataframe=df,
    mol_col="Molecule",
    data=["Name", "MW"],  # Fields for info tooltip
)
grid.display()

# Or use the DataFrame accessor
grid = df["Molecule"].chem.molgrid()
grid.display()
```

### Retrieving Selections

```python
# Get selected molecules
selected_mols = grid.get_selection()

# Get selected indices
indices = grid.get_selection_indices()
```

See the [MolGrid Demo Notebooks](#demo-notebooks) for comprehensive examples.

## Environment Support

### Jupyter Notebooks
CNotebook automatically integrates with Jupyter when imported:

```python
import cnotebook
from openeye import oechem

# Molecules will automatically render in cells
mol = oechem.OEGraphMol()
oechem.OESmilesToMol(mol, "CCO")
mol  # Displays as chemical structure
```

### Marimo
CNotebook provides seamless Marimo integration:

```python
import marimo as mo
import cnotebook
from openeye import oechem

# Create and display molecules
mol = oechem.OEGraphMol()
oechem.OESmilesToMol(mol, "c1ccccc1")
mol  # Automatically renders as PNG for Marimo compatibility
```

## DataFrame Usage

### Pandas DataFrames

```python
import cnotebook
import oepandas as oepd
import pandas as pd

# Create DataFrame with SMILES
df = pd.DataFrame({
    "Name": ["Benzene", "Pyridine", "Pyrimidine"],
    "SMILES": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
})

# Convert to molecules
df.chem.as_molecule("SMILES", inplace=True)

# DataFrame automatically renders molecules as structures
df  # Molecule column shows chemical structures!

# Add substructure highlighting
df.SMILES.chem.highlight("c1ccccc1")  # Highlight aromatic rings
df

# Align molecules to a reference
df.SMILES.chem.align_depictions("first")  # Align to first molecule
df
```

### Polars DataFrames

```python
import cnotebook
import oepolars as oeplr
import polars as pl

# Read molecules from a SMILES file
df = oeplr.read_smi("molecules.smi")

# Or create from SMILES column
df = pl.DataFrame({
    "Name": ["Benzene", "Pyridine", "Pyrimidine"],
    "smiles": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
})
df = df.chem.as_molecule("smiles")

# DataFrame automatically renders molecules as structures
df  # Molecule column shows chemical structures!

# Add substructure highlighting
df.get_column("smiles").chem.highlight("c1ccccc1")
df

# Align molecules to a reference
df.get_column("smiles").chem.align_depictions("first")
df
```

## Advanced Usage

### Rendering Configuration

```python
# Access global rendering context
ctx = cnotebook.cnotebook_context.get()

# Customize rendering options
ctx.width = 300
ctx.height = 300
ctx.image_format = "svg"  # Use SVG instead of PNG
ctx.max_width = 600      # Prevent oversized molecules

# Reset to defaults
ctx.reset()
```

### Substructure Highlighting

```python
# Highlight SMARTS patterns in Pandas
df["Pattern"] = ["cc", "cnc", "ncn"]
df.chem.highlight_using_column("Molecule", "Pattern", inplace=True)
df  # Shows molecules with different highlights per row

# Highlight SMARTS patterns in Polars
df = df.chem.highlight_using_column("Molecule", "Pattern")
df  # Shows molecules with different highlights per row
```

### Fingerprint Similarity

```python
# Color molecules by fingerprint similarity (Pandas)
reference_mol = oechem.OEGraphMol()
oechem.OESmilesToMol(reference_mol, "c1ccc(N)cc1")
df.chem.fingerprint_similarity("Molecule", reference_mol, inplace=True)
df  # Shows similarity coloring and Tanimoto coefficients

# Polars version
df = df.chem.fingerprint_similarity("Molecule", reference_mol)
df  # Shows similarity coloring and Tanimoto coefficients
```

## Demo Notebooks

Explore comprehensive examples in the `demos/` directory:

### Jupyter Demos
- **[pandas_jupyter_demo.ipynb](demos/pandas_jupyter_demo.ipynb)** - Complete Pandas tutorial
- **[polars_jupyter_demo.ipynb](demos/polars_jupyter_demo.ipynb)** - Complete Polars tutorial
- **[molgrid_jupyter_demo.ipynb](demos/molgrid_jupyter_demo.ipynb)** - MolGrid interactive grids

### Marimo Demos
- **[pandas_marimo_demo.py](demos/pandas_marimo_demo.py)** - Complete Pandas tutorial
- **[polars_marimo_demo.py](demos/polars_marimo_demo.py)** - Complete Polars tutorial
- **[molgrid_marimo_demo.py](demos/molgrid_marimo_demo.py)** - MolGrid interactive grids

## Documentation

Full API documentation is available in the `docs/` directory. Build the documentation locally with Sphinx:

```bash
cd docs
make html
```

Then open `docs/_build/html/index.html` in your browser.

## Contributing

We welcome contributions. Please ensure your code:
- Follows existing code style and conventions
- Includes appropriate tests
- Works with both Jupyter and Marimo environments
- Maintains compatibility with OpenEye Toolkits
- Works with both Pandas and Polars when applicable

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Issues & Support

For bug reports, feature requests, or general support, please open an issue on GitHub or contact the author at [scott.arne.johnson@gmail.com](mailto:scott.arne.johnson@gmail.com).

---

*CNotebook makes chemical data visualization effortless. Import once, visualize everywhere.*
