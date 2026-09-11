import pytest

from cnotebook.core.errors import CNotebookWarning

# Check if polars/oepolars available
polars_available = False
try:
    import oepolars as oeplr
    import polars as pl
    polars_available = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not polars_available, reason="polars/oepolars not available")

import cnotebook.polars_ext as _polars_ext  # noqa: F401


class TestPolarsDataFrameRendering:
    """Test DataFrame rendering with molecule columns."""

    def test_render_dataframe_with_molecules(self):
        """DataFrame with molecule column should render as HTML with images."""
        from cnotebook.polars_ext import render_polars_dataframe

        # Use chem.as_molecule() to create molecule columns (the oepolars way)
        df = pl.DataFrame({
            "name": ["ethanol"],
            "mol": ["CCO"]
        }).chem.as_molecule("mol")

        html = render_polars_dataframe(df)

        assert isinstance(html, str)
        assert "<table" in html
        assert "ethanol" in html
        # Should contain SVG or PNG image data
        assert "<svg" in html or "data:image/png" in html

    def test_render_empty_dataframe(self):
        """Empty DataFrame should render without error."""
        import os

        # Create empty DataFrame with molecule column using oepolars read function
        # (oepolars doesn't support direct empty Series creation with MoleculeType)
        import tempfile

        from cnotebook.polars_ext import render_polars_dataframe

        # Create a temp SMI file with just a header
        with tempfile.NamedTemporaryFile(mode='w', suffix='.smi', delete=False) as f:
            f.write("")  # Empty file
            temp_path = f.name

        try:
            df = oeplr.read_smi(temp_path)
            # Ensure it's empty
            assert len(df) == 0
            html = render_polars_dataframe(df)
            assert isinstance(html, str)
            assert "<table" in html
        finally:
            os.unlink(temp_path)

    def test_render_preserves_original_dataframe(self):
        """Rendering should not modify the original DataFrame."""
        from cnotebook.polars_ext import render_polars_dataframe

        # Create DataFrame with molecule column
        df = pl.DataFrame({"mol": ["CCO"]}).chem.as_molecule("mol")

        # Set title on the original molecule
        original_mol = df["mol"][0]
        original_mol.SetTitle("original")

        _ = render_polars_dataframe(df)

        # Original should be unchanged
        assert df["mol"][0].GetTitle() == "original"

    def test_render_with_null_molecules(self):
        """DataFrame with null molecules should render without error."""
        from cnotebook.polars_ext import render_polars_dataframe

        # Create DataFrame with valid and invalid SMILES (invalid becomes null)
        df = pl.DataFrame({
            "name": ["ethanol", "invalid"],
            "mol": ["CCO", "invalid_smiles_xyz"]
        }).chem.as_molecule("mol")

        html = render_polars_dataframe(df)
        assert isinstance(html, str)
        assert "<table" in html


class TestPolarsDataFrameHighlight:
    """Test DataFrame highlight method."""

    def test_highlight_adds_callback(self):
        """highlight() should add callback to the returned frame's column context."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        df = df.chem.highlight("mol", "c1ccccc1")

        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None
        assert len(ctx.callbacks) > 0

    def test_highlight_with_color(self):
        """highlight() should accept color parameter."""
        import warnings

        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Should not raise (may warn if default style incompatible with single color)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", CNotebookWarning)
            df = df.chem.highlight("mol", "c1ccccc1", color=oechem.OEColor(oechem.OERed))

        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None

    def test_highlight_requires_molecule_type(self):
        """highlight() should raise TypeError on non-molecule columns."""

        df = pl.DataFrame({"text": ["abc", "def"]})

        with pytest.raises(TypeError):
            df.chem.highlight("text", "abc")

    def test_highlight_requires_valid_column(self):
        """highlight() should raise ValueError on non-existent columns."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(ValueError):
            df.chem.highlight("nonexistent", "c1ccccc1")

    def test_highlight_with_multiple_patterns(self):
        """highlight() should accept multiple patterns."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Should accept list of patterns
        df = df.chem.highlight("mol", ["c1ccccc1", "[OH]"])

        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None
        # Should have 2 callbacks (one for each pattern)
        assert len(ctx.callbacks) == 2

    def test_clear_formatting_rules_clears_callbacks(self):
        """clear_formatting_rules() should clear DataFrame-level callbacks."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Add highlight
        df = df.chem.highlight("mol", "c1ccccc1")

        # Verify callback was added
        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None
        assert len(ctx.callbacks) == 1

        # Clear formatting rules
        df = df.chem.clear_formatting_rules("mol")

        # Verify callback was cleared
        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None  # Context should still exist
        assert len(ctx.callbacks) == 0  # But callbacks should be cleared

    def test_clear_formatting_rules_all_columns(self):
        """clear_formatting_rules() with no args should clear all columns."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        df = df.chem.as_molecule("mol1").chem.as_molecule("mol2")

        # Add highlights to both columns
        df = df.chem.highlight("mol1", "c1ccccc1")
        df = df.chem.highlight("mol2", "CCO")

        # Clear all formatting rules
        df = df.chem.clear_formatting_rules()

        # Verify both were cleared
        ctx1 = pe.context_for_token(df.schema["mol1"].token)
        ctx2 = pe.context_for_token(df.schema["mol2"].token)
        assert ctx1 is None or len(ctx1.callbacks) == 0
        assert ctx2 is None or len(ctx2.callbacks) == 0


class TestPolarsDataFrameCopyMolecules:
    """Test DataFrame copy_molecules method."""

    def test_copy_molecules_creates_new_column(self):
        """copy_molecules() should create a new column with copied molecules."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        result = df.chem.copy_molecules("mol", "mol_copy")

        assert "mol_copy" in result.columns
        assert isinstance(result.schema["mol_copy"], oeplr.MoleculeType)

    def test_copy_molecules_creates_deep_copy(self):
        """copy_molecules() should create independent molecule copies."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        result = df.chem.copy_molecules("mol", "mol_copy")

        # Original and copy should be different objects
        original = result["mol"].to_list()[0]
        copy = result["mol_copy"].to_list()[0]
        assert original is not copy

    def test_copy_molecules_requires_molecule_type(self):
        """copy_molecules() should raise TypeError on non-molecule columns."""

        df = pl.DataFrame({"text": ["abc", "def"]})

        with pytest.raises(TypeError):
            df.chem.copy_molecules("text", "text_copy")

    def test_copy_molecules_requires_valid_column(self):
        """copy_molecules() should raise ValueError on non-existent columns."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(ValueError):
            df.chem.copy_molecules("nonexistent", "copy")


