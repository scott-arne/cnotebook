import base64
import pickle

import pytest
from openeye import oechem

from cnotebook.core.io import (
    MoleculeParseError,
    load_design_unit,
    load_molecule,
    load_molecules,
)


def test_load_smiles():
    mol = load_molecule("c1ccccc1", "smiles")
    assert mol.NumAtoms() == 6


def test_molecule_parse_error_is_picklable():
    # The error crosses a ProcessPoolExecutor boundary in oefastapi, so it must
    # survive pickling with both its message and .format intact.
    err = MoleculeParseError("Could not parse SMILES.", "smiles")
    restored = pickle.loads(pickle.dumps(err))
    assert isinstance(restored, MoleculeParseError)
    assert str(restored) == "Could not parse SMILES."
    assert restored.format == "smiles"


def test_load_design_unit_roundtrip():
    # Build a design unit, serialize to oedu bytes, base64-encode, and read it back.
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    du = oechem.OEDesignUnit()
    oechem.OEUpdateDesignUnit(du, mol, oechem.OEDesignUnitComponents_Ligand)
    oss = oechem.oeosstream()
    assert oechem.OEWriteDesignUnit(oss, du)
    b64 = base64.b64encode(oss.str()).decode()
    loaded = load_design_unit(b64, encoding="base64")
    assert isinstance(loaded, oechem.OEDesignUnit)


def test_load_design_unit_bad_base64_raises():
    with pytest.raises(MoleculeParseError) as exc:
        load_design_unit("not valid base64 @@@", encoding="base64")
    assert exc.value.format == "oedu"


def test_load_inchi_uses_inchi_reader_not_smiles():
    # Benzene InChI; must parse to 6 carbons (would be wrong via OESmilesToMol).
    inchi = "InChI=1S/C6H6/c1-2-4-6-5-3-1/h1-6H"
    mol = load_molecule(inchi, "inchi")
    assert oechem.OECount(mol, oechem.OEIsCarbon()) == 6


def test_load_sdf_multi_record():
    sdf_one = _benzene_sdf()
    mols = load_molecules(sdf_one + sdf_one, "sdf")
    assert len(mols) == 2


def test_name_precedence_explicit_wins(monkeypatch):
    # When the caller passes nothing, title comes from the parsed record.
    mol = load_molecule("c1ccccc1 benzene", "smiles")
    assert mol.GetTitle() == "benzene"


def test_invalid_smiles_raises_parse_error():
    with pytest.raises(MoleculeParseError) as exc:
        load_molecule("this-is-not-smiles!!!", "smiles")
    assert exc.value.format == "smiles"


def test_text_format_rejects_base64_marker():
    with pytest.raises(MoleculeParseError):
        load_molecule("c1ccccc1", "smiles", encoding="base64")  # not valid base64


def test_unknown_format_raises():
    with pytest.raises(MoleculeParseError):
        load_molecule("xxx", "nope")


def _benzene_sdf() -> str:
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    oechem.OEAddExplicitHydrogens(mol)
    from openeye import oeomega
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    omega.Build(mol)
    oms = oechem.oemolostream()
    oms.SetFormat(oechem.OEFormat_SDF)
    oms.openstring()
    oechem.OEWriteMolecule(oms, mol)
    return oms.GetString().decode("utf-8")
