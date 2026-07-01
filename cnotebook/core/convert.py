"""Molecule conversion utilities for the C3D 3D viewer.

Converts OpenEye OEMolBase and OEDesignUnit objects into string
representations (SDF or PDB) that 3Dmol.js can consume.
"""

from __future__ import annotations

import base64
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openeye import oechem

from cnotebook.core.vocabulary import BINARY_MAP_FORMATS as _BINARY_MAP_FORMATS
from cnotebook.core.vocabulary import TEXT_MAP_FORMATS as _TEXT_MAP_FORMATS

log = logging.getLogger("cnotebook")


@dataclass
class MoleculeData:
    """Container for molecule data ready for 3Dmol.js consumption.

    :param name: Display name for the molecule.
    :param data: String content (SDF or PDB format).
    :param format: Format identifier (``"sdf"`` or ``"pdb"``).
    :param source_type: Origin type (``"molecule"`` or ``"design_unit"``).
    :param num_atoms: Number of atoms in the molecule.
    :param disabled: If True, the entry is hidden when the viewer starts.
    """

    name: str
    data: str
    format: str
    source_type: str
    num_atoms: int = 0
    disabled: bool = False


@dataclass
class MapData:
    """Container for volumetric map data ready for 3Dmol.js consumption.

    :param name: Display name for the map.
    :param data: Embedded map content.
    :param format: Format identifier (``"ccp4"`` or ``"cube"``).
    :param encoding: Data encoding (``"base64"`` or ``"text"``).
    """

    name: str
    data: str
    format: str
    encoding: str


_SUPPORTED_MAP_FORMATS = _BINARY_MAP_FORMATS | _TEXT_MAP_FORMATS


def convert_molecule(mol: oechem.OEMolBase, name: str | None = None, disabled: bool = False) -> MoleculeData:
    """Convert an OpenEye molecule to SDF string data for 3Dmol.js.

    If the molecule lacks 3D coordinates, conformer generation is
    attempted automatically via Omega. A warning is logged when this
    occurs.

    :param mol: OpenEye molecule to convert.
    :param name: Optional display name. Falls back to the molecule title,
        then to ``"molecule"``.
    :returns: :class:`MoleculeData` with ``format="sdf"`` and
        ``source_type="molecule"``.
    :raises TypeError: If *mol* is not an :class:`oechem.OEMolBase`.
    :raises ValueError: If conformer generation fails.

    Example::

        from openeye import oechem
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        data = convert_molecule(mol, name="benzene")
    """
    if not isinstance(mol, oechem.OEMolBase):
        raise TypeError(
            f"Expected OEMolBase, got {type(mol).__name__}"
        )

    mol = _ensure_3d_coords(mol)

    resolved_name = name or mol.GetTitle() or "molecule"

    if _has_residue_info(mol):
        data = _mol_to_pdb_string(mol)
        fmt = "pdb"
    else:
        data = _mol_to_sdf_string(mol)
        fmt = "sdf"

    return MoleculeData(
        name=resolved_name,
        data=data,
        format=fmt,
        source_type="molecule",
        num_atoms=mol.NumAtoms(),
        disabled=disabled,
    )


def convert_map(map_input: str | Path | Any, name: str | None = None, format: str | None = None) -> MapData:
    """Convert a local map path or OpenEye scalar grid for 3Dmol.js.

    Local paths are embedded directly. Binary CCP4-like formats are base64
    encoded, while cube files are embedded as UTF-8 text. OpenEye scalar
    grids are written to temporary CCP4 files before embedding.

    :param map_input: Local map path or :class:`oegrid.OEScalarGrid`.
    :param name: Optional display name. Path inputs fall back to the path
        stem, while scalar grids fall back to their title and then ``"map"``.
    :param format: Optional map format for path inputs.
    :returns: :class:`MapData` with embedded map content.
    :raises FileNotFoundError: If a path input does not exist.
    :raises ValueError: If a path input is not a file, the format is
        unsupported, or OpenEye grid writing fails.
    :raises TypeError: If *map_input* is not a supported map input.
    """
    if isinstance(map_input, (str, Path)):
        return _convert_map_path(Path(map_input), name=name, format=format)

    from openeye import oegrid

    if isinstance(map_input, oegrid.OEScalarGrid):
        return _convert_scalar_grid(map_input, name=name)

    raise TypeError(
        f"Expected a local map path or oegrid.OEScalarGrid, got {type(map_input).__name__}"
    )


