"""Tests for the C3D molecule conversion module."""

import os

import pytest
from openeye import oechem

from cnotebook.c3d.convert import (
    MoleculeData,
    convert_design_unit,
    convert_molecule,
)

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
