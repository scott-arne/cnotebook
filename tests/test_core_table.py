import pytest
from openeye import oechem

from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import CNotebookError
from cnotebook.core.table import (
    CellTokens,
    ColumnKind,
    RowWindow,
    pandas_max_rows_argument,
    polars_row_window,
    render_table,
)


class ListFrameAdapter:
    """Minimal adapter over parallel lists for testing render_table."""

    def __init__(self, labels, kinds, columns, *, dtypes=None, index=True, ctx=None):
        self._labels, self._kinds, self._columns = labels, kinds, columns
        self._dtypes, self._index = dtypes, index
        self._ctx = ctx or CNotebookContext(image_format="svg")

    def columns(self):
        return list(self._labels)

    def kind(self, pos):
        return self._kinds[pos]

    def nrows(self):
        return len(self._columns[0]) if self._columns else 0

    def context(self, pos):
        return self._ctx

    def window(self, max_rows):
        return polars_row_window(self.nrows(), max_rows, None)

    def cell(self, row, pos):
        return self._columns[pos][row]

    def other_cell_text(self, row, pos):
        value = self._columns[pos][row]
        return "null" if value is None else str(value)

    def index_text(self, row):
        return str(row) if self._index else None

    def header_extra_rows(self):
        return [list(self._dtypes)] if self._dtypes else []


def _mol():
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    return mol


def test_cell_tokens_substitute_exactly_once():
    tokens = CellTokens()
    a = tokens.token_for("<img a>")
    b = tokens.token_for("<img b>")
    assert a != b and a.startswith("@@CN-") and len(a.split("-")[1]) == 16
    assert tokens.substitute(f"<td>{a}</td><td>{b}</td>") == "<td><img a></td><td><img b></td>"
    with pytest.raises(CNotebookError):
        tokens.substitute(f"<td>{a}</td><td>{a}</td><td>{b}</td>")
    with pytest.raises(CNotebookError):
        tokens.substitute("<td>nothing</td>")


def test_cell_tokens_are_unpredictable_per_render():
    assert CellTokens().token_for("x").split("-")[1] != CellTokens().token_for("x").split("-")[1]


@pytest.mark.parametrize(
    "nrows,max_rows,dmax,dmin,expected",
    [
        (100, 5, 60, 10, 5),
        (3, 5, 60, 10, 5),
        (100, 0, 60, 10, None),
        (100, -1, 60, 10, None),
        (100, None, 60, 10, 10),
        (50, None, 60, 10, None),
        (100, None, None, 10, None),
        (100, None, 60, None, 60),
    ],
)
def test_pandas_max_rows_argument(nrows, max_rows, dmax, dmin, expected):
    assert pandas_max_rows_argument(nrows, max_rows, dmax, dmin) == expected


@pytest.mark.parametrize(
    "nrows,max_rows,configured,head,tail",
    [
        (100, 5, None, [0, 1, 2], [98, 99]),
        (3, 5, None, [0, 1, 2], []),
        (100, 0, None, list(range(100)), []),
        (100, None, None, [0, 1, 2, 3, 4], [95, 96, 97, 98, 99]),
        (100, None, 4, [0, 1], [98, 99]),
        (100, None, -1, list(range(100)), []),
        (8, None, 10, list(range(8)), []),
    ],
)
def test_polars_row_window(nrows, max_rows, configured, head, tail):
    window = polars_row_window(nrows, max_rows, configured)
    assert isinstance(window, RowWindow)
    assert window.head == head and window.tail == tail and window.total == nrows
    assert window.truncated == bool(tail)


def test_render_table_escapes_labels_index_dtypes_and_cells():
    adapter = ListFrameAdapter(
        ["<b>name</b>", 'x" onmouseover="1'],
        [ColumnKind.OTHER, ColumnKind.OTHER],
        [["a&b", "<i>"], [1, None]],
        dtypes=["str<", "i64"],
    )
    html = render_table(adapter)
    assert "&lt;b&gt;name&lt;/b&gt;" in html and "&quot; onmouseover=&quot;1" in html
    assert "str&lt;" in html and "a&amp;b" in html and "&lt;i&gt;" in html and "<td>null</td>" in html
    assert "<b>name</b>" not in html and 'onmouseover="1' not in html
    assert html.startswith('<table border="1" class="dataframe">')


def test_render_table_renders_molecule_cells_and_min_width():
    ctx = CNotebookContext(image_format="svg", width=150)
    adapter = ListFrameAdapter(["mol"], [ColumnKind.MOLECULE], [[_mol(), None]], ctx=ctx, index=False)
    html = render_table(adapter)
    assert html.count("<svg") == 1
    assert 'min-width: 150px' in html
    assert "<th></th>" not in html.split("<tbody>")[0]


def test_render_table_truncation_row():
    adapter = ListFrameAdapter(["x"], [ColumnKind.OTHER], [[list(range(30))][0]])
    html = render_table(adapter, max_rows=4)
    assert html.count("<tr") == 1 + 4 + 1  # header rows are styled; body rows + ellipsis
    assert "<td>...</td>" in html and "<th>...</th>" in html


def test_render_table_explicit_ctx_overrides_columns():
    column_ctx = CNotebookContext(image_format="svg")
    override = CNotebookContext(image_format="png", device_pixel_ratio=1.0)
    adapter = ListFrameAdapter(["mol"], [ColumnKind.MOLECULE], [[_mol()]], ctx=column_ctx)
    assert "<svg" in render_table(adapter)
    assert "data:image/png" in render_table(adapter, ctx=override)


def test_render_table_token_like_text_in_cells_is_plain_text():
    adapter = ListFrameAdapter(["mol", "note"], [ColumnKind.MOLECULE, ColumnKind.OTHER],
                               [[_mol()], ["@@CN-0000000000000000-1@@"]])
    html = render_table(adapter)
    assert "@@CN-0000000000000000-1@@" in html
