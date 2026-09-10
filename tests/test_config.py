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
