"""
Tests to verify feature parity between Jupyter and Marimo environments.
"""
import pytest
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict


class TestFeatureParity:
    """Tests verifying identical functionality in both environments"""

    def test_render_molecule_grid_available_both_envs(self):
        """Test render_molecule_grid is available for both environments"""
        # Can import from shared render module
        from cnotebook.render import render_molecule_grid
        assert callable(render_molecule_grid)

        # Can import from ipython_ext (backward compatibility)
        from cnotebook.ipython_ext import render_molecule_grid
        assert callable(render_molecule_grid)

        # Can import from package root
        from cnotebook import render_molecule_grid
        assert callable(render_molecule_grid)

    def test_oeimage_has_mime_handler(self):
        """Test OEImage has MIME handler for Marimo after import"""
        import cnotebook.marimo_ext
        assert hasattr(oedepict.OEImage, '_mime_')

    def test_oemolbase_has_mime_handler(self):
        """Test OEMolBase has MIME handler for Marimo after import"""
        import cnotebook.marimo_ext
        assert hasattr(oechem.OEMolBase, '_mime_')

    def test_display_has_mime_handler(self):
        """Test OE2DMolDisplay has MIME handler for Marimo after import"""
        import cnotebook.marimo_ext
        assert hasattr(oedepict.OE2DMolDisplay, '_mime_')

    def test_grid_output_compatible_with_both(self):
        """Test grid output (OEImage) works in both environments"""
        from cnotebook.render import render_molecule_grid

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        result = render_molecule_grid([mol])

        # Returns OEImage - which has formatters in both environments
        assert isinstance(result, oedepict.OEImage)

        # Jupyter: uses registered HTML formatter
        # Marimo: uses _mime_ attribute
        # Both should work with OEImage


class TestSharedCodeUsage:
    """Tests verifying both environments use the same core rendering code"""

    def test_both_use_render_module(self):
        """Test both environments use functions from render.py"""
        from cnotebook.render import oemol_to_html, oedisp_to_html, oeimage_to_html

        # These are the core functions used by both environments
        assert callable(oemol_to_html)
        assert callable(oedisp_to_html)
        assert callable(oeimage_to_html)

    def test_context_shared(self):
        """Test both environments use the same context system"""
        from cnotebook.context import cnotebook_context, CNotebookContext

        ctx = cnotebook_context.get()
        assert isinstance(ctx, CNotebookContext)

    def test_helpers_shared(self):
        """Test both environments use the same helper functions"""
        from cnotebook.helpers import create_structure_highlighter

        highlighter = create_structure_highlighter("[OH]")
        assert callable(highlighter)
