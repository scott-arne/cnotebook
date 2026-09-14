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


_DISPLAY_BLOCK_SOURCES = (
    "README.md",
    "docs/c3d.rst",
    "docs/molgrid.rst",
    "docs/dataframes.rst",
    "docs/rendering.rst",
)


def _markdown_python_blocks(text):
    """Yield ``(line_number, block_lines)`` for every fenced Python block in *text*."""
    lines = text.split("\n")
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("```") and stripped[3:].strip().lower() in ("python", "py"):
            start = index + 1
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                index += 1
            yield start + 1, lines[start:index]
        index += 1


def _rst_python_blocks(text):
    """Yield ``(line_number, block_lines)`` for every ``code-block:: python`` in *text*."""
    lines = text.split("\n")
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)\.\.\s+code-block::\s*(python|py)\s*$", line)
        if match is None:
            continue
        indent = len(match.group(1))
        cursor = index + 1
        # Skip the directive's own options and the blank line before the content.
        while cursor < len(lines) and (
            not lines[cursor].strip()
            or re.match(rf"^\s{{{indent + 1},}}:\w[\w-]*:", lines[cursor])
        ):
            cursor += 1
        start = cursor
        while cursor < len(lines) and (
            not lines[cursor].strip() or len(lines[cursor]) - len(lines[cursor].lstrip()) > indent
        ):
            cursor += 1
        yield start + 1, lines[start:cursor]


def _python_blocks(path, text):
    """Yield every Python code block of *text*, whichever markup *path* uses."""
    if path.endswith(".md"):
        yield from _markdown_python_blocks(text)
    else:
        yield from _rst_python_blocks(text)


def test_display_is_the_last_statement_of_its_example():
    """A block that displays a widget ends there, so a notebook actually renders it.

    ``display()`` returns a displayable object rather than publishing one, so a
    statement after it in the same cell means the widget is discarded and the
    interaction that follows has no front end to talk to.
    """
    for path in _DISPLAY_BLOCK_SOURCES:
        text = (_REPO_ROOT / path).read_text()
        for line_number, block in _python_blocks(path, text):
            if not any(".display(" in line for line in block):
                continue
            body = [
                line for line in block if line.strip() and not line.strip().startswith("#")
            ]
            assert ".display(" in body[-1], (
                f"{path}:{line_number}: the block continues after display(); "
                f"last statement is {body[-1].strip()!r}"
            )


_SEMVER_LITERAL = r"""["']([0-9]+\.[0-9]+\.[0-9]+[^"']*)["']"""


def _gui_bundle_version():
    """Return the version the 3dmol GUI bundle reports on its host API object."""
    text = (_REPO_ROOT / "cnotebook/core/static/3dmol-gui.js").read_text()
    direct = re.search(r"version\s*:\s*" + _SEMVER_LITERAL, text)
    if direct is not None:
        return direct.group(1)
    # Minification moves the literal into a module-level binding, so the host API
    # object only points at an identifier; resolve it before reading the string.
    indirect = re.search(r"version\s*:\s*([A-Za-z_$][\w$]*)\s*[,}]", text)
    assert indirect is not None, "3dmol-gui.js exposes no version on its host API"
    name = indirect.group(1)
    assignment = re.search(rf"\b{re.escape(name)}\s*=\s*" + _SEMVER_LITERAL, text)
    assert assignment is not None, f"3dmol-gui.js never assigns {name!r} a version"
    return assignment.group(1)


def test_embedded_c3d_documents_ship_the_current_viewer():
    """Every embedded viewer document carries the GUI bundle this package ships.

    The ``c3d-*.html`` files under ``docs/_static`` are generated artifacts that inline
    the bundle, so a bundle upgrade that is not followed by a regeneration leaves the
    documentation demonstrating a viewer the release no longer installs.
    """
    version = _gui_bundle_version()
    documents = sorted((_REPO_ROOT / "docs/_static").glob("c3d-*.html"))
    assert documents, "no embedded C3D viewer documents found"
    for path in documents:
        text = path.read_text()
        assert "window.c3d" in text, f"{path.name}: no window.c3d host API"
        assert version in text, f"{path.name}: does not embed GUI bundle version {version}"


def test_font_scale_range_is_documented_as_a_recommendation():
    """Nothing states the 0.5 to 2.0 font scale range as a hard limit.

    The context validates only finite values greater than zero, so the range is
    advice; every place that quotes it has to say so.
    """
    paths = [
        *sorted(p.relative_to(_REPO_ROOT).as_posix() for p in (_REPO_ROOT / "docs").glob("*.rst")),
        "README.md",
        "cnotebook/core/context.py",
    ]
    for path in paths:
        for number, line in enumerate((_REPO_ROOT / path).read_text().split("\n"), start=1):
            if "0.5 to 2.0" in line or "0.5-2.0" in line:
                assert "recommend" in line.lower(), f"{path}:{number}: {line.strip()!r}"