class TestPolarsSeriesMethods:
    """Test remaining Series accessor methods."""

    def test_align_depictions(self):
        """align_depictions() should create an aligner and apply it to molecules."""
        from unittest.mock import MagicMock, patch

        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        aligner = MagicMock(return_value=True)
        # columnops holds its own reference to create_aligner and passes the reference
        # molecule positionally.
        with patch('cnotebook.core.columnops.create_aligner', return_value=aligner) as mock_create_aligner:
            aligned = series.chem.align_depictions("first")

        mock_create_aligner.assert_called_once()
        assert isinstance(mock_create_aligner.call_args.args[0], oechem.OEMolBase)
        aligner.assert_called_once()
        assert isinstance(aligned.dtype, oeplr.MoleculeType)

    def test_recalculate_depiction_coordinates(self):
        """recalculate_depiction_coordinates() should prepare molecule depictions."""
        from unittest.mock import patch

        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        with patch('cnotebook.polars_ext.oedepict.OEPrepareDepiction') as mock_prepare:
            series.chem.recalculate_depiction_coordinates()

        mock_prepare.assert_called_once()

    def test_align_depictions_requires_molecule_type(self):
        """align_depictions() should raise TypeError on non-molecule columns."""

        s = pl.Series("text", ["abc"])

        with pytest.raises(TypeError):
            s.chem.align_depictions("first")

    def test_recalculate_depictions_requires_molecule_type(self):
        """recalculate_depiction_coordinates() should raise TypeError on non-molecule columns."""

        s = pl.Series("text", ["abc"])

        with pytest.raises(TypeError):
            s.chem.recalculate_depiction_coordinates()


class TestPolarsDataFrameMethods:
    """Test DataFrame accessor methods."""

    def test_dataframe_reset_depictions_specific_columns(self):
        """DataFrame reset_depictions() should accept molecule_columns parameter."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        df = df.chem.as_molecule("mol1").chem.as_molecule("mol2")
        df = df.chem.set_render_options(molecule_columns="mol1", width=111)
        df = df.chem.set_render_options(molecule_columns="mol2", width=222)

        # A list of names and a bare name both reset only the columns they name
        reset_first = df.chem.reset_depictions(molecule_columns=["mol1"])
        assert reset_first.schema["mol1"].token is None
        assert pe.context_for_token(reset_first.schema["mol2"].token).width == 222

        reset_second = reset_first.chem.reset_depictions(molecule_columns="mol2")
        assert reset_second.schema["mol2"].token is None
        # The frame the reset was taken from keeps its settings
        assert pe.context_for_token(df.schema["mol1"].token).width == 111

    def test_highlight_using_column(self):
        """highlight_using_column() should create display column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({
            "mol": [mol],
            "pattern": ["c1ccccc1"]
        })
        df = df.chem.as_molecule("mol")

        result = df.chem.highlight_using_column("mol", "pattern")

        assert "highlighted_substructures" in result.columns
        assert isinstance(result.schema["highlighted_substructures"], oeplr.DisplayType)

    def test_highlight_using_column_custom_name(self):
        """highlight_using_column() should accept custom column name."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({
            "mol": [mol],
            "pattern": ["c1ccccc1"]
        })
        df = df.chem.as_molecule("mol")

        result = df.chem.highlight_using_column("mol", "pattern", highlighted_column="my_highlights")

        assert "my_highlights" in result.columns
        assert isinstance(result.schema["my_highlights"], oeplr.DisplayType)

    def test_highlight_using_column_inplace(self):
        """highlight_using_column() with inplace=True should report the ignored argument."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({
            "mol": [mol],
            "pattern": ["c1ccccc1"]
        })
        df = df.chem.as_molecule("mol")

        # A polars frame cannot be modified in place, so the new frame is returned and
        # the ignored argument is reported
        with pytest.warns(CNotebookWarning, match="immutable"):
            result = df.chem.highlight_using_column("mol", "pattern", inplace=True)

        assert "highlighted_substructures" in result.columns
        assert "highlighted_substructures" not in df.columns

    def test_highlight_using_column_missing_molecule_column(self):
        """highlight_using_column() should raise KeyError for missing molecule column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({
            "mol": [mol],
            "pattern": ["c1ccccc1"]
        })
        df = df.chem.as_molecule("mol")

        with pytest.raises(KeyError):
            df.chem.highlight_using_column("nonexistent", "pattern")

    def test_highlight_using_column_missing_pattern_column(self):
        """highlight_using_column() should raise KeyError for missing pattern column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(KeyError):
            df.chem.highlight_using_column("mol", "nonexistent")

    def test_highlight_using_column_non_molecule_type(self):
        """highlight_using_column() should raise TypeError for non-molecule column."""

        df = pl.DataFrame({
            "text": ["hello"],
            "pattern": ["c1ccccc1"]
        })

        with pytest.raises(TypeError):
            df.chem.highlight_using_column("text", "pattern")

    def test_recalculate_depiction_coordinates_dataframe(self):
        """DataFrame recalculate_depiction_coordinates() should prepare molecule depictions."""
        from unittest.mock import patch

        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with patch('cnotebook.polars_ext.oedepict.OEPrepareDepiction') as mock_prepare:
            df.chem.recalculate_depiction_coordinates()

        mock_prepare.assert_called_once()

    def test_recalculate_depiction_coordinates_specific_columns(self):
        """DataFrame recalculate_depiction_coordinates() should process requested columns only."""
        from unittest.mock import patch

        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        df = df.chem.as_molecule("mol1").chem.as_molecule("mol2")

        with patch('cnotebook.polars_ext.oedepict.OEPrepareDepiction') as mock_prepare:
            df.chem.recalculate_depiction_coordinates(molecule_columns=["mol1"])

        mock_prepare.assert_called_once()


class TestPolarsFingerprintSimilarity:
    """Test fingerprint similarity visualization."""

    def test_fingerprint_similarity_creates_columns(self):
        """fingerprint_similarity() should create tanimoto and display columns."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "c1ccc(O)cc1")

        df = pl.DataFrame({"mol": [mol1, mol2]})
        df = df.chem.as_molecule("mol")

        result = df.chem.fingerprint_similarity("mol", mol1)

        assert "fingerprint_tanimoto" in result.columns
        assert "reference_similarity" in result.columns
        assert "target_similarity" in result.columns

    def test_fingerprint_similarity_calculates_tanimoto(self):
        """fingerprint_similarity() should calculate Tanimoto scores."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol1]})
        df = df.chem.as_molecule("mol")

        result = df.chem.fingerprint_similarity("mol", mol1)

        # Same molecule should have Tanimoto of 1.0
        assert result["fingerprint_tanimoto"][0] == pytest.approx(1.0)

    def test_fingerprint_similarity_default_reference(self):
        """fingerprint_similarity() should use first molecule as default reference."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "c1ccc(O)cc1")

        df = pl.DataFrame({"mol": [mol1, mol2]})
        df = df.chem.as_molecule("mol")

        # No reference - should use first molecule
        result = df.chem.fingerprint_similarity("mol")

        assert "fingerprint_tanimoto" in result.columns
        # First molecule compared to itself should be 1.0
        assert result["fingerprint_tanimoto"][0] == pytest.approx(1.0)

    def test_fingerprint_similarity_display_columns(self):
        """fingerprint_similarity() display columns should be DisplayType."""
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol1]})
        df = df.chem.as_molecule("mol")

        result = df.chem.fingerprint_similarity("mol", mol1)

        assert isinstance(result.schema["reference_similarity"], oeplr.DisplayType)
        assert isinstance(result.schema["target_similarity"], oeplr.DisplayType)

    def test_fingerprint_similarity_missing_column(self):
        """fingerprint_similarity() should raise KeyError for missing column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(KeyError):
            df.chem.fingerprint_similarity("nonexistent", mol)

    def test_fingerprint_similarity_non_molecule_type(self):
        """fingerprint_similarity() should raise TypeError for non-molecule column."""

        df = pl.DataFrame({"text": ["hello"]})

        with pytest.raises(TypeError):
            df.chem.fingerprint_similarity("text")


