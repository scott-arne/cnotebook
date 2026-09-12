import logging
from unittest.mock import MagicMock, patch

import pytest
from openeye import oechem, oedepict

from cnotebook import ipython_ext
from cnotebook.ipython_ext import (
    register_dataframe_formatters_by_name,
    register_ipython_formatters,
)
from cnotebook.render import (
    oedisp_to_html,
    oedu_to_html,
    oeimage_to_html,
    oemol_to_html,
)

# The expected type-to-renderer mappings
EXPECTED_REGISTRATIONS = {
    oechem.OEMolBase: oemol_to_html,
    oedepict.OE2DMolDisplay: oedisp_to_html,
    oechem.OEDesignUnit: oedu_to_html,
    oedepict.OEImage: oeimage_to_html,
}


def _make_mock_ipython(already_registered=None):
    """Create a mock IPython instance with an HTML formatter.

    :param already_registered: Set of types that should appear already registered
        (i.e. ``lookup_by_type`` will succeed for them). Defaults to none.
    :returns: Tuple of (mock ipython instance, mock html_formatter).
    """
    if already_registered is None:
        already_registered = set()

    mock_ipython = MagicMock()
    mock_html_formatter = MagicMock()

    def lookup_side_effect(type_):
        if type_ in already_registered:
            return MagicMock()  # already registered
        raise KeyError(type_)

    mock_html_formatter.lookup_by_type.side_effect = lookup_side_effect
    mock_ipython.display_formatter.formatters.__getitem__.return_value = mock_html_formatter

    return mock_ipython, mock_html_formatter


class TestRegisterIpythonFormatters:
    """Test the register_ipython_formatters function"""

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_registers_all_types(self, mock_get_ipython):
        """Test that all expected types are registered with correct renderers"""
        mock_ipython, mock_html_formatter = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        for type_, renderer in EXPECTED_REGISTRATIONS.items():
            mock_html_formatter.for_type.assert_any_call(type_, renderer)

        assert mock_html_formatter.for_type.call_count == len(EXPECTED_REGISTRATIONS)

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_registration_uses_lookup_by_type(self, mock_get_ipython):
        """The idempotence guard asks about the type, not about an instance of it.

        ``lookup`` takes an object and looks up ``type(obj)``, so asking it about a class
        answers for the metaclass and never reports the class as registered.
        """
        mock_ipython, mock_html_formatter = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        assert mock_html_formatter.lookup.call_count == 0
        assert mock_html_formatter.lookup_by_type.call_count == len(EXPECTED_REGISTRATIONS)
        assert mock_html_formatter.for_type.call_count == len(EXPECTED_REGISTRATIONS)

        mock_html_formatter.reset_mock()
        mock_html_formatter.lookup_by_type.side_effect = None
        mock_html_formatter.lookup_by_type.return_value = MagicMock()

        register_ipython_formatters()

        mock_html_formatter.for_type.assert_not_called()

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_skips_already_registered_types(self, mock_get_ipython):
        """Test idempotent behavior: already registered types are not re-registered"""
        all_types = set(EXPECTED_REGISTRATIONS.keys())
        mock_ipython, mock_html_formatter = _make_mock_ipython(already_registered=all_types)
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        mock_html_formatter.for_type.assert_not_called()

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_partial_registration(self, mock_get_ipython):
        """Test that only unregistered types get registered when some already exist"""
        already = {oechem.OEMolBase, oedepict.OEImage}
        mock_ipython, mock_html_formatter = _make_mock_ipython(already_registered=already)
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        registered_types = {c.args[0] for c in mock_html_formatter.for_type.call_args_list}
        expected_new = set(EXPECTED_REGISTRATIONS.keys()) - already
        assert registered_types == expected_new

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_looks_up_text_html_formatter(self, mock_get_ipython):
        """Test that the html formatter is retrieved via 'text/html' key"""
        mock_ipython, _ = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        mock_ipython.display_formatter.formatters.__getitem__.assert_called_with('text/html')


