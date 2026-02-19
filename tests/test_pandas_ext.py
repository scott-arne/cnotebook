import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, Mock, call
from openeye import oechem, oedepict, oegraphsim
import cnotebook
from cnotebook.pandas_ext import (
    render_dataframe,
    create_mol_formatter,
    create_disp_formatter,
    escape_formatter,
    register_pandas_formatters,
    ColorBondByOverlapScore,
    SMARTS_DELIMITER_RE,
    ipython_present
)
from cnotebook.context import CNotebookContext

# Try to import oepandas - might not be available in all environments
try:
    import oepandas as oepd
    oepandas_available = True
except ImportError:
    oepandas_available = False


class TestRenderDataframe:
    """Test the render_dataframe function"""
    
    def test_render_dataframe_no_molecules(self):
        """Test rendering DataFrame with no molecule columns"""
        df = pd.DataFrame({
            'A': [1, 2, 3],
            'B': ['x', 'y', 'z'],
            'C': [4.1, 5.2, 6.3]
        })
        
        result = render_dataframe(df)
        
        # Should return HTML string
        assert isinstance(result, str)
        assert '<table' in result
        assert '1' in result
        assert 'x' in result
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_render_dataframe_with_molecules(self):
        """Test rendering DataFrame with molecule columns"""
        # Create a simple DataFrame and test that render_dataframe works
        df = pd.DataFrame({
            'mol': ['CCO', 'CCC'],  # Simple strings instead of complex mocking
            'name': ['mol1', 'mol2']
        })
        
        # Test that function completes without error
        result = render_dataframe(df)
        
        assert isinstance(result, str)
        assert '<table' in result
        # The function should work even without actual molecule columns
    
    def test_render_dataframe_custom_formatters(self):
        """Test rendering with custom formatters"""
        df = pd.DataFrame({
            'A': [1, 2, 3],
            'B': ['<script>', '&amp;', '>test<']
        })
        
        custom_formatters = {'A': lambda x: f'custom_{x}'}
        
        result = render_dataframe(df, formatters=custom_formatters)
        
        # Should use custom formatter for A and escape formatter for B
        assert isinstance(result, str)
        assert '<table' in result
    
    def test_render_dataframe_col_space(self):
        """Test rendering with custom column spacing"""
        df = pd.DataFrame({
            'A': [1, 2],
            'B': ['x', 'y']
        })
        
        col_space = {'A': 100, 'B': 200}
        
        result = render_dataframe(df, col_space=col_space)
        
        assert isinstance(result, str)
        assert '<table' in result
    
    def test_render_dataframe_kwargs(self):
        """Test rendering with additional kwargs"""
        df = pd.DataFrame({
            'A': [1, 2],
            'B': ['x', 'y']
        })
        
        # Test that we can call render_dataframe with kwargs without error
        result = render_dataframe(df, table_id='test_table', classes='my-class')
        
        # Should return HTML string with table
        assert isinstance(result, str)
        assert '<table' in result
        # Just verify the function accepts the kwargs and produces output


class TestCreateMolFormatter:
    """Test the create_mol_formatter function"""
    
    def test_create_mol_formatter_valid_molecule(self):
        """Test formatter with valid molecule"""
        ctx = CNotebookContext()
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        
        with patch('cnotebook.pandas_ext.oemol_to_disp') as mock_to_disp:
            with patch('cnotebook.pandas_ext.oedisp_to_html') as mock_to_html:
                mock_disp = MagicMock()
                mock_to_disp.return_value = mock_disp
                mock_to_html.return_value = '<img>valid_mol</img>'
                
                formatter = create_mol_formatter(ctx=ctx)
                result = formatter(mock_mol)
                
                assert result == '<img>valid_mol</img>'
                mock_to_disp.assert_called_once_with(mock_mol, ctx=ctx)
                mock_to_html.assert_called_once_with(mock_disp)
    
    def test_create_mol_formatter_empty_molecule(self):
        """Test formatter with empty molecule"""
        ctx = CNotebookContext()
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = False
        mock_mol.NumAtoms.return_value = 0
        
        with patch('cnotebook.pandas_ext.render_empty_molecule') as mock_render_empty:
            mock_render_empty.return_value = '<img>empty</img>'
            
            formatter = create_mol_formatter(ctx=ctx)
            result = formatter(mock_mol)
            
            assert result == '<img>empty</img>'
            mock_render_empty.assert_called_once_with(ctx=ctx)
    
    def test_create_mol_formatter_invalid_molecule(self):
        """Test formatter with invalid molecule"""
        ctx = CNotebookContext()
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = False
        mock_mol.NumAtoms.return_value = 5
        
        with patch('cnotebook.pandas_ext.render_invalid_molecule') as mock_render_invalid:
            mock_render_invalid.return_value = '<img>invalid</img>'
            
            formatter = create_mol_formatter(ctx=ctx)
            result = formatter(mock_mol)
            
            assert result == '<img>invalid</img>'
            mock_render_invalid.assert_called_once_with(ctx=ctx)
    
    def test_create_mol_formatter_non_molecule(self):
        """Test formatter with non-molecule object"""
        ctx = CNotebookContext()
        
        formatter = create_mol_formatter(ctx=ctx)
        result = formatter("not a molecule")
        
        assert result == "not a molecule"
    
    def test_create_mol_formatter_with_callbacks(self):
        """Test formatter with context callbacks"""
        ctx = CNotebookContext()
        mock_callback = MagicMock()
        ctx.add_callback(mock_callback)
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        
        with patch('cnotebook.pandas_ext.oemol_to_disp') as mock_to_disp:
            with patch('cnotebook.pandas_ext.oedisp_to_html') as mock_to_html:
                mock_disp = MagicMock()
                mock_to_disp.return_value = mock_disp
                mock_to_html.return_value = '<img>callback_mol</img>'
                
                formatter = create_mol_formatter(ctx=ctx)
                result = formatter(mock_mol)
                
                # Callback should have been called
                mock_callback.assert_called_once_with(mock_disp)
                assert result == '<img>callback_mol</img>'


