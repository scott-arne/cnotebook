from cnotebook.core import vocabulary as v


def test_view_presets_match_engine():
    assert set(v.VIEW_PRESETS) == {"simple", "sites", "ball-and-stick"}


def test_style_presets_match_engine():
    assert set(v.STYLE_PRESETS) == {"cartoon", "stick", "sphere", "line", "cross", "surface"}


def test_map_formats_partitioned():
    assert v.BINARY_MAP_FORMATS == frozenset({"ccp4", "map", "mrc"})
    assert v.TEXT_MAP_FORMATS == frozenset({"cube"})
    assert set(v.MAP_FORMATS) == v.BINARY_MAP_FORMATS | v.TEXT_MAP_FORMATS


def test_binary_molecule_formats():
    assert v.BINARY_MOLECULE_FORMATS == frozenset({"oeb", "oedu"})


def test_defaults_present():
    assert v.DEFAULTS["max_heavy_atoms"] == 100
    assert v.DEFAULTS["image_format"] == "png"
    assert v.DEFAULTS["viewer_width"] == 800
