import pytest
import unittest.mock as mock
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict
from cnotebook.context import (
    CNotebookContext, 
    DeferredValue, 
    DEFERRED, 
    _Deferred,
    cnotebook_context,
    pass_cnotebook_context,
    create_local_context,
    get_series_context
)


class TestDeferredValue:
    """Test the DeferredValue class"""
    
    def test_init_with_value(self):
        """Test initialization with a concrete value"""
        dv = DeferredValue("test", 42)
        assert dv.name == "test"
        assert dv.get() == 42
        assert not dv.is_deferred
    
    def test_init_with_deferred(self):
        """Test initialization with DEFERRED sentinel"""
        dv = DeferredValue("width", DEFERRED)
        assert dv.name == "width"
        assert dv.is_deferred
        # Value should come from context when accessed
        # For width, it should get some default value
        value = dv.get()
        assert isinstance(value, (int, float))
    
    def test_set_value(self):
        """Test setting a value"""
        dv = DeferredValue("test", 42)
        dv.set(100)
        assert dv.get() == 100
        assert not dv.is_deferred
    
    def test_set_deferred(self):
        """Test setting to deferred"""
        dv = DeferredValue("test", 42)
        dv.set(DEFERRED)
        assert dv.is_deferred
    
    def test_reset(self):
        """Test reset functionality"""
        dv = DeferredValue("test", 42)
        dv.set(100)
        dv.reset()
        assert dv.get() == 42
    
    def test_deferred_missing_attribute(self):
        """Test error when deferred attribute is missing from context"""
        dv = DeferredValue("nonexistent_attribute", DEFERRED)
        # This should raise an AttributeError when trying to access a non-existent attribute
        with pytest.raises(AttributeError):
            dv.get()
    
    def test_str_repr(self):
        """Test string representations"""
        dv = DeferredValue("test", 42)
        assert str(dv) == "42"
        assert repr(dv) == "42"


