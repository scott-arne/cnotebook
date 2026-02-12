import pytest
from unittest.mock import MagicMock, patch, call
from openeye import oechem, oedepict
from cnotebook.ipython_ext import register_ipython_formatters
from cnotebook.render import oemol_to_html, oedisp_to_html, oedu_to_html, oeimage_to_html


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
        (i.e. ``lookup`` will succeed for them). Defaults to none.
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

    mock_html_formatter.lookup.side_effect = lookup_side_effect
    mock_ipython.display_formatter.formatters.__getitem__.return_value = mock_html_formatter

    return mock_ipython, mock_html_formatter


class TestRegisterIpythonFormatters:
    """Test the register_ipython_formatters function"""

    @patch('cnotebook.ipython_ext.get_ipython')
    def test_registers_all_types(self, mock_get_ipython):
        """Test that all expected types are registered with correct renderers"""
        mock_ipython, mock_html_formatter = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        for type_, renderer in EXPECTED_REGISTRATIONS.items():
            mock_html_formatter.for_type.assert_any_call(type_, renderer)

        assert mock_html_formatter.for_type.call_count == len(EXPECTED_REGISTRATIONS)

    @patch('cnotebook.ipython_ext.get_ipython')
    def test_skips_already_registered_types(self, mock_get_ipython):
        """Test idempotent behavior: already registered types are not re-registered"""
        all_types = set(EXPECTED_REGISTRATIONS.keys())
        mock_ipython, mock_html_formatter = _make_mock_ipython(already_registered=all_types)
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        mock_html_formatter.for_type.assert_not_called()

    @patch('cnotebook.ipython_ext.get_ipython')
    def test_partial_registration(self, mock_get_ipython):
        """Test that only unregistered types get registered when some already exist"""
        already = {oechem.OEMolBase, oedepict.OEImage}
        mock_ipython, mock_html_formatter = _make_mock_ipython(already_registered=already)
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        registered_types = {c.args[0] for c in mock_html_formatter.for_type.call_args_list}
        expected_new = set(EXPECTED_REGISTRATIONS.keys()) - already
        assert registered_types == expected_new

    @patch('cnotebook.ipython_ext.get_ipython')
    def test_no_ipython_instance(self, mock_get_ipython):
        """Test graceful handling when get_ipython() returns None"""
        mock_get_ipython.return_value = None

        # Should not raise
        register_ipython_formatters()

    @patch('cnotebook.ipython_ext.get_ipython')
    def test_looks_up_text_html_formatter(self, mock_get_ipython):
        """Test that the html formatter is retrieved via 'text/html' key"""
        mock_ipython, _ = _make_mock_ipython()
        mock_get_ipython.return_value = mock_ipython

        register_ipython_formatters()

        mock_ipython.display_formatter.formatters.__getitem__.assert_called_with('text/html')
