"""anywidget front end for MolGrid (traits only, whole-container reassignment)."""

from __future__ import annotations

from pathlib import Path

import anywidget
import traitlets

__all__ = ["MolGridWidget"]

_STATIC = Path(__file__).parent / "static"
# Read when this module is imported rather than per instance: anywidget re-reads a
# Path-valued _esm for every widget it creates, and a notebook that shows a dozen grids
# would read the same two files a dozen times.
_ESM = (_STATIC / "molgrid.js").read_text(encoding="utf-8")
_STYLESHEET = (_STATIC / "molgrid.css").read_text(encoding="utf-8")


class MolGridWidget(anywidget.AnyWidget):
    """Live molecule grid; the ES module renders the cards straight into the output cell.

    The traits below are the whole protocol between :class:`~cnotebook.grid.MolGrid` and
    the front end. Containers are always reassigned rather than mutated in place, because
    traitlets only notifies on a new value, and the grid holds no state of its own: it
    renders what ``items``, ``config`` and ``images`` say and publishes what the user does
    through ``visible``, ``selection`` and ``smarts_request``.

    ``items`` is written once at creation; ``images`` grows as the front end asks for the
    pages it is about to show, so a grid of thousands of molecules never renders more than
    the user looks at.
    """

    _esm = _ESM
    _css = _STYLESHEET

    items = traitlets.List(traitlets.Dict()).tag(sync=True)
    config = traitlets.Dict().tag(sync=True)
    revision = traitlets.Int(0).tag(sync=True)
    # ipywidgets echoes every browser-originated trait update straight back to the browser
    # (JUPYTER_WIDGETS_ECHO is on by default), which would return the window a view just
    # published, and the query it just typed, to the view that produced them. The traits
    # only the front end writes therefore opt out; ``selection`` keeps the echo because
    # Python writes it too and other views of the same widget have to follow it.
    visible = traitlets.List(traitlets.Int()).tag(sync=True, echo_update=False)
    images = traitlets.Dict().tag(sync=True)
    selection = traitlets.List(traitlets.Int()).tag(sync=True)
    smarts_request = traitlets.Dict().tag(sync=True, echo_update=False)
    smarts_result = traitlets.Dict().tag(sync=True)
    error = traitlets.Unicode("").tag(sync=True)
