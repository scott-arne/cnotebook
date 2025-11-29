import pytest
import re
from unittest.mock import MagicMock
from openeye import oechem
from cnotebook.helpers import (
    escape_html,
    escape_brackets, 
    remove_omega_conformer_id,
    create_structure_highlighter,
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

    def test_create_highlighter_exists(self):
        """Test that create_structure_highlighter function exists"""
        assert callable(create_structure_highlighter)

    def test_create_highlighter_basic(self):
        """Test basic functionality without calling OpenEye functions"""
        # Just test that we can create a highlighter and it's callable
        highlighter = create_structure_highlighter("CCO")
        assert callable(highlighter)

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
        """Test that all helper functions are available"""
        assert callable(escape_html)
        assert callable(escape_brackets)
        assert callable(remove_omega_conformer_id)
        assert callable(create_structure_highlighter)
        assert isinstance(CONFORMER_ID_REGEX, re.Pattern)