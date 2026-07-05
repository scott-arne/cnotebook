import importlib.util

import pytest
import logging
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict
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
        pandas_available = (
            importlib.util.find_spec("pandas") is not None
            and importlib.util.find_spec("oepandas") is not None
        )
        assert env.pandas_available is pandas_available

    def test_polars_available_reflects_imports(self):
        """Test polars_available reflects actual polars/oepolars availability"""
        env = get_env()
        polars_available = (
            importlib.util.find_spec("polars") is not None
            and importlib.util.find_spec("oepolars") is not None
        )
        assert env.polars_available is polars_available


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

    def test_all_expected_exports(self):
        """Public package exports should point at the imported implementations."""
        assert cnotebook.__version__ == __version__
        assert cnotebook.LevelSpecificFormatter is LevelSpecificFormatter
        assert cnotebook.enable_debugging is enable_debugging
        assert cnotebook.log is log
        assert cnotebook.render_dataframe is render_dataframe
        assert cnotebook.cnotebook_context is cnotebook_context
        assert cnotebook.get_env is get_env
        assert cnotebook.CNotebookEnvInfo is CNotebookEnvInfo


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

class TestErrorHandling:
    """Test error handling in module initialization"""

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


class TestDisplayFunction:
    """Test the display() function"""

    @patch('cnotebook._display_html')
    def test_display_molecule(self, mock_display_html):
        """Test display with an OEMolBase molecule"""
        from cnotebook import display

        mock_display_html.side_effect = lambda html, env: html

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        result = display(mol)

        mock_display_html.assert_called_once()
        # Real oemol_to_html produces an HTML img tag
        assert isinstance(result, str)
        assert "<" in result

    @patch('cnotebook._display_html')
    def test_display_molecule_with_ctx(self, mock_display_html):
        """Test display with an explicit CNotebookContext"""
        from cnotebook import display
        from cnotebook.context import CNotebookContext

        mock_display_html.side_effect = lambda html, env: html

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        custom_ctx = CNotebookContext(width=300, height=300)

        result = display(mol, ctx=custom_ctx)

        mock_display_html.assert_called_once()
        assert isinstance(result, str)
        assert "<" in result

    @patch('cnotebook._display_html')
    def test_display_oedisplay(self, mock_display_html):
        """Test display with an OE2DMolDisplay object"""
        from cnotebook import display

        mock_display_html.side_effect = lambda html, env: html

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)
        disp = oedepict.OE2DMolDisplay(mol, oedepict.OE2DMolDisplayOptions())

        result = display(disp)

        mock_display_html.assert_called_once()
        assert isinstance(result, str)
        assert "<" in result

    @patch('cnotebook._display_html')
    def test_display_pandas_dataframe(self, mock_display_html):
        """Test display with a Pandas DataFrame"""
        from cnotebook import display

        mock_display_html.side_effect = lambda html, env: html

        env = get_env()
        if not env.pandas_available:
            pytest.skip("Pandas not available")

        import pandas as pd
        df = pd.DataFrame({"a": [1, 2], "b": [3, 4]})

        result = display(df)

        mock_display_html.assert_called_once()
        assert isinstance(result, str)
        assert "<" in result

    def test_display_unsupported_type_raises(self):
        """Test display raises TypeError for unsupported types"""
        from cnotebook import display

        with pytest.raises(TypeError, match="Cannot display object of type int"):
            display(42)


class TestDisplayHtml:
    """Test the _display_html() function"""

    def test_display_html_fallback(self):
        """Test that _display_html returns raw HTML when no notebook env is available"""
        from cnotebook import _display_html

        env = CNotebookEnvInfo(
            pandas_version="",
            polars_version="",
            ipython_version="",
            marimo_version="",
            molgrid_available=False,
            c3d_available=False,
            is_jupyter_notebook=False,
            is_marimo_notebook=False,
        )

        html = "<div>test</div>"
        result = _display_html(html, env)
        assert result == html


class TestEnvC3dProperty:
    """Test CNotebookEnvInfo c3d-related properties"""

    def test_env_c3d_available_property(self):
        """Test that c3d_available returns a bool"""
        env = get_env()
        assert isinstance(env.c3d_available, bool)

    def test_env_repr_contains_c3d(self):
        """Test that repr() includes c3d info"""
        env = get_env()
        repr_str = repr(env)
        assert "c3d=" in repr_str


