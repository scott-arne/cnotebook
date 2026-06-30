import pytest
from openeye import oechem, oedepict

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