class TestPolarsDataFrameHighlightExtended:
    """Extended tests for DataFrame-level highlight method."""

    def test_highlight_smarts_string(self):
        """highlight() with a SMARTS string should store a callback."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        df = pl.DataFrame({"mol": [mol]}).chem.as_molecule("mol")

        df = df.chem.highlight("mol", "c1ccccc1")

        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None
        assert len(ctx.callbacks) >= 1

    def test_highlight_iterable_patterns(self):
        """highlight() with an iterable of SMARTS should add one callback per pattern."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")
        df = pl.DataFrame({"mol": [mol]}).chem.as_molecule("mol")

        df = df.chem.highlight("mol", ["c1ccccc1", "[OH]"])

        ctx = pe.context_for_token(df.schema["mol"].token)
        assert ctx is not None
        assert len(ctx.callbacks) == 2

    def test_highlight_unknown_type_raises(self):
        """highlight() with an unsupported type should raise TypeError."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        df = pl.DataFrame({"mol": [mol]}).chem.as_molecule("mol")

        with pytest.raises(TypeError):
            df.chem.highlight("mol", 123)

    def test_highlight_non_molecule_raises(self):
        """highlight() on a non-MoleculeType column should raise TypeError."""

        df = pl.DataFrame({"text": ["hello"]})
        with pytest.raises(TypeError):
            df.chem.highlight("text", "c1ccccc1")


class TestPolarsSeriesResetClear:
    """Test reset_depictions and clear_formatting_rules, which are DataFrame accessors."""

    def test_reset_depictions_clears_series_context(self):
        """reset_depictions() should leave the returned column with no stored state."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        df = pl.DataFrame({"mol": [mol]}).chem.as_molecule("mol")
        df = df.chem.set_render_options(width=321)
        assert pe.context_for_token(df.schema["mol"].token).width == 321

        reset = df.chem.reset_depictions("mol")

        assert reset.schema["mol"].token is None
        assert pe.context_for_token(reset.schema["mol"].token) is None

    def test_clear_formatting_rules_clears_series_callbacks(self):
        """clear_formatting_rules() should preserve the other options and remove callbacks."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        df = pl.DataFrame({"mol": [mol]}).chem.as_molecule("mol")
        df = df.chem.set_render_options(width=321).chem.highlight("mol", "c1ccccc1")
        assert len(pe.context_for_token(df.schema["mol"].token).callbacks) == 1

        cleared = df.chem.clear_formatting_rules("mol")

        ctx = pe.context_for_token(cleared.schema["mol"].token)
        assert len(ctx.callbacks) == 0
        assert ctx.width == 321
        # The frame the clear was taken from keeps its callback
        assert len(pe.context_for_token(df.schema["mol"].token).callbacks) == 1


class TestPolarsDataFrameRecalculateDepictions:
    """Test DataFrame-level recalculate_depiction_coordinates."""

    @staticmethod
    def _two_molecule_frame():
        """A frame of two freshly parsed molecule columns, so neither has 2D coordinates yet."""
        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")
        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        return df.chem.as_molecule("mol1").chem.as_molecule("mol2")

    @staticmethod
    def _assert_recalculated(source, out, columns):
        """Check the copy-on-write contract of recalculate_depiction_coordinates()."""
        assert out is not source
        for name in columns:
            assert out.schema[name].token is not None
            assert out.schema[name].token != source.schema[name].token
            before, after = source.get_column(name).to_list(), out.get_column(name).to_list()
            # Fresh molecules have no 2D coordinates; the caller's must still have none
            assert all(m.GetDimension() == 0 for m in before)
            assert all(m.GetDimension() == 2 for m in after)
            assert all(a is not b for a, b in zip(after, before, strict=True))
        for name in set(source.columns) - set(columns):
            assert out.schema[name].token == source.schema[name].token
            assert all(m.GetDimension() == 0 for m in out.get_column(name).to_list())

    def test_recalculate_all_columns(self):
        """recalculate_depiction_coordinates() with no args should process all molecule columns."""
        df = self._two_molecule_frame()

        out = df.chem.recalculate_depiction_coordinates()

        self._assert_recalculated(df, out, ["mol1", "mol2"])

    def test_recalculate_string_column(self):
        """recalculate_depiction_coordinates() should accept molecule_columns as a string."""
        df = self._two_molecule_frame()

        out = df.chem.recalculate_depiction_coordinates(molecule_columns="mol1")

        self._assert_recalculated(df, out, ["mol1"])

    def test_recalculate_list_column(self):
        """recalculate_depiction_coordinates() should accept molecule_columns as a list."""
        df = self._two_molecule_frame()

        out = df.chem.recalculate_depiction_coordinates(molecule_columns=["mol1"])

        self._assert_recalculated(df, out, ["mol1"])

    def test_recalculate_series_returns_a_new_column(self):
        """The Series accessor follows the same contract as the DataFrame one."""
        series = self._two_molecule_frame().get_column("mol1")

        out = series.chem.recalculate_depiction_coordinates()

        assert out is not series and out.name == series.name
        assert out.dtype.token is not None and out.dtype.token != series.dtype.token
        assert all(m.GetDimension() == 0 for m in series.to_list())
        assert all(m.GetDimension() == 2 for m in out.to_list())
        assert all(a is not b for a, b in zip(out.to_list(), series.to_list(), strict=True))

    def test_recalculate_non_molecule_warns(self):
        """recalculate_depiction_coordinates() should warn for non-molecule column."""
        df = pl.DataFrame({"text": ["hello"]})

        with pytest.warns(CNotebookWarning, match="MoleculeType") as caught:
            df.chem.recalculate_depiction_coordinates(molecule_columns=["text"])
        # The warning is the caller's problem, so it must be blamed on the caller's line
        assert caught[0].filename == __file__

    def test_recalculate_missing_column_warns(self):
        """recalculate_depiction_coordinates() should warn for missing column."""
        df = pl.DataFrame({"text": ["hello"]})

        with pytest.warns(CNotebookWarning, match="not found") as caught:
            df.chem.recalculate_depiction_coordinates(molecule_columns=["nonexistent"])
        assert caught[0].filename == __file__


class TestPolarsHighlightUsingColumnExtended:
    """Extended tests for DataFrame highlight_using_column."""

    def test_highlight_using_column_overlay_single_color_fallback(self):
        """highlight_using_column() with OEColor + overlay_default should fall back quietly."""
        import warnings

        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol], "pattern": ["c1ccccc1"]})
        df = df.chem.as_molecule("mol")

        # A single colour cannot drive the overlay highlighter; columnops falls back to
        # plain highlighting for that row rather than reporting it
        with warnings.catch_warnings():
            warnings.simplefilter("error", CNotebookWarning)
            result = df.chem.highlight_using_column(
                "mol", "pattern", color=oechem.OERed, style="overlay_default"
            )

        assert "highlighted_substructures" in result.columns
        assert isinstance(result.schema["highlighted_substructures"], oeplr.DisplayType)

    def test_highlight_using_column_traditional(self):
        """highlight_using_column() with an integer style should use traditional highlighting."""
        from openeye import oechem, oedepict

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol], "pattern": ["c1ccccc1"]})
        df = df.chem.as_molecule("mol")

        result = df.chem.highlight_using_column(
            "mol", "pattern", style=oedepict.OEHighlightStyle_BallAndStick
        )

        assert "highlighted_substructures" in result.columns
        assert isinstance(result.schema["highlighted_substructures"], oeplr.DisplayType)

    def test_highlight_using_column_iterable_patterns(self):
        """highlight_using_column() should handle a pattern column with a list of SMARTS."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        df = pl.DataFrame({"mol": [mol], "pattern": [["c1ccccc1", "[OH]"]]})
        df = df.chem.as_molecule("mol")

        result = df.chem.highlight_using_column("mol", "pattern")

        assert "highlighted_substructures" in result.columns

    def test_highlight_using_column_null_molecule(self):
        """highlight_using_column() with a None molecule should produce None in display column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol, None], "pattern": ["c1ccccc1", "CC"]})
        df = df.chem.as_molecule("mol")

        result = df.chem.highlight_using_column("mol", "pattern")

        assert "highlighted_substructures" in result.columns
        # The None molecule row should produce a None display
        assert result["highlighted_substructures"][1] is None


class TestPolarsFingerprintSimilarityExtended:
    """Extended tests for DataFrame fingerprint_similarity."""

    def test_fingerprint_similarity_invalid_ref(self):
        """fingerprint_similarity() with an invalid reference molecule should warn and add empty columns."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # An empty (invalid) molecule as reference
        bad_ref = oechem.OEMol()

        with pytest.warns(CNotebookWarning, match="not valid"):
            result = df.chem.fingerprint_similarity("mol", bad_ref)

        # The columns are still added, with nothing in them, so the frame keeps its shape
        added = ["fingerprint_tanimoto", "reference_similarity", "target_similarity"]
        assert list(result.columns) == [*df.columns, *added]
        for name in added:
            assert result.get_column(name).to_list() == [None]

    def test_fingerprint_similarity_with_null_rows(self):
        """fingerprint_similarity() with None molecules should produce None entries in display columns."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol, None]})
        df = df.chem.as_molecule("mol")

        result = df.chem.fingerprint_similarity("mol", mol)

        assert result["fingerprint_tanimoto"][1] is None
        assert result["reference_similarity"][1] is None
        assert result["target_similarity"][1] is None

    def test_fingerprint_similarity_inplace_false(self):
        """fingerprint_similarity() with inplace=False should leave original df unchanged."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        original_columns = list(df.columns)
        result = df.chem.fingerprint_similarity("mol", mol, inplace=False)

        assert list(df.columns) == original_columns
        assert "fingerprint_tanimoto" in result.columns


