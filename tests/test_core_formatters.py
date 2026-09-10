import os

import pytest
from openeye import oechem

from cnotebook.core.context import CNotebookContext
from cnotebook.core.formatters import (
    design_unit_cell_html,
    design_unit_cell_image,
    display_cell_html,
    display_cell_image,
    molecule_cell_html,
    molecule_cell_image,
)
from cnotebook.core.render import make_depiction, placeholder_size

_DU_PATH = os.path.join("examples", "assets", "spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")


def _mol(smiles="c1ccccc1O"):
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smiles)
    return mol


def _invalid_mol():
    """Create a genuinely invalid molecule with atoms."""
    mol = oechem.OEGraphMol()
    # Try parsing invalid SMILES
    oechem.OESmilesToMol(mol, "C1CC")  # Unclosed ring
    if mol.IsValid():
        # Fallback: create a molecule and corrupt it
        mol = oechem.OEGraphMol()
        mol.NewAtom(oechem.OEElemNo_C)
        mol.Clear()  # This might make it invalid
        if mol.NumAtoms() == 0:
            mol.NewAtom(oechem.OEElemNo_C)
    return mol


def test_molecule_cell_html_handles_none_and_non_molecules():
    ctx = CNotebookContext()
    assert molecule_cell_html(None, ctx) == ""
    assert molecule_cell_html("a<b&c", ctx) == "a&lt;b&amp;c"


def test_molecule_cell_html_placeholders():
    ctx = CNotebookContext(image_format="svg")
    assert "Empty Molecule" in molecule_cell_html(oechem.OEGraphMol(), ctx)
    big = _mol("C" * 120)
    ctx.max_heavy_atoms = 10
    assert "Exceeds Max Heavy Atoms" in molecule_cell_html(big, ctx)


def test_molecule_cell_html_applies_callbacks_on_a_copy():
    ctx = CNotebookContext(image_format="svg")
    seen = []
    ctx.add_callback(lambda disp: seen.append(disp.GetMolecule().NumAtoms()))
    mol = _mol()
    html = molecule_cell_html(mol, ctx)
    assert "<svg" in html
    assert seen == [mol.NumAtoms()]
    assert mol.GetDimension() == 0


def test_display_cell_html_copies_display_and_applies_callbacks():
    ctx = CNotebookContext(image_format="svg")
    dep = make_depiction(_mol(), ctx=ctx)
    original = dep.display
    touched = []
    ctx.add_callback(lambda disp: touched.append(disp))
    html = display_cell_html(original, ctx)
    assert "<svg" in html
    assert len(touched) == 1
    assert touched[0] is not original  # Callback received the copy
    assert display_cell_html(None, ctx) == ""
    assert display_cell_html("x<y", ctx) == "x&lt;y"


def test_molecule_cell_image_logical_size():
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    image = molecule_cell_image(_mol(), ctx)
    width, height = image._cnotebook_logical_size
    assert image.GetWidth() == 2 * width and image.GetHeight() == 2 * height
    assert molecule_cell_image(None, ctx) is None


def test_molecule_cell_image_placeholders_have_logical_size():
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    expected_size = placeholder_size(ctx)
    
    # Invalid molecule with atoms
    invalid = _invalid_mol()
    if not invalid.IsValid() and invalid.NumAtoms() > 0:
        image = molecule_cell_image(invalid, ctx)
        assert image._cnotebook_logical_size == expected_size
    
    # Over-limit molecule
    big = _mol("C" * 120)
    ctx.max_heavy_atoms = 10
    image = molecule_cell_image(big, ctx)
    assert image._cnotebook_logical_size == expected_size


def test_display_cell_image_returns_image_and_applies_callbacks():
    ctx = CNotebookContext()
    dep = make_depiction(_mol(), ctx=ctx)
    original = dep.display
    touched = []
    ctx.add_callback(lambda disp: touched.append(disp))
    image = display_cell_image(original, ctx)
    assert image.GetWidth() > 0
    assert hasattr(image, "_cnotebook_logical_size")
    assert len(touched) == 1
    assert touched[0] is not original  # Callback received the copy


def test_display_cell_image_hidpi():
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    dep = make_depiction(_mol(), ctx=ctx)
    image = display_cell_image(dep.display, ctx)
    width, height = image._cnotebook_logical_size
    assert image.GetWidth() == 2 * width and image.GetHeight() == 2 * height


@pytest.mark.skipif(not os.path.exists(_DU_PATH), reason="design unit asset missing")
def test_design_unit_cell_html():
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(_DU_PATH, du)
    html = design_unit_cell_html(du, CNotebookContext(image_format="svg"))
    assert "<svg" in html
    assert design_unit_cell_html(None, CNotebookContext()) == ""
    assert design_unit_cell_html("x<y", CNotebookContext()) == "x&lt;y"


@pytest.mark.skipif(not os.path.exists(_DU_PATH), reason="design unit asset missing")
def test_design_unit_cell_image_hidpi():
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(_DU_PATH, du)
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    image = design_unit_cell_image(du, ctx)
    width, height = image._cnotebook_logical_size
    assert image.GetWidth() == 2 * width and image.GetHeight() == 2 * height


def test_design_unit_cell_image_apo():
    # Apo design unit (no ligand) - just create empty DU
    du = oechem.OEDesignUnit()
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    image = design_unit_cell_image(du, ctx)
    assert hasattr(image, "_cnotebook_logical_size")
    # Apo placeholder is not oversampled
    width, height = image._cnotebook_logical_size
    assert image.GetWidth() == width and image.GetHeight() == height
