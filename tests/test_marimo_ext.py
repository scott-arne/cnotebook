import logging
import sys
import types
import warnings
from unittest.mock import MagicMock, patch

import oepolars as oeplr
import pandas as pd
import polars as pl
import pytest
from openeye import oechem, oedepict

# Import the other display functions for testing
import cnotebook.marimo_ext
import cnotebook.marimo_ext as me
import cnotebook.polars_ext as pe
from cnotebook.core.errors import CNotebookWarning
from cnotebook.marimo_ext import _display_mol

try:
    import oepandas as oepd
    oepandas_available = True
except ImportError:
    oepandas_available = False


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

    def test_mime_method_is_display_mol(self):
        """Test that the _mime_ method is our display function"""
        # The _mime_ method should be the _display_mol function
        assert oechem.OEMolBase._mime_ == _display_mol
    

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

    def test_polars_support_is_decided_by_sys_modules(self):
        """The adapter no longer keeps backend flags: an imported polars gets a formatter."""
        from marimo._output.formatting import OPINIONATED_FORMATTERS

        import cnotebook.marimo_ext

        assert not hasattr(cnotebook.marimo_ext, "oepolars_available")
        assert "polars" in sys.modules and "oepolars" in sys.modules
        cnotebook.marimo_ext._attach()
        assert OPINIONATED_FORMATTERS.formatters[pl.DataFrame] is cnotebook.marimo_ext.marimo_polars_formatter


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
        from cnotebook.marimo_ext import _create_molecule_formatter, _CtxBoundImage
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
        assert isinstance(result, _CtxBoundImage)
        assert isinstance(result._image, oedepict.OEImage)

    def test_valid_molecule_without_callbacks(self):
        """Test that a valid molecule without callbacks still renders an image"""
        from cnotebook.marimo_ext import _create_molecule_formatter, _CtxBoundImage
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext(callbacks=[])
        formatter = _create_molecule_formatter(ctx)

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        result = formatter(mol)

        assert isinstance(result, _CtxBoundImage)
        assert isinstance(result._image, oedepict.OEImage)


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
        from cnotebook.marimo_ext import _create_display_formatter, _CtxBoundImage
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
        # Result should be a _CtxBoundImage wrapping an OEImage
        assert isinstance(result, _CtxBoundImage)
        assert isinstance(result._image, oedepict.OEImage)


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
        """Test that valid OEDesignUnit is rendered to a _CtxBoundImage wrapping an OEImage"""
        from cnotebook.marimo_ext import _create_du_formatter, _CtxBoundImage
        from cnotebook.context import CNotebookContext

        ctx = CNotebookContext()
        formatter = _create_du_formatter(ctx)

        # Empty DesignUnit (apo, no ligand) still produces a _CtxBoundImage
        du = oechem.OEDesignUnit()

        result = formatter(du)
        assert isinstance(result, _CtxBoundImage)
        assert isinstance(result._image, oedepict.OEImage)


