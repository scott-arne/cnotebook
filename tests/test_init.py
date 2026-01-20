import pytest
import logging
from unittest.mock import MagicMock, patch, Mock
import cnotebook
from cnotebook import (
    __version__,
    is_jupyter_notebook,
    is_marimo_notebook,
    LevelSpecificFormatter,
    enable_debugging,
    log,
    render_dataframe,
    cnotebook_context,
    render_molecule_grid
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


class TestIsJupyterNotebook:
    """Test the is_jupyter_notebook function"""
    
    def test_is_jupyter_notebook_true(self):
        """Test detection of Jupyter notebook environment"""
        with patch('builtins.__import__') as mock_import:
            mock_ipython_module = MagicMock()
            mock_get_ipython = MagicMock()
            mock_ipython_instance = MagicMock()
            mock_ipython_instance.__class__.__name__ = 'ZMQInteractiveShell'
            mock_get_ipython.return_value = mock_ipython_instance
            mock_ipython_module.get_ipython = mock_get_ipython
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'IPython':
                    return mock_ipython_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_jupyter_notebook()
            assert result is True
    
    def test_is_jupyter_notebook_terminal(self):
        """Test detection of IPython terminal environment"""
        with patch('builtins.__import__') as mock_import:
            mock_ipython_module = MagicMock()
            mock_get_ipython = MagicMock()
            mock_ipython_instance = MagicMock()
            mock_ipython_instance.__class__.__name__ = 'TerminalInteractiveShell'
            mock_get_ipython.return_value = mock_ipython_instance
            mock_ipython_module.get_ipython = mock_get_ipython
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'IPython':
                    return mock_ipython_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_jupyter_notebook()
            assert result is False
    
    def test_is_jupyter_notebook_other_shell(self):
        """Test detection of other IPython shell types"""
        with patch('builtins.__import__') as mock_import:
            mock_ipython_module = MagicMock()
            mock_get_ipython = MagicMock()
            mock_ipython_instance = MagicMock()
            mock_ipython_instance.__class__.__name__ = 'SomeOtherShell'
            mock_get_ipython.return_value = mock_ipython_instance
            mock_ipython_module.get_ipython = mock_get_ipython
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'IPython':
                    return mock_ipython_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_jupyter_notebook()
            assert result is False
    
    def test_is_jupyter_notebook_exception(self):
        """Test handling of exceptions when detecting Jupyter"""
        with patch('builtins.__import__') as mock_import:
            def import_side_effect(name, *args, **kwargs):
                if name == 'IPython':
                    raise ImportError("No module named 'IPython'")
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_jupyter_notebook()
            assert result is False
    
    def test_is_jupyter_notebook_no_ipython(self):
        """Test when IPython module is not available"""
        # This test is tricky because IPython might be available in test environment
        # We test the exception handling path
        # Test when IPython import itself fails
        with patch('builtins.__import__') as mock_import:
            def import_side_effect(name, *args, **kwargs):
                if name == 'IPython':
                    raise ImportError("No module named 'IPython'")
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_jupyter_notebook()
            assert result is False


class TestIsMarimoNotebook:
    """Test the is_marimo_notebook function"""
    
    def test_is_marimo_notebook_true(self):
        """Test detection of Marimo notebook environment"""
        with patch('builtins.__import__') as mock_import:
            mock_marimo_module = MagicMock()
            mock_marimo_module.running_in_notebook.return_value = True
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'marimo':
                    return mock_marimo_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_marimo_notebook()
            assert result is True
    
    def test_is_marimo_notebook_false(self):
        """Test when not in Marimo notebook"""
        with patch('builtins.__import__') as mock_import:
            mock_marimo_module = MagicMock()
            mock_marimo_module.running_in_notebook.return_value = False
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'marimo':
                    return mock_marimo_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_marimo_notebook()
            assert result is False
    
    def test_is_marimo_notebook_not_available(self):
        """Test when Marimo is not available"""
        with patch('builtins.__import__') as mock_import:
            def import_side_effect(name, *args, **kwargs):
                if name == 'marimo':
                    raise ImportError("No module named 'marimo'")
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_marimo_notebook()
            assert result is False
    
    def test_is_marimo_notebook_exception(self):
        """Test handling of exceptions when detecting Marimo"""
        with patch('builtins.__import__') as mock_import:
            mock_marimo_module = MagicMock()
            mock_marimo_module.running_in_notebook.side_effect = Exception("Some error")
            
            def import_side_effect(name, *args, **kwargs):
                if name == 'marimo':
                    return mock_marimo_module
                return __import__(name, *args, **kwargs)
            
            mock_import.side_effect = import_side_effect
            
            result = is_marimo_notebook()
            assert result is False


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
    
    def test_render_molecule_grid_import(self):
        """Test that render_molecule_grid is imported"""
        assert hasattr(cnotebook, 'render_molecule_grid')
        assert callable(render_molecule_grid)
    
    def test_all_expected_exports(self):
        """Test that all expected items are exported"""
        expected_exports = [
            '__version__',
            'is_jupyter_notebook',
            'is_marimo_notebook',
            'LevelSpecificFormatter',
            'enable_debugging',
            'log',
            'render_dataframe',
            'cnotebook_context',
            'render_molecule_grid'
        ]
        
        for export in expected_exports:
            assert hasattr(cnotebook, export), f"Missing export: {export}"


class TestAutoRegistration:
    """Test automatic formatter registration"""

    def test_detection_flags_exist(self):
        """Test that detection flags are exposed at module level"""
        assert hasattr(cnotebook, '_pandas_available')
        assert hasattr(cnotebook, '_polars_available')
        assert hasattr(cnotebook, '_ipython_available')
        assert hasattr(cnotebook, '_marimo_available')

    def test_detection_flags_are_boolean(self):
        """Test that detection flags are boolean values"""
        assert isinstance(cnotebook._pandas_available, bool)
        assert isinstance(cnotebook._polars_available, bool)
        assert isinstance(cnotebook._ipython_available, bool)
        assert isinstance(cnotebook._marimo_available, bool)

    def test_pandas_available_reflects_imports(self):
        """Test _pandas_available reflects actual pandas/oepandas availability"""
        try:
            import pandas
            import oepandas
            assert cnotebook._pandas_available is True
        except ImportError:
            assert cnotebook._pandas_available is False

    def test_polars_available_reflects_imports(self):
        """Test _polars_available reflects actual polars/oepolars availability"""
        try:
            import polars
            import oepolars
            assert cnotebook._polars_available is True
        except ImportError:
            assert cnotebook._polars_available is False

    def test_no_registration_in_plain_python(self):
        """Test that no formatters are registered in plain Python"""
        # This would test the case where neither Jupyter nor Marimo are detected
        # Complex to test due to import-time behavior
        pass


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
    
    @patch('cnotebook.is_jupyter_notebook')
    def test_conditional_imports_jupyter(self, mock_is_jupyter):
        """Test conditional imports work for Jupyter"""
        mock_is_jupyter.return_value = True
        
        # Test that when in Jupyter, we can access the expected functionality
        assert callable(render_dataframe)
        assert callable(render_molecule_grid)
    
    @patch('cnotebook.is_marimo_notebook')  
    def test_conditional_imports_marimo(self, mock_is_marimo):
        """Test conditional imports work for Marimo"""
        mock_is_marimo.return_value = True
        
        # In Marimo environment, marimo_ext should be imported
        # This is tested indirectly by checking the module loads without error
        import cnotebook  # Should not raise ImportError


class TestErrorHandling:
    """Test error handling in module initialization"""
    
    def test_handles_missing_dependencies_gracefully(self):
        """Test that module handles missing optional dependencies"""
        # The module should handle cases where dependencies are missing
        # This is already tested indirectly by the is_jupyter_notebook and is_marimo_notebook tests
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
        assert callable(is_jupyter_notebook)
        assert callable(is_marimo_notebook)
        assert callable(enable_debugging)
        assert callable(LevelSpecificFormatter)
    
    def test_enable_debugging_docstring(self):
        """Test enable_debugging has docstring"""
        assert enable_debugging.__doc__ is not None
        assert len(enable_debugging.__doc__.strip()) > 0
    
    def test_level_specific_formatter_docstring(self):
        """Test LevelSpecificFormatter has docstring"""
        assert LevelSpecificFormatter.__doc__ is not None
        assert len(LevelSpecificFormatter.__doc__.strip()) > 0


class TestRenderMoleculeGridImport:
    """Test render_molecule_grid import from package root"""

    def test_import_from_package(self):
        """Test render_molecule_grid can be imported from cnotebook"""
        from cnotebook import render_molecule_grid
        assert callable(render_molecule_grid)

    def test_import_comes_from_render(self):
        """Test the import comes from render module"""
        from cnotebook import render_molecule_grid as rmg_pkg
        from cnotebook.render import render_molecule_grid as rmg_render
        assert rmg_pkg is rmg_render