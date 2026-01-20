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
