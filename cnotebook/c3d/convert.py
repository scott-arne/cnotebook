"""Molecule conversion utilities for the C3D 3D viewer.

Converts OpenEye OEMolBase and OEDesignUnit objects into string
representations (SDF or PDB) that 3Dmol.js can consume.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from openeye import oechem

log = logging.getLogger("cnotebook")


@dataclass
class MoleculeData:
    """Container for molecule data ready for 3Dmol.js consumption.

    :param name: Display name for the molecule.
    :param data: String content (SDF or PDB format).
    :param format: Format identifier (``"sdf"`` or ``"pdb"``).
    :param source_type: Origin type (``"molecule"`` or ``"design_unit"``).
    """

    name: str
    data: str
    format: str
    source_type: str


def convert_molecule(mol: oechem.OEMolBase, name: str | None = None) -> MoleculeData:
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

    if name is None:
        title = mol.GetTitle()
        name = title if title else "molecule"

    sdf_string = _mol_to_sdf_string(mol)

    return MoleculeData(
        name=name,
        data=sdf_string,
        format="sdf",
        source_type="molecule",
    )


def convert_design_unit(du: oechem.OEDesignUnit, name: str | None = None) -> MoleculeData:
    """Convert an OpenEye design unit to PDB string data for 3Dmol.js.

    Extracts the full complex (all components) from the design unit and
    writes it as a PDB string.

    :param du: OpenEye design unit to convert.
    :param name: Optional display name. Falls back to the design unit
        title, then to ``"design_unit"``.
    :returns: :class:`MoleculeData` with ``format="pdb"`` and
        ``source_type="design_unit"``.
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

    if name is None:
        title = du.GetTitle()
        name = title if title else "design_unit"

    pdb_string = _du_to_pdb_string(du)

    return MoleculeData(
        name=name,
        data=pdb_string,
        format="pdb",
        source_type="design_unit",
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


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


def _du_to_pdb_string(du: oechem.OEDesignUnit) -> str:
    """Extract all components from a design unit and write as PDB.

    :param du: Design unit to extract from.
    :returns: PDB-format string with ATOM/HETATM records.
    """
    complex_mol = oechem.OEGraphMol()
    du.GetComponents(complex_mol, oechem.OEDesignUnitComponents_All)

    oms = oechem.oemolostream()
    oms.openstring()
    oms.SetFormat(oechem.OEFormat_PDB)
    oechem.OEWriteMolecule(oms, complex_mol)
    return oms.GetString().decode("utf-8")


def _ensure_3d_coords(mol: oechem.OEMolBase) -> oechem.OEMolBase:
    """Ensure the molecule has 3D coordinates.

    If the molecule dimension is not 3, Omega is used to generate a
    single conformer. The original molecule is not modified; a copy
    (as :class:`oechem.OEMol`) is returned when generation is needed.

    :param mol: Input molecule (may be 2D or lacking coordinates).
    :returns: Molecule with 3D coordinates (may be a new OEMol copy).
    :raises ValueError: If Omega conformer generation fails.
    """
    if mol.GetDimension() == 3:
        return mol

    log.warning(
        "Molecule '%s' lacks 3D coordinates; generating with Omega.",
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
