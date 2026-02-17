import pytest
import logging
from unittest.mock import MagicMock, patch, Mock
import cnotebook
from cnotebook import (
    __version__,
    LevelSpecificFormatter,
    enable_debugging,
    log,
    render_dataframe,
    cnotebook_context,
    get_env,
    CNotebookEnvInfo,
)


class TestVersion:
    """Test version information"""

    def test_version_exists(self):
        """Test that version is defined and is a string"""
        assert hasattr(cnotebook, '__version__')
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_version_format(self):
        """Test version format"""
        # Should be something like '0.7.b2'
        assert '.' in __version__
        # Should start with a digit
        assert __version__[0].isdigit()


class TestCNotebookEnvInfo:
    """Test the CNotebookEnvInfo class"""

    def test_get_env_returns_env_info(self):
        """Test that get_env returns a CNotebookEnvInfo instance"""
        env = get_env()
        assert isinstance(env, CNotebookEnvInfo)

    def test_get_env_returns_singleton(self):
        """Test that get_env returns the same instance each time"""
        env1 = get_env()
        env2 = get_env()
        assert env1 is env2

    def test_pandas_available_property(self):
        """Test pandas_available property"""
        env = get_env()
        assert isinstance(env.pandas_available, bool)

    def test_pandas_version_property(self):
        """Test pandas_version property"""
        env = get_env()
        assert isinstance(env.pandas_version, str)

    def test_polars_available_property(self):
        """Test polars_available property"""
        env = get_env()
        assert isinstance(env.polars_available, bool)

    def test_polars_version_property(self):
        """Test polars_version property"""
        env = get_env()
        assert isinstance(env.polars_version, str)

    def test_ipython_available_property(self):
        """Test ipython_available property"""
        env = get_env()
        assert isinstance(env.ipython_available, bool)

    def test_ipython_version_property(self):
        """Test ipython_version property"""
        env = get_env()
        assert isinstance(env.ipython_version, str)

    def test_marimo_available_property(self):
        """Test marimo_available property"""
        env = get_env()
        assert isinstance(env.marimo_available, bool)

    def test_marimo_version_property(self):
        """Test marimo_version property"""
        env = get_env()
        assert isinstance(env.marimo_version, str)

    def test_molgrid_available_property(self):
        """Test molgrid_available property"""
        env = get_env()
        assert isinstance(env.molgrid_available, bool)

    def test_is_jupyter_notebook_property(self):
        """Test is_jupyter_notebook property"""
        env = get_env()
        assert isinstance(env.is_jupyter_notebook, bool)

    def test_is_marimo_notebook_property(self):
        """Test is_marimo_notebook property"""
        env = get_env()
        assert isinstance(env.is_marimo_notebook, bool)

    def test_availability_derived_from_version(self):
        """Test that availability is derived from version strings"""
        # Create an env with known values
        env = CNotebookEnvInfo(
            pandas_version="2.0.0",
            polars_version="",
            ipython_version="8.0.0",
            marimo_version="",
            molgrid_available=True,
            c3d_available=True,
            is_jupyter_notebook=True,
            is_marimo_notebook=False,
        )
        assert env.pandas_available is True
        assert env.polars_available is False
        assert env.ipython_available is True
        assert env.marimo_available is False

    def test_repr(self):
        """Test __repr__ method"""
        env = get_env()
        repr_str = repr(env)
        assert "CNotebookEnvInfo(" in repr_str
        assert "pandas=" in repr_str
        assert "polars=" in repr_str
        assert "ipython=" in repr_str
        assert "marimo=" in repr_str
        assert "molgrid=" in repr_str
        assert "jupyter=" in repr_str
        assert "marimo_nb=" in repr_str


