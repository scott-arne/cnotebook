"""Backend-neutral table rendering: cell tokens, row windows and a markup writer.

pandas frames use their own HTML writer plus :class:`CellTokens`; polars frames
(and any adapter without a native writer) use :func:`render_table`.
"""

from __future__ import annotations

import html
import math
import re
import secrets
from collections.abc import Hashable
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from cnotebook.core import formatters
from cnotebook.core.context import CNotebookContext
from cnotebook.core.errors import CNotebookError


class ColumnKind(Enum):
    """How a column is rendered."""

    MOLECULE = "molecule"
    QUERY = "query"
    DISPLAY = "display"
    DESIGN_UNIT = "design_unit"
    OTHER = "other"


class CellTokens:
    """Per-render registry mapping unpredictable placeholder tokens to cell HTML."""

    def __init__(self) -> None:
        self._nonce = secrets.token_hex(8)
        self._cells: list[str] = []
        # Matches only this registry's own token grammar, so tokens minted by
        # another render (a different nonce) are left alone as ordinary text.
        self._token_re = re.compile(rf"@@CN-{re.escape(self._nonce)}-([1-9][0-9]*)@@")

    def token_for(self, cell_html: str) -> str:
        """Register *cell_html* and return its token.

        :param cell_html: Trusted depiction HTML.
        :returns: Token of the form ``@@CN-<nonce>-<n>@@``.
        """
        self._cells.append(cell_html)
        return f"@@CN-{self._nonce}-{len(self._cells)}@@"

    def substitute(self, document: str) -> str:
        """Replace every registered token in *document* in a single pass.

        The caller must render exactly the rows it tokenized: every registered
        token has to occur in *document* exactly once, so a writer that drops,
        repeats or reorders a tokenized row fails closed instead of emitting a
        document with a stray token or a missing cell.

        :param document: HTML produced by a backend writer.
        :returns: The document with tokens replaced.
        :raises CNotebookError: If a token carries an unregistered index, or if
            any registered token does not occur exactly once.
        """
        seen = [0] * len(self._cells)

        def replace(match: re.Match[str]) -> str:
            index = int(match.group(1))
            if index > len(self._cells):
                raise CNotebookError(f"Cell token {index} is not registered")
            seen[index - 1] += 1
            # Returned from a callback rather than used as a template, so
            # backslashes and group references in the cell HTML stay literal.
            return self._cells[index - 1]

        substituted = self._token_re.sub(replace, document)
        for index, count in enumerate(seen, start=1):
            if count != 1:
                raise CNotebookError(f"Cell token {index} occurred {count} times; expected exactly once")
        return substituted


@dataclass
class RowWindow:
    """Row positions to render: ``head`` before the ellipsis, ``tail`` after it."""

    head: list[int]
    tail: list[int]
    total: int

    @property
    def truncated(self) -> bool:
        return len(self.head) + len(self.tail) < self.total


class FrameAdapter(Protocol):
    """What :func:`render_table` needs from a frame backend."""

    def columns(self) -> list[Hashable]: ...
    def kind(self, pos: int) -> ColumnKind: ...
    def nrows(self) -> int: ...
    def context(self, pos: int) -> CNotebookContext: ...
    def window(self, max_rows: int | None) -> RowWindow: ...
    def cell(self, row: int, pos: int) -> Any: ...
    def other_cell_text(self, row: int, pos: int) -> str: ...
    def index_text(self, row: int) -> str | None: ...
    def header_extra_rows(self) -> list[list[str]]: ...


def cell_html(kind: ColumnKind, value: Any, ctx: CNotebookContext) -> str:
    """Dispatch one cell to the shared formatters.

    :param kind: Column kind deciding which formatter renders the cell.
    :param value: Cell value; the formatters escape values of the wrong type.
    :param ctx: Column render context.
    :returns: Trusted depiction HTML for the molecule-like kinds, otherwise the
        HTML-escaped text of *value* (``""`` for ``None``).
    """
    if kind in (ColumnKind.MOLECULE, ColumnKind.QUERY):
        return formatters.molecule_cell_html(value, ctx)
    if kind is ColumnKind.DISPLAY:
        return formatters.display_cell_html(value, ctx)
    if kind is ColumnKind.DESIGN_UNIT:
        return formatters.design_unit_cell_html(value, ctx)
    return html.escape("" if value is None else str(value))