class TestCtxBoundImage:
    """Test that marimo DataFrame formatters carry per-column ctx through to HTML serialization."""

    def test_ctx_bound_image_mime_uses_bound_ctx(self):
        """_CtxBoundImage._mime_ must call oeimage_to_html with the bound ctx, not the global ContextVar."""
        from cnotebook.marimo_ext import _CtxBoundImage
        from cnotebook.context import CNotebookContext

        # Bound ctx with an explicit width that should survive through _mime_
        bound_ctx = CNotebookContext(width=123, height=77, image_format="png")

        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 400
        mock_image.GetHeight.return_value = 300

        wrapper = _CtxBoundImage(mock_image, bound_ctx)

        with patch('cnotebook.marimo_ext.oeimage_to_html') as mock_html:
            mock_html.return_value = '<img>bound</img>'
            mime_type, content = wrapper._mime_()

        assert mime_type == "text/html"
        assert content == '<img>bound</img>'
        # The critical assertion: the bound ctx — not cnotebook_context.get() — was passed through.
        mock_html.assert_called_once_with(mock_image, ctx=bound_ctx)

    def test_molecule_formatter_returns_ctx_bound_image(self):
        """_create_molecule_formatter wraps the OEImage in a _CtxBoundImage bound to the column ctx."""
        from cnotebook.marimo_ext import _create_molecule_formatter, _CtxBoundImage
        from cnotebook.context import CNotebookContext

        col_ctx = CNotebookContext(width=150, height=150, image_format="png")
        formatter = _create_molecule_formatter(col_ctx)

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        mock_mol.NumAtoms.return_value = 5

        # The formatter now delegates the rendering to the shared cell formatters.
        with patch('cnotebook.marimo_ext._fmt.molecule_cell_image') as mock_cell_image:
            mock_image = MagicMock(spec=oedepict.OEImage)
            mock_cell_image.return_value = mock_image
            # No callbacks path
            col_ctx._callbacks.set([])

            result = formatter(mock_mol)

        assert isinstance(result, _CtxBoundImage)
        assert result._image is mock_image
        assert result._ctx is col_ctx

    def test_display_formatter_returns_ctx_bound_image(self):
        """_create_display_formatter wraps its rendered OEImage in a _CtxBoundImage."""
        from cnotebook.marimo_ext import _create_display_formatter, _CtxBoundImage
        from cnotebook.context import CNotebookContext

        col_ctx = CNotebookContext(width=250, height=250, image_format="png")
        formatter = _create_display_formatter(col_ctx)

        # Create a real empty molecule and display
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")
        oedepict.OEPrepareDepiction(mol)
        disp = oedepict.OE2DMolDisplay(mol, col_ctx.display_options)
        col_ctx._callbacks.set([])

        result = formatter(disp)

        assert isinstance(result, _CtxBoundImage)
        assert isinstance(result._image, oedepict.OEImage)
        assert result._ctx is col_ctx

    def test_du_formatter_returns_ctx_bound_image(self):
        """_create_du_formatter wraps its rendered OEImage in a _CtxBoundImage."""
        from cnotebook.marimo_ext import _create_du_formatter, _CtxBoundImage
        from cnotebook.context import CNotebookContext

        col_ctx = CNotebookContext(width=200, height=200, image_format="png")
        formatter = _create_du_formatter(col_ctx)

        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        # The formatter now delegates the rendering to the shared cell formatters.
        with patch('cnotebook.marimo_ext._fmt.design_unit_cell_image') as mock_cell_image:
            mock_image = MagicMock(spec=oedepict.OEImage)
            mock_cell_image.return_value = mock_image

            result = formatter(mock_du)

        assert isinstance(result, _CtxBoundImage)
        assert result._image is mock_image
        assert result._ctx is col_ctx

    def test_per_column_width_survives_through_mime(self):
        """End-to-end: a per-column ctx.width propagates into the HTML <img> width attribute."""
        from cnotebook.marimo_ext import _CtxBoundImage
        from cnotebook.context import CNotebookContext

        # Build a real small image and a real ctx with explicit width/height.
        image = oedepict.OEImage(400, 400)
        col_ctx = CNotebookContext(width=150, height=150, image_format="png")

        wrapper = _CtxBoundImage(image, col_ctx)
        mime_type, content = wrapper._mime_()

        assert mime_type == "text/html"
        # ctx.width=150 should be reflected in the CSS preferred width.
        assert "width:150px" in content
        assert "height:auto" in content
        # Marimo's bundled Tailwind reset applies `img,video{max-width:100%}`
        # globally, which would clamp wide molecules to their container's
        # width and shrink bond strokes. Our img must explicitly declare
        # `max-width:none` so the intrinsic pixel width is honored regardless
        # of the host page's CSS.
        assert "max-width:none" in content
        assert "max-width:100%" not in content