def convert_design_unit(du: oechem.OEDesignUnit, name: str | None = None, disabled: bool = False) -> MoleculeData:
    """Convert an OpenEye design unit to PDB string data for 3Dmol.js.

    Extracts the full complex (all components) from the design unit and writes it as a PDB string.

    :param du: OpenEye design unit to convert.
    :param name: Optional display name. Falls back to the design unit title, then to ``"design_unit"``.
    :param disabled: bool, if ``True``, the entry will appear as disabled in the entries list.
    :returns: :class:`MoleculeData` with ``format="pdb"`` and ``source_type="design_unit"``.
    :raises TypeError: If *du* is not an :class:`oechem.OEDesignUnit`.

    Example::

        from openeye import oechem
        du = oechem.OEDesignUnit()
        oechem.OEReadDesignUnit("complex.oedu", du)
        data = convert_design_unit(du)
    """
    if not isinstance(du, oechem.OEDesignUnit):
        raise TypeError(
            f"Expected OEDesignUnit, got {type(du).__name__}"
        )

    resolved_name = name or du.GetTitle() or "design_unit"

    complex_mol = oechem.OEGraphMol()
    du.GetComponents(
        complex_mol,
        oechem.OEDesignUnitComponents_TargetComplex | oechem.OEDesignUnitComponents_ListComponents
    )

    # Extract the ligand separately and mark its atoms as HETATM
    # (This should probably be reported to OpenEye as a bug, as it should be unnecessary)
    lig_mol = oechem.OEGraphMol()
    if du.GetLigand(lig_mol):
        for atom in lig_mol.GetAtoms():
            res = oechem.OEAtomGetResidue(atom)
            res.SetHetAtom(True)
            oechem.OEAtomSetResidue(atom, res)
        oechem.OEAddMols(complex_mol, lig_mol)

    num_atoms = complex_mol.NumAtoms()
    pdb_string = _mol_to_pdb_string(complex_mol)

    return MoleculeData(
        name=resolved_name,
        data=pdb_string,
        format="pdb",
        source_type="design_unit",
        num_atoms=num_atoms,
        disabled=disabled,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _normalize_map_format(raw_format: str | None, path: Path | None = None) -> str:
    """Normalize and validate a map format string.

    :param raw_format: Explicit format name, with or without a leading dot.
    :param path: Optional path used for extension inference.
    :returns: Lowercase map format.
    :raises ValueError: If no supported format can be resolved.
    """
    fmt = raw_format
    if fmt is None and path is not None:
        fmt = path.suffix

    fmt = (fmt or "").lower().lstrip(".")
    if fmt not in _SUPPORTED_MAP_FORMATS:
        raise ValueError(f"Unsupported map format: {fmt or '<unknown>'}")

    return fmt


def _convert_map_path(path: Path, name: str | None = None, format: str | None = None) -> MapData:
    """Convert a filesystem map path to embedded map data.

    :param path: Local map file path.
    :param name: Optional display name. Defaults to the path stem.
    :param format: Optional format override.
    :returns: :class:`MapData` with embedded content.
    :raises FileNotFoundError: If *path* does not exist.
    :raises ValueError: If *path* is not a file or has an unsupported format.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    if not path.is_file():
        raise ValueError(f"Expected map path to be a file: {path}")

    fmt = _normalize_map_format(format, path=path)
    resolved_name = name or path.stem

    if fmt in _BINARY_MAP_FORMATS:
        data = base64.b64encode(path.read_bytes()).decode("ascii")
        return MapData(name=resolved_name, data=data, format=fmt, encoding="base64")

    data = path.read_text(encoding="utf-8")
    return MapData(name=resolved_name, data=data, format=fmt, encoding="text")


def _convert_scalar_grid(grid: Any, name: str | None = None) -> MapData:
    """Convert an OpenEye scalar grid to embedded CCP4 map data.

    :param grid: OpenEye ``OEScalarGrid`` instance.
    :param name: Optional display name.
    :returns: :class:`MapData` containing base64-encoded CCP4 data.
    :raises ValueError: If the temporary stream cannot be opened or grid
        writing fails.
    """
    from openeye import oegrid

    resolved_name = name
    if resolved_name is None and grid.IsTitleSet():
        resolved_name = grid.GetTitle()
    resolved_name = resolved_name or "map"

    with tempfile.NamedTemporaryFile(suffix=".ccp4") as temp_file:
        stream = oechem.oeofstream()
        if not stream.open(temp_file.name):
            raise ValueError("Failed to open temporary CCP4 stream for OEScalarGrid")
        try:
            if not oegrid.OEWriteGrid(stream, grid, oegrid.OEGridFileType_CCP4):
                raise ValueError("Failed to write OEScalarGrid as CCP4")
        finally:
            stream.close()

        data = base64.b64encode(Path(temp_file.name).read_bytes()).decode("ascii")

    return MapData(name=resolved_name, data=data, format="ccp4", encoding="base64")


def _has_residue_info(mol: oechem.OEMolBase) -> bool:
    """Check if a molecule contains standard protein residues.

    When a molecule has more than one standard protein residue it likely
    originated from a PDB file and should be written as PDB to preserve
    HETATM flags, chain IDs, and residue numbering that 3Dmol.js presets
    rely on.

    :param mol: Molecule to inspect.
    :returns: True if the molecule contains standard protein residues.
    """
    return oechem.OECount(mol, oechem.OEIsStandardAminoAcid()) > 1


def _mol_to_sdf_string(mol: oechem.OEMolBase) -> str:
    """Write an OEMolBase to an SDF-format string.

    :param mol: Molecule with valid 3D coordinates.
    :returns: SDF string including the ``$$$$`` record terminator.
    """
    oms = oechem.oemolostream()
    oms.openstring()
    oms.SetFormat(oechem.OEFormat_SDF)
    oechem.OEWriteMolecule(oms, mol)
    return oms.GetString().decode("utf-8")


def _mol_to_pdb_string(mol: oechem.OEMolBase) -> str:
    """Write an OEMolBase to a PDB-format string.

    :param mol: Molecule with valid 3D coordinates.
    :returns: PDB-format string with ATOM/HETATM records.
    """
    oms = oechem.oemolostream()
    oms.openstring()
    oms.SetFormat(oechem.OEFormat_PDB)
    oms.SetFlavor(
        oechem.OEFormat_PDB,
        oechem.OEOFlavor_PDB_DEFAULT | oechem.OEOFlavor_PDB_BONDS | oechem.OEOFlavor_PDB_ORDERS
    )
    oechem.OEWriteMolecule(oms, mol)
    val = oms.GetString().decode("utf-8")
    oms.close()
    return val


def _ensure_3d_coords(mol: oechem.OEMolBase) -> oechem.OEMolBase:
    """Ensure the molecule has 3D coordinates.

    If the molecule dimension is not 3, Omega is used to generate a
    single conformer. The original molecule is not modified; a copy
    (as :class:`oechem.OEMol`) is returned when generation is needed.

    :param mol: Input molecule (may be 2D or lacking coordinates).
    :returns: Molecule with 3D coordinates (may be a new OEMol copy).
    :raises ValueError: If Omega conformer generation fails.
    """
    # 2D and 3D are OK
    if mol.GetDimension() >= 2:
        return mol

    log.warning(
        "Molecule '%s' lacks 3D coordinates; generating with OEOmega.",
        mol.GetTitle() or "untitled",
    )

    from openeye import oeomega

    work_mol = oechem.OEMol(mol)
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    omega.SetStrictStereo(False)

    if not omega(work_mol):
        raise ValueError(
            f"Failed to generate 3D coordinates for molecule "
            f"'{mol.GetTitle() or 'untitled'}'"
        )

    return work_mol