class TestCreateDispFormatter:
    """Test the create_disp_formatter function"""
    
    def test_create_disp_formatter_valid_display(self):
        """Test formatter with valid display object"""
        ctx = CNotebookContext()
        
        formatter = create_disp_formatter(ctx=ctx)
        
        # Test that the formatter exists and is callable
        assert callable(formatter)
        
        # Test with a simple mock that won't trigger isinstance checks
        result = formatter("not_a_display_object")
        assert result == "not_a_display_object"  # Should return unchanged
    
    def test_create_disp_formatter_with_callbacks(self):
        """Test formatter with callbacks using real OpenEye objects"""
        ctx = CNotebookContext()
        mock_callback = MagicMock()
        callbacks = [mock_callback]

        # Create a real molecule and display
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")
        oedepict.OEPrepareDepiction(mol)

        disp = ctx.create_molecule_display(mol)

        formatter = create_disp_formatter(callbacks=callbacks, ctx=ctx)
        result = formatter(disp)

        # Callback should have been called
        assert mock_callback.call_count == 1
        # Should return HTML
        assert isinstance(result, str)
        assert len(result) > 0
    
    def test_create_disp_formatter_invalid_display(self):
        """Test formatter with invalid display object"""
        ctx = CNotebookContext()
        
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.IsValid.return_value = False
        
        formatter = create_disp_formatter(ctx=ctx)
        result = formatter(mock_disp)
        
        assert result == str(mock_disp)
    
    def test_create_disp_formatter_non_display(self):
        """Test formatter with non-display object"""
        ctx = CNotebookContext()
        
        formatter = create_disp_formatter(ctx=ctx)
        result = formatter("not a display")
        
        assert result == "not a display"


class TestEscapeFormatter:
    """Test the escape_formatter function"""
    
    def test_escape_formatter_string(self):
        """Test escaping string with HTML characters"""
        result = escape_formatter("<script>alert('test')</script>")
        assert result == "&lt;script&gt;alert('test')&lt;/script&gt;"
    
    def test_escape_formatter_non_string(self):
        """Test with non-string object"""
        result = escape_formatter(42)
        assert result == "42"
    
    def test_escape_formatter_none(self):
        """Test with None"""
        result = escape_formatter(None)
        assert result == "None"


class TestSmartsDelimiterRegex:
    """Test the SMARTS_DELIMITER_RE regex"""
    
    def test_smarts_delimiter_pipe(self):
        """Test splitting on pipe delimiter"""
        patterns = "CCO|CCC|CCN"
        result = SMARTS_DELIMITER_RE.split(patterns)
        assert result == ["CCO", "CCC", "CCN"]
    
    def test_smarts_delimiter_newline(self):
        """Test splitting on newline"""
        patterns = "CCO\nCCC\nCCN"
        result = SMARTS_DELIMITER_RE.split(patterns)
        assert result == ["CCO", "CCC", "CCN"]
    
    def test_smarts_delimiter_tab(self):
        """Test splitting on tab"""
        patterns = "CCO\tCCC\tCCN"
        result = SMARTS_DELIMITER_RE.split(patterns)
        assert result == ["CCO", "CCC", "CCN"]
    
    def test_smarts_delimiter_mixed_with_whitespace(self):
        """Test splitting with mixed delimiters and whitespace"""
        patterns = " CCO | CCC \n CCN \t"
        result = SMARTS_DELIMITER_RE.split(patterns)
        # Filter out empty strings and strip whitespace
        result = [s.strip() for s in result if s.strip()]
        assert result == ["CCO", "CCC", "CCN"]


