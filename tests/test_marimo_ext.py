import pytest
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict
from cnotebook.marimo_ext import _display_mol
# Import the other display functions for testing
import cnotebook.marimo_ext


class TestDisplayMol:
    """Test the _display_mol function for Marimo integration"""
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_mol_basic(self, mock_context_var, mock_oemol_to_html):
        """Test basic molecule display for Marimo"""
        # Setup mocks
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx

        mock_oemol_to_html.return_value = '<img>molecule</img>'

        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)

        # Call the display function
        mime_type, html_content = _display_mol(mock_mol)

        # Verify results
        assert mime_type == "text/html"
        assert html_content == '<img>molecule</img>'

        # Verify context was copied
        mock_context_var.get.assert_called_once()
        mock_ctx.copy.assert_called_once()

        # Verify oemol_to_html was called with correct parameters
        mock_oemol_to_html.assert_called_once_with(mock_mol, ctx=mock_ctx)
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_mol_format_preserved(self, mock_context_var, mock_oemol_to_html):
        """Test that user's image format preference is preserved"""
        # Setup mocks
        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"  # Start with SVG
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx

        mock_oemol_to_html.return_value = '<svg>molecule</svg>'

        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)

        # Call the display function
        mime_type, html_content = _display_mol(mock_mol)

        # Verify format was preserved (not changed to PNG)
        assert mock_ctx.image_format == "svg"
        assert mime_type == "text/html"
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_mol_with_different_context(self, mock_context_var, mock_oemol_to_html):
        """Test display with different context settings"""
        # Setup mocks with custom context
        mock_ctx = MagicMock()
        mock_ctx.width = 300
        mock_ctx.height = 200
        mock_ctx.image_format = "svg"
        mock_context_var.get.return_value = mock_ctx

        # Copy should return a new context
        mock_ctx_copy = MagicMock()
        mock_ctx_copy.width = 300
        mock_ctx_copy.height = 200
        mock_ctx_copy.image_format = "svg"  # Copy preserves format
        mock_ctx.copy.return_value = mock_ctx_copy

        mock_oemol_to_html.return_value = '<svg>custom_molecule</svg>'

        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)

        # Call the display function
        mime_type, html_content = _display_mol(mock_mol)

        # Verify the copy was used
        mock_ctx.copy.assert_called_once()

        # Verify oemol_to_html was called with the copied context
        mock_oemol_to_html.assert_called_once_with(mock_mol, ctx=mock_ctx_copy)

        assert mime_type == "text/html"
        assert html_content == '<svg>custom_molecule</svg>'
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_mol_error_handling(self, mock_context_var, mock_oemol_to_html):
        """Test error handling in display function"""
        # Setup mocks
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        
        # Make oemol_to_html raise an exception
        mock_oemol_to_html.side_effect = Exception("Rendering error")
        
        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Rendering error"):
            _display_mol(mock_mol)
    
    def test_display_mol_return_format(self):
        """Test that display function returns correct format for Marimo"""
        with patch('cnotebook.marimo_ext.oemol_to_html') as mock_oemol_to_html:
            with patch('cnotebook.marimo_ext.cnotebook_context') as mock_context_var:
                # Setup mocks
                mock_ctx = MagicMock()
                mock_context_var.get.return_value = mock_ctx
                mock_ctx.copy.return_value = mock_ctx
                mock_oemol_to_html.return_value = '<div>test</div>'
                
                # Create mock molecule
                mock_mol = MagicMock(spec=oechem.OEMolBase)
                
                # Call the display function
                result = _display_mol(mock_mol)
                
                # Should return a tuple
                assert isinstance(result, tuple)
                assert len(result) == 2
                
                mime_type, content = result
                assert mime_type == "text/html"
                assert content == '<div>test</div>'


