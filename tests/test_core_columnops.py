import gc
import warnings

import pytest
from openeye import oechem, oedepict

from cnotebook.core import columnops
from cnotebook.core.columnops import AlignmentReport, SimilarityResult
from cnotebook.core.context import CNotebookContext, create_local_context
from cnotebook.core.errors import CNotebookWarning
from cnotebook.core.render import Depiction


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
