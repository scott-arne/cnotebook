import importlib
import importlib.util
import itertools
import logging
import os
import subprocess
import sys
import textwrap
import warnings
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from openeye import oechem, oedepict

import cnotebook
from cnotebook import (
    CNotebookEnvInfo,
    LevelSpecificFormatter,
    __version__,
    cnotebook_context,
    enable_debugging,
    get_env,
    log,
    render_dataframe,
)
from cnotebook.core.errors import CNotebookWarning


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

    def test_get_env_returns_equal_values(self):
        """The environment is recomputed per call, so two calls agree without being one object."""
        env1 = get_env()
        env2 = get_env()
        assert env1 is not env2
        assert repr(env1) == repr(env2)

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


def _find_spec_without(*missing: str):
    """Build a ``find_spec`` replacement that reports *missing* as not installed.

    :param missing: Distribution names that should look absent.
    :returns: A callable with ``importlib.util.find_spec``'s signature.
    """
    real = importlib.util.find_spec

    def fake(name, *args, **kwargs):
        if name in missing:
            return None
        return real(name, *args, **kwargs)

    return fake


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

    @pytest.mark.parametrize("missing", ["pandas", "oepandas"])
    def test_pandas_needs_both_packages_installed(self, missing):
        """Detection asks the installed specs, so either half missing turns pandas off."""
        with patch("importlib.util.find_spec", side_effect=_find_spec_without(missing)):
            env = get_env()
        assert env.pandas_available is False
        assert env.pandas_version == ""

    @pytest.mark.parametrize("missing", ["polars", "oepolars"])
    def test_polars_needs_both_packages_installed(self, missing):
        """Detection asks the installed specs, so either half missing turns polars off."""
        with patch("importlib.util.find_spec", side_effect=_find_spec_without(missing)):
            env = get_env()
        assert env.polars_available is False
        assert env.polars_version == ""

    def test_molgrid_availability_follows_anywidget(self):
        """MolGrid's widget needs anywidget, and nothing is imported to find out."""
        with patch("importlib.util.find_spec", side_effect=_find_spec_without("anywidget")):
            assert get_env().molgrid_available is False
        assert get_env().molgrid_available is (importlib.util.find_spec("anywidget") is not None)


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
        assert log.level == logging.NOTSET

    def test_log_has_handler(self):
        """Test that logger has handlers configured"""
        # The module sets up a NullHandler
        assert len(log.handlers) > 0
        # Should have at least one NullHandler
        assert any(isinstance(h, logging.NullHandler) for h in log.handlers)

    def test_log_handler_formatter(self):
        """Test that handler uses custom formatter"""
        enable_debugging()
        debug_handlers = [h for h in log.handlers if getattr(h, "_cnotebook_debug", False)]
        assert len(debug_handlers) > 0
        handler = debug_handlers[0]
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
        """Public package exports should point at the imported implementations.

        Optional exports resolve through the module ``__getattr__``, so every name is
        read with ``getattr`` rather than assumed to be bound already.
        """
        expected = {
            "__version__": __version__,
            "LevelSpecificFormatter": LevelSpecificFormatter,
            "enable_debugging": enable_debugging,
            "log": log,
            "render_dataframe": render_dataframe,
            "cnotebook_context": cnotebook_context,
            "get_env": get_env,
            "CNotebookEnvInfo": CNotebookEnvInfo,
        }
        for name, value in expected.items():
            assert getattr(cnotebook, name) is value
        # `render_dataframe` is exported here because this environment has both halves of
        # the pandas backend; without them a star-import could not resolve it.
        assert get_env().pandas_available
        assert set(expected) <= set(cnotebook.__all__)

    def test_all_names_resolve_and_are_listed_once(self):
        """Every name in ``__all__`` has to resolve, or a star-import raises."""
        for name in cnotebook.__all__:
            assert getattr(cnotebook, name) is not None
        assert len(set(cnotebook.__all__)) == len(cnotebook.__all__)
        assert cnotebook.__all__ == sorted(cnotebook.__all__)
        # Each frame renderer is listed exactly when its backend is installed; both stay
        # reachable as attributes either way, and `__dir__` advertises all six.
        env = get_env()
        assert ("render_dataframe" in cnotebook.__all__) is env.pandas_available
        assert ("render_polars_dataframe" in cnotebook.__all__) is env.polars_available
        assert set(cnotebook._LAZY_EXPORTS) <= set(dir(cnotebook))


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


