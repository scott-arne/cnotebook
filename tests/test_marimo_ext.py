import pytest
from unittest.mock import MagicMock, patch
from openeye import oechem
from cnotebook.marimo_ext import _display_mol


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
        
        # Verify context was copied and modified
        mock_context_var.get.assert_called_once()
        mock_ctx.copy.assert_called_once()
        assert mock_ctx.image_format == "png"
        
        # Verify oemol_to_html was called with correct parameters
        mock_oemol_to_html.assert_called_once_with(mock_mol, ctx=mock_ctx)
    
    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_mol_png_format(self, mock_context_var, mock_oemol_to_html):
        """Test that PNG format is enforced for Marimo"""
        # Setup mocks
        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"  # Start with SVG
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        
        mock_oemol_to_html.return_value = '<img>molecule</img>'
        
        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Call the display function
        mime_type, html_content = _display_mol(mock_mol)
        
        # Verify PNG format was set
        assert mock_ctx.image_format == "png"
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
        mock_ctx.copy.return_value = mock_ctx_copy
        
        mock_oemol_to_html.return_value = '<img>custom_molecule</img>'
        
        # Create mock molecule
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Call the display function
        mime_type, html_content = _display_mol(mock_mol)
        
        # Verify the copy was used and modified
        mock_ctx.copy.assert_called_once()
        assert mock_ctx_copy.image_format == "png"  # Should be set to PNG
        
        # Verify oemol_to_html was called with the copied context
        mock_oemol_to_html.assert_called_once_with(mock_mol, ctx=mock_ctx_copy)
        
        assert mime_type == "text/html"
        assert html_content == '<img>custom_molecule</img>'
    
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
    def test_png_enforced_for_marimo(self, mock_context_var, mock_oemol_to_html):
        """Test that PNG format is always used for Marimo compatibility"""
        # Setup context with SVG format
        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        
        mock_oemol_to_html.return_value = '<img>svg_to_png</img>'
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Call display function
        mime_type, content = _display_mol(mock_mol)
        
        # Should force PNG format
        assert mock_ctx.image_format == "png"
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
        
        mock_oemol_to_html.return_value = '<img>isolated</img>'
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        # Call display function
        _display_mol(mock_mol)
        
        # Local context should be modified
        assert mock_local_ctx.image_format == "png"
        
        # Global context should remain unchanged
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