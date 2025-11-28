# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

---

[1.0.0]: https://github.com/[username]/cnotebook/releases/tag/v1.0.0