class TestLazyExports:
    """Test the module __getattr__ that resolves optional exports on first access."""

    def _unbind_exports(self, *names):
        """Forget resolved exports so the next access goes back through ``__getattr__``.

        :param names: Module attribute names to remove.
        :returns: Mapping of removed names to their previous values for restoration.
        """
        removed = {}
        for name in names:
            if name in cnotebook.__dict__:
                removed[name] = cnotebook.__dict__.pop(name)
            cnotebook._WARNED_EXPORTS.discard(name)
        return removed

    def test_lazy_export_resolves_to_the_submodule_object(self):
        """``cnotebook.MolGrid`` is the class from ``cnotebook.grid``, cached after first use."""
        from cnotebook.grid import MolGrid

        removed = self._unbind_exports("MolGrid")
        try:
            assert cnotebook.MolGrid is MolGrid
            # Resolution binds the name, so __getattr__ pays the import cost once.
            assert cnotebook.__dict__["MolGrid"] is MolGrid
        finally:
            cnotebook.__dict__.update(removed)

    @pytest.mark.parametrize("name", ["MolGrid", "molgrid", "BEST_FIT_ORIENTATION", "C3D",
                                      "render_dataframe", "render_polars_dataframe"])
    def test_every_lazy_export_resolves(self, name):
        """Each advertised lazy export imports cleanly in a fully installed environment."""
        assert getattr(cnotebook, name) is not None

    def test_dir_lists_the_lazy_exports(self):
        """Tab completion has to see the names that only ``__getattr__`` can produce."""
        listed = dir(cnotebook)
        assert set(cnotebook._LAZY_EXPORTS) <= set(listed)
        assert len(listed) == len(set(listed))

    def test_failed_lazy_import_warns_once_and_raises(self):
        """A broken optional import is reported once, naming the module and the real cause."""
        removed = self._unbind_exports("MolGrid")
        real_import_module = importlib.import_module

        def fake_import_module(name, *args, **kwargs):
            if name == "cnotebook.grid":
                raise ImportError("No module named 'anywidget'")
            return real_import_module(name, *args, **kwargs)

        try:
            with patch("importlib.import_module", side_effect=fake_import_module):
                with pytest.warns(CNotebookWarning, match="anywidget"), \
                        pytest.raises(AttributeError, match="cnotebook.grid"):
                    _ = cnotebook.MolGrid
                # The name has been explained once; repeating the warning would be noise.
                with warnings.catch_warnings():
                    warnings.simplefilter("error", CNotebookWarning)
                    with pytest.raises(AttributeError, match="cnotebook.grid"):
                        _ = cnotebook.MolGrid
        finally:
            cnotebook.__dict__.update(removed)
            cnotebook._WARNED_EXPORTS.discard("MolGrid")

    def test_failure_that_is_not_an_importerror_still_reads_as_a_missing_attribute(self):
        """A submodule may raise anything from its body, and ``hasattr`` must survive it."""
        removed = self._unbind_exports("C3D")
        real_import_module = importlib.import_module

        def fake_import_module(name, *args, **kwargs):
            if name == "cnotebook.c3d":
                raise RuntimeError("viewer version check failed")
            return real_import_module(name, *args, **kwargs)

        try:
            with patch("importlib.import_module", side_effect=fake_import_module):
                with pytest.warns(CNotebookWarning, match="viewer version check failed") as caught:
                    assert hasattr(cnotebook, "C3D") is False
                assert len(caught) == 1
                # A failed resolution must not be cached as though it had succeeded.
                assert "C3D" not in cnotebook.__dict__
        finally:
            cnotebook.__dict__.update(removed)
            cnotebook._WARNED_EXPORTS.discard("C3D")

    def test_unavailable_export_is_an_attributeerror_under_warnings_as_errors(self, caplog):
        """A filter that promotes CNotebookWarning must not change what a lookup raises.

        ``hasattr`` and ``getattr(..., default)`` swallow ``AttributeError`` and nothing
        else, so a warning raised from here would propagate out of both.
        """
        removed = self._unbind_exports("MolGrid")
        real_import_module = importlib.import_module

        def fake_import_module(name, *args, **kwargs):
            if name == "cnotebook.grid":
                raise ImportError("No module named 'anywidget'")
            return real_import_module(name, *args, **kwargs)

        try:
            with patch("importlib.import_module", side_effect=fake_import_module), \
                    caplog.at_level(logging.WARNING, logger="cnotebook"), \
                    warnings.catch_warnings():
                warnings.simplefilter("error", CNotebookWarning)
                assert hasattr(cnotebook, "MolGrid") is False
                assert getattr(cnotebook, "MolGrid", None) is None
            # The report still reaches the user, by the one route left open to it.
            assert "cnotebook.MolGrid is unavailable" in caplog.text
        finally:
            cnotebook.__dict__.update(removed)
            cnotebook._WARNED_EXPORTS.discard("MolGrid")

    def test_unknown_attribute_raises_without_warning(self):
        """An unknown name is a plain AttributeError, not an optional-dependency report."""
        with warnings.catch_warnings():
            warnings.simplefilter("error", CNotebookWarning)
            with pytest.raises(AttributeError, match="does_not_exist"):
                _ = cnotebook.does_not_exist