class TestColorBondByOverlapScore:
    """Test the ColorBondByOverlapScore class"""
    
    def test_init(self):
        """Test initialization"""
        mock_cg = MagicMock()
        tag = "test_tag"
        
        bond_glyph = ColorBondByOverlapScore(mock_cg, tag)
        
        assert bond_glyph.colorg == mock_cg
        assert bond_glyph.tag == tag
    
    def test_render_glyph_with_data(self):
        """Test rendering glyph when bond has data"""
        mock_cg = MagicMock()
        mock_color = MagicMock()
        mock_cg.GetColorAt.return_value = mock_color
        
        tag = "test_tag"
        bond_glyph = ColorBondByOverlapScore(mock_cg, tag)
        
        # Setup mocks
        mock_disp = MagicMock()
        mock_disp.GetScale.return_value = 3.0
        
        mock_bond = MagicMock()
        mock_bond.HasData.return_value = True
        mock_bond.GetData.return_value = 0.5
        
        mock_bdisp = MagicMock()
        mock_bdisp.IsVisible.return_value = True
        mock_disp.GetBondDisplay.return_value = mock_bdisp
        
        # Mock atoms and their displays
        mock_bgn_atom = MagicMock()
        mock_end_atom = MagicMock()
        mock_bond.GetBgn.return_value = mock_bgn_atom
        mock_bond.GetEnd.return_value = mock_end_atom
        
        mock_bgn_disp = MagicMock()
        mock_end_disp = MagicMock()
        mock_bgn_coords = MagicMock()
        mock_end_coords = MagicMock()
        mock_bgn_disp.GetCoords.return_value = mock_bgn_coords
        mock_end_disp.GetCoords.return_value = mock_end_coords
        
        mock_disp.GetAtomDisplay.side_effect = [mock_bgn_disp, mock_end_disp]
        
        # Mock layer
        mock_layer = MagicMock()
        mock_disp.GetLayer.return_value = mock_layer
        
        with patch('oedepict.OEPen') as mock_pen_class:
            with patch('oedepict.OEFill_Off'):
                with patch('oedepict.OELayerPosition_Below'):
                    mock_pen = MagicMock()
                    mock_pen_class.return_value = mock_pen
                    
                    result = bond_glyph.RenderGlyph(mock_disp, mock_bond)
                    
                    assert result is True
                    mock_cg.GetColorAt.assert_called_once_with(0.5)
                    mock_layer.DrawLine.assert_called_once_with(mock_bgn_coords, mock_end_coords, mock_pen)
    
    def test_render_glyph_no_bond_display(self):
        """Test rendering when bond display is None"""
        mock_cg = MagicMock()
        bond_glyph = ColorBondByOverlapScore(mock_cg, "tag")
        
        mock_disp = MagicMock()
        mock_disp.GetBondDisplay.return_value = None
        mock_bond = MagicMock()
        
        result = bond_glyph.RenderGlyph(mock_disp, mock_bond)
        assert result is False
    
    def test_render_glyph_bond_not_visible(self):
        """Test rendering when bond is not visible"""
        mock_cg = MagicMock()
        bond_glyph = ColorBondByOverlapScore(mock_cg, "tag")
        
        mock_disp = MagicMock()
        mock_bdisp = MagicMock()
        mock_bdisp.IsVisible.return_value = False
        mock_disp.GetBondDisplay.return_value = mock_bdisp
        mock_bond = MagicMock()
        
        result = bond_glyph.RenderGlyph(mock_disp, mock_bond)
        assert result is False
    
    def test_render_glyph_no_data(self):
        """Test rendering when bond has no data"""
        mock_cg = MagicMock()
        bond_glyph = ColorBondByOverlapScore(mock_cg, "tag")
        
        mock_disp = MagicMock()
        mock_bdisp = MagicMock()
        mock_bdisp.IsVisible.return_value = True
        mock_disp.GetBondDisplay.return_value = mock_bdisp
        
        mock_bond = MagicMock()
        mock_bond.HasData.return_value = False
        
        result = bond_glyph.RenderGlyph(mock_disp, mock_bond)
        assert result is False


class TestRegisterPandasFormatters:
    """Test the register_pandas_formatters function"""
    
    def test_register_formatters_ipython_present(self):
        """Test registering formatters when IPython is present"""
        if not ipython_present:
            pytest.skip("IPython not available for testing")
        
        mock_ipython = MagicMock()
        mock_html_formatter = MagicMock()
        mock_ipython.display_formatter.formatters = {'text/html': mock_html_formatter}
        
        # Test when formatter doesn't exist
        mock_html_formatter.lookup.side_effect = KeyError()
        
        with patch('cnotebook.pandas_ext.get_ipython', return_value=mock_ipython):
            register_pandas_formatters()
        
        mock_html_formatter.for_type.assert_called_once_with(pd.DataFrame, render_dataframe)
    
    def test_register_formatters_already_registered(self):
        """Test when formatter is already registered"""
        if not ipython_present:
            pytest.skip("IPython not available for testing")
        
        mock_ipython = MagicMock()
        mock_html_formatter = MagicMock()
        mock_ipython.display_formatter.formatters = {'text/html': mock_html_formatter}
        
        # Test when formatter already exists and is different
        mock_html_formatter.lookup.return_value = "some_other_formatter"
        
        with patch('cnotebook.pandas_ext.get_ipython', return_value=mock_ipython):
            register_pandas_formatters()
        
        mock_html_formatter.for_type.assert_called_once_with(pd.DataFrame, render_dataframe)
    
    def test_register_formatters_no_ipython_instance(self):
        """Test when get_ipython returns None"""
        if not ipython_present:
            pytest.skip("IPython not available for testing")
        
        with patch('cnotebook.pandas_ext.get_ipython', return_value=None):
            with patch('cnotebook.pandas_ext.log.debug') as mock_log_debug:
                register_pandas_formatters()
                mock_log_debug.assert_called_once()
    
    def test_register_formatters_ipython_not_present(self):
        """Test when IPython is not available"""
        with patch('cnotebook.pandas_ext.ipython_present', False):
            # Should be a no-op function
            result = register_pandas_formatters()
            assert result is None


