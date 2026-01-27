import pytest


class TestBackendDetection:
    """Test auto-detection of available backends."""

    def test_import_cnotebook_never_fails(self):
        """Importing cnotebook should never fail regardless of backends."""
        import cnotebook
        assert cnotebook is not None

    def test_pandas_available_via_get_env(self):
        """get_env().pandas_available should reflect pandas availability."""
        import cnotebook

        env = cnotebook.get_env()
        try:
            import pandas
            import oepandas
            assert env.pandas_available is True
        except ImportError:
            assert env.pandas_available is False

    def test_polars_available_via_get_env(self):
        """get_env().polars_available should reflect polars availability."""
        import cnotebook

        env = cnotebook.get_env()
        try:
            import polars
            import oepolars
            assert env.polars_available is True
        except ImportError:
            assert env.polars_available is False

    def test_version_accessible(self):
        """Version should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, '__version__')
        assert isinstance(cnotebook.__version__, str)

    def test_cnotebook_context_accessible(self):
        """cnotebook_context should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, 'cnotebook_context')

    def test_get_env_accessible(self):
        """get_env should always be accessible."""
        import cnotebook
        assert hasattr(cnotebook, 'get_env')
        assert callable(cnotebook.get_env)
