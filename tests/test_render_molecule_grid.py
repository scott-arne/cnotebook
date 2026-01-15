# tests/test_render_molecule_grid.py
import pytest
from openeye import oechem, oedepict


class TestRenderMoleculeGridInRender:
    """Test that render_molecule_grid is available from render.py"""

    def test_import_from_render_module(self):
        """Test render_molecule_grid can be imported from render.py"""
        from cnotebook.render import render_molecule_grid
        assert callable(render_molecule_grid)

    def test_basic_grid_rendering(self):
        """Test basic molecule grid rendering from render module"""
        from cnotebook.render import render_molecule_grid

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "CCO")
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "CCC")

        result = render_molecule_grid([mol1, mol2])

        assert isinstance(result, oedepict.OEImage)
        assert result.GetWidth() > 0
        assert result.GetHeight() > 0

    def test_grid_with_smarts_highlighting(self):
        """Test grid rendering with SMARTS highlighting"""
        from cnotebook.render import render_molecule_grid

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "CCO")

        result = render_molecule_grid([mol1], smarts="[OH]")

        assert isinstance(result, oedepict.OEImage)
        assert result.GetWidth() > 0

    def test_grid_with_alignment(self):
        """Test grid rendering with alignment"""
        from cnotebook.render import render_molecule_grid

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(O)cc1")

        result = render_molecule_grid([mol1, mol2], align=True)

        assert isinstance(result, oedepict.OEImage)
        assert result.GetWidth() > 0