class TestMarimoPandasFormatter:
    """Test Pandas DataFrame formatting for Marimo tables."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_query_dtype_gets_molecule_formatter(self):
        """QueryDtype columns should use the molecule formatter mapping."""
        if not hasattr(oepd, "QueryDtype"):
            pytest.skip("oepandas QueryDtype not available")
        if not hasattr(cnotebook.marimo_ext, "marimo_pandas_formatter"):
            pytest.skip("marimo table formatter not available")

        query = oechem.OEQMol()
        assert oechem.OEParseSmarts(query, "[#6]")
        df = pd.DataFrame({
            "query": pd.Series([query], dtype=oepd.QueryDtype()),
        })

        table_result = MagicMock()
        table_result._mime_.return_value = ("text/html", "<table></table>")

        with patch("cnotebook.marimo_ext.table", return_value=table_result) as mock_table, \
             patch("cnotebook.marimo_ext._column_width", return_value=123):
            result = cnotebook.marimo_ext.marimo_pandas_formatter(df)

        assert result == ("text/html", "<table></table>")
        format_mapping = mock_table.call_args.kwargs["format_mapping"]
        style_cell = mock_table.call_args.kwargs["style_cell"]
        assert "query" in format_mapping
        assert style_cell("0", "query", None)["width"] == "123px"


class TestColumnStyleCell:
    """Ensure molecule columns get a ``style_cell`` that lifts marimo's 300px td cap."""

    def test_make_style_cell_returns_overrides_for_known_column(self):
        """Known columns get inline td style overrides with the computed width."""
        from cnotebook.marimo_ext import _make_style_cell

        style_cell = _make_style_cell({"Mol": 344})
        style = style_cell("0", "Mol", None)

        assert style["maxWidth"] == "none"
        assert style["overflow"] == "visible"
        assert style["minWidth"] == "344px"
        assert style["width"] == "344px"

    def test_make_style_cell_returns_empty_for_unknown_column(self):
        """Non-molecule columns get no overrides so marimo's defaults apply."""
        from cnotebook.marimo_ext import _make_style_cell

        style_cell = _make_style_cell({"Mol": 344})
        assert style_cell("0", "OtherColumn", "some value") == {}

    def test_make_style_cell_handles_multiple_columns(self):
        """Each molecule column gets its own width in the emitted style."""
        from cnotebook.marimo_ext import _make_style_cell

        style_cell = _make_style_cell({"Mol": 344, "Du": 210})
        assert style_cell("0", "Mol", None)["minWidth"] == "344px"
        assert style_cell("0", "Du", None)["minWidth"] == "210px"

    def test_compute_molecule_column_width_uses_widest_structure(self):
        """_column_width returns the max intrinsic width across a mixed molecule column."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png")

        small = oechem.OEGraphMol()
        oechem.OESmilesToMol(small, "CCO")
        oedepict.OEPrepareDepiction(small)

        large = oechem.OEGraphMol()
        oechem.OESmilesToMol(large, "c1ccc2c(c1)cc1ccc3ccccc3c1c2")
        oedepict.OEPrepareDepiction(large)

        width = me._column_width([small, large, None], ColumnKind.MOLECULE, ctx)

        # The large molecule must set the column width.
        small_disp = oedepict.OE2DMolDisplay(small, ctx.display_options)
        large_disp = oedepict.OE2DMolDisplay(large, ctx.display_options)
        assert width == max(int(small_disp.GetWidth()), int(large_disp.GetWidth()))
        assert width >= int(large_disp.GetWidth())

    def test_compute_molecule_column_width_honors_heavy_atom_limit(self):
        """Molecules exceeding max_heavy_atoms use ctx.min_width, not their structure width."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png", max_heavy_atoms=1, min_width=250.0)

        big = oechem.OEGraphMol()
        oechem.OESmilesToMol(big, "c1ccc2c(c1)cc1ccc3ccccc3c1c2")
        oedepict.OEPrepareDepiction(big)

        width = me._column_width([big], ColumnKind.MOLECULE, ctx)

        assert width == int(ctx.min_width)

    def test_compute_molecule_column_width_handles_empty_and_invalid(self):
        """Empty or invalid molecules contribute ctx.min_width (placeholder size)."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png", min_width=225.0)

        empty = oechem.OEGraphMol()

        width = me._column_width([empty, None], ColumnKind.MOLECULE, ctx)

        assert width == int(ctx.min_width)

    def test_compute_molecule_column_width_empty_column(self):
        """An empty column returns 0 so the caller can skip the wrapper."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png")

        assert me._column_width([], ColumnKind.MOLECULE, ctx) == 0
        assert me._column_width([None, None], ColumnKind.MOLECULE, ctx) == 0

    def test_compute_display_column_width_uses_max(self):
        """_column_width picks the widest display in a display column."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png")

        m1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(m1, "CCO")
        oedepict.OEPrepareDepiction(m1)
        d1 = oedepict.OE2DMolDisplay(m1, ctx.display_options)

        m2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(m2, "c1ccc2c(c1)cc1ccc3ccccc3c1c2")
        oedepict.OEPrepareDepiction(m2)
        d2 = oedepict.OE2DMolDisplay(m2, ctx.display_options)

        width = me._column_width([d1, d2, None], ColumnKind.DISPLAY, ctx)

        assert width == max(int(d1.GetWidth()), int(d2.GetWidth()))

    def test_compute_du_column_width_apo_uses_min_width(self):
        """Apo design units (no ligand) contribute ctx.min_width."""
        from cnotebook.context import CNotebookContext
        from cnotebook.core.table import ColumnKind

        ctx = CNotebookContext(image_format="png", min_width=240.0)

        apo = oechem.OEDesignUnit()

        width = me._column_width([apo, None], ColumnKind.DESIGN_UNIT, ctx)

        assert width == int(ctx.min_width)



def test_marimo_molecule_cell_hidpi():
    """Marimo molecule cells should honor device_pixel_ratio (Finding B)."""
    import base64
    import re
    from cnotebook.marimo_ext import _display_mol
    from cnotebook.context import CNotebookContext, cnotebook_context
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    
    # Set global context with DPR 2.0
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    token = cnotebook_context.set(ctx)
    try:
        mime_type, content = _display_mol(mol)
        
        assert mime_type == "text/html"
        # Extract PNG size and CSS width
        match = re.search(r"base64,([^']+)'", content)
        assert match is not None
        data = base64.b64decode(match.group(1))
        width_px = int.from_bytes(data[16:20], "big")
        
        css_match = re.search(r"width:(\d+)px", content)
        assert css_match is not None
        css_width = int(css_match.group(1))
        
        # PNG should be 2x CSS width at DPR 2.0
        assert width_px == 2 * css_width
    finally:
        cnotebook_context.reset(token)


def test_marimo_display_cell_hidpi():
    """Marimo display cells should honor device_pixel_ratio (Finding B)."""
    import base64
    import re
    from cnotebook.marimo_ext import _display_display
    from cnotebook.context import CNotebookContext, cnotebook_context
    from cnotebook.core.render import oemol_to_disp
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    disp = oemol_to_disp(mol, ctx=ctx)
    
    # Set global context
    token = cnotebook_context.set(ctx)
    try:
        mime_type, content = _display_display(disp)
        
        assert mime_type == "text/html"
        match = re.search(r"base64,([^']+)'", content)
        assert match is not None
        data = base64.b64decode(match.group(1))
        width_px = int.from_bytes(data[16:20], "big")
        
        css_match = re.search(r"width:(\d+)px", content)
        assert css_match is not None
        css_width = int(css_match.group(1))
        
        assert width_px == 2 * css_width
    finally:
        cnotebook_context.reset(token)


def test_marimo_svg_unaffected_by_dpr():
    """Marimo SVG cells should ignore device_pixel_ratio (Finding B)."""
    from cnotebook.marimo_ext import _display_mol
    from cnotebook.context import CNotebookContext, cnotebook_context
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    
    ctx1 = CNotebookContext(image_format="svg", device_pixel_ratio=1.0)
    token1 = cnotebook_context.set(ctx1)
    try:
        _, content1 = _display_mol(mol)
    finally:
        cnotebook_context.reset(token1)
    
    ctx2 = CNotebookContext(image_format="svg", device_pixel_ratio=2.0)
    token2 = cnotebook_context.set(ctx2)
    try:
        _, content2 = _display_mol(mol)
    finally:
        cnotebook_context.reset(token2)

    # SVG should be identical regardless of DPR
    assert content1 == content2


########################################################################################################################
# Table formatters over the shared cell formatters
########################################################################################################################

def _mol():
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    return mol


def test_polars_highlight_visible_in_marimo_formatter(monkeypatch):
    df = pl.DataFrame([pl.Series("mol", [_mol()], dtype=oeplr.MoleculeType())]).chem.highlight("mol", "c1ccccc1")
    captured = {}

    def fake_table(frame, **kwargs):
        captured.update(kwargs)

        class _T:
            def _mime_(self):
                return ("text/html", "")

        return _T()

    monkeypatch.setattr(me, "table", fake_table)
    me.marimo_polars_formatter(df)
    image = captured["format_mapping"]["mol"](df.get_column("mol")[0])
    plain = me._create_molecule_formatter(pe.PolarsFrameAdapter(df.chem.reset_depictions("mol")).context(0))(df.get_column("mol")[0])
    assert isinstance(image, me._CtxBoundImage)
    assert image._mime_()[1] != plain._mime_()[1]


def test_attach_is_idempotent_and_registers_both_backends():
    from marimo._output.formatting import OPINIONATED_FORMATTERS

    me._attach()
    me._attach()
    import pandas as pd

    assert OPINIONATED_FORMATTERS.formatters[pd.DataFrame].__name__ == "marimo_pandas_formatter"
    assert OPINIONATED_FORMATTERS.formatters[pl.DataFrame].__name__ == "marimo_polars_formatter"
    assert not hasattr(pd.DataFrame, "_mime_") or pd.DataFrame._mime_.__name__ != "_display_dataframe"


def test_ctx_bound_image_uses_logical_size():
    from cnotebook.core.context import CNotebookContext
    from cnotebook.core.formatters import molecule_cell_image

    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    image = molecule_cell_image(_mol(), ctx)
    html = me._CtxBoundImage(image, ctx)._mime_()[1]
    import re

    css = int(re.search(r"width:(\d+)px", html).group(1))
    assert css == image._cnotebook_logical_size[0]


def _fake_marimo(*, version="0.12.9", running=None):
    """Build a stand-in ``marimo`` module the version guard will reject.

    :param version: Value for ``__version__``; the default is below ``_MIN_MARIMO``.
    :param running: Return value for ``running_in_notebook``; ``None`` omits the attribute.
    :returns: An object suitable for ``sys.modules["marimo"]``.
    """
    fake = types.SimpleNamespace(__version__=version)
    if running is not None:
        fake.running_in_notebook = lambda: running
    return fake


@pytest.mark.parametrize("running", [True, False], ids=["under-marimo", "elsewhere"])
def test_attach_reports_a_disabled_adapter_only_under_marimo(monkeypatch, caplog, running):
    """An unusable marimo warns in a marimo notebook and only logs anywhere else.

    Importing marimo is not the same as running under it: cnotebook's own environment
    detection imports marimo, so a Jupyter user with an old marimo must stay unbothered.
    """
    monkeypatch.setitem(sys.modules, "marimo", _fake_marimo(running=running))
    monkeypatch.setattr(me, "_WARNED", False)
    monkeypatch.setattr(me, "table", None)

    with caplog.at_level(logging.DEBUG, logger="cnotebook"):
        if running:
            with pytest.warns(CNotebookWarning, match="marimo table integration disabled"):
                me._attach()
        else:
            with warnings.catch_warnings():
                warnings.simplefilter("error", CNotebookWarning)
                me._attach()
            assert "marimo table integration disabled" in caplog.text

    # Either way the adapter stays out of marimo's way.
    assert me.table is None


def test_attach_reports_the_disabled_adapter_once(monkeypatch):
    """The warn-once flag survives the repeated _attach calls the backends make."""
    monkeypatch.setitem(sys.modules, "marimo", _fake_marimo(running=True))
    monkeypatch.setattr(me, "_WARNED", False)
    monkeypatch.setattr(me, "table", None)

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        me._attach()
        me._attach()

    disabled = [w for w in caught if issubclass(w.category, CNotebookWarning)]
    assert len(disabled) == 1
    assert "marimo table integration disabled" in str(disabled[0].message)


@pytest.mark.parametrize(
    ("marimo_module", "expected"),
    [
        (None, False),
        (_fake_marimo(), False),
        (_fake_marimo(running=False), False),
        (_fake_marimo(running=True), True),
    ],
    ids=["absent", "no-probe", "not-running", "running"],
)
def test_running_under_marimo_treats_anything_unusable_as_not_running(
    monkeypatch, marimo_module, expected
):
    """A missing marimo, a marimo without the probe, and a probe that raises all mean no."""
    if marimo_module is None:
        monkeypatch.delitem(sys.modules, "marimo", raising=False)
    else:
        monkeypatch.setitem(sys.modules, "marimo", marimo_module)
    assert me._running_under_marimo() is expected

    def boom():
        raise RuntimeError("marimo could not answer")

    monkeypatch.setitem(sys.modules, "marimo", types.SimpleNamespace(running_in_notebook=boom))
    assert me._running_under_marimo() is False


def test_column_width_consumes_only_the_sample():
    """_column_width samples a column lazily instead of materialising all of it."""
    from cnotebook.context import CNotebookContext
    from cnotebook.core.table import ColumnKind

    ctx = CNotebookContext(image_format="png")
    consumed = 0

    def counting_column():
        nonlocal consumed
        for _ in range(me._WIDTH_SAMPLE * 2):
            consumed += 1
            yield None

    assert me._column_width(counting_column(), ColumnKind.MOLECULE, ctx) == 0
    assert consumed == me._WIDTH_SAMPLE
