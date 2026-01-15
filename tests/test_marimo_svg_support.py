# tests/test_marimo_svg_support.py
import pytest
from unittest.mock import MagicMock, patch
from openeye import oechem


class TestMarimoSVGSupport:
    """Tests for SVG support in Marimo"""

    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_svg_format_respected(self, mock_context_var, mock_oemol_to_html):
        """Test that SVG format is respected in Marimo"""
        from cnotebook.marimo_ext import _display_mol

        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"  # User wants SVG
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oemol_to_html.return_value = '<svg>mol</svg>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mime_type, content = _display_mol(mock_mol)

        # Format should be preserved (not forced to PNG)
        assert mock_ctx.image_format == "svg"
        assert mime_type == "text/html"

    def test_svg_mime_type_in_html(self):
        """Test that SVG can be embedded in text/html MIME type"""
        # This test documents that SVG embedded in HTML should work
        # Marimo accepts text/html which can contain inline SVG
        svg_content = '<svg xmlns="http://www.w3.org/2000/svg"><circle r="10"/></svg>'
        html_with_svg = f'<div>{svg_content}</div>'

        # The content is valid HTML with embedded SVG
        assert '<svg' in html_with_svg
        assert '</svg>' in html_with_svg


class TestMarimoSVGEnabled:
    """Tests for when SVG is enabled in Marimo"""

    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_svg_format_preserved(self, mock_context_var, mock_oemol_to_html):
        """Test that SVG format is preserved when user requests it"""
        from cnotebook.marimo_ext import _display_mol

        mock_ctx = MagicMock()
        mock_ctx.image_format = "svg"
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oemol_to_html.return_value = '<svg>mol</svg>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mime_type, content = _display_mol(mock_mol)

        assert mime_type == "text/html"
        # Format should NOT be changed to PNG
        assert mock_ctx.image_format == "svg"

    @patch('cnotebook.marimo_ext.oemol_to_html')
    @patch('cnotebook.marimo_ext.cnotebook_context')
    def test_png_format_preserved(self, mock_context_var, mock_oemol_to_html):
        """Test that PNG format is preserved when user requests it"""
        from cnotebook.marimo_ext import _display_mol

        mock_ctx = MagicMock()
        mock_ctx.image_format = "png"
        mock_context_var.get.return_value = mock_ctx
        mock_ctx.copy.return_value = mock_ctx
        mock_oemol_to_html.return_value = '<img>mol</img>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mime_type, content = _display_mol(mock_mol)

        assert mime_type == "text/html"
        # Format should remain PNG
        assert mock_ctx.image_format == "png"
