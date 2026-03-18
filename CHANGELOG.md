# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `invoke update-gui` task to build and copy 3dmol-js-gui assets from the vendor submodule
- 3dmol-js-gui added as a git submodule at `vendor/3dmol-js-gui`

## [2.2.9] - 2026-03-18

### Fixed
- C3D: ligand atoms from design units now have HETATM flag set, fixing preset ligand detection (e.g., `sites` preset showing ligands as sticks)
- C3D: updated 3dmol-js-gui to 0.2.1, fixing empty viewer caused by demo code in the production bundle

## [2.2.8] - 2026-03-17

### Added
- C3D: auto theme detection with `theme` constructor parameter (`"light"`, `"dark"`, `"auto"`)
- C3D: batch `add_molecules` and `add_design_units` methods

## [2.2.7] - 2026-03-11

### Fixed
- Design units are now sent to C3D using the correct component flags (`OEDesignUnitComponents_TargetComplex | OEDesignUnitComponents_ListComponents`)

## [2.2.6] - 2026-03-11

### Fixed
- Two bugs related to exporting clustered and filtered rows in MolGrid

## [2.2.5] - 2026-03-09

### Fixed
- `OEQMol` was not being treated as a substructure for molecular alignment

## [2.2.4] - 2026-03-09

### Added
- C3D: `set_color` method for custom atom/bond coloring
- C3D: hydrogen atoms are now retained in 3D structures

### Fixed
- C3D: view presets corrected

## [2.2.3] - 2026-03-08

### Fixed
- C3D static files were missing from the package distribution

## [2.2.2] - 2026-02-19

### Fixed
- Skip rendering molecules that exceed `CNotebookContext.max_heavy_atoms` instead of failing

## [2.2.1] - 2026-02-18

### Fixed
- Updated bundled 3dmol-js-gui assets and improved C3D documentation

## [2.2.0] - 2026-02-18

### Added
- **C3D interactive 3D viewer** powered by 3Dmol.js with built-in GUI, terminal, and sidebar
- Builder-style API for adding molecules and design units
- View presets (`simple`, `sites`, `ball-and-stick`)
- Custom atom styles and string-based selection expressions
- `OEDesignUnit` rendering with consistent OEImage-based Marimo formatters

## [2.1.3] - 2026-02-06

### Added
- MolGrid: cluster viewing with dropdown navigation and cluster pills
- MolGrid: `cluster` and `cluster_counts` parameters

## [2.1.2] - 2026-02-03

### Fixed
- MolGrid JavaScript assets were missing from `pyproject.toml` package data

## [2.1.1] - 2026-02-02

### Changed
- Simplified MolGrid `title` parameter API

## [2.1.0] - 2026-02-02

### Added
- **MolGrid interactive molecule grid** with pagination, search, SMARTS filtering, and selection
- Actions dropdown with export to SMILES and CSV
- Information tooltips with click-to-pin and configurable data fields
- Pandas and Polars DataFrame accessors for MolGrid (`df.chem.molgrid()`)
- Atom label font scaling (default 1.5)
- Sphinx documentation

### Changed
- Renamed `molgrid` module to `grid`
- Improved DataFrame-level API consistency across Pandas and Polars

## [2.0.0] - 2026-01-20

### Added
- **Polars DataFrame support** with full feature parity via OEPolars

### Changed
- Minimum Python version updated to 3.11

## [1.2.0] - 2026-01-16

### Changed
- Updated example notebooks and aligned requirements for Python >= 3.11

## [1.1.0] - 2026-01-15

### Added
- Full Marimo/Jupyter feature parity for molecule and DataFrame rendering
- SVG support in Marimo respecting user's `image_format` preference
- `render_molecule_grid` shared across Jupyter and Marimo

## [1.0.1] - 2026-01-10

### Added
- Basic Marimo support for Pandas DataFrame visualization

## [1.0.0] - 2025-11-28

### Added
- **First public release under MIT License**
- Enhanced Marimo support with OE2DMolDisplay and OEImage rendering
- Comprehensive test suite with 215 tests
- Support for both Jupyter Notebooks and Marimo environments
- Zero-configuration automatic molecule rendering
- Pandas DataFrame integration with custom accessors
- SMARTS-based substructure highlighting
- Molecular alignment using MCSS
- Fingerprint similarity visualization with Tanimoto coefficients
- PNG and SVG output format support
- Molecule grid layouts with customizable parameters
- Context-based configuration system
- Comprehensive demo notebooks (Small_Molecules.ipynb, SVGs.ipynb)
- Marimo demo example (marimo_demo.py)

### Changed
- Migrated from unittest to pytest for testing framework
- Updated version from 0.8.0 to 1.0.0 for public release
- Updated package metadata for open source distribution
- Improved tasks.py with pytest integration and PyPI upload support

### Technical Details
- Python 3.10+ required
- Dependencies: pandas, oepandas>=1.3.0, openeye-toolkits
- MIT License
- Comprehensive documentation and examples included

---

## Pre-1.0.0 Development History

Prior to v1.0.0, this project was developed internally with the following major milestones:

### [0.8.0] - 2025-01-31
- SVG rendering support and optimization
- Bug fixes and performance improvements

### [0.7.0] - 2024-09-13
- Initial Marimo notebook support
- Multiple bug fixes and optimizations
- Spelling corrections in documentation

### [0.6.0] - 2024-11-12
- Improved DataFrame slicing and indexing
- Fixed molecule copying issues during rendering
- Enhanced depiction handling

### Early Development
- Core rendering engine implementation
- IPython/Jupyter integration
- Pandas DataFrame visualization
- OpenEye Toolkits integration
- Molecular alignment and fingerprinting
- SMARTS pattern highlighting
