import gc
import io
import threading
from html import escape
from pathlib import PurePosixPath
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from openeye import oechem, oedepict

import cnotebook.pandas_ext as pe
from cnotebook.context import CNotebookContext
from cnotebook.core.columnops import AlignmentReport, ColorBondByOverlapScore
from cnotebook.core.errors import CNotebookWarning
from cnotebook.pandas_ext import (
    SMARTS_DELIMITER_RE,
    PandasFrameAdapter,
    create_disp_formatter,
    create_mol_formatter,
    escape_formatter,
    ipython_present,
    register_pandas_formatters,
    render_dataframe,
)

# Try to import oepandas - might not be available in all environments
try:
    import oepandas as oepd
    oepandas_available = True
except ImportError:
    oepandas_available = False

try:
    from openeye import oeomega
    oeomega_available = True
except ImportError:
    oeomega_available = False


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

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_render_dataframe_with_query_dtype(self):
        """QueryDtype columns should use the molecule depiction formatter."""
        if not hasattr(oepd, "QueryDtype"):
            pytest.skip("oepandas QueryDtype not available")

        query = oechem.OEQMol()
        assert oechem.OEParseSmarts(query, "[#6]")

        df = pd.DataFrame({
            "query": pd.Series([query], dtype=oepd.QueryDtype()),
        })

        with patch("cnotebook.core.formatters.make_depiction") as mock_depict:
            mock_depict.return_value.to_html.return_value = "<img>query</img>"
            result = render_dataframe(df)

        assert "<img>query</img>" in result
        mock_depict.assert_called_once()
        assert isinstance(mock_depict.call_args.args[0], oechem.OEQMol)
    
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

        with patch('cnotebook.core.formatters.oechem.OECount', return_value=10), \
             patch('cnotebook.core.formatters.make_depiction') as mock_depict:
            mock_depict.return_value.to_html.return_value = '<img>valid_mol</img>'

            formatter = create_mol_formatter(ctx=ctx)
            result = formatter(mock_mol)

            assert result == '<img>valid_mol</img>'
            mock_depict.assert_called_once_with(mock_mol, ctx=ctx, apply_callbacks=False)
            mock_depict.return_value.to_html.assert_called_once_with(ctx)
    
    def test_create_mol_formatter_empty_molecule(self):
        """Test formatter with empty molecule"""
        ctx = CNotebookContext()
        
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = False
        mock_mol.NumAtoms.return_value = 0
        
        with patch('cnotebook.core.formatters.render_empty_molecule') as mock_render_empty:
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
        
        with patch('cnotebook.core.formatters.render_invalid_molecule') as mock_render_invalid:
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
        """Test formatter with context callbacks (callbacks applied by make_depiction)"""
        ctx = CNotebookContext()
        callback_invocations = []

        def test_callback(disp):
            callback_invocations.append(disp)

        ctx.add_callback(test_callback)

        # Use a real molecule instead of a mock
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        formatter = create_mol_formatter(ctx=ctx)
        result = formatter(mol)

        # Callback should have been called (by make_depiction in the render path)
        assert len(callback_invocations) == 1
        assert isinstance(callback_invocations[0], oedepict.OE2DMolDisplay)
        assert '<img' in result or '<div' in result


class TestCreateDispFormatter:
    """Test the create_disp_formatter function"""
    
    def test_create_disp_formatter_valid_display(self):
        """Test formatter with valid display object"""
        ctx = CNotebookContext()
        
        formatter = create_disp_formatter(ctx=ctx)
        
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

        assert result == escape_formatter(mock_disp)
    
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
        assert result == "&lt;script&gt;alert(&#x27;test&#x27;)&lt;/script&gt;"
    
    def test_escape_formatter_non_string(self):
        """Test with non-string object"""
        result = escape_formatter(42)
        assert result == "42"
    
    def test_escape_formatter_none(self):
        """Test with None"""
        result = escape_formatter(None)
        assert result == ""


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
        import warnings

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})

        # Should not raise (may warn if default style incompatible with single color)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", CNotebookWarning)
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


class TestPandasDataFrameRenderOptions:
    """Test DataFrame set_render_options method."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_specific_column(self):
        """DataFrame render options should update a requested molecule column."""
        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "CCO")

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "name": ["ethanol"],
        })

        result = df.chem.set_render_options(
            "mol",
            structure_scale=1.5,
            auto_scale=True,
            width=0,
            height=0,
        )

        ctx = df["mol"].array.metadata.get("cnotebook")
        assert result is None
        assert ctx is not None
        assert ctx.structure_scale == 1.5
        assert ctx.auto_scale is True
        assert ctx.width == 0
        assert ctx.height == 0

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_all_depictable_columns(self):
        """No column argument should update all MoleculeDtype and QueryDtype columns."""
        if not hasattr(oepd, "QueryDtype"):
            pytest.skip("oepandas QueryDtype not available")

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "CCO")
        query = oechem.OEQMol()
        assert oechem.OEParseSmarts(query, "[#6]")

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "query": pd.Series([query], dtype=oepd.QueryDtype()),
            "name": ["ethanol"],
        })

        df.chem.set_render_options(structure_scale=1.5)

        mol_ctx = df["mol"].array.metadata.get("cnotebook")
        query_ctx = df["query"].array.metadata.get("cnotebook")
        assert mol_ctx is not None
        assert query_ctx is not None
        assert mol_ctx.structure_scale == 1.5
        assert query_ctx.structure_scale == 1.5

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_rejects_non_molecule_column(self):
        """Explicit non-molecule columns should raise TypeError."""
        df = pd.DataFrame({"name": ["ethanol"]})

        with pytest.raises(TypeError, match="set_render_options only works on molecule columns"):
            df.chem.set_render_options("name", structure_scale=1.5)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_requires_existing_column(self):
        """Missing requested columns should warn and skip."""
        df = pd.DataFrame({"name": ["ethanol"]})

        with pytest.warns(CNotebookWarning, match="mol.*not found"):
            df.chem.set_render_options("mol", structure_scale=1.5)


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
        _ = render_dataframe(df)

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

        with pytest.raises(TypeError, match="highlight patterns must be SMARTS strings"):
            series.chem.highlight([123])

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_unknown_type_raises(self):
        """Highlight with an unsupported pattern type should raise TypeError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with pytest.raises(TypeError, match="highlight patterns must be SMARTS strings"):
            series.chem.highlight(123)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_non_molecule_dtype_raises(self):
        """Highlight on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="column operation only works on molecule columns"):
            series.chem.highlight("c1ccccc1")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_with_ref_runs_alignment(self):
        """Passing ref= should add a highlight and invoke the alignment path."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol2)

        series = pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())

        aligner = MagicMock(return_value=True)
        with patch('cnotebook.core.columnops.create_aligner', return_value=aligner) as mock_create_aligner:
            series.chem.highlight("c1ccccc1", ref="first")

        mock_create_aligner.assert_called_once()
        assert isinstance(mock_create_aligner.call_args.args[0], oechem.OEMolBase)
        assert aligner.call_count == 2
        ctx = series.array.metadata.get("cnotebook")
        assert ctx is not None
        assert len(ctx.callbacks) == 1

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_highlight_query_dtype_adds_callback(self):
        """QueryDtype series should share molecule depiction callbacks."""
        if not hasattr(oepd, "QueryDtype"):
            pytest.skip("oepandas QueryDtype not available")

        query = oechem.OEQMol()
        assert oechem.OEParseSmarts(query, "[#6]")

        series = pd.Series([query], dtype=oepd.QueryDtype())
        series.chem.highlight("[#6]")

        ctx = series.array.metadata.get("cnotebook")
        assert ctx is not None
        assert len(ctx.callbacks) == 1