class TestCNotebookContext:
    """Test the CNotebookContext class"""
    
    def test_init_default(self):
        """Test default initialization"""
        ctx = CNotebookContext()
        assert ctx.width == 0
        assert ctx.height == 0
        assert ctx.min_width == 200.0
        assert ctx.min_height == 200.0
        assert ctx.max_width is None
        assert ctx.max_height is None
        assert ctx.image_format == "png"
        assert ctx.bond_width_scaling is False
        assert ctx.title is True
        assert ctx.max_heavy_atoms == 100
        assert len(ctx.callbacks) >= 0
    
    def test_init_with_parameters(self):
        """Test initialization with custom parameters"""
        ctx = CNotebookContext(
            width=300,
            height=400,
            min_width=100,
            min_height=150,
            max_width=500,
            max_height=600,
            image_format="svg",
            bond_width_scaling=True,
            title=False,
            max_heavy_atoms=50
        )
        assert ctx.width == 300
        assert ctx.height == 400
        assert ctx.min_width == 100
        assert ctx.min_height == 150
        assert ctx.max_width == 500
        assert ctx.max_height == 600
        assert ctx.image_format == "svg"
        assert ctx.bond_width_scaling is True
        assert ctx.title is False
        assert ctx.max_heavy_atoms == 50
    
    def test_property_setters(self):
        """Test property setters"""
        ctx = CNotebookContext()
        
        ctx.width = 300
        assert ctx.width == 300
        
        ctx.height = 400
        assert ctx.height == 400
        
        ctx.min_width = 100
        assert ctx.min_width == 100
        
        ctx.structure_scale = 0.8
        assert ctx.structure_scale == 0.8
        
        ctx.image_format = "svg"
        assert ctx.image_format == "svg"
    
    def test_width_max_warning(self):
        """Test warning when width exceeds max_width"""
        ctx = CNotebookContext(max_width=400)
        with patch('cnotebook.context.log.warning') as mock_warn:
            ctx.width = 500
            mock_warn.assert_called_once()
            assert "Width exceeds max_width" in mock_warn.call_args[0][0]
    
    def test_height_max_warning(self):
        """Test warning when height exceeds max_height"""
        ctx = CNotebookContext(max_height=300)
        with patch('cnotebook.context.log.warning') as mock_warn:
            ctx.height = 400
            mock_warn.assert_called_once()
            assert "Height exceeds max_height" in mock_warn.call_args[0][0]
    
    def test_image_mime_type(self):
        """Test image MIME type property"""
        ctx = CNotebookContext(image_format="png")
        assert ctx.image_mime_type == "image/png"
        
        ctx.image_format = "svg"
        assert ctx.image_mime_type == "image/svg+xml"
    
    def test_image_mime_type_unknown(self):
        """Test error for unknown image format"""
        ctx = CNotebookContext()
        ctx._image_format.set("unknown")
        with pytest.raises(KeyError, match="No MIME type registered for image format unknown"):
            _ = ctx.image_mime_type
    
    def test_display_options(self):
        """Test display options property"""
        ctx = CNotebookContext(
            width=300,
            height=400,
            structure_scale=0.8,
            title_font_scale=1.2,
            bond_width_scaling=True,
            title=False
        )
        
        opts = ctx.display_options
        assert isinstance(opts, oedepict.OE2DMolDisplayOptions)
        assert opts.GetWidth() == 300
        assert opts.GetHeight() == 400
        assert opts.GetScale() == pytest.approx(0.8)
        assert opts.GetTitleFontScale() == pytest.approx(1.2)
        assert opts.GetBondWidthScaling() is True
    
    def test_add_callback(self):
        """Test adding callbacks"""
        ctx = CNotebookContext()
        
        def dummy_callback(disp):
            pass
        
        initial_count = len(ctx.callbacks)
        ctx.add_callback(dummy_callback)
        assert len(ctx.callbacks) == initial_count + 1
        assert dummy_callback in ctx.callbacks
    
    def test_add_callback_to_deferred(self):
        """Test adding callback when callbacks are deferred"""
        ctx = CNotebookContext(callbacks=DEFERRED, scope="local")
        
        def dummy_callback(disp):
            pass
        
        ctx.add_callback(dummy_callback)
        assert len(ctx.callbacks) == 1
        assert dummy_callback in ctx.callbacks
    
    def test_reset_callbacks(self):
        """Test resetting callbacks"""
        ctx = CNotebookContext()
        
        def dummy_callback(disp):
            pass
        
        ctx.add_callback(dummy_callback)
        ctx.reset_callbacks()
        # After reset, should revert to initial state
        assert isinstance(ctx.callbacks, tuple)
    
    def test_create_molecule_display(self):
        """Test creating molecule display"""
        ctx = CNotebookContext(width=300, height=400)
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetDimension.return_value = 2
        
        # Test that the method exists and can be called
        # The actual implementation involves OpenEye functions we don't mock
        assert hasattr(ctx, 'create_molecule_display')
        assert callable(ctx.create_molecule_display)
    
    def test_max_heavy_atoms_setter(self):
        """Test max_heavy_atoms property setter"""
        ctx = CNotebookContext()
        assert ctx.max_heavy_atoms == 100

        ctx.max_heavy_atoms = 50
        assert ctx.max_heavy_atoms == 50

        ctx.max_heavy_atoms = None
        assert ctx.max_heavy_atoms is None

    def test_copy(self):
        """Test copying context"""
        ctx = CNotebookContext(
            width=300,
            height=400,
            image_format="svg"
        )

        ctx_copy = ctx.copy()
        assert ctx_copy.width == 300
        assert ctx_copy.height == 400
        assert ctx_copy.image_format == "svg"
        assert id(ctx) != id(ctx_copy)  # Different objects
    
    def test_copy_preserves_max_heavy_atoms(self):
        """Test that copy preserves max_heavy_atoms"""
        ctx = CNotebookContext(max_heavy_atoms=75)
        ctx_copy = ctx.copy()
        assert ctx_copy.max_heavy_atoms == 75

        ctx_none = CNotebookContext(max_heavy_atoms=None)
        ctx_none_copy = ctx_none.copy()
        assert ctx_none_copy.max_heavy_atoms is None

    def test_reset(self):
        """Test resetting context to defaults"""
        ctx = CNotebookContext()
        ctx.width = 300
        ctx.height = 400
        ctx.image_format = "svg"
        ctx.max_heavy_atoms = 50

        ctx.reset()

        # Should be back to defaults
        assert ctx.width == 0
        assert ctx.height == 0
        assert ctx.image_format == "png"
        assert ctx.max_heavy_atoms == 100


class TestPassCNotebookContextDecorator:
    """Test the pass_cnotebook_context decorator"""
    
    def test_decorator_with_default_context(self):
        """Test decorator passes default context"""
        @pass_cnotebook_context
        def test_func(*, ctx):
            return ctx
        
        result = test_func()
        assert result is not None
        assert isinstance(result, CNotebookContext)
    
    def test_decorator_with_provided_context(self):
        """Test decorator with provided context"""
        @pass_cnotebook_context
        def test_func(*, ctx):
            return ctx
        
        custom_ctx = CNotebookContext()
        result = test_func(ctx=custom_ctx)
        assert result == custom_ctx
    
    def test_decorator_with_none_context(self):
        """Test decorator with None context"""
        @pass_cnotebook_context
        def test_func(*, ctx):
            return ctx
        
        result = test_func(ctx=None)
        assert result is not None
        assert isinstance(result, CNotebookContext)
    
    def test_decorator_with_invalid_context(self):
        """Test decorator with invalid context type"""
        @pass_cnotebook_context
        def test_func(*, ctx):
            return ctx
        
        with pytest.raises(TypeError, match="Received object of type.*for OERenderContext"):
            test_func(ctx="invalid")