def test_user_warnings_are_cnotebook_warnings():
    from cnotebook.core.helpers import create_structure_highlighter

    with pytest.warns(CNotebookWarning, match="Overlay coloring"):
        create_structure_highlighter("c1ccccc1", color=oechem.OEColor(oechem.OERed), style="overlay_default")


def test_no_stream_handler_at_import():
    code = (
        "import logging, cnotebook; "
        "hs = logging.getLogger('cnotebook').handlers; "
        "print(any(isinstance(h, logging.StreamHandler) and not isinstance(h, logging.NullHandler) for h in hs))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip().endswith("False")


def test_hasattr_optional_export(monkeypatch):
    monkeypatch.delattr(cnotebook, "MolGrid", raising=False)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CNotebookWarning)
        assert hasattr(cnotebook, "MolGrid") in (True, False)
    with pytest.raises(AttributeError):
        _ = cnotebook.no_such_attribute


def test_display_honours_column_contexts():
    pd = pytest.importorskip("pandas")
    oepd = pytest.importorskip("oepandas")
    import cnotebook
    from cnotebook.core.context import get_series_context

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    df = pd.DataFrame({"mol": pd.Series([mol], dtype=oepd.MoleculeDtype())})
    calls = []
    get_series_context(df["mol"].array.metadata, save=True).add_callback(lambda disp: calls.append(1))
    with patch("cnotebook._display_html", side_effect=lambda html, env: html):
        cnotebook.display(df)
    assert calls == [1]


