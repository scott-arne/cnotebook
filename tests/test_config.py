import warnings

import pytest

from cnotebook import config
from cnotebook.core.errors import CNotebookWarning


@pytest.fixture()
def fresh_config(monkeypatch, tmp_path):

    monkeypatch.delenv("CNOTEBOOK_CONFIG", raising=False)
    monkeypatch.delenv("CNOTEBOOK_DISPLAY_MODE", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(config, "_CONFIG", None)
    yield config
    monkeypatch.setattr(config, "_CONFIG", None)


def test_defaults_without_file(fresh_config):
    cfg = fresh_config.get_config()
    assert cfg.display_mode == "widget"
    assert cfg.c3d["width"] == 800
    assert cfg.molgrid["n_items_per_page"] == 24


def test_env_var_file_is_loaded(fresh_config, tmp_path, monkeypatch):
    path = tmp_path / "cn.toml"
    path.write_text('[display]\nmode = "static"\n[c3d]\nwidth = 640\n[molgrid]\nimage_format = "png"\n[render]\nimage_format = "svg"\n')
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path))
    cfg = fresh_config.load_config()
    assert cfg.display_mode == "static"
    assert cfg.c3d["width"] == 640
    assert cfg.molgrid["image_format"] == "png"
    assert cfg.render["image_format"] == "svg"


def test_xdg_file_is_discovered(fresh_config, tmp_path):
    xdg = tmp_path / "xdg" / "cnotebook"
    xdg.mkdir(parents=True)
    (xdg / "config.toml").write_text('[molgrid]\nn_items_per_page = 12\n')
    assert fresh_config.load_config().molgrid["n_items_per_page"] == 12


def test_malformed_file_warns_and_uses_defaults(fresh_config, tmp_path, monkeypatch):
    path = tmp_path / "bad.toml"
    path.write_text("[display\nmode = ")
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path))
    with pytest.warns(CNotebookWarning, match="bad.toml"):
        cfg = fresh_config.load_config()
    assert cfg.display_mode == "widget"


def test_unknown_and_invalid_keys_warn(fresh_config, tmp_path, monkeypatch):
    path = tmp_path / "cn.toml"
    path.write_text('[display]\nmode = "sideways"\n[c3d]\nbogus = 1\nwidth = "wide"\n')
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = fresh_config.load_config()
    messages = " ".join(str(w.message) for w in caught if issubclass(w.category, CNotebookWarning))
    assert "sideways" in messages and "bogus" in messages and "wide" in messages
    assert cfg.display_mode == "widget" and cfg.c3d["width"] == 800


def test_display_mode_env_override(fresh_config, monkeypatch, tmp_path):
    monkeypatch.setenv("CNOTEBOOK_DISPLAY_MODE", "static")
    assert fresh_config.load_config().display_mode == "static"
    path = tmp_path / "cn.toml"
    path.write_text('[display]\nmode = "static"\n')
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path))
    monkeypatch.setenv("CNOTEBOOK_DISPLAY_MODE", "nope")
    with pytest.warns(CNotebookWarning, match="nope"):
        assert fresh_config.load_config().display_mode == "widget"


def test_configure_and_resolve_precedence(fresh_config):
    fresh_config.get_config()
    assert fresh_config.resolve("c3d", "width", fresh_config.UNSET) == 800
    fresh_config.configure(display_mode="static", c3d={"width": 500}, molgrid={"theme": "dark"}, image_format="svg")
    assert fresh_config.get_config().display_mode == "static"
    assert fresh_config.resolve("c3d", "width", fresh_config.UNSET) == 500
    assert fresh_config.resolve("c3d", "width", 320) == 320
    assert fresh_config.resolve("molgrid", "theme", fresh_config.UNSET) == "dark"
    from cnotebook.core.context import cnotebook_context

    assert cnotebook_context.get().image_format == "svg"
    with pytest.raises(ValueError):
        fresh_config.configure(display_mode="sideways")
    with pytest.raises(KeyError):
        fresh_config.resolve("c3d", "bogus", fresh_config.UNSET)


def test_scalar_section_warns_and_imports(tmp_path, monkeypatch):
    """Test that scalar section values warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_text('[display]\nmode = "static"\nrender = 5\n')
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "render" in result.stderr or "5" in result.stderr


def test_array_section_warns_and_imports(tmp_path, monkeypatch):
    """Test that array section values warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_text('[display]\nmode = "static"\nc3d = ["a", "b"]\n')
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "c3d" in result.stderr


def test_unknown_render_key_warns_and_imports(tmp_path, monkeypatch):
    """Test that unknown render keys warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_text('[render]\nbogus_option = "value"\n')
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "bogus_option" in result.stderr or "unknown" in result.stderr.lower()


def test_readonly_render_property_warns_and_imports(tmp_path, monkeypatch):
    """Test that read-only render properties warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_text('[render]\nsvg_data = "bad"\n')
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "svg_data" in result.stderr and ("unknown" in result.stderr.lower() or "ignored" in result.stderr.lower())


def test_wrong_type_render_option_warns_and_imports(tmp_path, monkeypatch):
    """Test that wrong-type render options warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_text('[render]\nwidth = "not a number"\n')
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert "width" in result.stderr or "not a number" in result.stderr


def test_configure_unknown_key_doesnt_change_state(fresh_config):
    """Test that configure with unknown key doesn't partially apply changes."""
    fresh_config.get_config()
    from cnotebook.core.context import cnotebook_context

    original_display_mode = fresh_config.get_config().display_mode
    original_c3d_width = fresh_config.get_config().c3d["width"]
    original_ctx_width = cnotebook_context.get().width

    with pytest.raises(KeyError):
        fresh_config.configure(display_mode="static", c3d={"bogus": 1})

    assert fresh_config.get_config().display_mode == original_display_mode
    assert fresh_config.get_config().c3d["width"] == original_c3d_width
    assert cnotebook_context.get().width == original_ctx_width


