import contextlib
import gc
import re
import warnings

import pytest
from openeye import oechem, oedepict, oegraphsim

from cnotebook.core import columnops
from cnotebook.core.columnops import AlignmentReport, SimilarityResult
from cnotebook.core.context import (
    CNotebookContext,
    create_local_context,
    render_options,
)
from cnotebook.core.errors import CNotebookWarning
from cnotebook.core.render import Depiction, make_depiction


class ListColumnAdapter:
    def __init__(self, mols, name="mol"):
        self.name = name
        self._mols = list(mols)
        self._ctx = None
        self.report = None
        self.replaced = 0

    def molecules(self):
        return list(self._mols)

    def replace_molecules(self, mols):
        self._mols = list(mols)
        self.replaced += 1

    def get_context(self, *, create):
        if self._ctx is None and create:
            self._ctx = create_local_context()
        return self._ctx

    def set_context(self, ctx):
        self._ctx = ctx

    def clear_context(self):
        self._ctx = None

    def set_alignment_report(self, report):
        self.report = report


def _mol(smiles):
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smiles)
    return mol


def test_highlight_adds_callbacks_and_optionally_aligns():
    col = ListColumnAdapter([_mol("c1ccccc1O"), _mol("c1ccccc1OC")])
    assert columnops.highlight(col, "c1ccccc1") is None
    assert len(col.get_context(create=False).callbacks) == 1
    report = columnops.highlight(col, ["[OH]", "c1ccccc1"], ref="first")
    assert isinstance(report, AlignmentReport) and report.aligned == 2
    assert len(col.get_context(create=False).callbacks) == 3
    with pytest.raises(TypeError):
        columnops.highlight(col, 42)


def test_align_depictions_copies_skips_and_reports():
    originals = [_mol("c1ccccc1O"), None, oechem.OEGraphMol(), _mol("c1ccccc1OC"), _mol("CCCCCC")]
    col = ListColumnAdapter(originals)
    with pytest.warns(CNotebookWarning, match="failed for 1 of 5"):
        report = columnops.align_depictions(col, "c1ccccc1")
    assert (report.total, report.aligned, report.skipped_none, report.skipped_invalid, report.failed) == (5, 2, 1, 1, [4])
    assert col.report is report and col.replaced == 1
    assert originals[0].GetDimension() == 0 and originals[3].GetDimension() == 0
    new = col.molecules()
    assert new[0] is not originals[0] and new[0].GetDimension() == 2 and new[1] is None


def test_align_depictions_first_and_kwargs(monkeypatch):
    seen = {}
    real = columnops.create_aligner

    def spy(ref, method=None, **kwargs):
        seen.update(kwargs)
        return real(ref, method=method, **kwargs)

    monkeypatch.setattr(columnops, "create_aligner", spy)
    col = ListColumnAdapter([None, _mol("c1ccccc1O"), _mol("c1ccccc1OC")])
    report = columnops.align_depictions(col, "first", method="fp", threshold=0.1)
    assert seen == {"threshold": 0.1} and report.aligned >= 1


def test_align_depictions_without_valid_reference_warns():
    col = ListColumnAdapter([None, oechem.OEGraphMol()])
    with pytest.warns(CNotebookWarning, match="No valid molecule found in column 'mol'"):
        report = columnops.align_depictions(col, "first")
    assert (report.total, report.aligned) == (2, 0)
    assert col.report is report and col.replaced == 0


def test_align_depictions_rejects_unknown_method():
    col = ListColumnAdapter([_mol("CCO")])
    with pytest.raises(ValueError, match="Unknown depiction alignment method"):
        columnops.align_depictions(col, "CCO", method="bogus")
    assert col.replaced == 0 and col.report is None


def test_render_options_reset_and_clear():
    col = ListColumnAdapter([_mol("CCO")])
    columnops.set_render_options(col, image_format="svg", width=120)
    ctx = col.get_context(create=False)
    assert ctx.image_format == "svg" and ctx.width == 120
    with pytest.raises(TypeError):
        columnops.set_render_options(col, bogus=1)
    ctx.add_callback(lambda d: None)
    columnops.clear_formatting_rules(col)
    assert col.get_context(create=False).callbacks == ()
    columnops.reset_depictions(col)
    assert col.get_context(create=False) is None