class TestDisplayC3DMolGridStatic:
    """Test display() with C3D and MolGrid static parameter handling."""

    def test_display_c3d_without_static(self):
        """Test display(c3d) works when C3D.display doesn't support static yet."""
        env = get_env()
        if not env.c3d_available:
            pytest.skip("C3D not available")
        from cnotebook import C3D
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        c3d = C3D()
        c3d.add_molecule(mol, generate_3d=False)
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            result = cnotebook.display(c3d)
        assert result is not None

    def test_display_c3d_static_none_works(self):
        """Test display(c3d, static=None) works."""
        env = get_env()
        if not env.c3d_available:
            pytest.skip("C3D not available")
        from cnotebook import C3D
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        c3d = C3D()
        c3d.add_molecule(mol, generate_3d=False)
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            result = cnotebook.display(c3d, static=None)
        assert result is not None

    def test_display_c3d_static_true_forwards(self):
        """Test display(c3d, static=True) returns the self-contained HTML output."""
        env = get_env()
        if not env.c3d_available:
            pytest.skip("C3D not available")
        from cnotebook import C3D
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        c3d = C3D()
        c3d.add_molecule(mol, generate_3d=False)
        result = cnotebook.display(c3d, static=True)
        assert "<iframe" in result._repr_html_()

    def test_display_c3d_static_false_forwards(self):
        """Test display(c3d, static=False) returns the live widget."""
        env = get_env()
        if not env.c3d_available:
            pytest.skip("C3D not available")
        pytest.importorskip("anywidget")
        from cnotebook import C3D
        from cnotebook.c3d.widget import C3DWidget
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        c3d = C3D()
        c3d.add_molecule(mol, generate_3d=False)
        result = cnotebook.display(c3d, static=False)
        assert isinstance(result, C3DWidget)

    def test_display_molgrid_without_static(self):
        """Test display(molgrid) works when MolGrid.display doesn't support static yet."""
        env = get_env()
        if not env.molgrid_available:
            pytest.skip("MolGrid not available")
        from openeye import oechem

        from cnotebook import molgrid
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        mg = molgrid([mol])
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            result = cnotebook.display(mg)
        assert result is not None

    def test_display_molgrid_static_none_works(self):
        """Test display(molgrid, static=None) works."""
        env = get_env()
        if not env.molgrid_available:
            pytest.skip("MolGrid not available")
        from openeye import oechem

        from cnotebook import molgrid
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        mg = molgrid([mol])
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            result = cnotebook.display(mg, static=None)
        assert result is not None

    def test_display_molgrid_static_true_forwards(self):
        """Test display(molgrid, static=True) returns the self-contained HTML output."""
        env = get_env()
        if not env.molgrid_available:
            pytest.skip("MolGrid not available")
        from openeye import oechem

        from cnotebook import molgrid
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        mg = molgrid([mol])
        result = cnotebook.display(mg, static=True)
        assert "<iframe" in result._repr_html_()

    def test_display_molgrid_static_false_forwards(self):
        """Test display(molgrid, static=False) returns the live widget."""
        env = get_env()
        if not env.molgrid_available:
            pytest.skip("MolGrid not available")
        pytest.importorskip("anywidget")
        from openeye import oechem

        from cnotebook import molgrid
        from cnotebook.grid.widget import MolGridWidget
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C")
        mg = molgrid([mol])
        result = cnotebook.display(mg, static=False)
        assert isinstance(result, MolGridWidget)

    def test_display_static_forwarding_when_supported(self):
        """Test static parameter is forwarded when display method accepts it."""
        class StubWidget:
            def __init__(self):
                self.static_value = None
            def display(self, static=None):
                self.static_value = static
                return f"displayed with static={static}"
        
        stub = StubWidget()
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            cnotebook.display(stub, static=True)
        assert stub.static_value is True
        
        stub2 = StubWidget()
        with patch("cnotebook._display_html", side_effect=lambda html, env: html):
            cnotebook.display(stub2, static=False)
        assert stub2.static_value is False


########################################################################################################################
# Import cost: what `import cnotebook` is allowed to pull in
########################################################################################################################

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)

# cnotebook requires the OpenEye toolkits and nothing else, and IPython is as optional as
# the frame libraries: `_activate_ipython` only does anything for a session that already
# imported it, so an eager `import IPython` in the package would be a broken promise.
_OPTIONAL_LIBRARIES = ("IPython", "pandas", "polars", "oepandas", "oepolars", "marimo", "anywidget")


def _run(code: str, **env_overrides):
    """Run *code* in a fresh interpreter that imports this checkout's cnotebook.

    :param code: Python source to run with ``-c``.
    :param env_overrides: Environment variables to set for the child process.
    :returns: The completed process.
    """
    env = {**os.environ, **env_overrides}
    env["PYTHONPATH"] = os.pathsep.join(part for part in (_REPO_ROOT, env.get("PYTHONPATH")) if part)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, cwd=_REPO_ROOT, check=False)


