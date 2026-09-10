import os

import pytest
from openeye import oechem

from cnotebook.core.context import CNotebookContext
from cnotebook.core.formatters import (
    design_unit_cell_html,
    display_cell_html,
    display_cell_image,
    molecule_cell_html,
    molecule_cell_image,
)
from cnotebook.core.render import make_depiction

_DU_PATH = os.path.join("examples", "assets", "spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")


def _mol(smiles="c1ccccc1O"):
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smiles)
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


def test_display_cell_html_copies_display():
    ctx = CNotebookContext(image_format="svg")
    dep = make_depiction(_mol(), ctx=ctx)
    touched = []
    ctx.add_callback(lambda disp: touched.append(disp))
    html = display_cell_html(dep.display, ctx)
    assert "<svg" in html
    assert touched and touched[0] is not dep.display
    assert display_cell_html(None, ctx) == ""
    assert display_cell_html("x<y", ctx) == "x&lt;y"


def test_molecule_cell_image_logical_size():
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    image = molecule_cell_image(_mol(), ctx)
    width, height = image._cnotebook_logical_size
    assert image.GetWidth() == 2 * width and image.GetHeight() == 2 * height
    assert molecule_cell_image(None, ctx) is None


def test_display_cell_image_returns_image():
    ctx = CNotebookContext()
    dep = make_depiction(_mol(), ctx=ctx)
    assert display_cell_image(dep.display, ctx).GetWidth() > 0


@pytest.mark.skipif(not os.path.exists(_DU_PATH), reason="design unit asset missing")
def test_design_unit_cell_html():
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(_DU_PATH, du)
    html = design_unit_cell_html(du, CNotebookContext(image_format="svg"))
    assert "<svg" in html
    assert design_unit_cell_html(None, CNotebookContext()) == ""