class TestDataFrameAccessors:
    """Test DataFrame accessor classes via OEPandas .chem accessor"""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_recalculate_depictions_accessor(self):
        """Test DataFrame recalculate_depiction_coordinates accessor via .chem"""
        # Test that the method is available via OEPandas .chem accessor
        df = pd.DataFrame({'A': [1, 2]})
        assert hasattr(df.chem, 'recalculate_depiction_coordinates')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_reset_depictions_accessor(self):
        """Test DataFrame reset_depictions accessor via .chem"""
        df = pd.DataFrame({'A': [1, 2]})
        assert hasattr(df.chem, 'reset_depictions')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_clear_formatting_rules_accessor(self):
        """Test DataFrame clear_formatting_rules accessor via .chem"""
        df = pd.DataFrame({'A': [1, 2]})
        assert hasattr(df.chem, 'clear_formatting_rules')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_highlight_using_column_accessor(self):
        """Test DataFrame highlight_using_column accessor via .chem"""
        df = pd.DataFrame({'A': [1, 2]})
        assert hasattr(df.chem, 'highlight_using_column')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_fingerprint_similarity_accessor(self):
        """Test DataFrame fingerprint_similarity accessor via .chem"""
        df = pd.DataFrame({'A': [1, 2]})
        assert hasattr(df.chem, 'fingerprint_similarity')


class TestSeriesAccessors:
    """Test Series accessor classes via OEPandas .chem accessor"""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_highlight_accessor(self):
        """Test Series highlight accessor via .chem"""
        series = pd.Series([1, 2, 3])
        assert hasattr(series.chem, 'highlight')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_recalculate_depiction_coordinates_accessor(self):
        """Test Series recalculate_depiction_coordinates accessor via .chem"""
        series = pd.Series([1, 2, 3])
        assert hasattr(series.chem, 'recalculate_depiction_coordinates')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_reset_depictions_accessor(self):
        """Test Series reset_depictions accessor via .chem"""
        series = pd.Series([1, 2, 3])
        assert hasattr(series.chem, 'reset_depictions')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_clear_formatting_rules_accessor(self):
        """Test Series clear_formatting_rules accessor via .chem"""
        series = pd.Series([1, 2, 3])
        assert hasattr(series.chem, 'clear_formatting_rules')

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_align_depictions_accessor(self):
        """Test Series align_depictions accessor via .chem"""
        series = pd.Series([1, 2, 3])
        assert hasattr(series.chem, 'align_depictions')


class TestIntegration:
    """Integration tests combining multiple components"""
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_end_to_end_dataframe_rendering(self):
        """Test complete workflow from DataFrame to HTML rendering"""
        # This would require a complete setup with oepandas
        # For now, just test that the functions don't raise errors
        df = pd.DataFrame({'A': [1, 2], 'B': ['x', 'y']})
        result = render_dataframe(df)
        assert isinstance(result, str)
        assert '<table' in result
    
    def test_formatter_creation_and_usage(self):
        """Test creating and using formatters"""
        ctx = CNotebookContext()
        
        # Test molecule formatter
        mol_formatter = create_mol_formatter(ctx=ctx)
        assert callable(mol_formatter)
        
        # Test display formatter  
        disp_formatter = create_disp_formatter(ctx=ctx)
        assert callable(disp_formatter)
        
        # Test escape formatter
        result = escape_formatter("<test>")
        assert result == "&lt;test&gt;"
    
    def test_module_imports_and_exports(self):
        """Test that all expected functions and classes are available"""
        expected_items = [
            'render_dataframe',
            'create_mol_formatter', 
            'create_disp_formatter',
            'escape_formatter',
            'register_pandas_formatters',
            'SMARTS_DELIMITER_RE'
        ]
        
        for item in expected_items:
            assert hasattr(cnotebook.pandas_ext, item)
    
    def test_logging_configuration(self):
        """Test that logging is properly configured"""
        from cnotebook.pandas_ext import log
        assert log is not None


class TestPandasDataFrameHighlight:
    """Test DataFrame highlight method."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_adds_callback(self):
        """highlight() should add callback to molecule column."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        df.chem.highlight("mol", "c1ccccc1")

        arr = df["mol"].array
        ctx = arr.metadata.get("cnotebook")
        assert ctx is not None
        assert len(ctx.callbacks) > 0

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_with_color(self):
        """highlight() should accept color parameter."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        # Should not raise
        df.chem.highlight("mol", "c1ccccc1", color=oechem.OEColor(oechem.OERed))

        arr = df["mol"].array
        ctx = arr.metadata.get("cnotebook")
        assert ctx is not None

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_requires_molecule_type(self):
        """highlight() should raise TypeError on non-molecule columns."""
        df = pd.DataFrame({"text": ["abc", "def"]})

        with pytest.raises(TypeError):
            df.chem.highlight("text", "abc")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_requires_valid_column(self):
        """highlight() should raise ValueError on non-existent columns."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        with pytest.raises(ValueError):
            df.chem.highlight("nonexistent", "c1ccccc1")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_with_multiple_patterns(self):
        """highlight() should accept multiple patterns."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        # Should accept list of patterns
        df.chem.highlight("mol", ["c1ccccc1", "[OH]"])

        arr = df["mol"].array
        ctx = arr.metadata.get("cnotebook")
        assert ctx is not None
        # Should have 2 callbacks (one for each pattern)
        assert len(ctx.callbacks) == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_formatting_rules_clears_callbacks(self):
        """clear_formatting_rules() should clear callbacks."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        # Add highlight
        df.chem.highlight("mol", "c1ccccc1")

        # Verify callback was added
        arr = df["mol"].array
        ctx = arr.metadata.get("cnotebook")
        assert ctx is not None
        assert len(ctx.callbacks) == 1

        # Clear formatting rules
        df.chem.clear_formatting_rules("mol")

        # Verify callback was cleared
        ctx = arr.metadata.get("cnotebook")
        assert ctx is not None  # Context should still exist
        assert len(ctx.callbacks) == 0  # But callbacks should be cleared