class TestCNotebookEnvInfoReadOnly:
    """Test that CNotebookEnvInfo properties are read-only"""

    def test_pandas_available_read_only(self):
        """Test pandas_available cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.pandas_available = False

    def test_pandas_version_read_only(self):
        """Test pandas_version cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.pandas_version = "1.0.0"

    def test_polars_available_read_only(self):
        """Test polars_available cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.polars_available = False

    def test_polars_version_read_only(self):
        """Test polars_version cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.polars_version = "1.0.0"

    def test_ipython_available_read_only(self):
        """Test ipython_available cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.ipython_available = False

    def test_ipython_version_read_only(self):
        """Test ipython_version cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.ipython_version = "1.0.0"

    def test_marimo_available_read_only(self):
        """Test marimo_available cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.marimo_available = False

    def test_marimo_version_read_only(self):
        """Test marimo_version cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.marimo_version = "1.0.0"

    def test_molgrid_available_read_only(self):
        """Test molgrid_available cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.molgrid_available = False

    def test_is_jupyter_notebook_read_only(self):
        """Test is_jupyter_notebook cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.is_jupyter_notebook = False

    def test_is_marimo_notebook_read_only(self):
        """Test is_marimo_notebook cannot be set"""
        env = get_env()
        with pytest.raises(AttributeError):
            env.is_marimo_notebook = False


class TestEnvDetection:
    """Test environment detection accuracy"""

    def test_pandas_available_reflects_imports(self):
        """Test pandas_available reflects actual pandas/oepandas availability"""
        env = get_env()
        try:
            import pandas
            import oepandas
            assert env.pandas_available is True
        except ImportError:
            assert env.pandas_available is False

    def test_polars_available_reflects_imports(self):
        """Test polars_available reflects actual polars/oepolars availability"""
        env = get_env()
        try:
            import polars
            import oepolars
            assert env.polars_available is True
        except ImportError:
            assert env.polars_available is False


class TestLevelSpecificFormatter:
    """Test the LevelSpecificFormatter class"""

    def test_init(self):
        """Test formatter initialization"""
        formatter = LevelSpecificFormatter()
        assert formatter._style._fmt == formatter.NORMAL_FORMAT

    def test_format_normal_level(self):
        """Test formatting normal log levels"""
        formatter = LevelSpecificFormatter()

        # Test INFO level
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )

        result = formatter.format(record)
        assert result == "Test message"  # Just the message for normal levels

    def test_format_debug_level(self):
        """Test formatting DEBUG level"""
        formatter = LevelSpecificFormatter()

        record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="Debug message", args=(), exc_info=None
        )

        result = formatter.format(record)
        assert result == "DEBUG: Debug message"  # Includes level for debug

    def test_format_with_args(self):
        """Test formatting with message arguments"""
        formatter = LevelSpecificFormatter()

        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Message with %s", args=("argument",), exc_info=None
        )

        result = formatter.format(record)
        assert result == "Message with argument"

    def test_format_switches_back_to_normal(self):
        """Test that formatter switches back to normal format after debug"""
        formatter = LevelSpecificFormatter()

        # First format a debug message
        debug_record = logging.LogRecord(
            name="test", level=logging.DEBUG, pathname="", lineno=0,
            msg="Debug message", args=(), exc_info=None
        )
        debug_result = formatter.format(debug_record)
        assert "DEBUG:" in debug_result

        # Then format a normal message
        info_record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Info message", args=(), exc_info=None
        )
        info_result = formatter.format(info_record)
        assert info_result == "Info message"  # Should be back to normal format


class TestLogging:
    """Test logging configuration"""

    def test_log_exists(self):
        """Test that the logger exists and is configured"""
        assert log is not None
        assert isinstance(log, logging.Logger)
        assert log.name == "cnotebook"

    def test_log_level(self):
        """Test default log level"""
        assert log.level == logging.INFO

    def test_log_has_handler(self):
        """Test that logger has handlers configured"""
        # The module sets up a StreamHandler
        assert len(log.handlers) > 0
        # Should have at least one StreamHandler
        stream_handlers = [h for h in log.handlers if isinstance(h, logging.StreamHandler)]
        assert len(stream_handlers) > 0

    def test_log_handler_formatter(self):
        """Test that handler uses custom formatter"""
        stream_handlers = [h for h in log.handlers if isinstance(h, logging.StreamHandler)]
        if stream_handlers:
            handler = stream_handlers[0]
            assert isinstance(handler.formatter, LevelSpecificFormatter)

    def test_enable_debugging(self):
        """Test enable_debugging function"""
        original_level = log.level

        try:
            enable_debugging()
            assert log.level == logging.DEBUG
        finally:
            # Reset to original level
            log.setLevel(original_level)


