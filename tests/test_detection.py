import pytest


class TestBackendDetection:
    """Test auto-detection of available backends."""

    def test_import_cnotebook_never_fails(self):
        """Importing cnotebook should never fail regardless of backends."""
        import cnotebook
        assert cnotebook is not None

    def test_pandas_available_flag(self):
        """_pandas_available flag should reflect pandas availability."""
        import cnotebook

        try:
            import pandas
            import oepandas
            assert cnotebook._pandas_available is True
        except ImportError:
            assert cnotebook._pandas_available is False

    def test_polars_available_flag(self):
        """_polars_available flag should reflect polars availability."""
        import cnotebook

        try:
            import polars
            import oepolars
            assert cnotebook._polars_available is True
        except ImportError:
            assert cnotebook._polars_available is False

    def test_version_accessible(self):
        """Version should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, '__version__')
        assert isinstance(cnotebook.__version__, str)

    def test_cnotebook_context_accessible(self):
        """cnotebook_context should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, 'cnotebook_context')

    def test_render_molecule_grid_accessible(self):
        """render_molecule_grid should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, 'render_molecule_grid')