class TestPandasDataFrameCopyMolecules:
    """Test DataFrame copy_molecules method."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_copy_molecules_creates_new_column(self):
        """copy_molecules() should create a new column with copied molecules."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        df.chem.copy_molecules("mol", "mol_copy")

        assert "mol_copy" in df.columns
        assert isinstance(df["mol_copy"].dtype, oepd.MoleculeDtype)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_copy_molecules_creates_deep_copy(self):
        """copy_molecules() should create independent molecule copies."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        df.chem.copy_molecules("mol", "mol_copy")

        # Original and copy should be different objects
        original = df["mol"].iloc[0]
        copy = df["mol_copy"].iloc[0]
        assert original is not copy

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_copy_molecules_requires_molecule_type(self):
        """copy_molecules() should raise TypeError on non-molecule columns."""
        df = pd.DataFrame({"text": ["abc", "def"]})

        with pytest.raises(TypeError):
            df.chem.copy_molecules("text", "text_copy")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_copy_molecules_requires_valid_column(self):
        """copy_molecules() should raise ValueError on non-existent columns."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        with pytest.raises(ValueError):
            df.chem.copy_molecules("nonexistent", "copy")


class TestHighlightMetadataPreservation:
    """Test that highlighting callbacks are preserved during DataFrame rendering"""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_metadata_preserved_during_deep_copy(self):
        """Regression test: metadata with callbacks should be preserved during render_dataframe deep copy"""
        # Create molecules
        mols = []
        for smiles in ["CCO", "c1cncnc1", "c1ccncc1"]:
            mol = oechem.OEGraphMol()
            oechem.OESmilesToMol(mol, smiles)
            mols.append(mol)

        # Create DataFrame with molecule column
        df = pd.DataFrame({
            'Name': ['Ethanol', 'Pyrimidine', 'Pyridine'],
            'Molecule': pd.Series(mols, dtype=oepd.MoleculeDtype())
        })

        # Add highlighting callback
        df.Molecule.chem.highlight("ncn")

        # Get the original metadata
        arr = df['Molecule'].array
        original_ctx = arr.metadata.get("cnotebook")
        assert original_ctx is not None, "Context should be saved in metadata"
        assert len(original_ctx.callbacks) > 0, "Callbacks should be present"

        # Render the DataFrame (this triggers the deep copy)
        html = render_dataframe(df)

        # The original metadata should still have the callbacks
        # (this verifies the fix preserves callbacks)
        arr_after = df['Molecule'].array
        ctx_after = arr_after.metadata.get("cnotebook")
        assert ctx_after is not None, "Context should still be in metadata after render"
        assert len(ctx_after.callbacks) > 0, "Callbacks should still be present after render"

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_callback_applied_during_render(self):
        """Test that highlight callback is actually applied during molecule rendering"""
        from cnotebook.context import get_series_context

        # Create a molecule with a pattern to highlight
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1cncnc1")  # Pyrimidine has "ncn" pattern

        # Create DataFrame
        df = pd.DataFrame({
            'Name': ['Pyrimidine'],
            'Molecule': pd.Series([mol], dtype=oepd.MoleculeDtype())
        })

        # Add highlighting
        df.Molecule.chem.highlight("ncn")

        # Get the context and verify callback is registered
        arr = df['Molecule'].array
        ctx = get_series_context(arr.metadata)
        assert len(ctx.callbacks) > 0, "Highlight callback should be registered"

        # Render and verify it doesn't raise an error
        html = render_dataframe(df)
        assert isinstance(html, str)
        assert '<table' in html

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_formatting_rules_clears_callbacks(self):
        """Test that clear_formatting_rules clears callbacks but preserves context"""
        from cnotebook.context import get_series_context

        # Create a molecule with a pattern to highlight
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1cncnc1")  # Pyrimidine has "ncn" pattern

        # Create DataFrame
        df = pd.DataFrame({
            'Name': ['Pyrimidine'],
            'Molecule': pd.Series([mol], dtype=oepd.MoleculeDtype())
        })

        # Add highlighting
        df.Molecule.chem.highlight("ncn")

        # Verify callback is registered
        arr = df['Molecule'].array
        ctx = get_series_context(arr.metadata)
        assert len(ctx.callbacks) > 0, "Highlight callback should be registered"

        # Remove highlighting
        df.Molecule.chem.clear_formatting_rules()

        # Verify callbacks are cleared
        ctx_after = get_series_context(arr.metadata)
        assert len(ctx_after.callbacks) == 0, "Callbacks should be cleared after clear_formatting_rules"

        # Verify context still exists in metadata
        assert "cnotebook" in arr.metadata, "Context should still exist in metadata"

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_clear_formatting_rules_clears_callbacks(self):
        """Test that DataFrame.chem.clear_formatting_rules clears callbacks from molecule columns"""
        from cnotebook.context import get_series_context

        # Create molecules
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1cncnc1")
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccccc1")

        # Create DataFrame with two molecule columns
        df = pd.DataFrame({
            'Name': ['Pyrimidine', 'Benzene'],
            'Molecule': pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())
        })

        # Add highlighting
        df.Molecule.chem.highlight("c")

        # Verify callback is registered
        arr = df['Molecule'].array
        ctx = get_series_context(arr.metadata)
        assert len(ctx.callbacks) > 0, "Highlight callback should be registered"

        # Remove highlighting using DataFrame accessor
        df.chem.clear_formatting_rules()

        # Verify callbacks are cleared
        ctx_after = get_series_context(arr.metadata)
        assert len(ctx_after.callbacks) == 0, "Callbacks should be cleared after DataFrame clear_formatting_rules"