def test_set_render_options_rejects_read_only_options():
    col = ListColumnAdapter([_mol("CCO")])
    with pytest.raises(TypeError, match="read-only"):
        columnops.set_render_options(col, effective_scale=1.0)


def test_recalculate_depiction_coordinates_replaces_copies():
    mol = _mol("CCO")
    col = ListColumnAdapter([mol, None])
    columnops.recalculate_depiction_coordinates(col, add_depiction_hydrogens=False)
    new = col.molecules()
    assert new[0] is not mol and new[0].GetDimension() == 2 and mol.GetDimension() == 0 and new[1] is None


def test_build_highlight_column_owners_and_colors():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O"), None, _mol("CCO")]
    deps = columnops.build_highlight_column(mols, ["c1ccccc1 | [OH]", None, oechem.OESubSearch("CO")],
                                            colors=["#FF0000", None, oechem.OEColor(oechem.OEBlue)], ctx=ctx)
    assert isinstance(deps[0], Depiction) and deps[1] is None and isinstance(deps[2], Depiction)
    assert deps[0].display._cnotebook_owner is deps[0].mol
    assert mols[0].GetDimension() == 0
    del mols
    gc.collect()
    assert "<svg" in deps[0].to_html(ctx)


def test_build_highlight_column_overlay_and_int_style():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O")]
    overlaid = columnops.build_highlight_column(mols, ["c1ccccc1"], ctx=ctx)
    sticks = columnops.build_highlight_column(mols, ["c1ccccc1"], style=oedepict.OEHighlightStyle_Stick, ctx=ctx)
    assert "<svg" in overlaid[0].to_html(ctx) and "<svg" in sticks[0].to_html(ctx)
    assert mols[0].GetDimension() == 0


def test_parse_patterns_keeps_commas_inside_smarts():
    single = columnops._parse_patterns("[C,N]")
    assert len(single) == 1 and single[0].IsValid()
    delimited = columnops._parse_patterns("[C,N] | [OH]")
    assert len(delimited) == 2 and all(search.IsValid() for search in delimited)


def test_build_highlight_column_highlights_bracketed_alternatives():
    ctx = CNotebookContext(image_format="svg")
    with warnings.catch_warnings():
        warnings.simplefilter("error", CNotebookWarning)
        highlighted = columnops.build_highlight_column([_mol("CCN")], ["[C,N]"], ctx=ctx)
    plain = columnops.build_highlight_column([_mol("CCN")], [None], ctx=ctx)
    assert len(highlighted[0].to_html(ctx)) > len(plain[0].to_html(ctx))


def test_build_highlight_column_warns_for_unsupported_pattern():
    ctx = CNotebookContext(image_format="svg")
    with pytest.warns(CNotebookWarning, match="Do not know how to highlight"):
        deps = columnops.build_highlight_column([_mol("CCO")], [42], ctx=ctx)
    assert isinstance(deps[0], Depiction)


def test_build_highlight_column_skips_callbacks_of_the_source_context():
    ctx = CNotebookContext(image_format="svg")
    calls = []
    ctx.add_callback(calls.append)
    columnops.build_highlight_column([_mol("CCO")], ["CO"], ctx=ctx)
    assert calls == []


def test_parse_color():
    color = columnops.parse_color("#00ff00")
    assert isinstance(color, oechem.OEColor) and color.GetG() == 255
    assert isinstance(columnops.parse_color(oechem.OEGetLightColors()), oechem.OEColorIter)
    with pytest.raises(ValueError):
        columnops.parse_color("red-ish")


def test_parse_color_rejects_unsupported_type():
    with pytest.raises(TypeError):
        columnops.parse_color(42)


