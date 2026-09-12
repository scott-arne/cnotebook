"""Tests for the C3D molecule conversion module."""

import os
import warnings

import pytest
from openeye import oechem

from cnotebook.c3d.convert import (
    MoleculeData,
    convert_conformers,
    convert_design_unit,
    convert_molecule,
)
from cnotebook.core.errors import CNotebookWarning

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_ASSET_DIR = os.path.join(os.path.dirname(__file__), os.pardir, "examples", "assets")
_DU_PATH = os.path.join(_ASSET_DIR, "spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mol_3d() -> oechem.OEMol:
    """Return a small molecule with 3D coordinates (ethanol via Omega)."""
    from openeye import oeomega

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("ethanol")

    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    omega.SetStrictStereo(False)
    omega(mol)
    return mol


@pytest.fixture()
def mol_2d() -> oechem.OEGraphMol:
    """Return a small molecule with only 2D coordinates."""
    from openeye import oedepict

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    mol.SetTitle("benzene")
    oedepict.OEPrepareDepiction(mol, True)
    assert mol.GetDimension() == 2, "fixture should produce a 2D molecule"
    return mol


@pytest.fixture()
def design_unit() -> oechem.OEDesignUnit:
    """Load the test design unit from disk, or skip if not available."""
    if not os.path.isfile(_DU_PATH):
        pytest.skip(f"Design unit asset not found: {_DU_PATH}")

    du = oechem.OEDesignUnit()
    if not oechem.OEReadDesignUnit(_DU_PATH, du):
        pytest.skip("Failed to read design unit asset")
    return du


# ---------------------------------------------------------------------------
# MoleculeData dataclass
# ---------------------------------------------------------------------------


class TestMoleculeData:
    """Verify the MoleculeData dataclass fields."""

    def test_fields(self):
        """All four fields should be accessible."""
        md = MoleculeData(
            name="test", data="data", format="sdf", source_type="molecule"
        )
        assert md.name == "test"
        assert md.data == "data"
        assert md.format == "sdf"
        assert md.source_type == "molecule"

    def test_equality(self):
        """Two instances with the same values should be equal."""
        a = MoleculeData(name="x", data="d", format="f", source_type="s")
        b = MoleculeData(name="x", data="d", format="f", source_type="s")
        assert a == b


# ---------------------------------------------------------------------------
# convert_molecule
# ---------------------------------------------------------------------------


class TestConvertMolecule:
    """Tests for convert_molecule."""

    def test_3d_mol_produces_valid_sdf(self, mol_3d):
        """A 3D molecule should produce an SDF string with V2000/V3000 and $$$$."""
        result = convert_molecule(mol_3d)

        assert result.format == "sdf"
        assert result.source_type == "molecule"
        assert "V2000" in result.data or "V3000" in result.data
        assert "$$$$" in result.data

    def test_2d_mol_generates_coords(self, mol_2d):
        """A 2D molecule should trigger Omega and still produce valid SDF."""
        with pytest.warns(CNotebookWarning, match="lacks 3D coordinates"):
            result = convert_molecule(mol_2d)

        assert result.format == "sdf"
        assert "$$$$" in result.data

    def test_preserves_custom_name(self, mol_3d):
        """An explicit *name* argument should be used verbatim."""
        result = convert_molecule(mol_3d, name="custom_name")
        assert result.name == "custom_name"

    def test_uses_mol_title_as_default(self, mol_3d):
        """When no name is given, the molecule title should be used."""
        mol_3d.SetTitle("my_title")
        result = convert_molecule(mol_3d)
        assert result.name == "my_title"

    def test_fallback_name_when_no_title(self, mol_3d):
        """When there is no name and no title, fall back to 'molecule'."""
        mol_3d.SetTitle("")
        result = convert_molecule(mol_3d)
        assert result.name == "molecule"

    def test_raises_type_error_on_wrong_type(self):
        """Passing a non-OEMolBase should raise TypeError."""
        with pytest.raises(TypeError, match="Expected OEMolBase"):
            convert_molecule("not a molecule")

    def test_raises_type_error_on_none(self):
        """Passing None should raise TypeError."""
        with pytest.raises(TypeError, match="Expected OEMolBase"):
            convert_molecule(None)


# ---------------------------------------------------------------------------
# convert_design_unit
# ---------------------------------------------------------------------------


class TestConvertDesignUnit:
    """Tests for convert_design_unit."""

    def test_produces_pdb_with_atom_records(self, design_unit):
        """The output should be PDB format containing ATOM records."""
        result = convert_design_unit(design_unit)

        assert result.format == "pdb"
        assert result.source_type == "design_unit"
        assert "ATOM" in result.data

    def test_uses_title_as_default_name(self, design_unit):
        """When no name is given, the design unit title should be used."""
        result = convert_design_unit(design_unit)
        assert result.name == design_unit.GetTitle()

    def test_preserves_custom_name(self, design_unit):
        """An explicit *name* argument should be used verbatim."""
        result = convert_design_unit(design_unit, name="my_du")
        assert result.name == "my_du"

    def test_raises_type_error_on_wrong_type(self):
        """Passing a non-OEDesignUnit should raise TypeError."""
        with pytest.raises(TypeError, match="Expected OEDesignUnit"):
            convert_design_unit("not a design unit")

    def test_raises_type_error_on_none(self):
        """Passing None should raise TypeError."""
        with pytest.raises(TypeError, match="Expected OEDesignUnit"):
            convert_design_unit(None)


# ---------------------------------------------------------------------------
# TestEnsure3DCoords
# ---------------------------------------------------------------------------


class TestEnsure3DCoords:
    """Tests for the _ensure_3d_coords helper."""

    def test_ensure_3d_coords_generates_conformer(self):
        """A SMILES-only molecule (dimension 0) should get 3D coords via Omega."""
        from cnotebook.core.convert import _ensure_3d_coords

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "CCO")
        assert mol.GetDimension() == 0

        with pytest.warns(CNotebookWarning, match="lacks 3D coordinates"):
            result = _ensure_3d_coords(mol)
        # Omega should have produced a molecule with dimension >= 2
        assert result.GetDimension() >= 2

    def test_ensure_3d_coords_3d_passthrough(self, mol_3d):
        """A molecule that already has 3D coords should be returned unchanged."""
        from cnotebook.core.convert import _ensure_3d_coords

        result = _ensure_3d_coords(mol_3d)
        assert result is mol_3d