class TestPolarsRegisterFormatters:
    """Test register_polars_formatters function."""

    def test_register_formatters_ipython_present(self):
        """register_polars_formatters() should call for_type when IPython is available."""
        from unittest.mock import MagicMock, patch

        from cnotebook.polars_ext import render_polars_dataframe

        mock_ipython = MagicMock()
        mock_html_formatter = MagicMock()
        mock_html_formatter.lookup.side_effect = KeyError
        mock_ipython.display_formatter.formatters.__getitem__.return_value = mock_html_formatter

        with patch("cnotebook.polars_ext.get_ipython", return_value=mock_ipython):
            from cnotebook.polars_ext import register_polars_formatters
            register_polars_formatters()

        mock_html_formatter.for_type.assert_called_with(pl.DataFrame, render_polars_dataframe)

    def test_register_formatters_no_ipython_instance(self, caplog):
        """register_polars_formatters() should emit debug log when get_ipython() returns None."""
        import logging
        from unittest.mock import patch

        with patch("cnotebook.polars_ext.get_ipython", return_value=None):
            with caplog.at_level(logging.DEBUG, logger="cnotebook"):
                from cnotebook.polars_ext import register_polars_formatters
                register_polars_formatters()

        assert any("not in use" in record.message for record in caplog.records)

    def test_register_formatters_already_registered(self):
        """register_polars_formatters() should not re-register when render_polars_dataframe is already set."""
        from unittest.mock import MagicMock, patch

        from cnotebook.polars_ext import render_polars_dataframe

        mock_ipython = MagicMock()
        mock_html_formatter = MagicMock()
        mock_html_formatter.lookup.return_value = render_polars_dataframe
        mock_ipython.display_formatter.formatters.__getitem__.return_value = mock_html_formatter

        with patch("cnotebook.polars_ext.get_ipython", return_value=mock_ipython):
            from cnotebook.polars_ext import register_polars_formatters
            register_polars_formatters()

        mock_html_formatter.for_type.assert_not_called()