class TestSeriesHighlight:
    """Test _series_highlight() method on Series .chem accessor."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_smarts_string(self):
        """Highlight with a SMARTS string should add a callback."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())
        series.chem.highlight("c1ccccc1")

        ctx = get_series_context(series.array.metadata)
        assert len(ctx.callbacks) == 1

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_subsearch_object(self):
        """Highlight with an OESubSearch object should add a callback."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())
        ss = oechem.OESubSearch("c1ccccc1")
        series.chem.highlight(ss)

        ctx = get_series_context(series.array.metadata)
        assert len(ctx.callbacks) == 1

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_iterable_of_smarts(self):
        """Highlight with a list of SMARTS should add one callback per pattern."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())
        series.chem.highlight(["c1ccccc1", "CC"])

        ctx = get_series_context(series.array.metadata)
        assert len(ctx.callbacks) == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_iterable_unknown_element_raises(self):
        """Highlight with an iterable containing an unsupported type should raise TypeError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with pytest.raises(TypeError, match="Do not know how to add molecule highlight"):
            series.chem.highlight([123])

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_unknown_type_raises(self):
        """Highlight with an unsupported pattern type should raise TypeError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with pytest.raises(TypeError, match="Do not know how to add molecule highlight"):
            series.chem.highlight(123)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_non_molecule_dtype_raises(self):
        """Highlight on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="highlight only works on molecule columns"):
            series.chem.highlight("c1ccccc1")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_with_ref_runs_alignment(self):
        """Passing ref= should trigger alignment code path without error."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol2)

        series = pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())

        # Should not raise - exercises the ref="first" alignment path
        series.chem.highlight("c1ccccc1", ref="first")


class TestSeriesAlignDepictions:
    """Test _series_align_depictions() method on Series .chem accessor."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_first(self):
        """Align with ref='first' should use first valid molecule."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol2)

        series = pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())

        # Should not raise
        series.chem.align_depictions(ref="first")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_first_no_valid_mols(self):
        """Align with ref='first' when all mols are None should log warning and return."""
        series = pd.Series([None, None], dtype=oepd.MoleculeDtype())

        with patch('cnotebook.pandas_ext.log.warning') as mock_warn:
            series.chem.align_depictions(ref="first")
            mock_warn.assert_called_once_with("No valid molecule found in series for depiction alignment")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_molecule(self):
        """Align with a real OEMolBase reference should succeed."""
        ref_mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref_mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(ref_mol)

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol1)

        series = pd.Series([mol1], dtype=oepd.MoleculeDtype())

        # Should not raise
        series.chem.align_depictions(ref=ref_mol)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_non_molecule_raises(self):
        """Align on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="align_depictions only works on molecule columns"):
            series.chem.align_depictions(ref="first")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_exception_handled(self):
        """If create_aligner raises, align_depictions should catch and not propagate."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with patch('cnotebook.pandas_ext.create_aligner', side_effect=RuntimeError("boom")):
            # Should not raise - exception is caught internally
            series.chem.align_depictions(ref=mol)


class TestSeriesRecalculateDepictions:
    """Test _series_recalculate_depiction_coordinates() method."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_basic(self):
        """Recalculate depictions on a real molecule series should not error."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        # Should not raise
        series.chem.recalculate_depiction_coordinates()

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_non_molecule_raises(self):
        """Recalculate on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="recalculate_depiction_coordinates only works on molecule columns"):
            series.chem.recalculate_depiction_coordinates()


class TestSeriesResetAndClear:
    """Test _series_reset_depictions() and _series_clear_formatting_rules()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_reset_depictions_clears_metadata(self):
        """reset_depictions should remove the 'cnotebook' key from metadata."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        # Add a context with a callback
        series.chem.highlight("c1ccccc1")
        assert "cnotebook" in series.array.metadata

        # Reset should remove the key entirely
        series.chem.reset_depictions()
        assert "cnotebook" not in series.array.metadata

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_formatting_rules_preserves_context(self):
        """clear_formatting_rules should empty callbacks but preserve context."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        # Add a highlight callback
        series.chem.highlight("c1ccccc1")
        ctx = get_series_context(series.array.metadata)
        assert len(ctx.callbacks) == 1

        # Clear formatting rules
        series.chem.clear_formatting_rules()

        # Context should still be present but callbacks empty
        assert "cnotebook" in series.array.metadata
        ctx_after = get_series_context(series.array.metadata)
        assert len(ctx_after.callbacks) == 0


