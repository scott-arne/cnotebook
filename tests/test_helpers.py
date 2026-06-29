import pytest
import re
from unittest.mock import patch
from openeye import oechem, oedepict
from cnotebook.helpers import (
    escape_html,
    escape_brackets,
    remove_omega_conformer_id,
    create_structure_highlighter,
    highlight_smarts,
    CONFORMER_ID_REGEX
)


class TestEscapeHtml:
    """Test the escape_html function"""
    
    def test_escape_html_string(self):
        """Test escaping HTML characters in string"""
        result = escape_html("<div>Test</div>")
        assert result == "&lt;div&gt;Test&lt;/div&gt;"
    
    def test_escape_html_ampersand(self):
        """Test escaping ampersand"""
        result = escape_html("Tom & Jerry")
        assert result == "Tom &amp; Jerry"
    
    def test_escape_html_mixed(self):
        """Test escaping mixed HTML characters"""
        result = escape_html("<script>alert('test');</script>")
        assert result == "&lt;script&gt;alert('test');&lt;/script&gt;"
    
    def test_escape_html_non_string(self):
        """Test escape_html with non-string input"""
        result = escape_html(42)
        assert result == 42  # Returns the input unchanged
    
    def test_escape_html_empty_string(self):
        """Test escape_html with empty string"""
        result = escape_html("")
        assert result == ""
    
    def test_escape_html_already_escaped(self):
        """Test escape_html with already escaped content"""
        result = escape_html("&lt;div&gt;")
        assert result == "&amp;lt;div&amp;gt;"


class TestEscapeBrackets:
    """Test the escape_brackets function"""
    
    def test_escape_brackets_string(self):
        """Test escaping HTML brackets in string"""
        result = escape_brackets("Test <brackets> here")
        assert result == "Test &lt;brackets&gt; here"
    
    def test_escape_brackets_only_brackets(self):
        """Test escaping only HTML brackets"""
        result = escape_brackets("<>")
        assert result == "&lt;&gt;"
    
    def test_escape_brackets_non_string(self):
        """Test escape_brackets with non-string input"""
        result = escape_brackets(42)
        assert result == 42  # Returns the input unchanged
    
    def test_escape_brackets_empty_string(self):
        """Test escape_brackets with empty string"""
        result = escape_brackets("")
        assert result == ""


class TestRemoveOmegaConformerId:
    """Test the remove_omega_conformer_id function"""
    
    def test_remove_conformer_id_with_suffix(self):
        """Test removing conformer ID suffix"""
        result = remove_omega_conformer_id("molecule_001")
        assert result == "molecule"
    
    def test_remove_conformer_id_multiple_numbers(self):
        """Test with multiple number groups"""
        result = remove_omega_conformer_id("test_123_456")
        assert result == "test_123"
    
    def test_remove_conformer_id_no_suffix(self):
        """Test string without conformer ID suffix"""
        result = remove_omega_conformer_id("simple_name")
        assert result == "simple_name"
    
    def test_remove_conformer_id_non_string(self):
        """Test with non-string input"""
        result = remove_omega_conformer_id(42)
        assert result == 42  # Returns the input unchanged
    
    def test_remove_conformer_id_empty_string(self):
        """Test with empty string"""
        result = remove_omega_conformer_id("")
        assert result == ""
    
    def test_remove_conformer_id_only_numbers(self):
        """Test string that is only numbers"""
        result = remove_omega_conformer_id("123")
        assert result == "123"
    
    def test_conformer_id_regex(self):
        """Test the regex pattern directly"""
        # Test pattern matches underscore followed by digits at end
        assert CONFORMER_ID_REGEX.search("test_123")
        assert CONFORMER_ID_REGEX.search("molecule_001")
        assert not CONFORMER_ID_REGEX.search("test_abc")
        assert not CONFORMER_ID_REGEX.search("test123")  # no underscore