def pandas_max_rows_argument(
    nrows: int, max_rows: int | None, display_max_rows: int | None, display_min_rows: int | None
) -> int | None:
    """Value to pass as ``DataFrame.to_html(max_rows=...)`` (spec B1 decision table).

    :param nrows: Frame length.
    :param max_rows: Caller argument; ``None`` means the pandas rule, ``<= 0`` means all rows.
    :param display_max_rows: ``pandas.get_option("display.max_rows")``.
    :param display_min_rows: ``pandas.get_option("display.min_rows")``.
    :returns: ``None`` for no truncation, otherwise the row budget.
    """
    if max_rows is not None:
        return max_rows if max_rows > 0 else None
    if display_max_rows is None or nrows <= display_max_rows:
        return None
    return display_min_rows if display_min_rows is not None else display_max_rows


def polars_row_window(nrows: int, max_rows: int | None, configured: int | None) -> RowWindow:
    """Row window for polars frames (spec B1 decision table).

    :param nrows: Frame length.
    :param max_rows: Caller argument; ``None`` means the polars rule, ``<= 0`` means all rows.
    :param configured: ``POLARS_FMT_MAX_ROWS`` when set, else ``None`` (treated as 10).
    :returns: The window.
    """
    if max_rows is not None:
        limit: int | None = max_rows if max_rows > 0 else None
    else:
        budget = 10 if configured is None else configured
        limit = None if budget < 0 else budget
    if limit is None or nrows <= limit:
        return RowWindow(list(range(nrows)), [], nrows)
    head = math.ceil(limit / 2)
    tail = limit - head
    return RowWindow(list(range(head)), list(range(nrows - tail, nrows)), nrows)


def _th(text: Any) -> str:
    return f"<th>{html.escape(str(text), quote=True)}</th>"


def render_table(
    adapter: FrameAdapter, *, ctx: CNotebookContext | None = None, max_rows: int | None = None
) -> str:
    """Render a frame to pandas-style HTML markup.

    :param adapter: Frame backend.
    :param ctx: Overrides every column context when given.
    :param max_rows: See :func:`polars_row_window`.
    :returns: ``<table>`` markup; only depiction HTML is inserted raw.
    """
    labels = adapter.columns()
    kinds = [adapter.kind(pos) for pos in range(len(labels))]
    contexts = [ctx if ctx is not None else adapter.context(pos) for pos in range(len(labels))]
    window = adapter.window(max_rows)
    has_index = adapter.nrows() > 0 and adapter.index_text(0) is not None

    parts = ['<table border="1" class="dataframe">', "<thead>", '<tr style="text-align: right;">']
    if has_index:
        parts.append("<th></th>")
    for pos, label in enumerate(labels):
        style = ""
        if kinds[pos] is not ColumnKind.OTHER and contexts[pos].width > 0:
            style = f' style="min-width: {int(contexts[pos].width)}px;"'
        parts.append(f"<th{style}>{html.escape(str(label), quote=True)}</th>")
    parts.append("</tr>")
    for extra in adapter.header_extra_rows():
        parts.append("<tr>" + ("<th></th>" if has_index else "") + "".join(_th(c) for c in extra) + "</tr>")
    parts.append("</thead><tbody>")

    def row_html(row: int) -> str:
        cells = []
        if has_index:
            cells.append(_th(adapter.index_text(row)))
        for pos in range(len(labels)):
            if kinds[pos] is ColumnKind.OTHER:
                cells.append(f"<td>{html.escape(adapter.other_cell_text(row, pos))}</td>")
            else:
                cells.append(f"<td>{cell_html(kinds[pos], adapter.cell(row, pos), contexts[pos])}</td>")
        return "<tr>" + "".join(cells) + "</tr>"

    for row in window.head:
        parts.append(row_html(row))
    if window.truncated:
        parts.append("<tr>" + ("<th>...</th>" if has_index else "") + "".join("<td>...</td>" for _ in labels) + "</tr>")
    for row in window.tail:
        parts.append(row_html(row))
    parts.append("</tbody></table>")
    return "".join(parts)