def test_fingerprint_similarity_pads_none_rows():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O"), None, oechem.OEGraphMol(), _mol("c1ccccc1OC")]
    result = columnops.fingerprint_similarity(mols, None, ctx=ctx)
    assert isinstance(result, SimilarityResult)
    assert len(result.tanimotos) == 4 and result.tanimotos[1] is None and result.tanimotos[2] is None
    assert result.tanimotos[0] == pytest.approx(1.0)
    assert isinstance(result.target[3], Depiction) and result.reference[1] is None
    assert mols[0].GetDimension() == 0


def test_fingerprint_similarity_depictions_outlive_their_molecules():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O"), _mol("c1ccccc1OC")]
    result = columnops.fingerprint_similarity(mols, None, ctx=ctx)
    del mols
    gc.collect()
    assert "<svg" in result.reference[1].to_html(ctx) and "<svg" in result.target[1].to_html(ctx)


def test_fingerprint_similarity_warns_without_valid_reference():
    ctx = CNotebookContext(image_format="svg")
    with pytest.warns(CNotebookWarning, match="No valid reference molecule"):
        result = columnops.fingerprint_similarity([None, oechem.OEGraphMol()], None, ctx=ctx)
    assert result.tanimotos == [None, None]
    assert result.reference == [None, None] and result.target == [None, None]


def _multiconformer(smiles, conformers=3):
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, smiles)
    coords = oechem.OEFloatArray(mol.NumAtoms() * 3)
    for conformer in range(1, conformers):
        for index in range(len(coords)):
            coords[index] = float(conformer + index)
        mol.NewConf(coords)
    return mol


@contextlib.contextmanager
def _captured_toolkit_output():
    """Capture OpenEye's own diagnostic stream so leaked toolkit messages fail an assert."""
    stream = oechem.oeosstream()
    oechem.OEThrow.SetOutputStream(stream)
    try:
        yield stream
    finally:
        oechem.OEThrow.SetOutputStream(oechem.oeerr)


def _stroke_colors(html):
    return set(re.findall(r'stroke="([^"]+)"', html))


def _unglyphed_html(depiction, ctx):
    """Render the depiction's own molecule again with no glyph, so only the glyph can differ."""
    return Depiction(depiction.mol, ctx.create_molecule_display(depiction.mol)).to_html(ctx)


def test_align_depictions_preserves_conformer_ensembles():
    mol = _multiconformer("c1ccccc1O")
    col = ListColumnAdapter([mol])
    report = columnops.align_depictions(col, "c1ccccc1")
    aligned = col.molecules()[0]
    assert report.aligned == 1
    assert isinstance(aligned, oechem.OEMol) and aligned.NumConfs() == 3
    assert aligned is not mol and aligned.GetDimension() == 2
    assert mol.NumConfs() == 3 and mol.GetDimension() == 0


def test_recalculate_depiction_coordinates_preserves_conformer_ensembles():
    mol = _multiconformer("c1ccccc1O")
    col = ListColumnAdapter([mol])
    columnops.recalculate_depiction_coordinates(col)
    recalculated = col.molecules()[0]
    assert isinstance(recalculated, oechem.OEMol) and recalculated.NumConfs() == 3
    assert recalculated is not mol and recalculated.GetDimension() == 2
    assert mol.NumConfs() == 3 and mol.GetDimension() == 0


def test_align_depictions_copies_invalid_rows_too():
    valid, invalid = _mol("c1ccccc1O"), oechem.OEGraphMol()
    col = ListColumnAdapter([valid, invalid])
    report = columnops.align_depictions(col, "c1ccccc1")
    new = col.molecules()
    assert report.skipped_invalid == 1 and report.aligned == 1
    assert new[0] is not valid and new[1] is not invalid and not new[1].IsValid()


def test_highlight_failures_leave_the_column_context_unchanged():
    col = ListColumnAdapter([_mol("c1ccccc1O")])
    columnops.highlight(col, "c1ccccc1")
    before = col.get_context(create=False).callbacks
    assert len(before) == 1

    with (
        _captured_toolkit_output() as toolkit,
        pytest.raises(ValueError, match="Invalid SMARTS"),
    ):
        columnops.highlight(col, "not a smarts")
    assert b"SMARTS" not in toolkit.str()
    with pytest.raises(ValueError, match="Unknown highlight style"):
        columnops.highlight(col, "[OH]", style="sparkles")
    with pytest.raises(TypeError, match="Highlight style"):
        columnops.highlight(col, "[OH]", style=object())
    with pytest.raises(ValueError, match="Unknown depiction alignment method"):
        columnops.highlight(col, "[OH]", ref="first", method="bogus")

    assert col.get_context(create=False).callbacks == before
    assert col.replaced == 0


