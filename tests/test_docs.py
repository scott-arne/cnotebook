"""Checks that guard the documented API against the shipped one."""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_add_style_examples_use_style_then_selection():
    """Every ``add_style`` example passes the style before the selection."""
    for path in ("README.md", "docs/c3d.rst"):
        text = (_REPO_ROOT / path).read_text()
        assert 'add_style({"chain"' not in text, path
        assert re.search(r'add_style\("cartoon",\s*\{"chain": "A"\}', text), path


def test_migration_guide_covers_every_breaking_change():
    """The migration guide carries every identifier of the breaking-change ledger."""
    text = (_REPO_ROOT / "docs/migration-4.rst").read_text()
    for number in range(1, 24):
        assert f"M{number:02d}" in text, f"M{number:02d} missing from the migration guide"


def test_molgrid_docs_use_autodoc():
    """The MolGrid reference is generated from the class, not hand-written."""
    text = (_REPO_ROOT / "docs/molgrid.rst").read_text()
    assert ".. autoclass:: cnotebook.grid.MolGrid" in text
    assert "width=200, height=200" not in text


def test_rendering_docs_defaults_match_code():
    """The rendering options table states the defaults the context actually has."""
    from cnotebook.core.context import CNotebookContext

    text = (_REPO_ROOT / "docs/rendering.rst").read_text()
    ctx = CNotebookContext()
    assert f"``{ctx.atom_label_font_scale}``" in text
    assert "device_pixel_ratio" in text and "``2.0``" in text