class TestSeriesRenderOptions:
    """Test set_render_options() on Series .chem accessor."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_updates_molecule_context(self):
        """Series render options should be saved in the column CNotebook context."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())
        result = series.chem.set_render_options(
            structure_scale=1.5,
            image_format="svg",
            max_heavy_atoms=None,
            title=False,
        )

        ctx = series.array.metadata.get("cnotebook")
        assert result is None
        assert ctx is not None
        assert ctx.structure_scale == 1.5
        assert ctx.image_format == "svg"
        assert ctx.max_heavy_atoms is None
        assert ctx.title is False

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_preserves_existing_callbacks(self):
        """Updating render options should not remove highlight callbacks."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())
        series.chem.highlight("c1ccccc1")
        original_ctx = series.array.metadata["cnotebook"]

        series.chem.set_render_options(width=321)

        ctx = series.array.metadata["cnotebook"]
        assert ctx is not original_ctx  # set_render_options replaces the context atomically
        assert len(ctx.callbacks) == len(original_ctx.callbacks)  # but preserves callbacks
        assert ctx.width == 321
        assert len(ctx.callbacks) == 1

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_updates_query_context(self):
        """QueryDtype series should support the same render options."""
        if not hasattr(oepd, "QueryDtype"):
            pytest.skip("oepandas QueryDtype not available")

        query = oechem.OEQMol()
        assert oechem.OEParseSmarts(query, "[#6]")

        series = pd.Series([query], dtype=oepd.QueryDtype())
        series.chem.set_render_options(structure_scale=1.5)

        ctx = series.array.metadata.get("cnotebook")
        assert ctx is not None
        assert ctx.structure_scale == 1.5

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_set_render_options_non_molecule_raises(self):
        """Non-molecule-like Series should reject render options."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="column operation only works on molecule columns"):
            series.chem.set_render_options(structure_scale=1.5)