def test_highlight_failure_does_not_create_a_column_context():
    col = ListColumnAdapter([_mol("CCO")])
    with _captured_toolkit_output(), pytest.raises(ValueError, match="Invalid SMARTS"):
        columnops.highlight(col, "not a smarts")
    assert col.get_context(create=False) is None


def test_highlight_callback_applies_the_requested_color_and_style():
    mol = _mol("c1ccccc1O")
    col = ListColumnAdapter([mol])
    columnops.set_render_options(col, image_format="svg")
    columnops.highlight(col, "c1ccccc1", color="#3A6EC8", style=oedepict.OEHighlightStyle_Stick)
    ctx = col.get_context(create=False)
    highlighted = make_depiction(mol, ctx=ctx, apply_callbacks=True).to_html(ctx)
    control = make_depiction(mol, ctx=ctx, apply_callbacks=False).to_html(ctx)
    assert highlighted != control
    assert "#3a6ec8" in highlighted.lower() and "#3a6ec8" not in control.lower()
    # Stick highlighting draws bonds only; the ball-and-stick style adds the atom circles
    assert "<circle" not in highlighted

    balls = ListColumnAdapter([mol])
    columnops.set_render_options(balls, image_format="svg")
    columnops.highlight(balls, "c1ccccc1", color="#3A6EC8",
                        style=oedepict.OEHighlightStyle_BallAndStick)
    ball_ctx = balls.get_context(create=False)
    ball_html = make_depiction(mol, ctx=ball_ctx, apply_callbacks=True).to_html(ball_ctx)
    assert "#3a6ec8" in ball_html.lower() and "<circle" in ball_html


def test_set_render_options_is_atomic_on_failure():
    col = ListColumnAdapter([_mol("CCO")])
    columnops.set_render_options(col, image_format="svg", width=120)
    with pytest.raises(ValueError, match="image_format"):
        columnops.set_render_options(col, width=200, image_format="jpeg")
    ctx = col.get_context(create=False)
    assert ctx.image_format == "svg" and ctx.width == 120


def test_set_render_options_does_not_create_a_context_on_failure():
    col = ListColumnAdapter([_mol("CCO")])
    with pytest.raises(ValueError, match="image_format"):
        columnops.set_render_options(col, width=200, image_format="jpeg")
    assert col.get_context(create=False) is None


def test_set_render_options_keeps_untouched_options_deferred():
    col = ListColumnAdapter([_mol("CCO")])
    columnops.set_render_options(col, width=120)
    ctx = col.get_context(create=False)
    assert ctx.scope == "local"
    with render_options(image_format="svg"):
        assert ctx.image_format == "svg"
    with render_options(image_format="png"):
        assert ctx.image_format == "png"
    assert ctx.width == 120


@pytest.mark.parametrize("fptype", ["path", "tree", "circular", "maccs", "lingo"])
def test_fingerprint_similarity_scores_every_advertised_fingerprint_type(fptype):
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O"), _mol("c1ccccc1OC")]
    if fptype == "lingo":
        with pytest.warns(CNotebookWarning, match="no per-bond attribution"):
            result = columnops.fingerprint_similarity(mols, None, fptype=fptype, ctx=ctx)
    else:
        with warnings.catch_warnings():
            warnings.simplefilter("error", CNotebookWarning)
            result = columnops.fingerprint_similarity(mols, None, fptype=fptype, ctx=ctx)
    assert result.tanimotos[0] == pytest.approx(1.0)
    assert 0.0 < result.tanimotos[1] < 1.0
    assert all(isinstance(dep, Depiction) for dep in result.target + result.reference)