class TestPolarsCreateDispFormatter:
    """Test the create_disp_formatter closure."""

    def test_valid_display_returns_html(self):
        """create_disp_formatter with a valid OE2DMolDisplay should return HTML string."""
        from openeye import oechem, oedepict

        from cnotebook.context import CNotebookContext
        from cnotebook.polars_ext import create_disp_formatter

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        disp = oedepict.OE2DMolDisplay(mol, oedepict.OE2DMolDisplayOptions())
        ctx = CNotebookContext()
        formatter = create_disp_formatter(ctx=ctx)

        result = formatter(disp)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_valid_display_with_callbacks(self):
        """create_disp_formatter with callbacks should apply them."""
        from openeye import oechem, oedepict

        from cnotebook.context import CNotebookContext
        from cnotebook.polars_ext import create_disp_formatter

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)
        disp = oedepict.OE2DMolDisplay(mol, oedepict.OE2DMolDisplayOptions())

        callback_called = []

        def my_callback(d):
            callback_called.append(True)

        ctx = CNotebookContext()
        formatter = create_disp_formatter(ctx=ctx, callbacks=[my_callback])
        result = formatter(disp)
        assert len(callback_called) == 1
        assert isinstance(result, str)

    def test_invalid_display_returns_escaped_str(self):
        """create_disp_formatter with non-display input should return its escaped str()."""
        from cnotebook.context import CNotebookContext
        from cnotebook.polars_ext import create_disp_formatter

        ctx = CNotebookContext()
        formatter = create_disp_formatter(ctx=ctx)
        assert formatter("not a display") == "not a display"
        assert formatter("<script>a&b</script>") == "&lt;script&gt;a&amp;b&lt;/script&gt;"


class TestPolarsCreateDuFormatter:
    """Test the create_du_formatter closure."""

    def test_non_du_returns_str(self):
        """create_du_formatter with a non-DesignUnit should return str()."""
        from cnotebook.context import CNotebookContext
        from cnotebook.polars_ext import create_du_formatter

        ctx = CNotebookContext()
        formatter = create_du_formatter(ctx=ctx)
        result = formatter("not a design unit")
        assert result == "not a design unit"


class TestPolarsRenderWithDisplayColumns:
    """Test render_polars_dataframe with DisplayType columns."""

    def test_render_display_column(self):
        """render_polars_dataframe with a DisplayType column should produce HTML."""
        from openeye import oechem

        from cnotebook.polars_ext import render_polars_dataframe

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol], "pattern": ["c1ccccc1"]}).chem.as_molecule("mol")

        # highlight_using_column creates a DisplayType column
        result_df = df.chem.highlight_using_column("mol", "pattern")

        html = render_polars_dataframe(result_df)
        assert isinstance(html, str)
        assert len(html) > 0
        assert "<table" in html


class TestPolarsRenderWithDesignUnitColumns:
    """Test render_polars_dataframe with DesignUnitType columns."""

    def test_render_designunit_column(self):
        """render_polars_dataframe with a DesignUnitType column should produce HTML."""
        from openeye import oechem

        from cnotebook.polars_ext import render_polars_dataframe

        du = oechem.OEDesignUnit()
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"du": [du]}).chem.as_design_unit("du")

        html = render_polars_dataframe(df)
        assert isinstance(html, str)
        assert "<table" in html