class TestSeriesAlignDepictions:
    """Test _series_align_depictions() method on Series .chem accessor."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_first(self):
        """Align with ref='first' should build an aligner from the first valid molecule."""
        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol2, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol2)

        series = pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())

        aligner = MagicMock(return_value=True)
        with patch('cnotebook.core.columnops.create_aligner', return_value=aligner) as mock_create_aligner:
            series.chem.align_depictions(ref="first")

        mock_create_aligner.assert_called_once()
        assert isinstance(mock_create_aligner.call_args.args[0], oechem.OEMolBase)
        assert aligner.call_count == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_first_no_valid_mols(self):
        """Align with ref='first' when all mols are None should log warning and return."""
        series = pd.Series([None, None], dtype=oepd.MoleculeDtype())

        with pytest.warns(CNotebookWarning, match="No valid molecule found"):
            series.chem.align_depictions(ref="first")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_ref_molecule(self):
        """Align with a real OEMolBase reference should pass that molecule to create_aligner."""
        ref_mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref_mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(ref_mol)

        mol1 = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol1, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol1)

        series = pd.Series([mol1], dtype=oepd.MoleculeDtype())

        aligner = MagicMock(return_value=True)
        with patch('cnotebook.core.columnops.create_aligner', return_value=aligner) as mock_create_aligner:
            series.chem.align_depictions(ref=ref_mol)

        mock_create_aligner.assert_called_once_with(ref_mol, method=None)
        aligner.assert_called_once()
        assert isinstance(aligner.call_args.args[0], oechem.OEMolBase)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_non_molecule_raises(self):
        """Align on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="column operation only works on molecule columns"):
            series.chem.align_depictions(ref="first")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_align_exception_handled(self):
        """If create_aligner raises, align_depictions should propagate the exception."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with (
            patch('cnotebook.core.columnops.create_aligner', side_effect=RuntimeError("boom")),
            pytest.raises(RuntimeError, match="boom")
        ):
            series.chem.align_depictions(ref=mol)


class TestSeriesRecalculateDepictions:
    """Test _series_recalculate_depiction_coordinates() method."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_basic(self):
        """Recalculate depictions should call OpenEye depiction preparation for molecules."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        series = pd.Series([mol], dtype=oepd.MoleculeDtype())

        with patch('cnotebook.pandas_ext.oedepict.OEPrepareDepiction') as mock_prepare:
            series.chem.recalculate_depiction_coordinates()

        mock_prepare.assert_called_once()
        assert isinstance(mock_prepare.call_args.args[0], oechem.OEMolBase)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_non_molecule_raises(self):
        """Recalculate on a non-MoleculeDtype series should raise TypeError."""
        series = pd.Series(["abc", "def"], dtype=pd.StringDtype())

        with pytest.raises(TypeError, match="column operation only works on molecule columns"):
            series.chem.recalculate_depiction_coordinates()


class TestSeriesResetAndClear:
    """Test _series_reset_depictions() and _series_clear_formatting_rules()."""

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_reset_depictions_clears_metadata(self):
        """reset_depictions should remove the 'cnotebook' key from metadata."""
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

        df.chem.recalculate_depiction_coordinates()
        assert df["mol1"][0].GetDimension() == 2
        assert df["mol2"][0].GetDimension() == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_string_column(self):
        """Pass a single column name as string."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.chem.recalculate_depiction_coordinates(molecule_columns="mol1")
        assert df["mol1"][0].GetDimension() == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_list_column(self):
        """Pass a list of column names."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        df.chem.recalculate_depiction_coordinates(molecule_columns=["mol1"])
        assert df["mol1"][0].GetDimension() == 2

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_non_molecule_raises(self):
        """Specifying a non-molecule column should raise TypeError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
            "name": ["benzene"],
        })

        with pytest.raises(TypeError, match="only works on molecule columns"):
            df.chem.recalculate_depiction_coordinates(molecule_columns="name")

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_recalculate_missing_column_warns(self):
        """Specifying a missing column warns."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pd.DataFrame({
            "mol1": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        with pytest.warns(CNotebookWarning, match="nonexistent.*not found") as caught:
            df.chem.recalculate_depiction_coordinates(molecule_columns=["nonexistent"])
        # The warning is the caller's problem, so it must be blamed on the caller's line
        assert caught[0].filename == __file__


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

        result = df.chem.highlight_using_column(
            "mol", "pattern",
            color=oechem.OEColor(oechem.OERed),
            style="overlay_default"
        )

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

        with pytest.warns(CNotebookWarning, match="Fingerprint overlap was empty"):
            result = df.chem.fingerprint_similarity("mol")
        assert len(result) == 2
        # First molecule is the reference, so its tanimoto should be 1.0
        assert result["fingerprint_tanimoto"].iloc[0] == pytest.approx(1.0)

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_no_valid_mols(self):
        """All None molecules handled gracefully; creates columns with all None/NaN."""
        df = pd.DataFrame({
            "mol": pd.Series([None, None], dtype=oepd.MoleculeDtype()),
        })

        with pytest.warns(CNotebookWarning, match="No valid reference"):
            result = df.chem.fingerprint_similarity("mol")

        assert "fingerprint_tanimoto" in result.columns
        assert all(pd.isna(result["fingerprint_tanimoto"]))
        assert all(r is None for r in result["reference_similarity"])
        assert all(t is None for t in result["target_similarity"])

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_invalid_ref(self):
        """Invalid reference molecule should log warning and create columns with None/NaN."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        df = pd.DataFrame({
            "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        })

        invalid_ref = oechem.OEGraphMol()  # Empty mol, IsValid() returns False

        with pytest.warns(CNotebookWarning, match="not valid"):
            result = df.chem.fingerprint_similarity("mol", ref=invalid_ref)

        assert "fingerprint_tanimoto" in result.columns
        assert all(pd.isna(result["fingerprint_tanimoto"]))
        assert all(r is None for r in result["reference_similarity"])
        assert all(t is None for t in result["target_similarity"])

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

    @pytest.mark.skipif(not oepandas_available, reason="oepandas not available")
    def test_fingerprint_similarity_with_duplicate_output_raises(self):
        """fingerprint_similarity should raise ValueError if any output column is duplicated."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        # Create DataFrame with duplicate column labels
        df = pd.DataFrame(
            [[mol, 1, 2]],
            columns=["mol", "out", "out"]
        )
        df["mol"] = df["mol"].astype(oepd.MoleculeDtype())

        # Capture frame state
        original_columns = list(df.columns)
        original_dtypes = list(df.dtypes)

        with pytest.raises(ValueError, match="column label 'out' is not unique"):
            df.chem.fingerprint_similarity("mol", tanimoto_column="out")

        # Frame should be unchanged (no depiction work done)
        assert list(df.columns) == original_columns
        assert list(df.dtypes) == original_dtypes



def test_highlight_using_column_overlay_produces_different_svg():
    """Test that overlay highlighting actually modifies the rendered output."""
    import pandas as pd
    from openeye import oechem, oedepict

    from cnotebook.core.context import CNotebookContext
    from cnotebook.core.render import oedisp_to_html
    
    # Create a simple molecule
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")  # phenol
    oedepict.OEPrepareDepiction(mol)
    
    df = pd.DataFrame({
        "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        "pattern": ["c1ccccc1"]  # benzene ring
    })
    
    # Create highlighted version
    df_highlighted = df.chem.highlight_using_column(
        "mol", "pattern",
        highlighted_column="highlighted",
        style="overlay_default"
    )
    
    # Render both to SVG
    ctx = CNotebookContext(image_format="svg")
    from cnotebook.core.render import oemol_to_disp
    unhighlighted_disp = oemol_to_disp(mol, ctx=ctx)
    unhighlighted_svg = oedisp_to_html(unhighlighted_disp, ctx=ctx)
    
    highlighted_disp = df_highlighted["highlighted"].iloc[0]
    highlighted_svg = oedisp_to_html(highlighted_disp, ctx=ctx)
    
    # The SVGs should be different
    assert unhighlighted_svg != highlighted_svg
    assert "svg" in unhighlighted_svg.lower()
    assert "svg" in highlighted_svg.lower()


def test_highlight_using_column_traditional_produces_different_svg():
    """Test that traditional highlighting actually modifies the rendered output."""
    import pandas as pd
    from openeye import oechem, oedepict

    from cnotebook.core.context import CNotebookContext
    from cnotebook.core.render import oedisp_to_html, oemol_to_disp
    
    # Create a simple molecule
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")  # phenol
    oedepict.OEPrepareDepiction(mol)
    
    df = pd.DataFrame({
        "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        "pattern": ["c1ccccc1"]  # benzene ring
    })
    
    # Create highlighted version
    df_highlighted = df.chem.highlight_using_column(
        "mol", "pattern",
        highlighted_column="highlighted",
        color=oechem.OEColor(oechem.OEPink),
        style=oedepict.OEHighlightStyle_BallAndStick
    )
    
    # Render both to SVG
    ctx = CNotebookContext(image_format="svg")
    unhighlighted_disp = oemol_to_disp(mol, ctx=ctx)
    unhighlighted_svg = oedisp_to_html(unhighlighted_disp, ctx=ctx)
    
    highlighted_disp = df_highlighted["highlighted"].iloc[0]
    highlighted_svg = oedisp_to_html(highlighted_disp, ctx=ctx)
    
    # The SVGs should be different
    assert unhighlighted_svg != highlighted_svg
    assert "svg" in unhighlighted_svg.lower()
    assert "svg" in highlighted_svg.lower()


def test_pandas_honors_column_context_dpr():
    """Regression test for Finding 1: pandas must honor column-specific device_pixel_ratio."""
    import base64
    import re
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    
    # Create a series with DPR 1.0
    series = pd.Series([mol], dtype=oepd.MoleculeDtype())
    series.chem.set_render_options(device_pixel_ratio=1.0, image_format="png", width=100, height=100)

    # Render the DataFrame with implicit rendering (ctx=None)
    df = pd.DataFrame({"mol": series})
    html = render_dataframe(df)

    # Extract PNG size from the rendered HTML
    match = re.search(r"base64,([^']+)'", html)
    assert match is not None
    data = base64.b64decode(match.group(1))
    width_px = int.from_bytes(data[16:20], "big")

    # Column context (DPR 1.0) should be used in implicit rendering
    # PNG should be ~100px (OpenEye may round slightly)
    assert 100 <= width_px <= 105


def test_pandas_explicit_context_beats_column_context():
    """Explicit ctx parameter should override column context (Finding A)."""
    import base64
    import re
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    
    # Create a series with DPR 2.0 in column metadata
    series = pd.Series([mol], dtype=oepd.MoleculeDtype())
    series.chem.set_render_options(device_pixel_ratio=2.0, image_format="png", width=100, height=100)
    
    # Render with explicit context at DPR 1.0 (should win)
    df = pd.DataFrame({"mol": series})
    from cnotebook.context import CNotebookContext
    explicit_ctx = CNotebookContext(device_pixel_ratio=1.0)
    html = render_dataframe(df, ctx=explicit_ctx)
    
    # Extract PNG size
    match = re.search(r"base64,([^']+)'", html)
    assert match is not None
    data = base64.b64decode(match.group(1))
    width_px = int.from_bytes(data[16:20], "big")
    
    # Explicit context (DPR 1.0) should win, so PNG should be ~100px (not 200px from column DPR 2.0)
    assert width_px < 150  # Should be close to 100, not 200


########################################################################################################################
# Frame rendering through pandas' own HTML writer
########################################################################################################################


def _mols(n, smiles="c1ccccc1O"):
    out = []
    for i in range(n):
        m = oechem.OEGraphMol()
        oechem.OESmilesToMol(m, smiles)
        m.SetTitle(f"m{i}")
        out.append(m)
    return out


def _frame(n=3, **extra):
    data = {"mol": pd.Series(_mols(n), dtype=oepd.MoleculeDtype())}
    data.update(extra)
    return pd.DataFrame(data)


def test_render_dataframe_truncates_like_pandas():
    df = pd.DataFrame({"a": range(5000)})
    html = render_dataframe(df)
    assert html.count("<tr") == pd.DataFrame({"a": range(5000)})._repr_html_().count("<tr")
    assert render_dataframe(df, max_rows=0).count("<tr") == 5001
    assert render_dataframe(df, max_rows=4).count("<tr") == 1 + 4 + 1


def test_render_dataframe_copies_only_window(monkeypatch):
    df = _frame(200)
    calls = []
    import cnotebook.pandas_ext as pe

    original = pe.cell_html

    def counting(kind, value, ctx):
        calls.append(1)
        return original(kind, value, ctx)

    monkeypatch.setattr(pe, "cell_html", counting)
    with pd.option_context("display.max_rows", 20, "display.min_rows", 10):
        render_dataframe(df)
    assert len(calls) == 10


def test_column_render_options_affect_html():
    df = _frame(1)
    df["mol"].chem.set_render_options(image_format="svg", width=123)
    html = render_dataframe(df)
    assert "<svg" in html and "min-width: 123px" in html
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0)
    assert "data:image/png" in render_dataframe(df, ctx=ctx)


def test_render_dataframe_does_not_mutate_caller_dicts():
    df = _frame(1, x=[1])
    formatters = {"x": lambda v: f"[{v}]"}
    col_space = {"x": 50}
    html = render_dataframe(df, formatters=formatters, col_space=col_space)
    assert formatters == {"x": formatters["x"]} and list(formatters) == ["x"] and col_space == {"x": 50}
    assert "[1]" in html


def test_render_dataframe_does_not_mutate_frame_or_molecules():
    df = _frame(1)
    array_before = df["mol"].array
    mol_before = df["mol"][0]
    coords_before = oechem.OEFloatArray(mol_before.GetMaxAtomIdx() * 3)
    mol_before.GetCoords(coords_before)

    render_dataframe(df)

    assert df["mol"].array is array_before and df["mol"][0] is mol_before
    coords_after = oechem.OEFloatArray(mol_before.GetMaxAtomIdx() * 3)
    mol_before.GetCoords(coords_after)
    assert list(coords_after) == list(coords_before)


def test_render_dataframe_ignores_escape_kwarg_with_warning():
    df = _frame(1, s=["a&b"])
    with pytest.warns(CNotebookWarning, match="escape"):
        html = render_dataframe(df, escape=False)
    assert "a&amp;b" in html


def test_other_cells_escaped():
    df = _frame(1, s=["a&b<c"], f=[1 / 3])
    html = render_dataframe(df)
    assert "a&amp;b&lt;c" in html and "0.333333" in html and "0.3333333333" not in html


def test_all_none_display_column_renders():
    df = pd.DataFrame({"d": pd.Series([None, None], dtype=oepd.DisplayDtype())})
    html = render_dataframe(df)
    assert html.count("<tr") == 3


def test_token_like_values_survive_in_ordinary_cells():
    df = _frame(1, note=["@@CN-0000000000000000-1@@"], **{"@@CN-x@@": ["h"]})
    df.index = ["@@CN-idx@@"]
    html = render_dataframe(df)
    assert html.count("@@CN-0000000000000000-1@@") == 1 and "@@CN-x@@" in html and "@@CN-idx@@" in html


def test_render_dataframe_survives_a_small_display_max_colwidth():
    """Cell tokens are longer than a narrow ``display.max_colwidth``; pandas must not trim them."""
    df = _frame(1)
    with pd.option_context("display.max_colwidth", 4):
        html = render_dataframe(df)
    assert "data:image/png" in html and "@@CN-" not in html


def test_render_dataframe_survives_a_small_display_max_colwidth_in_notebook_mode():
    """NotebookFormatter does not lift the width limit itself, so render_dataframe must."""
    df = _frame(2)
    with pd.option_context("display.max_colwidth", 4):
        html = render_dataframe(df, notebook=True)
    assert html.count("data:image/png") == 2 and "@@CN-" not in html


def test_caller_col_space_strings_are_escaped():
    payload = '1px;"><script>alert(1)</script><th x="'
    df = pd.DataFrame({"a": [1]})
    html = render_dataframe(df, col_space={"a": payload})
    assert "<script>alert(1)</script>" not in html
    assert f'min-width: {escape(payload, quote=True)};' in html
    assert "min-width: 150px" in render_dataframe(df, col_space={"a": "150px"})


def test_caller_formatter_output_is_escaped():
    df = pd.DataFrame({"a": [1]})
    html = render_dataframe(df, formatters={"a": lambda v: "<b>b</b>"})
    assert "&lt;b&gt;" in html and "<b>b</b>" not in html


def test_columns_kwarg_selects_columns():
    df = _frame(1, keep=["k"], drop=["d"])
    for columns in (["mol", "keep"], ("mol", "keep")):
        html = render_dataframe(df, columns=columns)
        assert ">keep<" in html and ">drop<" not in html and "data:image/png" in html


def test_buf_kwarg_is_rejected():
    buf = io.StringIO()
    with pytest.raises(TypeError, match="buf is not supported"):
        render_dataframe(_frame(1), buf=buf)
    assert buf.getvalue() == ""
    # buf=None is Pandas' own default and asks for the HTML back, so it is accepted.
    assert "<table" in render_dataframe(_frame(1), buf=None)


class _InvalidMolecule(oechem.OEGraphMol):
    """A molecule with atoms that reports itself invalid; OEChem parses even broken SMILES into valid mols."""

    def IsValid(self):
        return False


def test_none_and_invalid_molecule_cells():
    invalid = _InvalidMolecule()
    oechem.OESmilesToMol(invalid, "CCO")
    mols = [None, oechem.OEGraphMol(), invalid, *_mols(1)]
    df = pd.DataFrame({"mol": pd.Series(mols, dtype=oepd.MoleculeDtype())})
    html = render_dataframe(df, ctx=CNotebookContext(image_format="svg"))
    assert "Empty Molecule" in html and "Invalid Molecule" in html and html.count("<tr") == 5
    assert html.count("<td></td>") == 1 and ">None<" not in html


def test_frame_adapter_classification():
    df = _frame(1, x=[1])
    adapter = PandasFrameAdapter(df)
    assert [k.name for k in (adapter.kind(0), adapter.kind(1))] == ["MOLECULE", "OTHER"]
    assert adapter.columns() == ["mol", "x"]


def test_frame_adapter_rows_and_window():
    df = _frame(2, x=["a", "b"])
    df.index = ["first", "second"]
    adapter = PandasFrameAdapter(df)
    assert adapter.nrows() == 2 and adapter.index_text(1) == "second"
    assert adapter.other_cell_text(0, 1) == "a" and adapter.cell(0, 0) is df["mol"].iloc[0]
    assert adapter.header_extra_rows() == []

    full = adapter.window(None)
    assert (full.head, full.tail, full.truncated) == ([0, 1], [], False)
    truncated = PandasFrameAdapter(_frame(5)).window(3)
    assert (truncated.head, truncated.tail, truncated.total) == ([0, 1], [4], 5)


def test_duplicate_column_labels_keep_their_own_kinds_and_contexts():
    left = pd.DataFrame({"mol": pd.Series(_mols(1), dtype=oepd.MoleculeDtype())})
    right = pd.DataFrame({"mol": ["plain text"]})
    df = pd.concat([left, right], axis=1)  # two columns labelled "mol": one molecule, one text
    html = render_dataframe(df)
    assert html.count("<img") + html.count("<svg") == 1 and "plain text" in html
    both = pd.concat([left, left.copy()], axis=1)
    both.iloc[:, 0].array.metadata["cnotebook"] = CNotebookContext(image_format="svg")
    both.iloc[:, 1].array.metadata["cnotebook"] = CNotebookContext(image_format="png", device_pixel_ratio=1.0)
    html = render_dataframe(both)
    assert "<svg" in html and "data:image/png" in html


def test_render_links_kwarg_is_rejected_with_warning():
    """pandas writes the unescaped cell text into the href of a linkified cell."""
    df = pd.DataFrame({"u": ['https://example.com/"><img src=x onerror=alert(1)>']})
    with pytest.warns(CNotebookWarning, match="render_links"):
        html = render_dataframe(df, render_links=True)
    assert "<a " not in html and "<img" not in html
    assert "&lt;img src=x onerror=alert(1)&gt;" in html


def test_attribute_valued_kwargs_are_escaped():
    payload = '"><script>alert(1)</script><table x="'
    escaped = escape(payload, quote=True)
    df = pd.DataFrame({"a": [1]})
    html = render_dataframe(df, table_id=payload, classes=payload, border=payload)
    table_tag = html[html.index("<table"):html.index(">", html.index("<table")) + 1]

    assert "<script>" not in html
    assert f' id="{escaped}"' in table_tag and f' border="{escaped}"' in table_tag
    assert table_tag.split('class="')[1].split('"')[0] == f"dataframe {escaped}"

    from_list = render_dataframe(df, classes=[payload, "safe"])
    assert "<script>" not in from_list
    assert f'class="dataframe {escaped} safe"' in from_list

    # pandas checks justify against a fixed list, so no payload of any shape reaches the writer.
    with pytest.raises(ValueError, match="justify"):
        render_dataframe(df, justify=payload)


def test_attribute_valued_kwargs_keep_legitimate_values():
    df = pd.DataFrame({"a": [1]})
    html = render_dataframe(df, table_id="t1", classes=["a", "b"], border=1, justify="left")
    assert ' id="t1"' in html and ' border="1"' in html
    assert 'class="dataframe a b"' in html and '<tr style="text-align: left;">' in html
    # pandas drops the attribute for a falsy border rather than writing border="0".
    assert "border=" not in render_dataframe(df, border=0)


def test_notebook_max_colwidth_guard_is_serialised(monkeypatch):
    """The notebook writer needs the process-global width option lifted, so renders take turns."""
    recorded = []
    entered = threading.Event()
    release = threading.Event()
    original = pd.DataFrame.to_html

    def blocking_to_html(self, *args, **kwargs):
        recorded.append(pd.get_option("display.max_colwidth"))
        if not entered.is_set():
            entered.set()
            release.wait(10)
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_html", blocking_to_html)

    frames = {"first": _frame(1), "second": _frame(1)}
    outputs = {}

    def render(key):
        outputs[key] = render_dataframe(frames[key], notebook=True)

    with pd.option_context("display.max_colwidth", 4):
        first = threading.Thread(target=render, args=("first",))
        second = threading.Thread(target=render, args=("second",))
        first.start()
        assert entered.wait(10), "the first render never reached to_html"
        second.start()
        second.join(0.2)
        blocked = second.is_alive()
        release.set()
        first.join(10)
        second.join(10)
        assert blocked, "the second notebook render was not serialised behind the first"
        assert pd.get_option("display.max_colwidth") == 4

    assert set(outputs) == {"first", "second"}
    assert recorded == [None, None]
    assert all("@@CN-" not in out for out in outputs.values())


def test_notebook_mode_does_not_truncate_ordinary_strings():
    """Cell tokens cannot survive truncation, so no cell is truncated under either writer."""
    text = "x" * 80
    df = pd.DataFrame({"a": [text]})
    with pd.option_context("display.max_colwidth", 4):
        html = render_dataframe(df, notebook=True)
    assert text in html


def test_none_cells_render_empty_for_every_depiction_kind():
    df = pd.DataFrame({
        "mol": pd.Series([None], dtype=oepd.MoleculeDtype()),
        "disp": pd.Series([None], dtype=oepd.DisplayDtype()),
        "du": pd.Series([None], dtype=oepd.DesignUnitDtype()),
    })
    html = render_dataframe(df)
    assert html.count("<td></td>") == 3 and "None" not in html


def test_render_dataframe_leaves_none_cells_in_the_caller_frame():
    mols = _mols(1)
    df = pd.DataFrame({"mol": pd.Series([None, *mols], dtype=oepd.MoleculeDtype()), "x": [1, 2]})
    dtypes_before = list(df.dtypes)

    render_dataframe(df)

    assert list(df.dtypes) == dtypes_before
    assert df["mol"].iloc[0] is None and df["mol"].iloc[1] is mols[0]
    assert list(df["x"]) == [1, 2]


def test_none_cells_in_the_head_and_tail_of_a_truncated_frame():
    df = pd.DataFrame({"mol": pd.Series([None, *_mols(3), None], dtype=oepd.MoleculeDtype())})
    html = render_dataframe(df, max_rows=4)
    assert html.count("<td></td>") == 2 and ">None<" not in html


def test_duplicate_labels_with_a_none_cell():
    left = pd.DataFrame({"mol": pd.Series([None], dtype=oepd.MoleculeDtype())})
    right = pd.DataFrame({"mol": pd.Series(_mols(1), dtype=oepd.MoleculeDtype())})
    df = pd.concat([left, right], axis=1)
    html = render_dataframe(df)
    assert html.count("<td></td>") == 1 and html.count("<img") == 1 and ">None<" not in html


def _omega(smiles="CCO"):
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, smiles)
    oechem.OEAddExplicitHydrogens(mol)
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    assert omega(mol)
    return mol


def test_dataframe_recalculate_depiction_coordinates_works():
    df = _frame(2)
    df.chem.recalculate_depiction_coordinates()
    assert all(m.GetDimension() == 2 for m in df["mol"])
    with pytest.warns(CNotebookWarning, match="missing"):
        df.chem.recalculate_depiction_coordinates(molecule_columns=["missing"])


@pytest.mark.skipif(not oeomega_available, reason="oeomega not available")
def test_align_depictions_skips_none_and_forwards_kwargs(monkeypatch):
    seen = {}
    real = pe.columnops.create_aligner

    def spy(ref, method=None, **kwargs):
        seen.update(kwargs)
        return real(ref, method=method, **kwargs)

    monkeypatch.setattr(pe.columnops, "create_aligner", spy)
    series = pd.Series([*_mols(1), None, *_mols(2)], dtype=oepd.MoleculeDtype())
    report = series.chem.align_depictions(ref="first", threshold=0.1, fptype="circular")
    assert isinstance(report, AlignmentReport) and report.skipped_none == 1 and report.aligned == 3
    assert seen == {"threshold": 0.1, "fptype": "circular"}
    assert series.chem.alignment_report is report
    assert [m.GetDimension() if m is not None else None for m in series] == [2, None, 2, 2]


@pytest.mark.skipif(not oeomega_available, reason="oeomega not available")
def test_align_depictions_does_not_touch_caller_molecules():
    mol3d = _omega()
    df = pd.DataFrame({"mol": pd.Series([mol3d], dtype=oepd.MoleculeDtype())})
    df["mol"].chem.align_depictions("first")
    assert mol3d.GetDimension() == 3 and df["mol"][0].GetDimension() == 2


def test_fingerprint_similarity_with_none_rows():
    df = pd.DataFrame({"mol": pd.Series([*_mols(1), None, *_mols(1, "c1ccccc1OC")], dtype=oepd.MoleculeDtype())})
    out = df.chem.fingerprint_similarity("mol")
    assert list(out.columns) == ["mol", "fingerprint_tanimoto", "reference_similarity", "target_similarity"]
    assert pd.isna(out["fingerprint_tanimoto"][1]) and out["target_similarity"][1] is None
    assert out["fingerprint_tanimoto"][0] == pytest.approx(1.0)
    out2 = pd.DataFrame({"mol": pd.Series([None, *_mols(1)], dtype=oepd.MoleculeDtype())}).chem.fingerprint_similarity("mol")
    assert out2["fingerprint_tanimoto"][1] == pytest.approx(1.0)


def test_highlight_using_column_renders_after_source_dropped():
    df = pd.DataFrame({"mol": pd.Series(_mols(2), dtype=oepd.MoleculeDtype()), "pat": ["c1ccccc1", "[OH]"]})
    out = df.chem.highlight_using_column("mol", "pat").drop(columns=["mol"])
    del df
    gc.collect()
    html = render_dataframe(out)
    assert html.count("<img") + html.count("<svg") == 2


@pytest.mark.skipif(not oeomega_available, reason="oeomega not available")
def test_highlight_using_column_does_not_mutate_source_and_supports_color_column():
    mol3d = _omega("c1ccccc1O")
    df = pd.DataFrame({"mol": pd.Series([mol3d], dtype=oepd.MoleculeDtype()), "pat": ["[OH]"], "col": ["#FF0000"]})
    out = df.chem.highlight_using_column("mol", "pat", color_column="col")
    assert mol3d.GetDimension() == 3 and df["mol"][0] is mol3d
    assert "highlighted_substructures" in out.columns and out["highlighted_substructures"][0].IsValid()


def test_series_molgrid_frame_argument():
    df = _frame(2, MW=[46.0, 78.0])
    grid = df["mol"].chem.molgrid(frame=df)
    assert grid.information_fields == ["MW"]
    assert df["mol"].chem.molgrid().information_fields == []


def test_attach_is_idempotent_and_guarded(monkeypatch):
    from oepandas.pandas_extensions import OESeriesAccessor

    before = OESeriesAccessor.highlight
    pe._attach()
    pe._attach()
    assert OESeriesAccessor.highlight is before or callable(OESeriesAccessor.highlight)
    monkeypatch.setattr(pe, "_MIN_OEPANDAS", "99.0.0")
    monkeypatch.setattr(pe, "_ATTACHED", False)
    with pytest.warns(CNotebookWarning, match="pandas integration disabled"):
        pe._attach()
    monkeypatch.setattr(pe, "_MIN_OEPANDAS", "3.3.0")
    monkeypatch.setattr(pe, "_ATTACHED", False)
    pe._attach()


def test_copy_molecules_preserves_integer_index():
    """copy_molecules should preserve non-default integer index."""
    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    df = pd.DataFrame({"mol": pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())})
    df.index = [10, 20]

    # Assert source column is non-None before copy
    assert df["mol"][10] is not None
    assert df["mol"][20] is not None

    result = df.chem.copy_molecules("mol", "copy")
    assert result["copy"][10] is not None
    assert result["copy"][20] is not None
    assert result["copy"][10].NumAtoms() == mol1.NumAtoms()


def test_copy_molecules_preserves_string_index():
    """copy_molecules should preserve string index."""
    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")

    df = pd.DataFrame({"mol": pd.Series([mol1], dtype=oepd.MoleculeDtype())})
    df.index = ["a"]

    # Assert source column is non-None before copy
    assert df["mol"]["a"] is not None

    result = df.chem.copy_molecules("mol", "copy")
    assert result["copy"]["a"] is not None


def test_copy_molecules_preserves_duplicate_index():
    """copy_molecules should work with duplicate index labels."""
    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    df = pd.DataFrame({"mol": pd.Series([mol1, mol2], dtype=oepd.MoleculeDtype())})
    df.index = ["a", "a"]

    # Assert source column is non-None before copy
    assert all(m is not None for m in df["mol"])

    result = df.chem.copy_molecules("mol", "copy")
    assert all(m is not None for m in result["copy"])


def test_copy_molecules_creates_distinct_objects():
    """Copied molecules should be distinct from source."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})
    result = df.chem.copy_molecules("mol", "copy")

    assert result["copy"][0] is not result["mol"][0]
    result["mol"][0].SetTitle("changed")
    assert result["copy"][0].GetTitle() != "changed"


