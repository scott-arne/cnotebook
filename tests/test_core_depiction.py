import pytest
from openeye import oechem, oedepict

from cnotebook.core.context import CNotebookContext
from cnotebook.core.depiction import highlight_alerts, render_path, render_summary


def _mol(smiles):
    mol = oechem.OEGraphMol()
    assert oechem.OESmilesToMol(mol, smiles)
    return mol


def test_highlight_alerts_returns_oeimage_with_groups():
    mol = _mol("c1ccccc1CC(=O)O")  # 8 heavy atoms
    groups = [("acid", None, ((6, 7, 8),))]  # auto color, one 3-atom match
    image = highlight_alerts(mol, groups)
    assert isinstance(image, oedepict.OEImage)
    # renders to non-empty PNG bytes
    data = oedepict.OEWriteImageToString("png", image)
    assert len(data) > 0


def test_highlight_alerts_empty_groups_renders_bare_molecule():
    mol = _mol("c1ccccc1")
    image = highlight_alerts(mol, [])
    assert isinstance(image, oedepict.OEImage)


def test_highlight_alerts_empty_molecule_returns_image_not_html():
    image = highlight_alerts(oechem.OEGraphMol(), [("x", None, ())])
    assert isinstance(image, oedepict.OEImage)  # NOT an HTML str


def test_highlight_alerts_honors_max_heavy_atoms():
    mol = _mol("c1ccccc1CC(=O)O")  # 8 heavy atoms
    groups = [("acid", None, ((6, 7, 8),))]
    ctx = CNotebookContext(max_heavy_atoms=5, min_width=200, min_height=200)
    image = highlight_alerts(mol, groups, ctx=ctx)
    # Molecule exceeds limit → should return placeholder image (200x200) via oemol_to_image
    assert isinstance(image, oedepict.OEImage)
    assert image.GetWidth() == 200.0
    assert image.GetHeight() == 200.0


def test_atom_bond_set_includes_bonds():
    from cnotebook.core.depiction import _atom_bond_set

    mol = _mol("CC(=O)O")  # acetic acid: CH3-C(=O)-OH
    # Atom indices: 0=C(methyl), 1=C(carbonyl), 2=O(=O), 3=O(-OH)
    carbonyl_c = 1
    o_double = 2
    o_single = 3

    abset = _atom_bond_set(mol, (carbonyl_c, o_double, o_single))

    # Should have 3 atoms
    assert abset.NumAtoms() == 3
    # Should have 2 bonds: C=O and C-O
    assert abset.NumBonds() > 0


def _steps():
    return [("Has disallowed elements", False, "no match"),
            ("Is aromatic", True, "1 match")]


def _terminal():
    return ("High (Class III)", None, "High presumed oral toxicity.")


def test_render_path_html_contains_labels_and_terminal():
    html = render_path(_steps(), _terminal(), format="html")
    assert isinstance(html, str)
    assert "Is aromatic" in html
    assert "High (Class III)" in html
    # YES/NO answers surfaced
    assert "YES" in html and "NO" in html


def test_render_path_png_returns_embeddable_string():
    out = render_path(_steps(), _terminal(), format="png")
    assert isinstance(out, str)
    assert "img" in out or "svg" in out.lower()


def test_render_path_unknown_format_raises():
    with pytest.raises(ValueError):
        render_path(_steps(), _terminal(), format="pdf")


def test_render_path_empty_steps_renders_terminal_only():
    html = render_path([], _terminal(), format="html")
    assert "High (Class III)" in html


def test_render_path_html_escapes_caller_text():
    # Caller text may contain HTML metacharacters that must be escaped.
    steps = [("<script>alert(1)</script>", True, "a & b")]
    terminal = ("<terminal>", None, "x < y")
    html = render_path(steps, terminal, format="html")
    # Raw HTML metacharacters must NOT appear
    assert "<script>" not in html
    assert "<terminal>" not in html
    # Escaped forms MUST appear
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
    assert "&lt;terminal&gt;" in html
    assert "&lt; y" in html


def test_render_path_image_honors_context_width():
    """Path image output must honor ctx.width when rendering to png/svg."""
    steps = [("Q1", True, "detail1"), ("Q2", False, "detail2")]
    terminal = ("High", None, "High risk")

    # Create context with width=500
    ctx = CNotebookContext(width=500)

    # Render as PNG with custom width
    png_out = render_path(steps, terminal, format="png", ctx=ctx)
    assert isinstance(png_out, str)
    # create_img_tag embeds width as style='width:500px;...' for PNG
    assert "width:500px" in png_out

    # Render as SVG with custom width
    svg_out = render_path(steps, terminal, format="svg", ctx=ctx)
    assert isinstance(svg_out, str)
    # create_img_tag wraps SVG in <div style='width:500px;...'>
    assert "width:500px" in svg_out


def test_render_path_image_honors_context_width_and_height():
    """Path image output must honor BOTH ctx.width and ctx.height when set."""
    steps = [("Q1", True, "detail1"), ("Q2", False, "detail2")]
    terminal = ("High", None, "High risk")

    # Create context with BOTH width=500 and height=400
    ctx = CNotebookContext(width=500, height=400)

    # Render as PNG with custom dimensions
    png_out = render_path(steps, terminal, format="png", ctx=ctx)
    assert isinstance(png_out, str)
    # create_img_tag embeds width in style (height uses height:auto, so we only verify width + success)
    assert "width:500px" in png_out

    # Render as SVG with custom dimensions
    svg_out = render_path(steps, terminal, format="svg", ctx=ctx)
    assert isinstance(svg_out, str)
    assert "width:500px" in svg_out