class TestPolarsHighlightUsingColumnPatterns:
    """Test highlight_using_column pattern parsing paths."""

    def test_highlight_using_column_subsearch_pattern(self):
        """highlight_using_column with OESubSearch in pattern column."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        ss = oechem.OESubSearch("c1ccccc1")

        df = pl.DataFrame({"mol": [mol], "pattern": [ss]}).chem.as_molecule("mol")
        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns

    def test_highlight_using_column_iterable_with_subsearch(self):
        """highlight_using_column with iterable containing OESubSearch."""
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        ss = oechem.OESubSearch("c1ccccc1")

        # Polars can't handle nested lists of mixed OE types directly in DataFrame constructor.
        # Instead, build with pl.Series using Object dtype so the list is stored as a single element.
        pattern_list = [ss, "[OH]"]
        mol_series = pl.Series("mol", [mol], dtype=oeplr.MoleculeType())
        pattern_series = pl.Series("pattern", [pattern_list], dtype=pl.Object)
        df = pl.DataFrame([mol_series, pattern_series])

        result = df.chem.highlight_using_column("mol", "pattern")
        assert "highlighted_substructures" in result.columns


class TestPolarsAlignDepictionsEdge:
    """Test series align_depictions edge cases."""

    def test_align_exception_handled(self):
        """align_depictions should report an aligner it cannot build to the caller."""
        from unittest.mock import patch

        from openeye import oechem, oedepict

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol1)
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "c1ccc(C)cc1")
        oedepict.OEPrepareDepiction(mol2)

        df = pl.DataFrame({"mol": [mol1, mol2]}).chem.as_molecule("mol")
        series = df.get_column("mol")

        # columnops does not swallow a failing aligner: silently unaligned depictions
        # would look like a successful alignment
        with (patch('cnotebook.core.columnops.create_aligner', side_effect=RuntimeError("boom")) as mock_create_aligner,
              pytest.raises(RuntimeError, match="boom")):
            series.chem.align_depictions(ref=mol1)

        mock_create_aligner.assert_called_once()

    def test_align_no_valid_mols(self):
        """align_depictions with ref='first' and all None mols should warn."""
        df = pl.DataFrame({"mol": [None, None]}).chem.as_molecule("mol")
        series = df.get_column("mol")

        with pytest.warns(CNotebookWarning, match="No valid molecule"):
            series.chem.align_depictions(ref="first")



def test_highlight_using_column_overlay_produces_different_svg():
    """Test that overlay highlighting actually modifies the rendered output."""
    import polars as pl
    from openeye import oechem, oedepict
    from cnotebook.core.render import oedisp_to_html, oemol_to_disp
    from cnotebook.core.context import CNotebookContext
    
    # Create a simple molecule
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")  # phenol
    oedepict.OEPrepareDepiction(mol)
    
    df = pl.DataFrame({
        "mol": [mol],
        "pattern": ["c1ccccc1"]  # benzene ring
    })
    df = df.chem.as_molecule("mol")
    
    # Create highlighted version
    df_highlighted = df.chem.highlight_using_column(
        "mol", "pattern",
        highlighted_column="highlighted",
        style="overlay_default"
    )
    
    # Render both to SVG
    ctx = CNotebookContext(image_format="svg")
    unhighlighted_disp = oemol_to_disp(mol, ctx=ctx)
    unhighlighted_svg = oedisp_to_html(unhighlighted_disp, ctx=ctx)
    
    highlighted_disp = df_highlighted["highlighted"][0]
    highlighted_svg = oedisp_to_html(highlighted_disp, ctx=ctx)
    
    # The SVGs should be different
    assert unhighlighted_svg != highlighted_svg
    assert "svg" in unhighlighted_svg.lower()
    assert "svg" in highlighted_svg.lower()


def test_highlight_using_column_traditional_produces_different_svg():
    """Test that traditional highlighting actually modifies the rendered output."""
    import polars as pl
    from openeye import oechem, oedepict
    from cnotebook.core.render import oedisp_to_html, oemol_to_disp
    from cnotebook.core.context import CNotebookContext
    
    # Create a simple molecule
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")  # phenol
    oedepict.OEPrepareDepiction(mol)
    
    df = pl.DataFrame({
        "mol": [mol],
        "pattern": ["c1ccccc1"]  # benzene ring
    })
    df = df.chem.as_molecule("mol")
    
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
    
    highlighted_disp = df_highlighted["highlighted"][0]
    highlighted_svg = oedisp_to_html(highlighted_disp, ctx=ctx)
    
    # The SVGs should be different
    assert unhighlighted_svg != highlighted_svg
    assert "svg" in unhighlighted_svg.lower()
    assert "svg" in highlighted_svg.lower()


# ----------------------------------------------------------------------------------------
# Token registry and table-plan rendering
# ----------------------------------------------------------------------------------------

import gc
import sys
import warnings

from openeye import oechem

import cnotebook.polars_ext as pe
from cnotebook.core import columnops
from cnotebook.core.columnops import AlignmentReport
from cnotebook.core.context import (
    CNotebookContext,
    cnotebook_context,
    create_local_context,
)


def _mols(n, smiles="c1ccccc1O"):
    """Build *n* titled copies of *smiles* as graph molecules."""
    out = []
    for i in range(n):
        m = oechem.OEGraphMol()
        oechem.OESmilesToMol(m, smiles)
        m.SetTitle(f"m{i}")
        out.append(m)
    return out


def _pframe(n=3, token=None, **extra):
    """Build a frame with a molecule column carrying *token* plus any extra columns."""
    cols = [pl.Series("mol", _mols(n), dtype=oeplr.MoleculeType(token))]
    for name, values in extra.items():
        cols.append(pl.Series(name, values))
    return pl.DataFrame(cols)


def test_render_polars_truncates_per_config():
    """Truncation follows POLARS_FMT_MAX_ROWS, and max_rows <= 0 or tbl_rows=-1 renders everything."""
    df = pl.DataFrame({"a": list(range(100))})
    with pl.Config(tbl_rows=6):
        html = pe.render_polars_dataframe(df)
    # 6 data rows + the ellipsis row + the dtype header row; the label header row
    # carries a style attribute, so it is not counted by the bare "<tr>" literal.
    assert html.count("<tr>") == 6 + 1 + 1
    assert pe.render_polars_dataframe(df, max_rows=0).count("<td>") == 100
    with pl.Config(tbl_rows=-1):
        assert pe.render_polars_dataframe(df).count("<td>") == 100


def test_configured_max_rows_handles_unset():
    """configured_max_rows reads the polars option and reports None when it is unset."""
    with pl.Config(tbl_rows=7):
        assert pe.configured_max_rows() == 7
    with pl.Config(restore_defaults=True):
        assert pe.configured_max_rows() is None
        # An unset option falls back to the spec B1 default of 10: five head rows, the
        # ellipsis row and five tail rows. A bare cell count cannot tell that apart from
        # output that stopped truncating, so pin which values survive the window.
        html = pe.render_polars_dataframe(pl.DataFrame({"a": list(range(11))}))
        assert html.count("<td>") == 11
        assert html.count("<td>...</td>") == 1
        assert "<td>5</td>" not in html  # the dropped middle row
        for value in (0, 1, 2, 3, 4, 6, 7, 8, 9, 10):
            assert f"<td>{value}</td>" in html


def test_render_polars_resolves_context_by_token():
    """A dtype token resolves to the registered column state."""
    token = pe.new_token()
    ctx = create_local_context()
    ctx.image_format = "svg"
    ctx.width = 111
    pe.store_state(token, pe.ColumnState(ctx))
    html = pe.render_polars_dataframe(_pframe(1, token=token))
    assert "<svg" in html and "min-width: 111px" in html
    assert "molecule" in html  # dtype header row
    assert token not in html  # the registry token is never printed


def test_render_polars_escapes_and_honours_formatters():
    """Caller formatter output and column labels are escaped by the writer."""
    df = _pframe(1, note=["a&b<c>"], **{"<h>": ["x"]})
    html = pe.render_polars_dataframe(df, formatters={"note": lambda v: f"[{v}]"})
    assert "[a&amp;b&lt;c&gt;]" in html and "&lt;h&gt;" in html and "<h>" not in html


def test_render_polars_none_and_invalid_cells():
    """A None molecule renders as an empty cell; an empty molecule renders the placeholder."""
    df = pl.DataFrame([pl.Series("mol", [None, oechem.OEGraphMol(), *_mols(1)], dtype=oeplr.MoleculeType())])
    # The placeholder text is drawn into the image, so it is only greppable in SVG output.
    html = pe.render_polars_dataframe(df, ctx=CNotebookContext(image_format="svg"))
    assert "Empty Molecule" in html and html.count("<td>") == 3
    assert html.count("<td></td>") == 1


def test_render_polars_null_ordinary_cells():
    """A missing ordinary cell renders as the polars "null" text."""
    df = pl.DataFrame({"a": [None, "x"]})
    html = pe.render_polars_dataframe(df)
    assert "<td>null</td>" in html and "<td>x</td>" in html


def test_render_polars_warns_when_a_formatter_targets_a_depiction_column():
    """A caller formatter aimed at a depiction column is reported and never reaches the document."""
    df = _pframe(1)
    with pytest.warns(CNotebookWarning, match="Overwriting the formatter") as record:
        html = pe.render_polars_dataframe(df, formatters={"mol": lambda v: "LEAKED"})
    assert "LEAKED" not in html
    # The warning must blame the caller's render call, not a line inside polars_ext.py.
    assert record[0].filename == __file__


def test_render_polars_warns_when_col_space_is_ignored():
    """A non-empty col_space is accepted for compatibility but reported as ignored."""
    df = pl.DataFrame({"a": [1]})
    with pytest.warns(CNotebookWarning, match="col_space"):
        html = pe.render_polars_dataframe(df, col_space={"a": 200})
    assert "min-width: 200px" not in html


def test_registry_is_bounded_and_clearable():
    """The token registry is a bounded LRU that clear_column_contexts empties."""
    pe.clear_column_contexts()
    assert pe.context_for_token(None) is None
    oldest = pe.new_token()
    pe.store_state(oldest, pe.ColumnState(create_local_context()))
    for _ in range(pe._MAX_STATES - 1):
        pe.store_state(pe.new_token(), pe.ColumnState(create_local_context()))
    # Reading the oldest token makes it the most recent, so the next insert evicts
    # the untouched entry behind it instead.
    assert pe.state_for_token(oldest) is not None
    pe.store_state(pe.new_token(), pe.ColumnState(create_local_context()))
    assert len(pe._STATES) == pe._MAX_STATES
    assert pe.context_for_token(oldest) is not None

    for _ in range(5):
        pe.store_state(pe.new_token(), pe.ColumnState(create_local_context()))
    assert len(pe._STATES) == pe._MAX_STATES
    pe.clear_column_contexts()
    assert len(pe._STATES) == 0 and pe.context_for_token("missing") is None


# ----------------------------------------------------------------------------------------
# Copy-on-write accessors returning frames
# ----------------------------------------------------------------------------------------


def test_context_clone_preserves_deferral():
    local = create_local_context()
    local.width = 50
    clone = local.clone()
    assert clone.scope == "local" and clone.width == 50 and clone._image_format.is_deferred
    g = cnotebook_context.get()
    saved = g.image_format
    try:
        g.image_format = "svg"
        assert clone.image_format == "svg"
    finally:
        g.image_format = saved


def test_highlight_returns_new_frame_and_survives_filter():
    df = _pframe(3, x=[1, 2, 3])
    out = df.chem.highlight("mol", "c1ccccc1")
    assert out is not df and df.schema["mol"].token is None
    token = out.schema["mol"].token
    assert token and len(pe.context_for_token(token).callbacks) == 1
    filtered = out.filter(pl.col("x") > 1)
    assert filtered.schema["mol"].token == token
    assert pe.render_polars_dataframe(filtered).count("<svg") + pe.render_polars_dataframe(filtered).count("<img") == 2


def test_context_changes_do_not_leak_to_sibling_frames():
    base = _pframe(2).chem.set_render_options("mol", image_format="svg")
    sibling = base.filter(pl.col("mol").is_not_null())
    changed = base.chem.set_render_options("mol", width=321)
    assert changed.schema["mol"].token != base.schema["mol"].token
    # The sibling never saw the width, so it still follows the global context for it
    assert pe.context_for_token(sibling.schema["mol"].token).width == 0
    assert pe.context_for_token(sibling.schema["mol"].token)._width.is_deferred
    assert pe.context_for_token(changed.schema["mol"].token).width == 321


def test_reset_and_clear_return_frames():
    out = _pframe(1).chem.highlight("mol", "[OH]")
    cleared = out.chem.clear_formatting_rules("mol")
    assert pe.context_for_token(cleared.schema["mol"].token).callbacks == ()
    reset = cleared.chem.reset_depictions("mol")
    assert reset.schema["mol"].token is None


def test_align_depictions_accepts_smarts_ref_without_mutation():
    df = _pframe(2)
    originals = df.get_column("mol").to_list()
    out = df.chem.align_depictions("mol", "c1ccccc1")
    report = out.chem.alignment_report("mol")
    assert isinstance(report, AlignmentReport) and report.aligned == 2
    assert all(m.GetDimension() == 0 for m in originals)
    assert all(m.GetDimension() == 2 for m in out.get_column("mol").to_list())
    series = df.get_column("mol").chem.align_depictions(oechem.OESubSearch("c1ccccc1"))
    assert isinstance(series, pl.Series) and series.dtype.token is not None


def test_series_accessors_work_on_an_unnamed_series():
    """polars labels an unnamed Series 'column_0' inside a frame; the name must survive."""
    unnamed = pl.Series(_mols(2), dtype=oeplr.MoleculeType())
    assert unnamed.name == ""
    aligned = unnamed.chem.align_depictions("first")
    assert aligned.name == "" and aligned.dtype.token is not None
    laid_out = unnamed.chem.recalculate_depiction_coordinates()
    assert laid_out.name == "" and laid_out.dtype.token is not None
    # The molecules really were laid out again, on copies
    assert all(m.GetDimension() == 0 for m in unnamed.to_list())
    assert all(m.GetDimension() == 2 for m in laid_out.to_list())


def test_alignment_reports_are_not_shared_between_forks():
    """A report read from one fork is the fork's own; writing to it must not reach a sibling."""
    aligned = _pframe(2).chem.align_depictions("mol", "c1ccccc1")
    sibling = aligned.filter(pl.col("mol").is_not_null())
    forked = aligned.chem.set_render_options("mol", width=210)

    report = forked.chem.alignment_report("mol")
    assert report is not sibling.chem.alignment_report("mol")
    report.failed.append(99)
    report.aligned = -1

    for other in (aligned, sibling):
        untouched = other.chem.alignment_report("mol")
        assert untouched.failed == [] and untouched.aligned == 2