def test_copy_molecules_does_not_share_context():
    """Copied column should have independent rendering context."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})
    df["mol"].chem.highlight("c1ccccc1")

    original_ctx = df["mol"].array.metadata.get("cnotebook")
    original_callback_count = len(original_ctx.callbacks)

    result = df.chem.copy_molecules("mol", "copy")

    result["copy"].chem.highlight("[OH]")

    # Source context should be unchanged
    assert len(original_ctx.callbacks) == original_callback_count


def test_copy_molecules_preserves_render_options():
    """Copied column should preserve source's render options at copy time."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})
    df["mol"].chem.set_render_options(image_format="png")

    result = df.chem.copy_molecules("mol", "copy")
    copy_ctx = result["copy"].array.metadata.get("cnotebook")

    assert copy_ctx is not None
    assert copy_ctx.image_format == "png"


def test_copy_molecules_with_duplicate_dest_raises():
    """copy_molecules should raise ValueError if dest_column is duplicated."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    # Create DataFrame with duplicate column labels
    df = pd.DataFrame(
        [[mol, 1, 2]],
        columns=["mol", "dest", "dest"]
    )
    df["mol"] = df["mol"].astype(oepd.MoleculeDtype())

    # Capture frame state before the call
    original_columns = list(df.columns)
    original_dtypes = list(df.dtypes)
    original_mol = df.iloc[0, 0]

    with pytest.raises(ValueError, match="column label 'dest' is not unique"):
        df.chem.copy_molecules("mol", "dest")

    # Frame should be byte-for-byte unchanged
    assert list(df.columns) == original_columns
    assert list(df.dtypes) == original_dtypes
    assert df.iloc[0, 0] is original_mol


def test_copy_molecules_with_duplicate_dest_and_context_raises():
    """copy_molecules should raise ValueError for duplicated dest even with context."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    # Create DataFrame with duplicate column labels
    df = pd.DataFrame(
        [[mol, 1, 2]],
        columns=["mol", "dest", "dest"]
    )
    df["mol"] = df["mol"].astype(oepd.MoleculeDtype())
    df.iloc[:, 0].chem.highlight("c1ccccc1")

    # Capture frame state
    original_columns = list(df.columns)
    original_dtypes = list(df.dtypes)
    original_mol = df.iloc[0, 0]
    original_ctx = df.iloc[:, 0].array.metadata.get("cnotebook")

    with pytest.raises(ValueError, match="column label 'dest' is not unique"):
        df.chem.copy_molecules("mol", "dest")

    # Frame should be unchanged and context intact
    assert list(df.columns) == original_columns
    assert list(df.dtypes) == original_dtypes
    assert df.iloc[0, 0] is original_mol
    assert df.iloc[:, 0].array.metadata.get("cnotebook") is original_ctx