def test_configure_wrong_type_doesnt_change_state(fresh_config):
    """Test that configure with wrong type doesn't partially apply changes."""
    fresh_config.get_config()
    from cnotebook.core.context import cnotebook_context

    original_display_mode = fresh_config.get_config().display_mode
    original_c3d_width = fresh_config.get_config().c3d["width"]
    original_ctx_width = cnotebook_context.get().width

    with pytest.raises(ValueError):
        fresh_config.configure(display_mode="static", c3d={"width": "wide"})

    assert fresh_config.get_config().display_mode == original_display_mode
    assert fresh_config.get_config().c3d["width"] == original_c3d_width
    assert cnotebook_context.get().width == original_ctx_width


def test_configure_invalid_display_mode_doesnt_change_state(fresh_config):
    """Test that configure with invalid display_mode doesn't partially apply changes."""
    fresh_config.get_config()
    from cnotebook.core.context import cnotebook_context

    original_c3d_width = fresh_config.get_config().c3d["width"]
    original_ctx_width = cnotebook_context.get().width

    with pytest.raises(ValueError):
        fresh_config.configure(display_mode="sideways", c3d={"width": 500})

    assert fresh_config.get_config().c3d["width"] == original_c3d_width
    assert cnotebook_context.get().width == original_ctx_width


def test_configure_readonly_render_option_raises(fresh_config):
    """Test that configure rejects read-only render properties."""
    fresh_config.get_config()
    with pytest.raises((KeyError, AttributeError)):
        fresh_config.configure(svg_data="bad")


def test_configure_wrong_type_render_option_raises(fresh_config):
    """Test that configure rejects wrong-type render options."""
    fresh_config.get_config()
    from cnotebook.core.context import cnotebook_context

    original_width = cnotebook_context.get().width
    with pytest.raises((ValueError, TypeError)):
        fresh_config.configure(width="not a number")

    assert cnotebook_context.get().width == original_width


def test_non_utf8_config_warns_and_imports(tmp_path, monkeypatch):
    """Test that non-UTF-8 config files warn but don't prevent import."""
    import subprocess
    import sys

    path = tmp_path / "bad.toml"
    path.write_bytes(b"\xff\xfe[render]\n")
    code = f'import os; os.environ["CNOTEBOOK_CONFIG"] = {str(path)!r}; import cnotebook; print("OK")'
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300, check=False)
    assert result.returncode == 0
    assert "OK" in result.stdout
    assert str(path.name) in result.stderr or "Could not read" in result.stderr or "UTF-8" in result.stderr or "UnicodeDecodeError" in result.stderr


import pytest


@pytest.mark.parametrize("option,valid_value,invalid_value", [
    ("width", 500, "not a number"),
    ("height", 400, "not a number"),
    ("min_width", 100, "not a number"),
    ("min_height", 100, "not a number"),
    ("max_width", 1000, "not a number"),
    ("max_height", 800, "not a number"),
    ("structure_scale", 1.5, "not a number"),
    ("atom_label_font_scale", 1.2, "not a number"),
    ("title_font_scale", 1.1, "not a number"),
    ("image_format", "png", "invalid_format"),
    ("max_heavy_atoms", 100, "not a number"),
    ("device_pixel_ratio", 2.0, "not a number"),
])
def test_render_option_validation(fresh_config, tmp_path, monkeypatch, option, valid_value, invalid_value):
    """Test that render options validate correctly through both file and configure()."""
    import warnings
    
    # Test valid value through file
    path = tmp_path / "valid.toml"
    if isinstance(valid_value, bool):
        path.write_text(f'[render]\n{option} = {"true" if valid_value else "false"}\n')
    elif isinstance(valid_value, str):
        path.write_text(f'[render]\n{option} = "{valid_value}"\n')
    else:
        path.write_text(f'[render]\n{option} = {valid_value}\n')
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path))
    
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = fresh_config.load_config()
    
    # Should not warn for valid values
    config_warnings = [w for w in caught if issubclass(w.category, CNotebookWarning)]
    assert len(config_warnings) == 0, f"Valid {option}={valid_value} produced warnings: {[str(w.message) for w in config_warnings]}"
    assert option in cfg.render
    
    # Test invalid value through file
    path2 = tmp_path / "invalid.toml"
    if isinstance(invalid_value, str):
        path2.write_text(f'[render]\n{option} = "{invalid_value}"\n')
    else:
        path2.write_text(f'[render]\n{option} = {invalid_value}\n')
    monkeypatch.setenv("CNOTEBOOK_CONFIG", str(path2))
    fresh_config._CONFIG = None
    
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        cfg = fresh_config.load_config()
    
    config_warnings = [w for w in caught if issubclass(w.category, CNotebookWarning)]
    assert len(config_warnings) >= 1, f"Invalid {option}={invalid_value} did not warn"
    
    # Test valid value through configure()
    fresh_config._CONFIG = None
    fresh_config.get_config()
    fresh_config.configure(**{option: valid_value})
    from cnotebook.core.context import cnotebook_context
    assert getattr(cnotebook_context.get(), option) == valid_value
    
    # Test invalid value through configure()
    with pytest.raises((ValueError, TypeError, KeyError)):
        fresh_config.configure(**{option: invalid_value})