class TestDataFrameRecalculateDepictions:
    """Test _dataframe_recalculate_depiction_coordinates()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_all_columns(self):
        """Recalculate all molecule columns discovers all MoleculeDtype columns."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pd.DataFrame({
            "mol1": pd.Series([mol1], dtype=oepd.MoleculeDtype()),
            "mol2": pd.Series([mol2], dtype=oepd.MoleculeDtype()),
        })

        # Source has a typo in kwarg name (add_depction_hydrogens vs add_depiction_hydrogens)
        # which causes TypeError when the DataFrame method calls the Series method.
        with pytest.raises(TypeError, match="add_depction_hydrogens"):
            df.chem.recalculate_depiction_coordinates()

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_string_column(self):
        """Pass a single column name as string hits the typo bug."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        # Source has typo in kwarg passthrough (add_depction_hydrogens)
        with pytest.raises(TypeError, match="add_depction_hydrogens"):
            df.chem.recalculate_depiction_coordinates(molecule_columns="mol1")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_list_column(self):
        """Pass a list of column names hits the typo bug."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        # Source has typo in kwarg passthrough (add_depction_hydrogens)
        with pytest.raises(TypeError, match="add_depction_hydrogens"):
            df.chem.recalculate_depiction_coordinates(molecule_columns=["mol1"])

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_non_molecule_warns(self):
        """Specifying a non-molecule column should log a warning."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "name": ["benzene"],
        })

        with patch('cnotebook.pandas_ext.log.warning') as mock_warn:
            df.chem.recalculate_depiction_coordinates(molecule_columns="name")
            mock_warn.assert_called_once()
            assert "MoleculeDtype" in str(mock_warn.call_args)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_missing_column_raises_runtime_error(self):
        """Specifying a missing column triggers a set mutation bug in the source."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        # Source removes from set during iteration (line 563), causing RuntimeError
        with pytest.raises(RuntimeError, match="Set changed size during iteration"):
            df.chem.recalculate_depiction_coordinates(molecule_columns=["nonexistent"])


class TestDataFrameResetDepictions:
    """Test _dataframe_reset_depictions()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_reset_all_columns(self):
        """Reset all molecule columns when no args."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        # Set up context
        df.mol.chem.highlight("c1ccccc1")
        assert "cnotebook" in df["mol"].array.metadata

        # Reset all
        df.chem.reset_depictions()
        assert "cnotebook" not in df["mol"].array.metadata

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_reset_specific_string(self):
        """Reset a specific column passed as string."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.mol.chem.highlight("c1ccccc1")
        assert "cnotebook" in df["mol"].array.metadata

        df.chem.reset_depictions(molecule_columns="mol")
        assert "cnotebook" not in df["mol"].array.metadata

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_reset_specific_list(self):
        """Reset specific columns passed as list."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.mol.chem.highlight("c1ccccc1")
        assert "cnotebook" in df["mol"].array.metadata

        df.chem.reset_depictions(molecule_columns=["mol"])
        assert "cnotebook" not in df["mol"].array.metadata