def test_copy_molecules_overwrites_single_existing_dest():
    """copy_molecules should overwrite an existing single destination column."""
    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    df = pd.DataFrame({
        "mol": pd.Series([mol1], dtype=oepd.MoleculeDtype()),
        "dest": ["placeholder"],
    })

    result = df.chem.copy_molecules("mol", "dest")

    # Should overwrite and keep MoleculeDtype
    assert isinstance(result["dest"].dtype, oepd.MoleculeDtype)
    assert result["dest"][0] is not None
    assert result["dest"][0].NumAtoms() == mol1.NumAtoms()


def test_copy_molecules_context_is_distinct_object():
    """Copied column's context should be a distinct object from source."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})
    df["mol"].chem.highlight("c1ccccc1")

    source_ctx = df["mol"].array.metadata.get("cnotebook")

    result = df.chem.copy_molecules("mol", "copy")
    dest_ctx = result["copy"].array.metadata.get("cnotebook")

    # Context objects should be distinct
    assert dest_ctx is not source_ctx


def test_bulk_accessor_with_duplicate_labels():
    """Bulk accessors should handle duplicate column labels."""
    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    df = pd.DataFrame({
        "mol": pd.Series([mol1], dtype=oepd.MoleculeDtype()),
        "other": pd.Series([mol2], dtype=oepd.MoleculeDtype())
    })
    df.columns = ["mol", "mol"]

    df.chem.set_render_options(width=200)

    # Both columns should be affected
    assert df.iloc[:, 0].array.metadata.get("cnotebook") is not None
    assert df.iloc[:, 1].array.metadata.get("cnotebook") is not None


def test_highlight_using_column_rejects_duplicate_molecule_column():
    """highlight_using_column should reject duplicate molecule column labels."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")

    df = pd.DataFrame({
        "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        "other": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        "pat": ["c1ccccc1"]
    })
    df.columns = ["mol", "mol", "pat"]

    with pytest.raises(ValueError, match="not unique"):
        df.chem.highlight_using_column("mol", "pat")