class TestCreateStructureHighlighter:
    """Test the create_structure_highlighter function"""

    def _make_benzene_display(self):
        """Create a real OE2DMolDisplay for benzene."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)
        self._benzene_mol = mol
        opts = oedepict.OE2DMolDisplayOptions()
        return oedepict.OE2DMolDisplay(mol, opts)

    @patch("cnotebook.core.helpers.oedepict.OEAddHighlighting")
    def test_string_query_traditional_highlighter_adds_matches(self, mock_add_highlighting):
        """A string SMARTS query should highlight real substructure matches."""
        color = oechem.OEColor(oechem.OELightBlue)
        highlighter = create_structure_highlighter(
            "c1ccccc1",
            color=color,
            style=oedepict.OEHighlightStyle_BallAndStick,
        )

        highlighter(self._make_benzene_display())

        assert mock_add_highlighting.call_count >= 1

    @patch("cnotebook.core.helpers.oedepict.OEAddHighlightOverlay")
    def test_subsearch_overlay_highlighter_adds_overlay(self, mock_add_overlay):
        """An OESubSearch query should drive overlay highlighting."""
        ss = oechem.OESubSearch("c1ccccc1")
        highlighter = create_structure_highlighter(ss, color=oechem.OEGetLightColors())

        highlighter(self._make_benzene_display())

        mock_add_overlay.assert_called_once()

    @patch("cnotebook.core.helpers.oedepict.OEAddHighlighting")
    def test_traditional_highlighter_uses_first_color_from_iterator(self, mock_add_highlighting):
        """Traditional highlighting should work when color is an OEColorIter."""
        highlighter = create_structure_highlighter(
            "c1ccccc1",
            color=oechem.OEGetLightColors(),
            style=oedepict.OEHighlightStyle_BallAndStick,
        )

        highlighter(self._make_benzene_display())

        assert mock_add_highlighting.call_count >= 1

    def test_create_highlighter_invalid_type(self):
        """Test that invalid query type raises TypeError"""
        with pytest.raises(TypeError) as exc_info:
            create_structure_highlighter(123)  # Invalid type
        assert "Cannot create structure highlighter" in str(exc_info.value)


class TestIntegration:
    """Integration tests for helper functions"""
    
    def test_html_escaping_workflow(self):
        """Test complete HTML escaping workflow"""
        raw_text = "<div>Tom & Jerry's adventure</div>"
        
        # First escape HTML
        html_escaped = escape_html(raw_text)
        assert "&lt;" in html_escaped
        assert "&gt;" in html_escaped
        assert "&amp;" in html_escaped
        
        # Then escape HTML brackets (note: escape_brackets only handles < >)
        bracket_escaped = escape_brackets(html_escaped)
        # escape_brackets doesn't change already-escaped content
        assert "&lt;" in bracket_escaped
        assert "&gt;" in bracket_escaped
    
    def test_conformer_id_removal_workflow(self):
        """Test conformer ID removal workflow"""
        names = ["molecule_001", "compound_123", "simple_name"]
        
        cleaned_names = [remove_omega_conformer_id(name) for name in names]
        
        assert cleaned_names[0] == "molecule"
        assert cleaned_names[1] == "compound"
        assert cleaned_names[2] == "simple_name"
    
    def test_function_availability(self):
        """Helper regex should remain a compiled conformer-id matcher."""
        assert isinstance(CONFORMER_ID_REGEX, re.Pattern)


class TestCreateStructureHighlighterAdvanced:
    """Advanced tests for the create_structure_highlighter function."""

    def _make_benzene_display(self):
        """Create a real OE2DMolDisplay for benzene."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)
        self._benzene_mol = mol
        opts = oedepict.OE2DMolDisplayOptions()
        return oedepict.OE2DMolDisplay(mol, opts)

    @patch('cnotebook.core.helpers.log')
    @patch("cnotebook.core.helpers.oedepict.OEAddHighlighting")
    def test_highlighter_overlay_single_color_fallback(self, mock_add_highlighting, mock_log):
        """Test that overlay with single OEColor triggers warning and fallback."""
        color = oechem.OEColor(oechem.OELightBlue)
        highlighter = create_structure_highlighter("c1ccccc1", color=color, style="overlay_default")

        highlighter(self._make_benzene_display())

        mock_log.warning.assert_called_once()
        warning_msg = mock_log.warning.call_args[0][0]
        assert "Overlay coloring is not compatible" in warning_msg
        assert mock_add_highlighting.call_count >= 1


class TestHighlightSmarts:
    """Test the highlight_smarts function."""

    def _make_mol(self, smiles: str = "c1ccc2c(c1)nc(n2)N"):
        """Create a molecule from SMILES."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        return mol

    def test_highlight_single_smarts(self):
        """Test highlighting a single SMARTS pattern returns OE2DMolDisplay."""
        mol = self._make_mol()
        disp = highlight_smarts(mol, "c1ccccc1")
        assert isinstance(disp, oedepict.OE2DMolDisplay)

    def test_highlight_multiple_smarts(self):
        """Test highlighting multiple SMARTS patterns returns OE2DMolDisplay."""
        mol = self._make_mol()
        disp = highlight_smarts(mol, ["ncn", "c1ccccc1"])
        assert isinstance(disp, oedepict.OE2DMolDisplay)

    def test_highlight_color_length_mismatch_raises(self):
        """Test that mismatched color list length raises ValueError."""
        mol = self._make_mol()
        colors = [
            oechem.OEColor(oechem.OELightBlue),
            oechem.OEColor(oechem.OEPink),
            oechem.OEColor(oechem.OELightGreen),
        ]
        with pytest.raises(ValueError, match="Length of color sequence"):
            highlight_smarts(mol, ["ncn", "c1ccccc1"], color=colors)

    def test_highlight_style_length_mismatch_raises(self):
        """Test that mismatched style list length raises ValueError."""
        mol = self._make_mol()
        styles = [
            oedepict.OEHighlightStyle_Stick,
            oedepict.OEHighlightStyle_BallAndStick,
            oedepict.OEHighlightStyle_Cogwheel,
        ]
        with pytest.raises(ValueError, match="Length of style sequence"):
            highlight_smarts(mol, ["ncn", "c1ccccc1"], style=styles)

    def test_highlight_with_custom_opts(self):
        """Test highlighting with custom OE2DMolDisplayOptions."""
        mol = self._make_mol()
        opts = oedepict.OE2DMolDisplayOptions()
        opts.SetWidth(400)
        opts.SetHeight(300)
        disp = highlight_smarts(mol, "c1ccccc1", opts=opts)
        assert isinstance(disp, oedepict.OE2DMolDisplay)

    def test_highlight_multiple_colors_and_styles(self):
        """Test highlighting with per-pattern colors and styles."""
        mol = self._make_mol()
        colors = [
            oechem.OEColor(oechem.OELightBlue),
            oechem.OEColor(oechem.OEPink),
        ]
        styles = [
            oedepict.OEHighlightStyle_Stick,
            oedepict.OEHighlightStyle_BallAndStick,
        ]
        disp = highlight_smarts(mol, ["ncn", "c1ccccc1"], color=colors, style=styles)
        assert isinstance(disp, oedepict.OE2DMolDisplay)