class TestRegisterNoopWhenNoIpython:
    """Test register_ipython_formatters when IPython is not active."""

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_register_noop_when_get_ipython_returns_none(self, mock_get_ipython, caplog):
        """register_ipython_formatters() should emit a debug log when get_ipython() returns None."""
        mock_get_ipython.return_value = None

        with caplog.at_level(logging.DEBUG, logger="cnotebook"):
            register_ipython_formatters()

        assert any("no IPython shell" in record.message for record in caplog.records)

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_by_name_registration_noop_without_a_shell(self, mock_get_ipython):
        """Nothing to register against, and nothing raised either."""
        mock_get_ipython.return_value = None

        register_dataframe_formatters_by_name()

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_registration_noop_when_the_shell_has_no_display_formatter(self, mock_get_ipython):
        """A shell that has no display formatter is treated as no shell at all.

        ``display_formatter`` is an optional trait, so a shell can answer ``None`` for it;
        reaching through that for ``formatters`` would raise instead of skipping.
        """
        mock_ipython, mock_html_formatter = _make_mock_ipython()
        mock_ipython.display_formatter = None
        mock_get_ipython.return_value = mock_ipython

        assert ipython_ext._html_formatter() is None

        register_ipython_formatters()
        register_dataframe_formatters_by_name()

        mock_html_formatter.for_type.assert_not_called()
        mock_html_formatter.for_type_by_name.assert_not_called()


class TestRegisterDataFrameFormattersByName:
    """Test the DataFrame registration that does not import pandas or polars."""

    @patch('cnotebook.ipython_ext._get_ipython')
    def test_registers_both_libraries_by_name(self, mock_get_ipython):
        """Every supported type name is deferred to the matching renderer."""
        mock_ipython, mock_html_formatter = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_dataframe_formatters_by_name()

        expected = [((module, name, ipython_ext._render_pandas))
                    for module, name in ipython_ext._PANDAS_DATAFRAME_NAMES]
        expected += [((module, name, ipython_ext._render_polars))
                     for module, name in ipython_ext._POLARS_DATAFRAME_NAMES]
        assert [call.args for call in mock_html_formatter.for_type_by_name.call_args_list] == expected

    def test_registered_names_match_the_installed_dataframe_classes(self):
        """A name that no installed release reports would silently never match.

        IPython matches a deferred printer on the class's ``__module__``/``__name__``, and
        both libraries have moved theirs (pandas 3 reports ``pandas``, pandas 2 reported
        ``pandas.core.frame``), so the registered names are checked against the real ones.
        """
        pd = pytest.importorskip("pandas")
        pl = pytest.importorskip("polars")

        assert (pd.DataFrame.__module__, pd.DataFrame.__name__) in ipython_ext._PANDAS_DATAFRAME_NAMES
        assert (pl.DataFrame.__module__, pl.DataFrame.__name__) in ipython_ext._POLARS_DATAFRAME_NAMES

    def test_renderers_use_the_cnotebook_adapters(self):
        """The deferred callables render through cnotebook, not through the library's own HTML."""
        pd = pytest.importorskip("pandas")
        pl = pytest.importorskip("polars")
        from cnotebook.pandas_ext import render_dataframe
        from cnotebook.polars_ext import render_polars_dataframe

        frame = pd.DataFrame({"a": [1]})
        with patch("cnotebook.pandas_ext.render_dataframe", wraps=render_dataframe) as rendered:
            assert "<table" in ipython_ext._render_pandas(frame)
        rendered.assert_called_once_with(frame)

        frame = pl.DataFrame({"a": [1]})
        with patch("cnotebook.polars_ext.render_polars_dataframe", wraps=render_polars_dataframe) as rendered:
            assert "<table" in ipython_ext._render_polars(frame)
        rendered.assert_called_once_with(frame)

    def test_renderers_fall_back_to_the_library_when_the_adapter_is_missing(self):
        """An adapter that cannot import must cost the styling, not the output."""
        class Frame:
            def _repr_html_(self):
                return "<table>plain</table>"

        real_import = __import__

        def guard(name, *args, **kwargs):
            if name in ("cnotebook.pandas_ext", "cnotebook.polars_ext"):
                raise ImportError(name)
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guard):
            assert ipython_ext._render_pandas(Frame()) == "<table>plain</table>"
            assert ipython_ext._render_polars(Frame()) == "<table>plain</table>"