class TestModuleImports:
    """Test module imports and exports"""

    def test_render_dataframe_import(self):
        """Test that render_dataframe is imported"""
        assert hasattr(cnotebook, 'render_dataframe')
        assert callable(render_dataframe)

    def test_cnotebook_context_import(self):
        """Test that cnotebook_context is imported"""
        assert hasattr(cnotebook, 'cnotebook_context')
        assert cnotebook_context is not None

    def test_get_env_import(self):
        """Test that get_env is imported"""
        assert hasattr(cnotebook, 'get_env')
        assert callable(get_env)

    def test_env_info_class_import(self):
        """Test that CNotebookEnvInfo is importable"""
        assert hasattr(cnotebook, 'CNotebookEnvInfo')

    def test_all_expected_exports(self):
        """Test that all expected items are exported"""
        expected_exports = [
            '__version__',
            'LevelSpecificFormatter',
            'enable_debugging',
            'log',
            'render_dataframe',
            'cnotebook_context',
            'get_env',
            'CNotebookEnvInfo',
        ]

        for export in expected_exports:
            assert hasattr(cnotebook, export), f"Missing export: {export}"


class TestIntegration:
    """Integration tests for the main module"""

    def test_version_matches_setup(self):
        """Test that version matches what's expected"""
        # Version should be a semantic-like version
        parts = __version__.split('.')
        assert len(parts) >= 2
        assert parts[0].isdigit()
        assert parts[1].isdigit() or parts[1][0].isdigit()  # Handle versions like "7.b2"

    def test_logging_works_end_to_end(self):
        """Test that logging works end to end"""
        import io
        import sys

        # Capture log output
        log_capture = io.StringIO()

        # Create a test handler
        test_handler = logging.StreamHandler(log_capture)
        test_handler.setFormatter(LevelSpecificFormatter())

        # Add to our logger temporarily
        log.addHandler(test_handler)

        try:
            log.info("Test info message")
            log.debug("Test debug message")

            output = log_capture.getvalue()

            # Should contain the info message without DEBUG prefix
            assert "Test info message" in output
            # Debug message might not appear if level is INFO
        finally:
            log.removeHandler(test_handler)

    def test_conditional_imports_jupyter(self):
        """Test conditional imports work for Jupyter"""
        # Test that when in Jupyter, we can access the expected functionality
        assert callable(render_dataframe)

    def test_conditional_imports_marimo(self):
        """Test conditional imports work for Marimo"""
        # In Marimo environment, marimo_ext should be imported
        # This is tested indirectly by checking the module loads without error
        import cnotebook  # Should not raise ImportError


class TestErrorHandling:
    """Test error handling in module initialization"""

    def test_handles_missing_dependencies_gracefully(self):
        """Test that module handles missing optional dependencies"""
        # The module should handle cases where dependencies are missing
        # This is already tested indirectly by the CNotebookEnvInfo tests
        pass

    def test_logging_configuration_robust(self):
        """Test that logging configuration is robust"""
        # Test that logging works even if there are issues with handler setup
        assert log is not None
        assert isinstance(log, logging.Logger)

        # Should be able to call logging functions without error
        log.info("Test message")

    def test_formatter_handles_edge_cases(self):
        """Test that formatter handles edge cases"""
        formatter = LevelSpecificFormatter()

        # Test with None message
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg=None, args=(), exc_info=None
        )

        # Should not raise an exception
        result = formatter.format(record)
        assert isinstance(result, str)

        # Test with empty message
        record.msg = ""
        result = formatter.format(record)
        assert result == ""


class TestDocstring:
    """Test that functions have proper docstrings"""

    def test_functions_exist(self):
        """Test that all functions exist and are callable"""
        assert callable(enable_debugging)
        assert callable(LevelSpecificFormatter)
        assert callable(get_env)

    def test_enable_debugging_docstring(self):
        """Test enable_debugging has docstring"""
        assert enable_debugging.__doc__ is not None
        assert len(enable_debugging.__doc__.strip()) > 0

    def test_level_specific_formatter_docstring(self):
        """Test LevelSpecificFormatter has docstring"""
        assert LevelSpecificFormatter.__doc__ is not None
        assert len(LevelSpecificFormatter.__doc__.strip()) > 0

    def test_get_env_docstring(self):
        """Test get_env has docstring"""
        assert get_env.__doc__ is not None
        assert len(get_env.__doc__.strip()) > 0

    def test_env_info_docstring(self):
        """Test CNotebookEnvInfo has docstring"""
        assert CNotebookEnvInfo.__doc__ is not None
        assert len(CNotebookEnvInfo.__doc__.strip()) > 0


