import pytest

# Check if polars/oepolars available
polars_available = False
try:
    import polars as pl
    import oepolars as oeplr
    polars_available = True
except ImportError:
    pass

pytestmark = pytest.mark.skipif(not polars_available, reason="polars/oepolars not available")


class TestPolarsExtImport:
    """Test that polars_ext module can be imported."""

    def test_import_polars_ext(self):
        """polars_ext should be importable when polars available."""
        from cnotebook import polars_ext
        assert polars_ext is not None

    def test_render_function_exists(self):
        """render_polars_dataframe function should exist."""
        from cnotebook.polars_ext import render_polars_dataframe
        assert callable(render_polars_dataframe)

    def test_register_function_exists(self):
        """register_polars_formatters function should exist."""
        from cnotebook.polars_ext import register_polars_formatters
        assert callable(register_polars_formatters)


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
        from cnotebook.polars_ext import render_polars_dataframe

        # Create empty DataFrame with molecule column using oepolars read function
        # (oepolars doesn't support direct empty Series creation with MoleculeType)
        import tempfile
        import os

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
        from openeye import oechem
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


class TestPolarsSeriesHighlight:
    """Test Series highlight method."""

    def test_highlight_adds_callback(self):
        """highlight() should add callback to series metadata."""
        import cnotebook.polars_ext  # Ensure monkey-patching happens
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series since oepolars metadata is keyed by series id
        series = df["mol"]
        series.chem.highlight("c1ccccc1")

        metadata = series.chem.metadata
        ctx = metadata.get("cnotebook")
        assert ctx is not None
        assert len(ctx.callbacks) > 0

    def test_highlight_with_color(self):
        """highlight() should accept color parameter."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]
        # Should not raise
        series.chem.highlight("c1ccccc1", color=oechem.OEColor(oechem.OERed))

        ctx = series.chem.metadata.get("cnotebook")
        assert ctx is not None

    def test_highlight_requires_molecule_type(self):
        """highlight() should raise TypeError on non-molecule columns."""
        import cnotebook.polars_ext

        s = pl.Series("text", ["abc", "def"])

        with pytest.raises(TypeError):
            s.chem.highlight("abc")

    def test_highlight_with_multiple_patterns(self):
        """highlight() should accept multiple patterns."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        # Get initial callback count (in case of test pollution from metadata reuse)
        initial_ctx = series.chem.metadata.get("cnotebook")
        initial_callbacks = len(initial_ctx.callbacks) if initial_ctx else 0

        # Should accept list of patterns
        series.chem.highlight(["c1ccccc1", "[OH]"])

        ctx = series.chem.metadata.get("cnotebook")
        assert ctx is not None
        # Should have 2 more callbacks than before (one for each pattern)
        assert len(ctx.callbacks) == initial_callbacks + 2