class TestDisplayPolarsDataFrame:
    """Test display() with Polars DataFrame."""

    @patch('cnotebook._display_html')
    def test_display_polars_dataframe(self, mock_display_html):
        """Test display with a Polars DataFrame."""
        from cnotebook import display

        mock_display_html.side_effect = lambda html, env: html

        env = get_env()
        if not env.polars_available:
            pytest.skip("Polars not available")

        import polars as pl
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})

        result = display(df)

        mock_display_html.assert_called_once()
        assert isinstance(result, str)
        assert "<" in result


class TestDisplayHtmlEnvironments:
    """Test _display_html with different environments."""

    def test_display_html_ipython(self):
        """Test _display_html uses IPython display when available."""
        from cnotebook import _display_html

        env = CNotebookEnvInfo(
            pandas_version="",
            polars_version="",
            ipython_version="8.0.0",
            marimo_version="",
            molgrid_available=False,
            c3d_available=False,
            is_jupyter_notebook=False,
            is_marimo_notebook=False,
        )

        mock_html_class = MagicMock()
        mock_ipy_display = MagicMock(return_value="displayed")

        with patch('IPython.display.HTML', mock_html_class), \
             patch('IPython.display.display', mock_ipy_display):
            _display_html("<div>test</div>", env)
            mock_html_class.assert_called_once_with("<div>test</div>")

    def test_display_html_marimo(self):
        """Test _display_html uses marimo.Html when in marimo."""
        from cnotebook import _display_html

        env = CNotebookEnvInfo(
            pandas_version="",
            polars_version="",
            ipython_version="",
            marimo_version="0.1.0",
            molgrid_available=False,
            c3d_available=False,
            is_jupyter_notebook=False,
            is_marimo_notebook=True,
        )

        mock_mo = MagicMock()
        mock_mo.Html.return_value = "marimo_html"

        with patch.dict('sys.modules', {'marimo': mock_mo}):
            result = _display_html("<div>test</div>", env)
            mock_mo.Html.assert_called_once_with("<div>test</div>")
            assert result == "marimo_html"


class TestMissingOptionalExport:
    """Test the module __getattr__ that explains unavailable optional exports."""

    def _unbind_exports(self, *names):
        """Remove optional exports from the module, simulating a failed import.

        :param names: Module attribute names to remove.
        :returns: Mapping of removed names to their previous values for restoration.
        """
        removed = {}
        for name in names:
            if name in cnotebook.__dict__:
                removed[name] = cnotebook.__dict__.pop(name)
        return removed

    def test_missing_anywidget_raises_actionable_import_error(self):
        """Accessing molgrid without anywidget warns and raises with install guidance."""
        removed = self._unbind_exports("molgrid", "MolGrid", "BEST_FIT_ORIENTATION")
        try:
            real_find_spec = importlib.util.find_spec

            def fake_find_spec(name, *args, **kwargs):
                if name == "anywidget":
                    return None
                return real_find_spec(name, *args, **kwargs)

            with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
                    patch.object(cnotebook.log, "warning") as mock_warn:
                with pytest.raises(ImportError, match="requires the optional 'anywidget'"):
                    cnotebook.molgrid
                mock_warn.assert_called_once()
                assert "anywidget" in mock_warn.call_args[0][0]
        finally:
            cnotebook.__dict__.update(removed)

    def test_present_anywidget_reports_underlying_failure(self):
        """When anywidget is present but grid still failed, point at cnotebook.grid."""
        removed = self._unbind_exports("molgrid", "MolGrid", "BEST_FIT_ORIENTATION")
        try:
            real_find_spec = importlib.util.find_spec
            fake_spec = MagicMock()

            def fake_find_spec(name, *args, **kwargs):
                if name == "anywidget":
                    return fake_spec
                return real_find_spec(name, *args, **kwargs)

            with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
                    patch.object(cnotebook.log, "warning") as mock_warn:
                with pytest.raises(ImportError, match="cnotebook.grid"):
                    cnotebook.MolGrid
                mock_warn.assert_called_once()
        finally:
            cnotebook.__dict__.update(removed)

    def test_missing_c3d_reports_underlying_failure(self):
        """C3D has no optional dependency, so a failed import points at cnotebook.c3d."""
        removed = self._unbind_exports("C3D")
        try:
            with patch.object(cnotebook.log, "warning") as mock_warn:
                with pytest.raises(ImportError, match="cnotebook.c3d") as exc_info:
                    cnotebook.C3D
                # The message must not falsely blame anywidget: C3D does not use it.
                assert "anywidget" not in str(exc_info.value)
                mock_warn.assert_called_once()
        finally:
            cnotebook.__dict__.update(removed)

    def test_unknown_attribute_raises_attribute_error(self):
        """Unknown attributes still raise AttributeError, not ImportError."""
        with pytest.raises(AttributeError, match="does_not_exist"):
            cnotebook.does_not_exist
