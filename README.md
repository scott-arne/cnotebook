# CNotebook - Chemistry Visualization for Jupyter & Marimo

**Author:** Scott Arne Johnson ([scott.arne.johnson@gmail.com](mailto:scott.arne.johnson@gmail.com))

CNotebook provides ergonomic chemistry visualization in Jupyter Notebooks and Marimo with the OpenEye Toolkits. Simply import the package and your molecular data will be automatically rendered as beautiful chemical structures - no additional configuration required!

## 🚀 Quick Start

### Installation

```bash
pip install cnotebook
```

**Prerequisites:** Requires OpenEye Toolkits and oepandas to be installed and properly licensed.

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

That's it! CNotebook automatically registers formatters so that OpenEye molecule objects display as chemical structures instead of cryptic text representations.

## 📚 Features

### ✨ Automatic Rendering
- **Zero Configuration**: Just import and go - molecules automatically render as structures
- **Multiple Formats**: Supports both Jupyter Notebooks and Marimo environments
- **Smart Detection**: Automatically detects your notebook environment

### 🧪 Molecule Support
- **OEMol Objects**: Direct rendering of `oechem.OEMolBase` derived objects
- **OE2DMolDisplay**: Advanced rendering with custom depiction options
- **Pandas Integration**: Seamless rendering in DataFrames with oepandas

### 🎨 Visualization Options
- **Multiple Formats**: PNG (default) or SVG output
- **Customizable Sizing**: Configurable width, height, and scaling
- **Grid Layouts**: Multi-molecule grid displays
- **Substructure Highlighting**: SMARTS pattern highlighting
- **Molecular Alignment**: Align molecules to reference structures

### 📊 Pandas Integration
- **DataFrame Rendering**: Automatic molecule column detection and rendering
- **Column Highlighting**: Highlight different patterns per row
- **Alignment Tools**: Align molecular depictions in DataFrames
- **Fingerprint Similarity**: Visual similarity coloring
- **Property Calculation**: Chemistry-aware DataFrame operations

## 🛠️ Environment Support

### Jupyter Notebooks
CNotebook automatically integrates with Jupyter when imported:

```python
import cnotebook
import pandas as pd
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

## 📖 Advanced Usage

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

### Molecule Grids

```python
# Display multiple molecules in a grid
molecules = [mol1, mol2, mol3, mol4]
cnotebook.render_molecule_grid(
    molecules,
    ncols=2,
    smarts="c1ccccc1",  # Highlight benzene rings
    scale=0.8
)
```

### Pandas DataFrame Integration

```python
import oepandas as oepd
import pandas as pd

# Create DataFrame with SMILES
df = pd.DataFrame({
    "Name": ["Benzene", "Pyridine", "Pyrimidine"],
    "SMILES": ["c1ccccc1", "c1cnccc1", "n1cnccc1"]
})

# Convert to molecules
df.as_molecule("SMILES", inplace=True)

# DataFrame automatically renders molecules as structures
df  # Molecule column shows chemical structures!

# Add substructure highlighting
df.SMILES.highlight("c1ccccc1")  # Highlight aromatic rings
df

# Align molecules to a reference
df.SMILES.align_depictions("first")  # Align to first molecule
df
```

### Substructure Highlighting

```python
# Highlight SMARTS patterns
df["Pattern"] = ["cc", "cnc", "ncn"]
df.highlight_using_column("Molecule", "Pattern", inplace=True)
df  # Shows molecules with different highlights per row
```

### Fingerprint Similarity

```python
# Color molecules by fingerprint similarity
reference_mol = oechem.OEGraphMol()
oechem.OESmilesToMol(reference_mol, "c1ccc(N)cc1")

df.fingerprint_similarity("Molecule", reference_mol, inplace=True)
df  # Shows similarity coloring and Tanimoto coefficients
```

## 📁 Demo Notebooks

Explore comprehensive examples in the `demos/` directory:

### [Small_Molecules.ipynb](demos/Small_Molecules.ipynb)
**Complete CNotebook Tutorial** - Comprehensive guide covering:
- Basic molecule rendering and display options
- OE2DMolDisplay objects with custom styling
- Molecule grid layouts with highlighting
- Advanced rendering configuration
- Pandas DataFrame integration with oepandas
- Substructure highlighting and SMARTS patterns
- Column-based highlighting with different patterns per row
- Molecular alignment techniques
- Fingerprint similarity visualization
- Empty and invalid molecule handling

### [SVGs.ipynb](demos/SVGs.ipynb)
**SVG Rendering Guide** - Learn how to:
- Switch from PNG to SVG output format
- Benefits and trade-offs of SVG vs PNG
- High-quality crisp molecular graphics
- SVG compatibility considerations

## 🔧 Configuration Options

### Global Context Settings

```python
ctx = cnotebook.cnotebook_context.get()

# Image dimensions
ctx.width = 250          # Default width in pixels
ctx.height = 250         # Default height in pixels
ctx.max_width = 1200     # Maximum width (prevents oversized molecules)
ctx.max_height = 800     # Maximum height

# Output format
ctx.image_format = "png"  # or "svg"

# Display options
ctx.scale = 1.0          # Scaling factor
```

### Environment-Specific Behavior

- **Jupyter**: Supports both PNG and SVG formats
- **Marimo**: Automatically uses PNG format for compatibility
- **Console**: Falls back to string representations

## 🤝 Contributing

We welcome contributions! Please ensure your code:
- Follows existing code style and conventions
- Includes appropriate tests
- Works with both Jupyter and Marimo environments
- Maintains compatibility with OpenEye Toolkits

## 📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## 🐛 Issues & Support

For bug reports, feature requests, or general support, please open an issue on GitHub or contact the author at [scott.arne.johnson@gmail.com](mailto:scott.arne.johnson@gmail.com).

---

*CNotebook makes chemical data visualization effortless. Import once, visualize everywhere!* 🧬✨