def test_copy_molecules_carries_the_alignment_report():
    """B6: the copy starts from the source's whole state, report included, but shares nothing."""
    aligned = _pframe(2).chem.align_depictions("mol", "c1ccccc1")
    copied = aligned.chem.copy_molecules("mol", "mol_copy")

    source_report = aligned.chem.alignment_report("mol")
    copy_report = copied.chem.alignment_report("mol_copy")
    assert copy_report == source_report
    assert copy_report is not source_report

    copy_report.failed.append(7)
    assert aligned.chem.alignment_report("mol").failed == []


def test_reset_depictions_keeps_sibling_state():
    base = _pframe(2).chem.highlight("mol", "[OH]")
    sibling = base.filter(pl.col("mol").is_not_null())
    reset = base.chem.reset_depictions("mol")
    assert reset.schema["mol"].token is None
    assert len(pe.context_for_token(sibling.schema["mol"].token).callbacks) == 1


def test_generated_display_columns_carry_copied_context():
    base = _pframe(1, x=["[OH]"]).chem.set_render_options("mol", image_format="svg", width=133)
    out = base.chem.highlight_using_column("mol", "x")
    token = out.schema["highlighted_substructures"].token
    assert token and token != base.schema["mol"].token
    assert pe.context_for_token(token).width == 133
    sim = base.chem.fingerprint_similarity("mol")
    assert pe.context_for_token(sim.schema["target_similarity"].token).image_format == "svg"


def test_copy_molecules_mints_new_token():
    base = _pframe(1).chem.highlight("mol", "[OH]")
    out = base.chem.copy_molecules("mol", "copy")
    assert out.schema["copy"].token not in (None, base.schema["mol"].token)
    assert out.get_column("copy")[0] is not out.get_column("mol")[0]


def test_highlight_using_column_and_color_column_keep_owners():
    df = pl.DataFrame([
        pl.Series("mol", _mols(2), dtype=oeplr.MoleculeType()),
        pl.Series("pat", ["c1ccccc1", None]),
        pl.Series("col", ["#00FF00", None]),
    ])
    out = df.chem.highlight_using_column("mol", "pat", color_column="col").drop("mol")
    del df
    gc.collect()
    html = pe.render_polars_dataframe(out)
    assert html.count("<img") + html.count("<svg") == 2


def test_fingerprint_similarity_displays_keep_molecules():
    df = pl.DataFrame([pl.Series("mol", [*_mols(1), None, *_mols(1, "c1ccccc1OC")], dtype=oeplr.MoleculeType())])
    out = df.chem.fingerprint_similarity("mol").drop("mol")
    del df
    gc.collect()
    assert out["fingerprint_tanimoto"][1] is None and out["fingerprint_tanimoto"][0] == pytest.approx(1.0)
    html = pe.render_polars_dataframe(out)
    assert html.count("<img") + html.count("<svg") == 4


