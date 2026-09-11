import re

import oepandas as oepd
import oepolars as oeplr
import pandas as pd
import polars as pl
import pytest
from openeye import oechem

import cnotebook.marimo_ext as me
from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import CNotebookWarning
from cnotebook.pandas_ext import render_dataframe
from cnotebook.polars_ext import render_polars_dataframe

SMILES = ["c1ccccc1O", "CCO", "C" * 130]


def _mols():
    out = []
    for smi in SMILES:
        m = oechem.OEGraphMol()
        oechem.OESmilesToMol(m, smi)
        out.append(m)
    return out + [None, oechem.OEGraphMol()]


def _cells(html: str) -> list[str]:
    return re.findall(r"<td>(.*?)</td>", html, flags=re.DOTALL)


def _images(cells: list[str]) -> list[str]:
    return [re.sub(r"Creation Date.*?-->", "", c) for c in cells]


def _marimo_html(formatted) -> str:
    # Formatters return a _CtxBoundImage for molecules and a plain string (empty for None) otherwise;
    # every value, None included, goes through the formatter so the public path is what is compared.
    return formatted._mime_()[1] if hasattr(formatted, "_mime_") else str(formatted)


@pytest.mark.parametrize("image_format", ["svg", "png"])
def test_pandas_and_polars_render_identical_cells(image_format):
    pdf = pd.DataFrame({"mol": pd.Series(_mols(), dtype=oepd.MoleculeDtype())})
    pdf["mol"].chem.set_render_options(image_format=image_format, device_pixel_ratio=1.0, max_heavy_atoms=100)
    pdf["mol"].chem.highlight("c1ccccc1")
    with pytest.warns(CNotebookWarning, match=r"Depiction alignment failed for 2 of 5 rows"):
        pdf["mol"].chem.align_depictions("first")
    plf = pl.DataFrame([pl.Series("mol", _mols(), dtype=oeplr.MoleculeType())])
    plf = plf.chem.set_render_options("mol", image_format=image_format, device_pixel_ratio=1.0, max_heavy_atoms=100)
    plf = plf.chem.highlight("mol", "c1ccccc1")
    with pytest.warns(CNotebookWarning, match=r"Depiction alignment failed for 2 of 5 rows"):
        plf = plf.chem.align_depictions("mol", "first")
    pandas_cells = _images(_cells(render_dataframe(pdf, max_rows=0)))
    polars_cells = _images(_cells(render_polars_dataframe(plf, max_rows=0)))
    assert pandas_cells == polars_cells
    assert "width:200px;height:200px" in pandas_cells[-1]
    assert "width:200px;height:200px" in pandas_cells[2]
    if image_format == "svg":
        assert "Empty Molecule" in pandas_cells[-1] and "Exceeds Max Heavy Atoms" in pandas_cells[2]


def test_marimo_formatters_match_table_renderers(monkeypatch):
    # Drive the public formatter functions, not the private factory, so the frame adapters,
    # the backend-specific value access and the format_mapping wiring are all exercised.
    captured: dict[str, object] = {}

    def fake_table(frame, **kwargs):
        captured.update(kwargs)

        class _T:
            def _mime_(self):
                return ("text/html", "")

        return _T()

    monkeypatch.setattr(me, "table", fake_table)

    pdf = pd.DataFrame({"mol": pd.Series(_mols(), dtype=oepd.MoleculeDtype())})
    pdf["mol"].chem.set_render_options(image_format="svg", max_heavy_atoms=100)
    pdf["mol"].chem.highlight("c1ccccc1")
    with pytest.warns(CNotebookWarning, match=r"Depiction alignment failed for 2 of 5 rows"):
        pdf["mol"].chem.align_depictions("first")
    me.marimo_pandas_formatter(pdf)
    pandas_formatter = captured["format_mapping"]["mol"]
    pandas_marimo = [_marimo_html(pandas_formatter(m)) for m in pdf["mol"]]
    assert _images(pandas_marimo) == _images(_cells(render_dataframe(pdf, max_rows=0)))

    captured.clear()
    plf = pl.DataFrame([pl.Series("mol", _mols(), dtype=oeplr.MoleculeType())])
    plf = plf.chem.set_render_options("mol", image_format="svg", max_heavy_atoms=100)
    with pytest.warns(CNotebookWarning, match=r"Depiction alignment failed for 2 of 5 rows"):
        plf = plf.chem.highlight("mol", "c1ccccc1").chem.align_depictions("mol", "first")
    me.marimo_polars_formatter(plf)
    polars_formatter = captured["format_mapping"]["mol"]
    polars_marimo = [_marimo_html(polars_formatter(m)) for m in plf.get_column("mol").to_list()]
    assert _images(polars_marimo) == _images(_cells(render_polars_dataframe(plf, max_rows=0)))
    assert _images(polars_marimo) == _images(pandas_marimo)


def test_fingerprint_similarity_parity():
    mols = _mols()[:2] + [None]
    with pytest.warns(CNotebookWarning, match=r"produced no per-bond attribution for 1 of 3 rows"):
        pdf = pd.DataFrame({"mol": pd.Series(mols, dtype=oepd.MoleculeDtype())}).chem.fingerprint_similarity("mol")
    with pytest.warns(CNotebookWarning, match=r"produced no per-bond attribution for 1 of 3 rows"):
        plf = pl.DataFrame([pl.Series("mol", mols, dtype=oeplr.MoleculeType())]).chem.fingerprint_similarity("mol")
    assert list(pdf["fingerprint_tanimoto"].fillna(-1)) == [(-1 if t is None else t) for t in plf["fingerprint_tanimoto"].to_list()]
    ctx = CNotebookContext(image_format="svg")
    p_html = _images(_cells(render_dataframe(pdf[["target_similarity"]], ctx=ctx)))
    l_html = _images(_cells(render_polars_dataframe(plf.select("target_similarity"), ctx=ctx)))
    assert p_html == l_html
