from openeye import oechem, oedepict

from cnotebook.core.context import CNotebookContext
from cnotebook.core.depiction import highlight_alerts


def _mol(smiles):
    mol = oechem.OEGraphMol()
    assert oechem.OESmilesToMol(mol, smiles)
    return mol


def test_highlight_alerts_returns_oeimage_with_groups():
    mol = _mol("c1ccccc1CC(=O)O")  # 8 heavy atoms
    groups = [("acid", None, ((6, 7, 8),))]  # auto color, one 3-atom match
    image = highlight_alerts(mol, groups)
    assert isinstance(image, oedepict.OEImage)
    # renders to non-empty PNG bytes
    data = oedepict.OEWriteImageToString("png", image)
    assert len(data) > 0


def test_highlight_alerts_empty_groups_renders_bare_molecule():
    mol = _mol("c1ccccc1")
    image = highlight_alerts(mol, [])
    assert isinstance(image, oedepict.OEImage)


def test_highlight_alerts_empty_molecule_returns_image_not_html():
    image = highlight_alerts(oechem.OEGraphMol(), [("x", None, ())])
    assert isinstance(image, oedepict.OEImage)  # NOT an HTML str


def test_highlight_alerts_honors_max_heavy_atoms():
    mol = _mol("c1ccccc1CC(=O)O")  # 8 heavy atoms
    groups = [("acid", None, ((6, 7, 8),))]
    ctx = CNotebookContext(max_heavy_atoms=5, min_width=200, min_height=200)
    image = highlight_alerts(mol, groups, ctx=ctx)
    # Molecule exceeds limit → should return placeholder image (200x200) via oemol_to_image
    assert isinstance(image, oedepict.OEImage)
    assert image.GetWidth() == 200.0
    assert image.GetHeight() == 200.0


def test_atom_bond_set_includes_bonds():
    from cnotebook.core.depiction import _atom_bond_set

    mol = _mol("CC(=O)O")  # acetic acid: CH3-C(=O)-OH
    # Atom indices: 0=C(methyl), 1=C(carbonyl), 2=O(=O), 3=O(-OH)
    carbonyl_c = 1
    o_double = 2
    o_single = 3

    abset = _atom_bond_set(mol, (carbonyl_c, o_double, o_single))

    # Should have 3 atoms
    assert abset.NumAtoms() == 3
    # Should have 2 bonds: C=O and C-O
    assert abset.NumBonds() > 0