def test_polars_attach_is_idempotent_and_guarded(monkeypatch):
    pe._attach()
    pe._attach()
    monkeypatch.setattr(pe, "_MIN_OEPOLARS", (99, 0, 0))
    monkeypatch.setattr(pe, "_ATTACHED", False)
    with pytest.warns(CNotebookWarning, match="polars integration disabled"):
        pe._attach()
    monkeypatch.setattr(pe, "_MIN_OEPOLARS", (0, 4, 0))
    monkeypatch.setattr(pe, "_ATTACHED", False)
    pe._attach()
    assert not hasattr(pe, "_dataframe_column_contexts")


@pytest.mark.parametrize("without_packaging", [False, True], ids=["packaging", "fallback"])
@pytest.mark.parametrize(("version", "attaches"), [
    ("0.4.0", True),
    ("0.3.9", False),
    ("0.4.0.dev1", False),
    ("0.4.0rc1", False),
    ("0.4.0.post1", True),
    ("0.4.0-1", True),
    ("0.4.0post1", True),
    ("0.4.0-r1", True),
    ("0.4.0.post1.dev1", True),
    ("0.4.0+corp", True),
    ("1!0.4.0", True),
    ("not-a-version", False),
    # Release segments shorter or longer than the floor, and the v prefix
    ("0.4", True),
    ("1", True),
    ("v0.4.0", True),
])
def test_polars_attach_version_guard(monkeypatch, version, attaches, without_packaging):
    """PEP 440 ordering decides: pre-releases and dev builds of the floor are below it,
    post-releases are not. The packaging-less fallback must reach the same verdict."""
    if without_packaging:
        # A None entry in sys.modules makes the import of packaging fail
        monkeypatch.setitem(sys.modules, "packaging.version", None)
    monkeypatch.setattr(oeplr, "__version__", version)
    monkeypatch.setattr(pe, "_ATTACHED", False)
    if attaches:
        with warnings.catch_warnings():
            warnings.simplefilter("error", CNotebookWarning)
            pe._attach()
        assert pe._ATTACHED
    else:
        with pytest.warns(CNotebookWarning, match="polars integration disabled"):
            pe._attach()
        assert not pe._ATTACHED


def test_at_least_without_packaging_rejects_an_unreadable_version(monkeypatch):
    """The fallback parser reports a version it cannot read, like packaging does."""
    monkeypatch.setitem(sys.modules, "packaging.version", None)
    with pytest.raises(ValueError, match="release number"):
        pe._at_least("not-a-version", (0, 4, 0))


def _spy_on_highlight_column(monkeypatch) -> dict:
    """Record the arguments the polars accessor hands to :func:`columnops.build_highlight_column`."""
    recorded: dict = {}
    real = columnops.build_highlight_column

    def spy(mols, patterns, **kwargs):
        recorded["patterns"] = patterns
        recorded["colors"] = kwargs.get("colors")
        return real(mols, patterns, **kwargs)

    monkeypatch.setattr(columnops, "build_highlight_column", spy)
    return recorded


def test_highlight_using_column_passes_missing_entries_as_none(monkeypatch):
    """Null pattern and colour cells reach the column operation as ``None``."""
    recorded = _spy_on_highlight_column(monkeypatch)
    df = pl.DataFrame([
        pl.Series("mol", _mols(2), dtype=oeplr.MoleculeType()),
        pl.Series("pat", ["c1ccccc1", None]),
        pl.Series("col", [None, "#00FF00"]),
    ])

    df.chem.highlight_using_column("mol", "pat", color_column="col")

    assert recorded["patterns"] == ["c1ccccc1", None]
    assert recorded["colors"] == [None, "#00FF00"]


def test_highlight_using_column_accepts_a_falsy_color_column_name(monkeypatch):
    """The colour column is tested against None, so a column named "" is still used."""
    recorded = _spy_on_highlight_column(monkeypatch)
    # Built from a mapping: polars renames an empty Series name when it builds a frame
    # from a list of Series, and the point of the test is the empty column name.
    df = pl.DataFrame({"pat": ["c1ccccc1"], "": ["#00FF00"]}).with_columns(
        pl.Series("mol", _mols(1), dtype=oeplr.MoleculeType())
    )

    df.chem.highlight_using_column("mol", "pat", color_column="")

    assert recorded["colors"] == ["#00FF00"]


def test_highlight_using_column_inplace_reports_the_ignored_argument():
    """A polars frame cannot be modified in place, so inplace=True is reported once."""
    df = _pframe(1, pat=["c1ccccc1"])
    with pytest.warns(CNotebookWarning, match="immutable") as record:
        out = df.chem.highlight_using_column("mol", "pat", inplace=True)
    assert sum("immutable" in str(w.message) for w in record) == 1
    assert "highlighted_substructures" in out.columns
    assert "highlighted_substructures" not in df.columns


def test_fingerprint_similarity_inplace_reports_the_ignored_argument():
    """A polars frame cannot be modified in place, so inplace=True is reported once."""
    df = _pframe(1)
    with pytest.warns(CNotebookWarning, match="immutable") as record:
        out = df.chem.fingerprint_similarity("mol", inplace=True)
    assert sum("immutable" in str(w.message) for w in record) == 1
    assert "fingerprint_tanimoto" in out.columns
    assert "fingerprint_tanimoto" not in df.columns


def test_inplace_false_is_silent():
    """The default path reports nothing."""
    df = _pframe(1, pat=["c1ccccc1"])
    with warnings.catch_warnings():
        warnings.simplefilter("error", CNotebookWarning)
        df.chem.highlight_using_column("mol", "pat", inplace=False)
        df.chem.fingerprint_similarity("mol", inplace=False)


def test_copy_molecules_copies_conformers():
    """The copy is a distinct molecule that keeps the source's conformer ensemble."""
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "CCO")
    coords = oechem.OEFloatArray(mol.NumAtoms() * 3)
    for conformer in range(1, 3):
        for index in range(len(coords)):
            coords[index] = float(conformer + index)
        mol.NewConf(coords)
    df = pl.DataFrame([pl.Series("mol", [mol], dtype=oeplr.MoleculeType())])

    out = df.chem.copy_molecules("mol", "copy")

    copied = out.get_column("copy")[0]
    assert copied is not mol
    assert copied.NumConfs() == mol.NumConfs() == 3


def test_alignment_report_reports_a_missing_column_as_a_value_error():
    """alignment_report validates its column like every other molecule-column accessor."""
    df = _pframe(1)
    with pytest.raises(ValueError, match="nope"):
        df.chem.alignment_report("nope")
    assert df.chem.alignment_report("mol") is None