def test_fingerprint_similarity_refuses_to_colour_lingo_overlaps():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1OC")]
    with (
        _captured_toolkit_output() as toolkit,
        pytest.warns(CNotebookWarning, match="no per-bond attribution") as record,
    ):
        result = columnops.fingerprint_similarity(
            mols, _mol("c1ccccc1O"), fptype="lingo", ctx=ctx
        )
    assert len(record) == 1 and b"Lingo" not in toolkit.str()
    depiction = result.target[0]
    assert _stroke_colors(depiction.to_html(ctx)) == _stroke_colors(_unglyphed_html(depiction, ctx))


def test_fingerprint_similarity_warns_once_for_zero_overlap_rows():
    ctx = CNotebookContext(image_format="svg")
    mols = [_mol("c1ccccc1O"), _mol("[Na+]"), _mol("[Xe]")]
    with (
        _captured_toolkit_output() as toolkit,
        pytest.warns(CNotebookWarning, match="overlap was empty for 2 of 3 rows") as record,
    ):
        result = columnops.fingerprint_similarity(mols, None, ctx=ctx)
    assert len(record) == 1 and b"OEPrepareMultiAlignedDepiction" not in toolkit.str()
    assert result.tanimotos[1] == pytest.approx(0.0)
    assert isinstance(result.target[1], Depiction)


def test_fingerprint_similarity_matches_an_independent_tanimoto():
    ctx = CNotebookContext(image_format="svg")
    ref, target = _mol("c1ccccc1O"), _mol("c1ccccc1OC")
    result = columnops.fingerprint_similarity([target], ref, ctx=ctx)
    fingerprints = []
    for mol in (ref, target):
        fingerprint = oegraphsim.OEFingerPrint()
        oegraphsim.OEMakeTreeFP(fingerprint, mol, 4096, 0, 4,
                                oegraphsim.OEFPAtomType_DefaultTreeAtom,
                                oegraphsim.OEFPBondType_DefaultTreeBond)
        fingerprints.append(fingerprint)
    expected = oegraphsim.OETanimoto(*fingerprints)
    assert 0.0 < expected < 1.0
    assert result.tanimotos[0] == pytest.approx(expected)


def test_fingerprint_similarity_glyph_colours_bonds_by_overlap():
    ctx = CNotebookContext(image_format="svg")
    result = columnops.fingerprint_similarity([_mol("c1ccccc1OC")], _mol("c1ccccc1O"), ctx=ctx)
    depiction = result.target[0]
    glyphed = depiction.to_html(ctx)
    unglyphed = _unglyphed_html(depiction, ctx)
    assert _stroke_colors(glyphed) > _stroke_colors(unglyphed)
    assert len(glyphed) > len(unglyphed)


def test_fingerprint_similarity_does_not_glyph_atom_only_fingerprints():
    ctx = CNotebookContext(image_format="svg")
    mol, ref = _mol("c1ccccc1CCO"), _mol("c1ccccc1CCO")
    with (
        _captured_toolkit_output() as toolkit,
        pytest.warns(
            CNotebookWarning, match="produced no per-bond attribution for 1 of 1 rows"
        ) as record,
    ):
        atom_only = columnops.fingerprint_similarity(
            [mol], ref, fptype="path", max_distance=0, ctx=ctx
        )
    assert len(record) == 1 and toolkit.str() == b""
    assert atom_only.tanimotos[0] == pytest.approx(1.0)
    plain = atom_only.target[0]
    assert _stroke_colors(plain.to_html(ctx)) == _stroke_colors(_unglyphed_html(plain, ctx))

    # The same identical pair still gets its colouring once the paths are long enough to hit bonds
    with warnings.catch_warnings():
        warnings.simplefilter("error", CNotebookWarning)
        bonded = columnops.fingerprint_similarity(
            [mol], ref, fptype="path", max_distance=4, ctx=ctx
        )
    glyphed = bonded.target[0]
    assert _stroke_colors(glyphed.to_html(ctx)) > _stroke_colors(_unglyphed_html(glyphed, ctx))