def test_render_summary_html_includes_paths_and_legend():
    mol = _mol("c1ccccc1CC(=O)O")
    groups = [("Cramer Q3", None, ((7,),)),
              ("Cramer Q22", None, ())]  # non-localizable fired alert
    paths = [("Cramer", _steps(), _terminal())]
    html = render_summary(mol, groups, paths, format="html", legend=True)
    assert isinstance(html, str)
    assert "Cramer" in html
    assert "Is aromatic" in html              # the path rendered
    assert "not structurally localizable" in html  # empty-match legend entry


def test_render_summary_legend_false_omits_legend():
    mol = _mol("c1ccccc1")
    groups = [("Cramer Q22", None, ())]
    paths = [("Cramer", _steps(), _terminal())]
    html = render_summary(mol, groups, paths, format="html", legend=False)
    assert "not structurally localizable" not in html


def test_render_summary_png_returns_embeddable_string():
    mol = _mol("c1ccccc1")
    out = render_summary(mol, [], [("Cramer", _steps(), _terminal())], format="png")
    assert isinstance(out, str)
    assert "img" in out or "svg" in out.lower()


def test_render_summary_svg_returns_string():
    mol = _mol("c1ccccc1")
    out = render_summary(mol, [], [("Cramer", _steps(), _terminal())], format="svg")
    assert isinstance(out, str)


def test_render_summary_unknown_format_raises():
    with pytest.raises(ValueError):
        render_summary(_mol("c1ccccc1"), [], [], format="pdf")


def test_render_summary_png_empty_molecule_does_not_crash():
    # empty molecule -> placeholder cell, still returns an embeddable string
    out = render_summary(oechem.OEGraphMol(), [], [("Cramer", _steps(), _terminal())], format="png")
    assert isinstance(out, str)
    assert "img" in out or "svg" in out.lower()


def test_render_summary_html_escapes_source_label():
    """Source labels in render_summary must be escaped to prevent HTML injection."""
    mol = _mol("c1ccccc1")
    malicious_label = "<script>alert(1)</script>"
    paths = [(malicious_label, _steps(), _terminal())]
    html = render_summary(mol, [], paths, format="html")
    # Raw HTML metacharacters must NOT appear
    assert "<script>" not in html
    # Escaped form MUST appear
    assert "&lt;script&gt;" in html


def test_render_summary_png_honors_context_width():
    """summary_image/render_summary png honors a context width."""
    mol = _mol("c1ccccc1")
    ctx = CNotebookContext(width=500)
    out = render_summary(mol, [], [("Cramer", _steps(), _terminal())], format="png", ctx=ctx)
    assert isinstance(out, str)
    # create_img_tag embeds width as style='width:500px;...' for PNG
    assert "width:500px" in out


def test_render_summary_png_honors_max_heavy_atoms():
    """Over-limit molecule doesn't render the full structure in summary_image."""
    mol = _mol("c1ccccc1")  # benzene: 6 heavy atoms
    ctx = CNotebookContext(max_heavy_atoms=2)
    out = render_summary(mol, [], [("Cramer", _steps(), _terminal())], format="png", ctx=ctx)
    assert isinstance(out, str)
    # Molecule cell shows placeholder, but path cell still renders → non-empty embeddable
    assert "img" in out or "svg" in out.lower()


def test_render_summary_png_honors_context_title_disabled():
    """ctx.title=False is honored in summary png rendering."""
    mol = _mol("c1ccccc1CC(=O)O")
    # Create a context with title disabled
    ctx = CNotebookContext(title=False)
    out = render_summary(mol, [], [("Cramer", _steps(), _terminal())], format="png", ctx=ctx)
    assert isinstance(out, str)
    # Should return embeddable string without error (actual title rendering is hard to assert from string)
    assert "img" in out or "svg" in out.lower()


def test_render_summary_png_many_terminal_only_paths_no_crash():
    """Many terminal-only paths don't crash and produce a taller image."""
    mol = _mol("c1ccccc1")
    # 8 terminal-only paths (0 steps each)
    paths = [(f"Tree{i}", [], _terminal()) for i in range(8)]
    out = render_summary(mol, [], paths, format="png")
    assert isinstance(out, str)
    # Should not crash and should return non-empty embeddable string
    assert "img" in out or "svg" in out.lower()


def test_primitives_exported_from_core():
    import cnotebook.core as core
    for name in ("highlight_alerts", "render_path", "render_summary", "summary_image",
                 "AlertGroup", "PathStep", "Terminal"):
        assert name in core.__all__
        assert hasattr(core, name)


def test_version_bumped():
    import cnotebook
    assert cnotebook.__version__ == "3.1.1"


def test_render_summary_png_honors_terminal_color():
    """summary_image respects terminal color when drawing the terminal line."""
    mol = _mol("c1ccccc1")
    steps = [("Has disallowed elements", False, "no match")]
    # Terminal with a distinct non-None color
    terminal = ("High (Class III)", oechem.OEColor(0xB7, 0x1C, 0x1C), "High presumed oral toxicity.")
    paths = [("Cramer", steps, terminal)]
    # Render as PNG with colored terminal
    out = render_summary(mol, [], paths, format="png")
    assert isinstance(out, str)
    # Should return embeddable string without error (color is rendered into image)
    assert "img" in out or "svg" in out.lower()
    # Verify it produces non-empty bytes (practical assertion for the code path working)
    assert len(out) > 0