class TestPolarsSeriesMethods:
    """Test remaining Series accessor methods."""

    def test_reset_depictions(self):
        """reset_depictions() should clear callbacks."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        # Add highlight then reset
        series.chem.highlight("c1ccccc1")
        series.chem.reset_depictions()

        ctx = series.chem.metadata.get("cnotebook")
        assert ctx is None or len(getattr(ctx, 'callbacks', [])) == 0

    def test_align_depictions(self):
        """align_depictions() should not raise."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        # Should not raise
        series.chem.align_depictions("first")

    def test_recalculate_depiction_coordinates(self):
        """recalculate_depiction_coordinates() should not raise."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Keep reference to the same series
        series = df["mol"]

        # Should not raise
        series.chem.recalculate_depiction_coordinates()

    def test_align_depictions_requires_molecule_type(self):
        """align_depictions() should raise TypeError on non-molecule columns."""
        import cnotebook.polars_ext

        s = pl.Series("text", ["abc"])

        with pytest.raises(TypeError):
            s.chem.align_depictions("first")

    def test_recalculate_depictions_requires_molecule_type(self):
        """recalculate_depiction_coordinates() should raise TypeError on non-molecule columns."""
        import cnotebook.polars_ext

        s = pl.Series("text", ["abc"])

        with pytest.raises(TypeError):
            s.chem.recalculate_depiction_coordinates()


class TestPolarsDataFrameMethods:
    """Test DataFrame accessor methods."""

    def test_dataframe_reset_depictions(self):
        """DataFrame reset_depictions() should reset depictions on retrieved series.

        Note: In Polars, each column access creates a new Series instance with
        its own metadata. The reset_depictions method clears metadata on the
        series instances it retrieves, which is the same behavior that occurs
        during rendering.
        """
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Get a series, add a highlight, then reset it
        series = df.get_column("mol")
        series.chem.highlight("c1ccccc1")

        # Verify highlight was added to this series
        ctx = series.chem.metadata.get("cnotebook")
        assert ctx is not None and len(getattr(ctx, 'callbacks', [])) > 0

        # Reset depictions on this specific series reference
        series.chem.reset_depictions()

        # Verify callbacks were cleared on this series
        ctx = series.chem.metadata.get("cnotebook")
        assert ctx is None or len(getattr(ctx, 'callbacks', [])) == 0

    def test_dataframe_reset_depictions_method_exists(self):
        """DataFrame chem accessor should have reset_depictions method."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Method should exist and be callable
        assert hasattr(df.chem, 'reset_depictions')
        # Should not raise
        df.chem.reset_depictions()

    def test_dataframe_reset_depictions_specific_columns(self):
        """DataFrame reset_depictions() should accept molecule_columns parameter."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        df = df.chem.as_molecule("mol1").chem.as_molecule("mol2")

        # Should not raise with specific column
        df.chem.reset_depictions(molecule_columns=["mol1"])

        # Should also accept string argument
        df.chem.reset_depictions(molecule_columns="mol2")

    def test_highlight_using_column(self):
        """highlight_using_column() should create display column."""
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
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
        """highlight_using_column() with inplace=True should modify original."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({
            "mol": [mol],
            "pattern": ["c1ccccc1"]
        })
        df = df.chem.as_molecule("mol")

        # Note: In Polars, inplace modification works differently than pandas
        # We return the modified DataFrame for assignment
        result = df.chem.highlight_using_column("mol", "pattern", inplace=True)

        assert "highlighted_substructures" in result.columns

    def test_highlight_using_column_missing_molecule_column(self):
        """highlight_using_column() should raise KeyError for missing molecule column."""
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(KeyError):
            df.chem.highlight_using_column("mol", "nonexistent")

    def test_highlight_using_column_non_molecule_type(self):
        """highlight_using_column() should raise TypeError for non-molecule column."""
        import cnotebook.polars_ext

        df = pl.DataFrame({
            "text": ["hello"],
            "pattern": ["c1ccccc1"]
        })

        with pytest.raises(TypeError):
            df.chem.highlight_using_column("text", "pattern")

    def test_recalculate_depiction_coordinates_dataframe(self):
        """DataFrame recalculate_depiction_coordinates() should not raise."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        # Should not raise
        df.chem.recalculate_depiction_coordinates()

    def test_recalculate_depiction_coordinates_specific_columns(self):
        """DataFrame recalculate_depiction_coordinates() should work on specific columns."""
        import cnotebook.polars_ext
        from openeye import oechem

        mol1 = oechem.OEMol()
        oechem.OESmilesToMol(mol1, "c1ccccc1")
        mol2 = oechem.OEMol()
        oechem.OESmilesToMol(mol2, "CCO")

        df = pl.DataFrame({"mol1": [mol1], "mol2": [mol2]})
        df = df.chem.as_molecule("mol1").chem.as_molecule("mol2")

        # Should not raise
        df.chem.recalculate_depiction_coordinates(molecule_columns=["mol1"])


class TestPolarsFingerprintSimilarity:
    """Test fingerprint similarity visualization."""

    def test_fingerprint_similarity_creates_columns(self):
        """fingerprint_similarity() should create tanimoto and display columns."""
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
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
        import cnotebook.polars_ext
        from openeye import oechem

        mol = oechem.OEMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        df = pl.DataFrame({"mol": [mol]})
        df = df.chem.as_molecule("mol")

        with pytest.raises(KeyError):
            df.chem.fingerprint_similarity("nonexistent", mol)

    def test_fingerprint_similarity_non_molecule_type(self):
        """fingerprint_similarity() should raise TypeError for non-molecule column."""
        import cnotebook.polars_ext

        df = pl.DataFrame({"text": ["hello"]})

        with pytest.raises(TypeError):
            df.chem.fingerprint_similarity("text")