def _two_d_molecule():
    ifs = oechem.oemolistream("examples/assets/two_series.sdf")
    mol = oechem.OEGraphMol()
    assert oechem.OEReadMolecule(ifs, mol)
    ifs.close()
    assert mol.GetDimension() == 2
    return mol


def _has_nonzero_z(sdf: str) -> bool:
    for line in sdf.splitlines()[4:]:
        parts = line.split()
        if len(parts) >= 4 and parts[3].isalpha() and abs(float(parts[2])) > 1e-6:
            return True
    return False


def test_2d_molecule_gets_3d_coordinates():
    mol = _two_d_molecule()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        data = convert_molecule(mol)
    assert any(issubclass(w.category, CNotebookWarning) for w in caught)
    assert _has_nonzero_z(data.data)
    assert mol.GetDimension() == 2


def test_generate_3d_false_keeps_2d():
    mol = _two_d_molecule()
    data = convert_molecule(mol, generate_3d=False)
    assert not _has_nonzero_z(data.data)
    assert data.frames is False


# ---------------------------------------------------------------------------
# convert_conformers
# ---------------------------------------------------------------------------


def _conformer_molecule(n: int = 3) -> oechem.OEMol:
    """Return a molecule carrying *n* Omega conformers."""
    from openeye import oeomega

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "CCCCO")
    mol.SetTitle("butanol")
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(n)
    omega.SetStrictStereo(False)
    assert omega(mol)
    return mol


def _coords(mol) -> list[float]:
    """Flatten a molecule's coordinates in atom index order."""
    coords = mol.GetCoords()
    return [value for index in sorted(coords) for value in coords[index]]


def _read_sdf_records(sdf: str) -> list[oechem.OEGraphMol]:
    """Parse an SDF string back into one molecule per record."""
    ims = oechem.oemolistream()
    ims.SetFormat(oechem.OEFormat_SDF)
    assert ims.openstring(sdf.encode("utf-8"))
    records = [oechem.OEGraphMol(mol) for mol in ims.GetOEGraphMols()]
    ims.close()
    return records


def test_convert_conformers_writes_every_conformer_in_order():
    """The frames of the entry are the conformers, so the records the GUI reads back
    have to be those conformers, in that order, with their own coordinates."""
    mol = _conformer_molecule()
    data = convert_conformers(mol)

    assert data.frames is True
    assert data.format == "sdf"
    assert data.source_type == "molecule"
    assert data.name == "butanol"
    assert data.num_atoms == mol.NumAtoms()

    records = _read_sdf_records(data.data)
    assert len(records) == mol.NumConfs() == 3
    assert data.data.count("$$$$") == 3
    for conformer, record in zip(mol.GetConfs(), records, strict=True):
        assert record.NumAtoms() == conformer.NumAtoms()
        # SDF carries four decimals, so the frames are the source coordinates rounded.
        assert _coords(record) == pytest.approx(_coords(conformer), abs=1e-3)
    # Distinct frames: comparing the round trip against identical conformers would
    # pass however the writer ordered or duplicated them.
    assert _coords(records[0]) != pytest.approx(_coords(records[1]), abs=1e-3)


def test_convert_conformers_keeps_per_conformer_titles():
    """A conformer that carries its own title keeps it, the way the SDF writer does
    for any molecule; the rest carry the molecule's."""
    mol = _conformer_molecule()
    for index, conformer in enumerate(mol.GetConfs()):
        conformer.SetTitle(f"pose_{index}")

    records = _read_sdf_records(convert_conformers(mol).data)
    assert [record.GetTitle() for record in records] == ["pose_0", "pose_1", "pose_2"]


def test_convert_conformers_names_the_entry_and_leaves_the_molecule_alone():
    mol = _conformer_molecule()
    assert convert_conformers(mol, name="confs").name == "confs"
    assert convert_conformers(mol, disabled=True).disabled is True
    assert convert_conformers(mol).disabled is False

    mol.SetTitle("")
    assert convert_conformers(mol).name == "conformers"
    assert mol.NumConfs() == 3  # the conversion reads the molecule, never edits it


def test_convert_conformers_refuses_a_single_conformer():
    """A one-model entry has nothing to step through and the GUI rejects `animate` and
    `frame` on it, so the entry is refused here instead of failing on screen."""
    mol = _conformer_molecule(1)
    assert mol.NumConfs() == 1
    with pytest.raises(ValueError, match="has 1"):
        convert_conformers(mol)


def test_convert_conformers_rejects_a_single_conformer_type():
    """An OEGraphMol holds no conformers at all, whatever its coordinates."""
    with pytest.raises(TypeError, match="OEMCMolBase"):
        convert_conformers(_two_d_molecule())