def test_import_does_not_import_optional_libraries():
    """``import cnotebook`` costs the OpenEye toolkits and nothing else."""
    code = (f"import sys, cnotebook; print(sorted(m for m in {_OPTIONAL_LIBRARIES!r} if m in sys.modules))")
    out = _run(code)
    assert out.returncode == 0, out.stderr
    # Compared as a whole line so a failure names the library that was imported.
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_detection_imports_nothing():
    """A detection pass must not pull in a library the session had not imported.

    This can only be asserted from a child. Under pytest the libraries detection could
    reach for are already imported, so an in-process check cannot tell an import that never
    happened from one that had happened long before.
    """
    code = textwrap.dedent(f"""
        import sys

        import cnotebook

        before = set(sys.modules)
        cnotebook.get_env()
        # Twice: the first call could plausibly be the one that memoises something.
        cnotebook.get_env()
        forbidden = set({_OPTIONAL_LIBRARIES!r})
        print(sorted(forbidden & (set(sys.modules) - before)))
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "[]"


def test_star_import_binds_the_public_names_including_the_installed_renderers():
    """`from cnotebook import *` binds every name ``__all__`` promises, and no private one.

    Star-importing resolves each lazy name through ``__getattr__``, which is how the frame
    renderers keep the package-scope binding notebooks star-import them for. Paying pandas
    and polars for that is the point here; the guarantee that a plain `import cnotebook`
    pays nothing belongs to ``test_import_does_not_import_optional_libraries``.
    """
    code = textwrap.dedent("""
        from cnotebook import *

        bound = set(globals())
        import sys

        import cnotebook
        missing = sorted(n for n in cnotebook.__all__ if n not in bound)
        # Module-level helpers of cnotebook's own; `__all__` is what keeps them private.
        leaked = sorted(n for n in ("sys", "importlib", "logging", "oechem", "oedepict") if n in bound)
        renderers = sorted(n for n in ("render_dataframe", "render_polars_dataframe") if n in bound)
        print(missing, leaked, renderers)
        lazy = ("cnotebook.c3d", "cnotebook.grid", "cnotebook.pandas_ext", "cnotebook.polars_ext")
        print(sorted(m for m in lazy if m in sys.modules))
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-2:] == [
        "[] [] ['render_dataframe', 'render_polars_dataframe']",
        "['cnotebook.c3d', 'cnotebook.grid', 'cnotebook.pandas_ext', 'cnotebook.polars_ext']",
    ]


