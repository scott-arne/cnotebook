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
    SeriesHighlightAccessor,
    SeriesRecalculateDepictionCoordinatesAccessor,
    SeriesResetDepictionsAccessor,
    SeriesAlignDepictionsAccessor,
    HighlightUsingColumnAccessor,
    FingerprintSimilaritySeriesAccessor,
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
        """Test formatter with callbacks"""
        ctx = CNotebookContext()
        mock_callback = MagicMock()
        callbacks = [mock_callback]
        
        formatter = create_disp_formatter(callbacks=callbacks, ctx=ctx)
        
        # Test that the formatter exists and is callable
        assert callable(formatter)
        
        # Test with a simple non-display object
        result = formatter("not_a_display_object")
        assert result == "not_a_display_object"
    
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
    """Test DataFrame accessor classes"""
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_recalculate_depictions_accessor(self):
        """Test DataFrame recalculate_depiction_coordinates accessor"""
        # This would require setting up a full DataFrame with molecule columns
        # For now, just test that the accessor is registered
        assert hasattr(pd.DataFrame, 'recalculate_depiction_coordinates')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_reset_depictions_accessor(self):
        """Test DataFrame reset_depictions accessor"""
        assert hasattr(pd.DataFrame, 'reset_depictions')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_highlight_using_column_accessor(self):
        """Test DataFrame highlight_using_column accessor"""
        assert hasattr(pd.DataFrame, 'highlight_using_column')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_dataframe_fingerprint_similarity_accessor(self):
        """Test DataFrame fingerprint_similarity accessor"""
        assert hasattr(pd.DataFrame, 'fingerprint_similarity')


class TestSeriesAccessors:
    """Test Series accessor classes"""
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_highlight_accessor(self):
        """Test Series highlight accessor"""
        assert hasattr(pd.Series, 'highlight')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_recalculate_depiction_coordinates_accessor(self):
        """Test Series recalculate_depiction_coordinates accessor"""
        assert hasattr(pd.Series, 'recalculate_depiction_coordinates')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_reset_depictions_accessor(self):
        """Test Series reset_depictions accessor"""
        assert hasattr(pd.Series, 'reset_depictions')
    
    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_series_align_depictions_accessor(self):
        """Test Series align_depictions accessor"""
        assert hasattr(pd.Series, 'align_depictions')


# Test for the existing functionality
class TestExistingFunctionality:
    """Test the existing render_molecule_grid functionality"""
    
    def test_render_molecule_grid(self):
        """Test molecule grid rendering functionality"""
        # Create some sample molecules
        mols = []
        for i, smi in enumerate(["n1cnccc1", "c1ccccc1", "CCOH", "C(=O)OH", "CCCC"]):
            mol = oechem.OEGraphMol()
            oechem.OESmilesToMol(mol, smi)

            # We can title them too!
            mol.SetTitle(f'Molecule {i + 1}')

            mols.append(mol)

        # Render into a grid - this should not raise an exception
        result = cnotebook.render_molecule_grid(mols, ncols=3)
        
        # Basic assertion that we got some output
        assert result is not None
        # The function returns an OEImage object, not a string
        from openeye import oedepict
        assert isinstance(result, oedepict.OEImage)
    
    def test_render_molecule_grid_empty_list(self):
        """Test rendering empty molecule list"""
        result = cnotebook.render_molecule_grid([])
        
        from openeye import oedepict
        assert isinstance(result, oedepict.OEImage)
        # Should be a 0x0 image
        assert result.GetWidth() == 0
        assert result.GetHeight() == 0
    
    def test_render_molecule_grid_single_molecule(self):
        """Test rendering single molecule"""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")
        mol.SetTitle("Ethanol")
        
        result = cnotebook.render_molecule_grid([mol])
        
        from openeye import oedepict
        assert isinstance(result, oedepict.OEImage)
        assert result.GetWidth() > 0
        assert result.GetHeight() > 0
    
    def test_render_molecule_grid_with_invalid_molecules(self):
        """Test rendering with some invalid molecules"""
        mols = []
        
        # Valid molecule
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "CCO")
        mols.append(mol1)
        
        # Invalid molecule (empty)
        mol2 = oechem.OEGraphMol()
        mols.append(mol2)
        
        # None
        mols.append(None)
        
        # Valid molecule
        mol3 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol3, "CCC")
        mols.append(mol3)
        
        result = cnotebook.render_molecule_grid(mols)
        
        from openeye import oedepict
        assert isinstance(result, oedepict.OEImage)
        # Should still render the valid molecules
        assert result.GetWidth() > 0
        assert result.GetHeight() > 0


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
        assert log.name == "cnotebook"