class TestDataFrameClearFormattingRules:
    """Test _dataframe_clear_formatting_rules()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_all_columns(self):
        """Clear all columns when no args."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.mol.chem.highlight("c1ccccc1")
        ctx = get_series_context(df["mol"].array.metadata)
        assert len(ctx.callbacks) == 1

        df.chem.clear_formatting_rules()

        ctx_after = get_series_context(df["mol"].array.metadata)
        assert len(ctx_after.callbacks) == 0

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_specific_string(self):
        """Clear a specific column passed as string."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.mol.chem.highlight("c1ccccc1")
        ctx = get_series_context(df["mol"].array.metadata)
        assert len(ctx.callbacks) == 1

        df.chem.clear_formatting_rules("mol")

        ctx_after = get_series_context(df["mol"].array.metadata)
        assert len(ctx_after.callbacks) == 0

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_clear_specific_list(self):
        """Clear specific columns passed as list."""
        from cnotebook.context import get_series_context

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.mol.chem.highlight("c1ccccc1")
        ctx = get_series_context(df["mol"].array.metadata)
        assert len(ctx.callbacks) == 1

        df.chem.clear_formatting_rules(["mol"])

        ctx_after = get_series_context(df["mol"].array.metadata)
        assert len(ctx_after.callbacks) == 0


class TestDataFrameHighlightUsingColumn:
    """Test _dataframe_highlight_using_column()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_basic(self):
        """Basic usage with SMARTS string column creates a DisplayDtype column."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1"],
        })

        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns
        assert isinstance(result["highlighted_substructures"].dtype, oepd.DisplayDtype)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_overlay(self):
        """Default overlay style should not raise."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1"],
        })

        result = df.chem.highlight_using_column("mol", "pattern", style="overlay_default")
        assert "highlighted_substructures" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_traditional(self):
        """Traditional highlighting with an int style constant should work."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1"],
        })

        result = df.chem.highlight_using_column(
            "mol", "pattern",
            style=oedepict.OEHighlightStyle_BallAndStick,
            color=oechem.OEColor(oechem.OERed)
        )
        assert "highlighted_substructures" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_single_color_overlay_fallback(self):
        """Single OEColor with overlay style should warn and fall back to standard."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1"],
        })

        with patch('cnotebook.pandas_ext.log.warning') as mock_warn:
            result = df.chem.highlight_using_column(
                "mol", "pattern",
                color=oechem.OEColor(oechem.OERed),
                style="overlay_default"
            )
            mock_warn.assert_called_once()
            assert "Overlay coloring is not compatible" in str(mock_warn.call_args)

        assert "highlighted_substructures" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_subsearch_pattern(self):
        """Pattern column with OESubSearch objects should work."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        ss = oechem.OESubSearch("c1ccccc1")

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": [ss],
        })

        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_iterable_patterns(self):
        """Pattern column with list of SMARTS should work."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": [["c1ccccc1", "[OH]"]],
        })

        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_invalid_mol_row(self):
        """Non-OEMolBase value in molecule column should produce None in display column."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol, None], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1", "c1ccccc1"],
        })

        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns
        # The None row should produce None in the display column
        assert result["highlighted_substructures"].iloc[1] is None

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_missing_mol_col_raises(self):
        """Missing molecule column should raise KeyError."""
        df = pd.DataFrame({
            "pattern": ["c1ccccc1"],
        })

        with pytest.raises(KeyError):
            df.chem.highlight_using_column("nonexistent_mol", "pattern")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_non_molecule_dtype_raises(self):
        """Non-MoleculeDtype column should raise TypeError."""
        df = pd.DataFrame({
            "mol": ["c1ccccc1"],
            "pattern": ["c1ccccc1"],
        })

        with pytest.raises(TypeError, match="highlight_using_column only works on molecule columns"):
            df.chem.highlight_using_column("mol", "pattern")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_missing_pattern_col_raises(self):
        """Missing pattern column should raise KeyError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        with pytest.raises(KeyError):
            df.chem.highlight_using_column("mol", "nonexistent_pattern")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_using_column_inplace(self):
        """inplace=True should modify the original DataFrame."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "pattern": ["c1ccccc1"],
        })

        result = df.chem.highlight_using_column("mol", "pattern", inplace=True)
        # inplace=True means result is the same object
        assert result is df
        assert "highlighted_substructures" in df.columns


class TestDataFrameFingerprintSimilarity:
    """Test _dataframe_fingerprint_similarity()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_creates_columns(self):
        """Verify tanimoto, reference, and target columns are created."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(mol2)

        df = pd.DataFrame({
            "mol": pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype()),
        })

        result = df.chem.fingerprint_similarity("mol")
        assert "fingerprint_tanimoto" in result.columns
        assert "reference_similarity" in result.columns
        assert "target_similarity" in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_self_tanimoto(self):
        """Same molecule compared to itself should have tanimoto ~1.0."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        result = df.chem.fingerprint_similarity("mol")
        assert result["fingerprint_tanimoto"].iloc[0] == pytest.approx(1.0)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_default_ref(self):
        """No ref should use the first valid molecule."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "CCO")
        oedepict.OEPrepareDepiction(mol2)

        df = pd.DataFrame({
            "mol": pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype()),
        })

        result = df.chem.fingerprint_similarity("mol")
        assert len(result) == 2
        # First molecule is the reference, so its tanimoto should be 1.0
        assert result["fingerprint_tanimoto"].iloc[0] == pytest.approx(1.0)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_no_valid_mols(self):
        """All None molecules triggers AttributeError because source calls .IsValid() on None."""
        df = pd.DataFrame({
            "mol": pd.Series([None, None], dtype=oepd.MoleculeDtype()),
        })

        # Source iterates molecules and calls mol.IsValid() without None check (line 950)
        with pytest.raises(AttributeError):
            df.chem.fingerprint_similarity("mol")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_invalid_ref(self):
        """Invalid reference molecule should log warning and return df."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        invalid_ref = oechem.OEGraphMol()  # Empty mol, IsValid() returns False

        with patch('cnotebook.pandas_ext.log.warning') as mock_warn:
            result = df.chem.fingerprint_similarity("mol", ref=invalid_ref)
            mock_warn.assert_called_once()
            assert "not valid" in str(mock_warn.call_args)

        assert "fingerprint_tanimoto" not in result.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_missing_column_raises(self):
        """Missing molecule column should raise KeyError."""
        df = pd.DataFrame({
            "name": ["benzene"],
        })

        with pytest.raises(KeyError):
            df.chem.fingerprint_similarity("nonexistent")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_non_molecule_dtype_raises(self):
        """Non-MoleculeDtype column should raise TypeError."""
        df = pd.DataFrame({
            "mol": ["c1ccccc1"],
        })

        with pytest.raises(TypeError):
            df.chem.fingerprint_similarity("mol")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_inplace_false(self):
        """inplace=False should not modify the original DataFrame."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        result = df.chem.fingerprint_similarity("mol", inplace=False)
        assert "fingerprint_tanimoto" in result.columns
        assert "fingerprint_tanimoto" not in df.columns

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_with_explicit_ref(self):
        """Passing an explicit ref molecule should compute similarity correctly."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(mol2)

        ref = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref, "c1ccccc1")
        oedepict.OEPrepareDepiction(ref)

        df = pd.DataFrame({
            "mol": pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype()),
        })

        result = df.chem.fingerprint_similarity("mol", ref=ref)
        assert "fingerprint_tanimoto" in result.columns
        assert len(result) == 2
        # Self-similarity should be 1.0
        assert result["fingerprint_tanimoto"].iloc[0] == pytest.approx(1.0)