def test_highlight_using_column_color_column_zero():
    """color_column=0 should work for integer-labeled columns."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    df = pd.DataFrame({
        0: ["#FF0000"],
        1: pd.Series([mol], dtype=oepd.MoleculeDtype()),
        2: ["[OH]"]
    })

    result = df.chem.highlight_using_column(1, 2, color_column=0)
    # Should not raise and should have the column
    assert "highlighted_substructures" in result.columns


def test_highlight_using_column_handles_na_colors():
    """pd.NA in color column should use default color."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    df = pd.DataFrame({
        "mol": pd.Series([mol], dtype=oepd.MoleculeDtype()),
        "pat": ["[OH]"],
        "col": pd.array([pd.NA], dtype=pd.StringDtype())
    })

    # Should not raise TypeError
    result = df.chem.highlight_using_column("mol", "pat", color_column="col")
    assert "highlighted_substructures" in result.columns


def test_highlight_using_column_with_duplicate_output_raises():
    """highlight_using_column should raise ValueError if output column is duplicated."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")

    # Create DataFrame with duplicate column labels
    df = pd.DataFrame(
        [[mol, "c1ccccc1", 1, 2]],
        columns=["mol", "pat", "out", "out"]
    )
    df["mol"] = df["mol"].astype(oepd.MoleculeDtype())

    # Capture frame state
    original_columns = list(df.columns)
    original_dtypes = list(df.dtypes)

    with pytest.raises(ValueError, match="column label 'out' is not unique"):
        df.chem.highlight_using_column("mol", "pat", highlighted_column="out")

    # Frame should be unchanged (no depiction work done)
    assert list(df.columns) == original_columns
    assert list(df.dtypes) == original_dtypes


def test_attach_with_dev_version(monkeypatch):
    """_attach should reject dev versions."""
    monkeypatch.setattr(pe, "_ATTACHED", False)
    monkeypatch.setattr(oepd, "__version__", "3.3.0.dev1")

    with pytest.warns(CNotebookWarning, match="pandas integration disabled"):
        pe._attach()


def test_attach_with_local_version(monkeypatch):
    """_attach should accept local versions like 3.3.0+corp."""
    monkeypatch.setattr(pe, "_ATTACHED", False)
    monkeypatch.setattr(oepd, "__version__", "3.3.0+corp")

    pe._attach()

    # Should attach successfully
    from oepandas.pandas_extensions import OESeriesAccessor
    assert hasattr(OESeriesAccessor, "highlight")
    monkeypatch.setattr(oepd, "__version__", oepd.__version__)
    pe._attach()


########################################################################################################################
# df.chem.style()
########################################################################################################################


def _style_cells(html_out):
    """Body cell contents of a Styler table, in row-major order."""
    import re

    return re.findall(r"<td[^>]*>(.*?)</td>", html_out, re.DOTALL)


def test_style_formats_each_molecule_column_with_its_own_context():
    df = _frame(1)
    df["png"] = df["mol"].chem.copy_molecules()
    df["mol"].chem.set_render_options(image_format="svg")
    df["png"].chem.set_render_options(image_format="png", device_pixel_ratio=1.0)
    html = df.chem.style().to_html()
    assert "<svg" in html and "data:image/png" in html


def test_style_escapes_ordinary_values_and_labels():
    df = _frame(1, **{"<b>bad</b>": ["<script>alert(1)</script>"]})
    df.index = ["<i>row</i>"]
    html = df.chem.style().to_html()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<b>bad</b>" not in html and "&lt;b&gt;bad&lt;/b&gt;" in html
    assert "<i>row</i>" not in html and "&lt;i&gt;row&lt;/i&gt;" in html
    assert "<img" in html or "<svg" in html


def test_style_renders_a_missing_molecule_cell_as_an_empty_cell():
    df = pd.DataFrame({
        "mol": pd.Series([None, *_mols(1)], dtype=oepd.MoleculeDtype()),
        "<b>label</b>": ["<script>alert(1)</script>", "plain"],
    })
    html = df.chem.style().to_html()
    cells = _style_cells(html)

    # The empty first cell is what proves the missing molecule did not leak Pandas'
    # own scalar text ("None" or "nan") into the document.
    assert [cells[0], cells[1], cells[3]] == ["", "&lt;script&gt;alert(1)&lt;/script&gt;", "plain"]
    assert cells[2].startswith("<img")
    assert "<script>alert(1)</script>" not in html
    assert "<b>label</b>" not in html and "&lt;b&gt;label&lt;/b&gt;" in html


def test_style_applies_column_callbacks_once_per_rendered_cell():
    df = _frame(2)
    seen = []
    df["mol"].array.metadata["cnotebook"] = CNotebookContext(image_format="svg", callbacks=[seen.append])

    html = df.chem.style().to_html()

    assert html.count("<svg") == 2 and len(seen) == 2
    assert all(isinstance(disp, oedepict.OE2DMolDisplay) for disp in seen)
    # Each callback gets the depiction copy, which carries the 2D coordinates the
    # caller's molecules (parsed from SMILES) never gain.
    assert [disp.GetMolecule().GetDimension() for disp in seen] == [2, 2]
    assert [mol.GetDimension() for mol in df["mol"]] == [0, 0]


def test_style_escapes_axis_names():
    df = _frame(1, x=["v"])
    df.index = pd.Index(["r0"], name="<i>rows</i>")
    df.columns = pd.Index(["mol", "x"], name="<i>cols</i>")
    html = df.chem.style().to_html()

    assert "<i>rows</i>" not in html and "&lt;i&gt;rows&lt;/i&gt;" in html
    assert "<i>cols</i>" not in html and "&lt;i&gt;cols&lt;/i&gt;" in html
    assert "&amp;lt;" not in html  # escaped exactly once
    # The names are escaped on a derived frame, so the caller's own frame keeps the raw ones.
    assert df.index.name == "<i>rows</i>" and df.columns.name == "<i>cols</i>"


def test_style_escapes_multiindex_axis_names_and_keeps_unnamed_levels_unnamed():
    df = _frame(1, x=["v"])
    df.columns = pd.MultiIndex.from_tuples([("a", "mol"), ("a", "x")], names=["<i>top</i>", None])
    df.index = pd.Index(["r0"], name=7)
    html = df.chem.style().to_html()

    assert "<i>top</i>" not in html and "&lt;i&gt;top&lt;/i&gt;" in html
    assert "&amp;lt;" not in html
    assert ">7<" in html  # a non-string name renders as its plain text
    assert "<img" in html
    assert list(df.columns.names) == ["<i>top</i>", None] and df.index.name == 7


def test_style_rejects_duplicate_column_labels():
    """Styler.format resolves a subset by label, so duplicates would share one formatter."""
    df = pd.concat([
        pd.DataFrame({"mol": pd.Series(_mols(1), dtype=oepd.MoleculeDtype())}),
        pd.DataFrame({"mol": ["<script>alert(1)</script>"]}),
    ], axis=1)

    with pytest.raises(ValueError, match="unique column labels"):
        df.chem.style()


def test_style_with_a_duplicate_index_renders_and_escapes():
    """A duplicate index is fine: Styler addresses rows positionally when it renders."""
    df = _frame(2, s=["<b>a</b>", "<b>b</b>"])
    df.index = ["<i>r</i>", "<i>r</i>"]
    html = df.chem.style().to_html()

    assert html.count("<img") == 2
    assert "<i>r</i>" not in html and html.count("&lt;i&gt;r&lt;/i&gt;") == 2
    assert "<b>a</b>" not in html and "&lt;b&gt;a&lt;/b&gt;" in html
    assert "<b>b</b>" not in html and "&lt;b&gt;b&lt;/b&gt;" in html


def test_style_escapes_non_string_values_labels_and_axis_names():
    """Pandas' escape="html" only touches values that are already str, so cnotebook escapes the text."""
    hostile = PurePosixPath("<img src=x onerror=owned()>")
    df = _frame(1, obj=[hostile], plain=["ok"])
    df.columns = pd.Index(["mol", "obj", hostile], name=hostile)
    df.index = pd.Index([hostile], name=hostile)

    html = df.chem.style().to_html()

    assert "<img src=x onerror=owned()>" not in html
    # The cell value, the column label, the row label and both axis names.
    assert html.count("&lt;img src=x onerror=owned()&gt;") == 5
    assert "&amp;lt;" not in html
    assert "<img src='data:" in html  # the molecule column still renders a depiction


