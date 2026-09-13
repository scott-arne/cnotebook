# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2026-09-13

### Added
- `cnotebook.render_molecule`, `render_display`, `render_design_unit`, `save_image` headless rendering API
- `cnotebook.context.render_options()` context manager, `cnotebook.configure()`, `get_config()`, and a TOML configuration file
- `CNotebookContext.device_pixel_ratio` (HiDPI PNG output)
- Live anywidget outputs for C3D and MolGrid with `display(static=...)`, `save()`, and a global display mode
- C3D: `execute`, `on_pick`/`picked`, `view`/`set_view`/`save_view`/`restore_view`, `screenshot`/`save_png`, `color_entry`, `label_residues`, `measure_distance`, `add_conformers`, `animate`
- MolGrid: on-demand image loading, `badges`, `sort_by`, `theme`, `selection_frame()`, `close()`, cluster sequences and mappings
- pandas `df.chem.style()`, `color_column` for `highlight_using_column`, `alignment_report`
- polars token-based column settings that survive frame operations (requires oepolars 0.4.0)
- Post-import hooks, lazy exports, `CNotebookWarning`, `CNotebookError`
- JavaScript test suite, headless smoke check, GitHub Actions CI

### Changed
- One table plan renders pandas (through pandas' own writer), polars and marimo frames with shared cell formatters
- 3dmol-js-gui updated to 0.4.0 (host API, distance measurements, frame animation, label templates)
- Import no longer imports pandas, polars, marimo or anywidget
- `import cnotebook` costs about 90 ms beyond the OpenEye toolkits
- A 5000-row molecule frame renders only the pandas display window: 12 table rows, about 40 KB
- Dependency floors raised to `pandas>=2.2.2` (NumPy 2 compatibility with oepandas 3.3.0), `polars>=1.44.1` and `oepolars>=0.4.0`; supported Python is 3.11-3.13 (3.10 dropped)

### Fixed
- D01 MCS alignment no longer aborts the kernel
- D02 Displaying a molecule no longer destroys its 3D coordinates or hydrogens
- D03 Display columns keep their molecules alive; rendering after the source frame is dropped no longer hangs
- D04 MolGrid no longer allows script or attribute injection from data
- D05 SMARTS alignment aligns instead of silently failing
- D06 `cnotebook.display(df)` honours per-column settings
- D07 pandas column render options apply in Jupyter tables
- D08 Local contexts defer `title` and `atom_label_font_scale`
- D09 polars highlights render in marimo
- D10 The dict form of MolGrid `cluster` works
- D11 2D molecules receive 3D coordinates before 3D display
- D12 Multi-record SMILES input parses every record
- D13 DataFrame `recalculate_depiction_coordinates` works (misspelled keyword removed)
- D14 `None` molecules render as placeholders in MolGrid; SMARTS search reports errors
- D15 `fingerprint_similarity` tolerates `None` and invalid rows
- D16 `align_depictions` skips `None` rows and forwards keyword arguments
- D17 polars alignment accepts SMARTS references without mutating them
- D18 Bare OpenEye objects render without oepandas installed
- D19 `hasattr(cnotebook, "MolGrid")` works
- D20 Non-clustered grids no longer raise a JavaScript ReferenceError
- D21 Placeholder images tolerate missing minimum sizes
- D22 `structure_scale <= 0` is rejected with guidance
- D23 `series.chem.molgrid` works on pandas 3 (`frame=` argument)
- D24 MolGrid instances are released after `close()`
- D25 Repeated SMARTS queries are re-evaluated
- D26 Non-string column labels work in MolGrid
- D27 polars fingerprint similarity prepares depictions before alignment
- D28 polars similarity displays keep their molecules alive
- D29 `render_dataframe` never mutates caller dictionaries
- D30 All-`None` display columns render
- D31 `cnotebook.grid` imports without pandas
- D32 IPython formatter registration uses `lookup_by_type`
- D33 HTML wrappers respect `max_width`/`max_height`
- D34 Constructing a MolGrid has no display side effect
- D35 Invalid SMARTS patterns produce a visible message
- D36 User-facing warnings use the `warnings` module
- D37 No logging handler is attached at import
- D38 DataFrame output truncates like pandas and polars
- D39 Only displayed rows are copied and depicted
- D40 Packaging metadata corrected (extras, classifiers, package data)
- D41 Optional libraries are no longer imported at import time
- D42 Ordinary cells escape ampersands
- D43 Documentation examples use the correct `add_style` argument order
- D44 ruff and mypy baselines are clean

### Removed
- `pd.DataFrame._mime_` and polars `_mime_` monkey-patches
- The id-keyed polars column store
- List.js and the inline grid JavaScript

### Migration
- M01 MolGrid constructor no longer displays; call `display()`
- M02 Widget output is the default; use `display(static=True)`, `to_html()`, `save()`, or `configure(display_mode="static")`
- M03 `cnotebook.display(df)` honours column settings; pass `ctx=` to override
- M04 DataFrame output truncates; `render_dataframe(df, max_rows=0)` for all rows
- M05 Displaying molecules never mutates them
- M06 pandas alignment and recalculation replace column molecules with copies
- M07 pandas `series.chem.align_depictions` returns an `AlignmentReport`
- M08 polars accessor methods return new frames
- M09 polars requires `oepolars>=0.4.0`
- M10 `series.chem.molgrid(frame=df)`
- M11 `structure_scale <= 0` raises; use `auto_scale=True`
- M12 Context option validation raises `ValueError`
- M13 Warnings are `CNotebookWarning`
- M14 Call `enable_debugging()` for console logging
- M15 `oedu_to_disp` returns a `Depiction`
- M16 `render_dataframe` ignores `escape=`
- M17 Keyword spelled `add_depiction_hydrogens`
- M18 Post-import hooks attach integrations; `CNOTEBOOK_NO_IMPORT_HOOKS=1` opts out
- M19 `get_env()` is computed per call
- M20 Unavailable exports raise `AttributeError`
- M21 PNG rasterised at device pixel ratio 2
- M22 Live outputs are widget instances
- M23 Differently tokened polars frames cannot be concatenated; `reset_depictions()` first

## [3.1.3] - 2026-09-05

### Changed
- C3D: updated bundled 3dmol-js-gui to 0.3.4
  - Zoom, orient, and the initial fit keep the whole selection inside the frame with a margin instead of placing its edge flush against the viewport
  - UI panel visibility, theme, and background are applied before molecules load, so the viewer no longer flashes the default chrome and dark theme while structures load
  - Sidebar entries show type glyphs and a unified chevron

## [3.1.1] - 2026-07-05

### Fixed
- Importing `molgrid`/`MolGrid` or `C3D` from `cnotebook` now raises a clear, actionable error when the optional module is unavailable (e.g. `molgrid` when `anywidget` is not installed) instead of a cryptic `cannot import name` error.

## [3.1.0] - 2026-07-04

### Added
- `invoke update-gui` task to build and copy 3dmol-js-gui assets from the vendor submodule
- 3dmol-js-gui added as a git submodule at `vendor/3dmol-js-gui`
- `CNotebookContext.auto_scale` (and matching MolGrid / DataFrame render options) to size structures to fill the image canvas instead of using a fixed scale
- `CNotebookContext.effective_scale` read-only property exposing the resolved OpenEye display scale

### Changed
- **Breaking:** `structure_scale` is now a factor multiplied by `oedepict.OEScale_Default` (default `0.6`) rather than an absolute OpenEye scale. Autoscaling is now controlled by the new `auto_scale` flag instead of setting `structure_scale = oedepict.OEScale_AutoScale`. The default rendered size is unchanged.

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