def test_star_import_without_the_frame_backends_leaves_the_renderers_out():
    """Where a backend is missing its renderer leaves ``__all__``, not the API.

    The child makes the four packages undiscoverable to ``importlib.util.find_spec``,
    which is what the export list is decided by, and unimportable, which is what the lazy
    attribute runs into. A ``builtins.__import__`` guard alone would prove nothing:
    detection never imports.
    """
    code = textwrap.dedent("""
        import builtins
        import importlib.util

        blocked = {"pandas", "oepandas", "polars", "oepolars"}
        real_find_spec = importlib.util.find_spec
        real_import = builtins.__import__

        def find_spec(name, package=None):
            return None if name.split(".")[0] in blocked else real_find_spec(name, package)

        def guarded_import(name, *args, **kwargs):
            if name.split(".")[0] in blocked:
                raise ImportError("blocked " + name)
            return real_import(name, *args, **kwargs)

        importlib.util.find_spec = find_spec
        builtins.__import__ = guarded_import

        from cnotebook import *

        bound = set(globals())
        import cnotebook
        renderers = ("render_dataframe", "render_polars_dataframe")
        print(sorted(n for n in renderers if n in cnotebook.__all__))
        print(sorted(n for n in renderers if n in bound))
        try:
            cnotebook.render_dataframe
        except AttributeError as exc:
            print("is unavailable" in str(exc))
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-3:] == ["[]", "[]", "True"]


def test_bare_formatters_registered_without_oepandas():
    """OpenEye objects get their IPython formatters even where the frame libraries cannot load."""
    code = textwrap.dedent("""
        import builtins, sys
        real = builtins.__import__
        def guard(name, *a, **k):
            if name.split('.')[0] == 'oepandas':
                raise ImportError('blocked oepandas')
            return real(name, *a, **k)
        builtins.__import__ = guard
        from IPython.core.interactiveshell import InteractiveShell
        shell = InteractiveShell.instance()
        import cnotebook
        from openeye import oechem
        fmt = shell.display_formatter.formatters['text/html']
        print(fmt.lookup_by_type(oechem.OEGraphMol) is not None)
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("True")


def test_dataframes_render_through_cnotebook_without_being_imported_first():
    """The by-name registration means a frame imported after cnotebook still renders as ours."""
    code = textwrap.dedent("""
        from IPython.core.interactiveshell import InteractiveShell
        shell = InteractiveShell.instance()
        import sys
        import cnotebook
        assert 'pandas' not in sys.modules and 'polars' not in sys.modules
        import pandas as pd
        import polars as pl
        from cnotebook.ipython_ext import _render_pandas, _render_polars
        fmt = shell.display_formatter.formatters['text/html']
        frames = (pd.DataFrame({'a': [1]}), pl.DataFrame({'a': [1]}))
        print(fmt.lookup(frames[0]) is _render_pandas, fmt.lookup(frames[1]) is _render_polars)
        print(all('<table' in fmt(frame) for frame in frames))
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines() == ["True True", "True"]


@pytest.mark.parametrize("order", list(itertools.permutations(["import marimo", "import oepandas",
                                                               "import oepolars"])))
def test_marimo_attach_import_orders(order):
    """Whichever of marimo, oepandas and oepolars lands last, both table formatters are marimo's."""
    pytest.importorskip("marimo")
    code = "import cnotebook\n" + "\n".join(order) + textwrap.dedent("""
        import pandas as pd, polars as pl
        from marimo._output.formatting import OPINIONATED_FORMATTERS
        registry = OPINIONATED_FORMATTERS.formatters
        print(registry[pd.DataFrame].__name__, registry[pl.DataFrame].__name__)
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-1] == "marimo_pandas_formatter marimo_polars_formatter"


def test_marimo_alone_still_gets_the_adapter_and_its_openeye_hooks():
    """A marimo session with no frame library still has the marimo adapter and its hooks.

    The adapter registers a ``_mime_`` method on four OpenEye types from its module body, so
    rendering a bare molecule in marimo depends on ``cnotebook.marimo_ext`` being imported at
    all. Nothing here imports it but the marimo post-import hook: the pandas and polars
    adapters, which would pull it in as a side effect, are never reached.
    """
    pytest.importorskip("marimo")
    code = textwrap.dedent("""
        import cnotebook
        import marimo

        import sys
        from openeye import oechem, oedepict

        types = (oechem.OEMolBase, oechem.OEDesignUnit, oedepict.OE2DMolDisplay, oedepict.OEImage)
        print("adapter:", "cnotebook.marimo_ext" in sys.modules)
        print("frames:", sorted(m for m in ("pandas", "polars", "oepandas", "oepolars") if m in sys.modules))
        print("mime:", [hasattr(t, "_mime_") for t in types])
    """)
    out = _run(code)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().splitlines()[-3:] == [
        "adapter: True",
        "frames: []",
        "mime: [True, True, True, True]",
    ]


def test_lazy_exports_and_get_env_is_live():
    """The optional exports resolve on demand and the environment is answered per call."""
    assert cnotebook.C3D.__name__ == "C3D"
    assert cnotebook.MolGrid.__name__ == "MolGrid"
    env = cnotebook.get_env()
    assert env.c3d_available is True
    assert isinstance(env.pandas_available, bool)
    assert cnotebook.get_env() is not env


def test_changelog_lists_current_version():
    """The changelog documents the version the package reports, so a bump cannot ship undocumented."""
    text = (Path(_REPO_ROOT) / "CHANGELOG.md").read_text()
    assert f"## [{cnotebook.__version__}]" in text