def test_style_escapes_tuple_labels_and_axis_names():
    """A tuple label is not a str either, so pandas would write its repr raw."""
    df = _frame(1, x=["v"])
    df.columns = pd.Index(["mol", ("<script>a</script>", 7)], name=("<script>n</script>", 7), dtype=object)

    html = df.chem.style().to_html()

    assert "<script>" not in html
    assert "&lt;script&gt;a&lt;/script&gt;" in html and "&lt;script&gt;n&lt;/script&gt;" in html
    assert "&amp;lt;" not in html


def test_style_escapes_multiindex_level_values_that_are_not_strings():
    hostile = PurePosixPath("<img src=x onerror=owned()>")
    df = _frame(1, x=["v"])
    df.columns = pd.MultiIndex.from_tuples([(hostile, "mol"), (hostile, "x")], names=["lvl", None])
    df.index = pd.MultiIndex.from_tuples([(hostile, "r0")], names=[hostile, None])

    html = df.chem.style().to_html()

    assert "<img src=x onerror=owned()>" not in html
    # Sparsified column level, the index level value and the index axis name.
    assert html.count("&lt;img src=x onerror=owned()&gt;") == 3
    assert "&amp;lt;" not in html
    assert "<img src='data:" in html


def test_style_renders_numbers_and_missing_values_like_the_native_styler():
    """Escaping the display text must not change how pandas formats ordinary scalars."""
    df = pd.DataFrame({"i": [1, 2], "f": [1.5, float("nan")], "b": [True, False], "o": [None, "x"]})

    assert _style_cells(df.chem.style().to_html()) == _style_cells(df.style.to_html())
    assert _style_cells(df.style.to_html()) == ["1", "1.500000", "True", "nan", "2", "nan", "False", "x"]