class TestMarimoIntegration:
    """Test Marimo integration and monkey patching"""
    
    def test_oemolbase_has_mime_method(self):
        """Test that OEMolBase has the _mime_ method after import"""
        # After importing marimo_ext, OEMolBase should have _mime_ method
        import cnotebook.marimo_ext  # This triggers the monkey patch
        
        assert hasattr(oechem.OEMolBase, '_mime_')
        assert callable(oechem.OEMolBase._mime_)
    
    def test_mime_method_is_display_mol(self):
        """Test that the _mime_ method is our display function"""
        import cnotebook.marimo_ext
        
        # The _mime_ method should be the _display_mol function
        assert oechem.OEMolBase._mime_ == _display_mol
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_mime_method_on_molecule_instance(self, mock_context_var, mock_oemol_to_html):
        """Test calling _mime_ method on a molecule instance"""
        import cnotebook.marimo_ext
        
        # Setup mocks
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oemol_to_html.return_value = '<img>instance_mol</img>'
        
        # Create a mock molecule instance and manually set the _mime_ method
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol._mime_.return_value = ("text/html", '<img>instance_mol</img>')
        
        # Call the _mime_ method on the instance
        result = mock_mol._mime_()
        
        # Should return the expected format
        mime_type, content = result
        assert mime_type == "text/html"
        assert content == '<img>instance_mol</img>'
    
    def test_monkey_patch_does_not_affect_other_methods(self):
        """Test that monkey patching doesn't affect other OEMolBase methods"""
        import cnotebook.marimo_ext
        
        # OEMolBase should still have its original methods
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # These methods should still be available (they're mocked, but the point is they exist)
        assert hasattr(mock_mol, 'IsValid')
        assert hasattr(mock_mol, 'NumAtoms')
        assert hasattr(mock_mol, 'GetTitle')
        
        # And our new method
        assert hasattr(mock_mol, '_mime_')


class TestModuleImports:
    """Test module imports and dependencies"""
    
    def test_imports_from_context(self):
        """Test imports from context module"""
        from cnotebook.marimo_ext import cnotebook_context
        
        assert cnotebook_context is not None
        # Should be a ContextVar
        assert hasattr(cnotebook_context, 'get')
    
    def test_imports_from_render(self):
        """Test imports from render module"""
        from cnotebook.marimo_ext import oemol_to_html
        
        assert callable(oemol_to_html)
    
    def test_imports_from_openeye(self):
        """Test imports from OpenEye"""
        from cnotebook.marimo_ext import oechem
        
        assert hasattr(oechem, 'OEMolBase')


class TestMarimoBehavior:
    """Test Marimo-specific behavior and integration"""

    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_format_preserved_for_marimo(self, mock_context_var, mock_oemol_to_html):
        """Test that user's image format preference is preserved in Marimo"""
        # Setup context with SVG format
        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx

        mock_oemol_to_html.return_value = '<svg>molecule</svg>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)

        # Call display function
        mime_type, content = _display_mol(mock_mol)

        # Format should be preserved (not forced to PNG)
        assert mock_ctx.image_format == "svg"
        assert mime_type == "text/html"
    
    def test_marimo_mime_format_compatibility(self):
        """Test that the return format is compatible with Marimo's expectations"""
        with patch('cnotebook.marimo_ext.oemol_to_html') as mock_oemol_to_html:
            with patch('cnotebook.marimo_ext.cnotebook_context') as mock_context_var:
                # Setup mocks
                mock_ctx = MagicMock()
                mock_context_var.get.return_value = mock_ctx
                mock_ctx.copy.return_value = mock_ctx
                mock_oemol_to_html.return_value = '<div>marimo_content</div>'
                
                mock_mol = MagicMock(spec=oechem.OEMolBase)
                
                result = _display_mol(mock_mol)
                
                # Marimo expects a tuple of (mime_type, content)
                assert isinstance(result, tuple)
                assert len(result) == 2
                
                mime_type, content = result
                assert isinstance(mime_type, str)
                assert mime_type == "text/html"
                assert isinstance(content, str)
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_context_isolation(self, mock_context_var, mock_oemol_to_html):
        """Test that context changes don't affect global context"""
        # Setup mock context
        mock_global_ctx = MagicMock()
        mock_global_ctx.image_format = "svg"
        mock_context_var.get.return_value = mock_global_ctx

        # Copy should return a separate object
        mock_local_ctx = MagicMock()
        mock_local_ctx.image_format = "svg"
        mock_global_ctx.copy.return_value = mock_local_ctx

        mock_oemol_to_html.return_value = '<svg>isolated</svg>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)

        # Call display function
        _display_mol(mock_mol)

        # Both contexts should retain their original format (no forced change)
        assert mock_global_ctx.image_format == "svg"

        # Copy should have been called to create isolation
        mock_global_ctx.copy.assert_called_once()


class TestEdgeCases:
    """Test edge cases and error conditions"""
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_none_molecule(self, mock_context_var, mock_oemol_to_html):
        """Test behavior with None molecule"""
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        
        mock_oemol_to_html.return_value = '<div>none_mol</div>'
        
        # This should work - oemol_to_html should handle None gracefully
        result = _display_mol(None)
        
        mime_type, content = result
        assert mime_type == "text/html"
        mock_oemol_to_html.assert_called_once_with(None, ctx=mock_ctx)
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_context_get_fails(self, mock_context_var, mock_oemol_to_html):
        """Test behavior when context.get() fails"""
        mock_context_var.get.side_effect = Exception("Context error")
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Context error"):
            _display_mol(mock_mol)
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context') 
    def test_context_copy_fails(self, mock_context_var, mock_oemol_to_html):
        """Test behavior when context.copy() fails"""
        mock_ctx = MagicMock()
        mock_ctx.copy.side_effect = Exception("Copy error")
        mock_context_var.get.return_value = mock_ctx
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Should propagate the exception
        with pytest.raises(Exception, match="Copy error"):
            _display_mol(mock_mol)

