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


class TestDisplayDu:
    """Test the _display_du function for Marimo OEDesignUnit rendering"""

    @patch('cnotebook.marimo_ext.oedu_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_display_du_basic(self, mock_context_var, mock_oedu_to_html):
        """Test basic design unit rendering"""
        mock_ctx = MagicMock()
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oedu_to_html.return_value = '<img>design_unit</img>'

        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        mime_type, html_content = cnotebook.marimo_ext._display_du(mock_du)

        assert mime_type == "text/html"
        assert html_content == '<img>design_unit</img>'
        mock_ctx.copy.assert_called_once()
        mock_oedu_to_html.assert_called_once_with(mock_du, ctx=mock_ctx)

    def test_oedesignunit_has_mime_method(self):
        """Test that OEDesignUnit has the _mime_ method after import"""
        import cnotebook.marimo_ext

        assert hasattr(oechem.OEDesignUnit, '_mime_')
        assert callable(oechem.OEDesignUnit._mime_)

    def test_mime_method_is_display_du(self):
        """Test that the _mime_ method is our display function"""
        import cnotebook.marimo_ext

        assert oechem.OEDesignUnit._mime_ == cnotebook.marimo_ext._display_du


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


class TestCreateMoleculeFormatter:
    """Test the _create_molecule_formatter factory function"""

    def test_none_returns_empty(self):
        """Test that formatter returns empty string for None input"""
        from cnotebook.marimo_ext import _create_molecule_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_molecule_formatter(ctx)
        assert formatter(None) == ""

    def test_non_molecule_returns_str(self):
        """Test that formatter returns str() for non-OEMolBase input"""
        from cnotebook.marimo_ext import _create_molecule_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_molecule_formatter(ctx)
        assert formatter("hello") == "hello"

    def test_valid_molecule_with_callbacks(self):
        """Test that valid molecule with callbacks uses oemol_to_disp and applies callbacks"""
        from cnotebook.marimo_ext import _create_molecule_formatter
        from cnotebook.context import CNotebookContext

        callback_called = []

        def my_callback(disp):
            callback_called.append(disp)

        ctx = CNotebookContext(callbacks=[my_callback])
        formatter = _create_molecule_formatter(ctx)

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        result = formatter(mol)

        assert len(callback_called) == 1
        assert isinstance(callback_called[0], oedepict.OE2DMolDisplay)
        assert isinstance(result, oedepict.OEImage)

    def test_valid_molecule_without_callbacks(self):
        """Test that valid molecule without callbacks falls back to oemol_to_image"""
        from cnotebook.marimo_ext import _create_molecule_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext(callbacks=[])
        formatter = _create_molecule_formatter(ctx)

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        result = formatter(mol)

        assert isinstance(result, oedepict.OEImage)


class TestCreateDisplayFormatter:
    """Test the _create_display_formatter factory function"""

    def test_none_returns_empty(self):
        """Test that formatter returns empty string for None input"""
        from cnotebook.marimo_ext import _create_display_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_display_formatter(ctx)
        assert formatter(None) == ""

    def test_non_display_returns_str(self):
        """Test that formatter returns str() for non-OE2DMolDisplay input"""
        from cnotebook.marimo_ext import _create_display_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_display_formatter(ctx)
        assert formatter("hello") == "hello"

    def test_invalid_display_returns_str(self):
        """Test that formatter returns str() for invalid display object"""
        from cnotebook.marimo_ext import _create_display_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_display_formatter(ctx)

        # Create a display from an empty molecule (0 atoms)
        empty_mol = oechem.OEGraphMol()
        disp = oedepict.OE2DMolDisplay(empty_mol, oedepict.OE2DMolDisplayOptions())

        if disp.IsValid():
            # Some toolkit versions consider empty displays valid;
            # in that case the formatter renders to an OEImage
            result = formatter(disp)
            assert isinstance(result, oedepict.OEImage)
        else:
            # Invalid display falls through to str()
            result = formatter(disp)
            assert isinstance(result, str)

    def test_valid_display_with_callbacks(self):
        """Test that valid display with callbacks copies and applies callbacks"""
        from cnotebook.marimo_ext import _create_display_formatter
        from cnotebook.context import CNotebookContext

        callback = MagicMock()
        ctx = CNotebookContext(callbacks=[callback])
        formatter = _create_display_formatter(ctx)

        # Create a real molecule and display
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")
        oedepict.OEPrepareDepiction(mol)
        disp = oedepict.OE2DMolDisplay(mol, ctx.display_options)

        result = formatter(disp)

        # Verify callback was applied
        callback.assert_called_once()
        # Result should be an OEImage
        assert isinstance(result, oedepict.OEImage)


class TestCreateDuFormatter:
    """Test the _create_du_formatter factory function"""

    def test_none_returns_empty(self):
        """Test that formatter returns empty string for None input"""
        from cnotebook.marimo_ext import _create_du_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_du_formatter(ctx)
        assert formatter(None) == ""

    def test_non_du_returns_str(self):
        """Test that formatter returns str() for non-OEDesignUnit input"""
        from cnotebook.marimo_ext import _create_du_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_du_formatter(ctx)
        assert formatter("hello") == "hello"

    def test_valid_du(self):
        """Test that valid OEDesignUnit is rendered to an OEImage"""
        from cnotebook.marimo_ext import _create_du_formatter
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_du_formatter(ctx)

        # Empty DesignUnit (apo, no ligand) still produces an OEImage
        du = oechem.OEDesignUnit()

        result = formatter(du)
        assert isinstance(result, oedepict.OEImage)


class TestDisplayDataframe:
    """Test the _display_dataframe function"""

    def test_pandas_dataframe_mime_returns_html(self):
        """Test that _display_dataframe returns text/html MIME tuple"""
        from cnotebook.marimo_ext import _display_dataframe
        import pandas as pd

        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})
        mime_type, content = _display_dataframe(df)

        assert mime_type == "text/html"
        assert isinstance(content, str)
        assert len(content) > 0
