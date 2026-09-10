import time

import pytest
from openeye import oechem

from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import CNotebookError
from cnotebook.core.render import make_depiction
from cnotebook.core.table import (
    CellTokens,
    ColumnKind,
    RowWindow,
    cell_html,
    pandas_max_rows_argument,
    polars_row_window,
    render_table,
)

# Hostile payloads reused by the escaping tests, with their expected escaped forms.
SCRIPT_PAYLOAD = "</td><script>alert(1)</script>"
ESCAPED_SCRIPT = "&lt;/td&gt;&lt;script&gt;alert(1)&lt;/script&gt;"
ATTRIBUTE_PAYLOAD = 'x" onmouseover="1'
ESCAPED_ATTRIBUTE = "x&quot; onmouseover=&quot;1"


class ListFrameAdapter:
    """Minimal adapter over parallel lists for testing render_table.

    ``index`` is ``True`` for row positions, ``False`` for no index column, or a
    sequence of explicit index values.
    """

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
        if self._index is True:
            return str(row)
        if self._index is False:
            return None
        return str(self._index[row])

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
    nonce = a.split("-")[1]
    assert a != b and a.startswith("@@CN-") and len(nonce) == 16
    assert tokens.substitute(f"<td>{a}</td><td>{b}</td>") == "<td><img a></td><td><img b></td>"
    with pytest.raises(CNotebookError) as duplicated:
        tokens.substitute(f"<td>{a}</td><td>{a}</td><td>{b}</td>")
    with pytest.raises(CNotebookError) as missing:
        tokens.substitute("<td>nothing</td>")
    # The message names the cell index and its count, never the nonce itself.
    assert nonce not in str(duplicated.value) and nonce not in str(missing.value)
    assert "2 times" in str(duplicated.value) and "0 times" in str(missing.value)


def test_cell_tokens_reject_an_unknown_token_index():
    tokens = CellTokens()
    token = tokens.token_for("<img a>")
    nonce = token.split("-")[1]
    with pytest.raises(CNotebookError) as unknown:
        tokens.substitute(f"<td>{token}</td><td>@@CN-{nonce}-2@@</td>")
    assert nonce not in str(unknown.value)


def test_cell_tokens_are_unpredictable_per_render():
    assert CellTokens().token_for("x").split("-")[1] != CellTokens().token_for("x").split("-")[1]


def test_cell_tokens_substitute_scales_to_large_documents():
    tokens = CellTokens()
    cells = [
        f'<svg xmlns="http://www.w3.org/2000/svg"><title>cell {i}</title>'
        f'<path d="{"M0 0L1 1" * 75}"/></svg>'
        for i in range(4000)
    ]
    document = "".join(
        f"<tr><th>{i}</th><td>{tokens.token_for(cell)}</td><td>row {i}</td></tr>"
        for i, cell in enumerate(cells)
    )
    expected = "".join(
        f"<tr><th>{i}</th><td>{cell}</td><td>row {i}</td></tr>" for i, cell in enumerate(cells)
    )
    start = time.perf_counter()
    rendered = tokens.substitute(document)
    elapsed = time.perf_counter() - start
    assert rendered == expected
    assert "@@CN-" not in rendered
    assert elapsed < 2.0, f"substitution of {len(cells)} cells took {elapsed:.2f}s"


def test_cell_tokens_substitute_around_hostile_and_foreign_token_text():
    foreign = CellTokens().token_for("<img foreign>")
    tokens = CellTokens()
    token = tokens.token_for("<svg>depiction</svg>")
    document = (
        '<table border="1" class="dataframe"><tbody><tr>'
        f"<th>{ESCAPED_SCRIPT}</th>"
        f"<td>{token}</td>"
        f"<td>{ESCAPED_ATTRIBUTE}</td>"
        f"<td>{foreign}</td>"
        "</tr></tbody></table>"
    )
    rendered = tokens.substitute(document)
    assert "<svg>depiction</svg>" in rendered
    assert foreign in rendered  # another render's nonce is left untouched
    assert ESCAPED_SCRIPT in rendered and ESCAPED_ATTRIBUTE in rendered
    assert "<script>" not in rendered and 'onmouseover="1' not in rendered


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
        (2, 1, None, [0], []),  # truncated with an empty tail
        (5, 5, None, list(range(5)), []),  # nrows == limit
        (6, 5, None, [0, 1, 2], [4, 5]),  # nrows == limit + 1
    ],
)
def test_polars_row_window(nrows, max_rows, configured, head, tail):
    window = polars_row_window(nrows, max_rows, configured)
    assert isinstance(window, RowWindow)
    assert window.head == head and window.tail == tail and window.total == nrows
    assert window.truncated == (len(head) + len(tail) < nrows)


def test_cell_html_dispatches_each_column_kind():
    ctx = CNotebookContext(image_format="svg")
    mol = _mol()
    query = oechem.OEQMol(mol)
    display = make_depiction(mol, ctx=ctx).display
    design_unit = oechem.OEDesignUnit()

    assert "<svg" in cell_html(ColumnKind.MOLECULE, mol, ctx)
    assert "<svg" in cell_html(ColumnKind.QUERY, query, ctx)
    assert "<svg" in cell_html(ColumnKind.DISPLAY, display, ctx)
    assert "<svg" in cell_html(ColumnKind.DESIGN_UNIT, design_unit, ctx)
    assert cell_html(ColumnKind.OTHER, "<b>x</b>", ctx) == "&lt;b&gt;x&lt;/b&gt;"
    assert cell_html(ColumnKind.OTHER, None, ctx) == ""

    # A swapped dispatch cannot depict anything: every formatter escapes a value
    # of the wrong type instead of rendering it.
    assert "<svg" not in cell_html(ColumnKind.MOLECULE, display, ctx)
    assert "<svg" not in cell_html(ColumnKind.DISPLAY, design_unit, ctx)
    assert "<svg" not in cell_html(ColumnKind.DESIGN_UNIT, display, ctx)
    assert "<svg" not in cell_html(ColumnKind.OTHER, mol, ctx)


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


def test_render_table_escapes_hostile_labels_index_and_dtypes():
    foreign_token = CellTokens().token_for("<img foreign>")
    payloads = [SCRIPT_PAYLOAD, ATTRIBUTE_PAYLOAD, foreign_token]
    adapter = ListFrameAdapter(
        payloads,
        [ColumnKind.OTHER] * 3,
        [[payload] for payload in payloads],
        dtypes=payloads,
        index=[SCRIPT_PAYLOAD],
    )
    html = render_table(adapter)
    assert "<script>" not in html and "</script>" not in html
    assert 'onmouseover="1' not in html
    # Header label, dtype row, body cell and index value are each escaped once.
    assert html.count(ESCAPED_SCRIPT) == 4 and html.count(ESCAPED_ATTRIBUTE) == 3
    assert f"<td>{ESCAPED_SCRIPT}</td>" in html and f"<th>{ESCAPED_SCRIPT}</th>" in html
    # A token from another render is inert text here: render_table substitutes nothing.
    assert html.count(foreign_token) == 3
    assert html.count("<tr") == 3 and html.count("<td>") == 3


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


def test_render_table_single_row_window():
    adapter = ListFrameAdapter(["x"], [ColumnKind.OTHER], [list(range(10))])
    html = render_table(adapter, max_rows=1)
    assert html.count("<tr") == 1 + 1 + 1  # header, one body row, ellipsis row
    assert html.count("<td>...</td>") == 1
    assert "<td>0</td>" in html and "<td>9</td>" not in html


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