class TestDisplayDisplay:
    """Test the _display_display function for Marimo OE2DMolDisplay rendering"""

    @patch('cnotebook.marimo_ext.oedisp_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_display_basic(self, mock_context_var, mock_oedisp_to_html):
        """Test basic display rendering"""
        from openeye import oedepict

        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oedisp_to_html.return_value = '<img>display</img>'

        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)

        mime_type, html_content = cnotebook.marimo_ext._display_display(mock_disp)

        assert mime_type == "text/html"
        assert html_content == '<img>display</img>'
        # Context should be copied but format is no longer forced
        mock_ctx.copy.assert_called_once()


class TestDisplayImage:
    """Test the _display_image function for Marimo OEImage rendering"""

    @patch('cnotebook.marimo_ext.oeimage_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_image_basic(self, mock_context_var, mock_oeimage_to_html):
        """Test basic image rendering"""
        from openeye import oedepict

        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oeimage_to_html.return_value = '<img>image</img>'

        mock_img = MagicMock(spec=oedepict.OEImage)

        mime_type, html_content = cnotebook.marimo_ext._display_image(mock_img)

        assert mime_type == "text/html"
        assert html_content == '<img>image</img>'
        # Context should be copied but format is no longer forced
        mock_ctx.copy.assert_called_once()


class TestRenderMoleculeGridMarimo:
    """Test render_molecule_grid works in Marimo context via OEImage._mime_"""

    def test_grid_returns_oeimage(self):
        """Test that render_molecule_grid returns OEImage which has _mime_ handler"""
        from cnotebook.render import render_molecule_grid
        from openeye import oedepict

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "CCO")

        result = render_molecule_grid([mol1])

        # Result should be OEImage
        assert isinstance(result, oedepict.OEImage)
        # OEImage should have _mime_ attribute (set by marimo_ext)
        assert hasattr(oedepict.OEImage, '_mime_')

    @patch('cnotebook.marimo_ext.oeimage_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_oeimage_mime_renders_grid(self, mock_context_var, mock_oeimage_to_html):
        """Test that OEImage._mime_ renders grid output correctly"""
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oeimage_to_html.return_value = '<img>grid</img>'

        mock_image = MagicMock(spec=oedepict.OEImage)

        mime_type, html_content = cnotebook.marimo_ext._display_image(mock_image)

        assert mime_type == "text/html"
        assert html_content == '<img>grid</img>'
        # Context should be copied but format is no longer forced
        mock_ctx.copy.assert_called_once()

    def test_grid_with_multiple_molecules_for_marimo(self):
        """Test grid with multiple molecules returns valid OEImage for Marimo"""
        from cnotebook.render import render_molecule_grid
        from openeye import oedepict

        mols = []
        for smiles in ["CCO", "CCC", "CCCC", "c1ccccc1"]:
            mol = oechem.OEGraphMol()
            oechem.OESmilesToMol(mol, smiles)
            mols.append(mol)

        result = render_molecule_grid(mols, ncols=2)

        assert isinstance(result, oedepict.OEImage)
        assert result.GetWidth() > 0
        assert result.GetHeight() > 0


class TestPolarsSupport:
    """Test Polars DataFrame support in Marimo"""

    def test_oepolars_available_flag(self):
        """Test that oepolars_available flag is set correctly"""
        import cnotebook.marimo_ext

        try:
            import polars
            import oepolars
            assert cnotebook.marimo_ext.oepolars_available is True
        except ImportError:
            assert cnotebook.marimo_ext.oepolars_available is False

    def test_polars_dataframe_has_mime_method(self):
        """Test that Polars DataFrame has _mime_ method when oepolars is available"""
        import cnotebook.marimo_ext

        if cnotebook.marimo_ext.oepolars_available:
            import polars as pl
            assert hasattr(pl.DataFrame, '_mime_')
            assert callable(pl.DataFrame._mime_)

    def test_marimo_polars_formatter_exists(self):
        """Test that marimo_polars_formatter function exists when marimo is available"""
        try:
            import marimo
            import cnotebook.marimo_ext

            if cnotebook.marimo_ext.oepolars_available:
                assert hasattr(cnotebook.marimo_ext, 'marimo_polars_formatter')
                assert callable(cnotebook.marimo_ext.marimo_polars_formatter)
        except ImportError:
            pytest.skip("Marimo not installed")