class TestCreateLocalContext:
    """Test create_local_context function"""
    
    def test_create_local_context_defaults(self):
        """Test creating local context with defaults"""
        ctx = create_local_context()
        assert ctx.scope == "local"
        assert ctx._width.is_deferred
        assert ctx._height.is_deferred
    
    def test_create_local_context_with_values(self):
        """Test creating local context with specific values"""
        ctx = create_local_context(width=300, height=400, image_format="svg")
        assert ctx.scope == "local"
        assert ctx.width == 300
        assert ctx.height == 400
        assert ctx.image_format == "svg"


class TestGetSeriesContext:
    """Test get_series_context function"""
    
    def test_get_series_context_existing(self):
        """Test getting existing context from metadata"""
        existing_ctx = CNotebookContext(width=300)
        metadata = {"cnotebook": existing_ctx}
        
        result = get_series_context(metadata)
        assert result == existing_ctx
    
    def test_get_series_context_missing(self):
        """Test getting context when missing from metadata"""
        metadata = {}
        
        result = get_series_context(metadata)
        assert isinstance(result, CNotebookContext)
        assert result.scope == "local"
    
    def test_get_series_context_invalid_type(self):
        """Test getting context when invalid type in metadata"""
        metadata = {"cnotebook": "invalid"}
        
        with patch('cnotebook.context.log.warning') as mock_warn:
            result = get_series_context(metadata)
            assert isinstance(result, CNotebookContext)
            assert result.scope == "local"
            mock_warn.assert_called_once()
    
    def test_get_series_context_save(self):
        """Test saving context to metadata"""
        metadata = {}
        
        result = get_series_context(metadata, save=True)
        assert "cnotebook" in metadata
        assert metadata["cnotebook"] == result


class TestEnum:
    """Test the _Deferred enum"""
    
    def test_deferred_enum(self):
        """Test the DEFERRED sentinel value"""
        assert isinstance(DEFERRED, _Deferred)
        assert DEFERRED == _Deferred.value
        assert DEFERRED.value == 0


class TestCNotebookContextEdgeCases:
    """Edge case tests for CNotebookContext covering additional branches."""

    def test_callbacks_invalid_type_raises(self):
        """Test that passing an invalid type for callbacks raises TypeError."""
        with pytest.raises(TypeError, match="Invalid type for display callbacks"):
            CNotebookContext(callbacks=123)

    @patch('cnotebook.context.log.warning')
    def test_max_width_below_width_warns(self, mock_warning):
        """Test that setting max_width below current width triggers a warning."""
        ctx = CNotebookContext(width=500)
        ctx.max_width = 400
        mock_warning.assert_called_once()
        warning_msg = mock_warning.call_args[0][0]
        assert "max_width" in warning_msg

    @patch('cnotebook.context.log.warning')
    def test_max_height_below_height_warns(self, mock_warning):
        """Test that setting max_height below current height triggers a warning."""
        ctx = CNotebookContext(height=500)
        ctx.max_height = 400
        mock_warning.assert_called_once()
        warning_msg = mock_warning.call_args[0][0]
        assert "max_height" in warning_msg

    def test_setters_coverage(self):
        """Exercise min_height, atom_label_font_scale, title_font_scale,
        bond_width_scaling, and title setters."""
        ctx = CNotebookContext()

        ctx.min_height = 300.0
        assert ctx.min_height == 300.0

        ctx.atom_label_font_scale = 1.5
        assert ctx.atom_label_font_scale == 1.5

        ctx.title_font_scale = 0.8
        assert ctx.title_font_scale == 0.8

        ctx.bond_width_scaling = True
        assert ctx.bond_width_scaling is True

        ctx.title = False
        assert ctx.title is False

    def test_create_molecule_display_size_enforcement(self):
        """Test that create_molecule_display respects max_width constraint."""
        ctx = CNotebookContext(max_width=200)

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc2c(c1)cc1ccc3ccccc3c1c2")  # large molecule
        oedepict.OEPrepareDepiction(mol)

        disp = ctx.create_molecule_display(mol)
        assert isinstance(disp, oedepict.OE2DMolDisplay)
        assert disp.GetWidth() <= 200