def test_style_captures_the_frame_when_called():
    """style() snapshots the frame; only in-place mutation of a shared cell object shows through."""
    df = _frame(1, x=["before"])
    styler = df.chem.style()
    df.loc[df.index[0], "x"] = "after"

    html = styler.to_html()
    assert "before" in html and "after" not in html

    assert "after" in df.chem.style().to_html()

    shared = df["mol"].iloc[0]
    assert styler.data["mol"].iloc[0] is shared
    shared.SetTitle("renamed")
    assert styler.data["mol"].iloc[0].GetTitle() == "renamed"


def test_style_escapes_a_column_labelled_false():
    """Pandas reads an all-boolean subset as a positional mask, so a label subset selects nothing."""
    df = pd.DataFrame({False: ["<script>alert(1)</script>"]})

    html = df.chem.style().to_html()

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_style_handles_boolean_labels_on_both_kinds_of_column():
    df = _frame(1, x=["<b>v</b>"])
    df["mol"].chem.set_render_options(image_format="svg")
    df.columns = [False, True]  # the molecule column is False, the ordinary one True

    html = df.chem.style().to_html()

    assert "<svg" in html  # the depiction column still gets its own context
    assert "<b>v</b>" not in html and "&lt;b&gt;v&lt;/b&gt;" in html


def test_style_handles_mixed_boolean_and_string_labels():
    df = _frame(1, a=["<b>a</b>"], b=["<b>b</b>"])
    df.columns = pd.Index(["mol", True, "b"], dtype=object)

    html = df.chem.style().to_html()

    assert "<b>a</b>" not in html and "&lt;b&gt;a&lt;/b&gt;" in html
    assert "<b>b</b>" not in html and "&lt;b&gt;b&lt;/b&gt;" in html
    assert "<img" in html


def test_style_binds_the_float_precision_when_called():
    """Pandas binds styler.format.precision when the Styler is built, so cnotebook must too."""
    df = pd.DataFrame({"f": [1.5]})
    styler = df.chem.style()
    native = df.style

    with pd.option_context("styler.format.precision", 2):
        assert _style_cells(styler.to_html()) == ["1.500000"]
        assert _style_cells(native.to_html()) == ["1.500000"]  # native pandas agrees
        assert _style_cells(df.chem.style().to_html()) == ["1.50"]
