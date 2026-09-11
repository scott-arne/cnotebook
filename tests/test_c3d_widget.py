"""Tests for the C3D anywidget bridge (traits, commands, picks, screenshots)."""

import asyncio
import base64
import json
import logging

import pytest

pytest.importorskip("anywidget")

import traitlets

from cnotebook.c3d import widget as widget_module
from cnotebook.c3d.widget import C3DWidget, CommandHandle, CommandResult, PickEvent
from cnotebook.core.errors import CNotebookError


def _boom(_event):
    """Callback that always fails, used to pin the callback error policy."""
    raise ValueError("callback exploded")


# ---------------------------------------------------------------------------
# ESM assembly
# ---------------------------------------------------------------------------


def test_esm_contains_assets_and_no_sentinel():
    esm = C3DWidget._esm
    assert '{"__cnotebook_assets__": null}' not in esm
    assert '"threeDmol"' in esm and "escapeScriptJson" in esm


def test_esm_is_valid_javascript(tmp_path):
    import shutil
    import subprocess

    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    path = tmp_path / "c3d_widget_check.mjs"
    path.write_text(C3DWidget._esm, encoding="utf-8")
    result = subprocess.run(
        [node, "--check", str(path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


def test_esm_inlines_the_core_static_assets_verbatim():
    """The sentinel is replaced once with escaped, losslessly decodable asset text."""
    template = (widget_module._STATIC / "c3d_widget.js").read_text(encoding="utf-8")
    head, sentinel, tail = template.partition(widget_module._ASSET_SENTINEL)
    assert sentinel and widget_module._ASSET_SENTINEL not in tail

    esm = C3DWidget._esm
    assert esm.startswith(head) and esm.endswith(tail)
    assets = json.loads(esm[len(head) : len(esm) - len(tail)])

    assert set(assets) == {"threeDmol", "gui", "css"}
    core_static = widget_module._CORE_STATIC
    assert assets["threeDmol"] == (core_static / "3Dmol-min.js").read_text(encoding="utf-8")
    assert assets["gui"] == (core_static / "3dmol-gui.js").read_text(encoding="utf-8")
    assert assets["css"] == (core_static / "3dmol-gui.css").read_text(encoding="utf-8")
    # Script-context characters inside the bundles are escaped, and the module stays ASCII
    # so it can always be encoded (see viewer3d.escape_script_json).
    assert "\\u003c" in esm and esm.isascii()


def test_missing_sentinel_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(widget_module, "_STATIC", tmp_path)
    (tmp_path / "c3d_widget.js").write_text("export default { render() {} };", encoding="utf-8")
    with pytest.raises(CNotebookError, match="exactly once"):
        widget_module._load_esm()


def test_instances_share_the_module_built_at_import(monkeypatch):
    """No per-instance file reads: constructing a widget touches no asset file."""
    from pathlib import Path

    def forbidden(*args, **kwargs):
        raise AssertionError("C3DWidget must not read files per instance")

    monkeypatch.setattr(Path, "read_text", forbidden)
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    # The guard is live: building the module again would trip it.
    with pytest.raises(AssertionError):
        widget_module._load_esm()
    first = C3DWidget(payload="{}")
    second = C3DWidget(payload="{}")
    assert first._esm is C3DWidget._esm and second._esm is C3DWidget._esm


def test_widget_never_writes_into_core_static():
    before = {
        path.name: path.stat() for path in sorted(widget_module._CORE_STATIC.iterdir())
    }
    widget = C3DWidget(payload="{}")
    widget.submit("zoom")
    widget.set_view([1, 2, 3])
    widget_module._load_esm()
    after = {path.name: path.stat() for path in sorted(widget_module._CORE_STATIC.iterdir())}
    assert set(before) == set(after)
    for name, stat_before in before.items():
        assert (stat_before.st_size, stat_before.st_mtime_ns) == (
            after[name].st_size,
            after[name].st_mtime_ns,
        )


# ---------------------------------------------------------------------------
# Traits
# ---------------------------------------------------------------------------


def test_traits_match_the_d1_contract():
    traits = C3DWidget.class_traits()
    expected = {
        "payload": traitlets.Unicode,
        "width": traitlets.Int,
        "height": traitlets.Int,
        "status": traitlets.Unicode,
        "status_message": traitlets.Unicode,
        "commands": traitlets.List,
        "command_results": traitlets.List,
        "view": traitlets.List,
        "view_origin": traitlets.Unicode,
        "picked": traitlets.Dict,
        "screenshot_request": traitlets.Int,
        "screenshot": traitlets.Dict,
    }
    for name, kind in expected.items():
        assert isinstance(traits[name], kind), name
        assert traits[name].metadata.get("sync") is True, name
    widget = C3DWidget()
    assert widget.status == "loading" and widget.view_origin == "js"
    assert (widget.width, widget.height) == (800, 500)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def test_submit_reassigns_command_list_and_results_resolve_handles():
    widget = C3DWidget(payload="{}")
    first = widget.submit("zoom")
    second = widget.submit("orient")
    assert [c["id"] for c in widget.commands] == [1, 2]
    assert isinstance(first, CommandHandle) and not first.done
    seen = []
    first.add_done_callback(lambda h: seen.append(h.result.ok))
    widget.command_results = [{"id": 1, "ok": True, "output": ["Zoomed"]}]
    assert first.done and first.result == CommandResult(True, ["Zoomed"]) and seen == [True]
    assert [c["id"] for c in widget.commands] == [2]
    assert not second.done


def test_done_callback_added_after_resolution_runs_immediately():
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    widget.command_results = [{"id": handle.id, "ok": True, "output": []}]
    seen = []
    handle.add_done_callback(seen.append)
    assert seen == [handle]


def test_results_for_unknown_settled_or_malformed_commands_are_ignored():
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    widget.command_results = [{"id": handle.id, "ok": True, "output": ["done"]}]
    assert handle.result == CommandResult(True, ["done"])
    # A duplicate result, an id that was never submitted, and an entry without a usable
    # id must all be dropped rather than raise inside the trait observer.
    widget.command_results = [
        {"id": handle.id, "ok": False, "output": ["late"]},
        {"id": 99, "ok": True, "output": []},
        {"ok": True, "output": []},
        {"id": "not-a-number", "ok": True, "output": []},
    ]
    assert handle.result == CommandResult(True, ["done"])
    assert widget.commands == []


def test_handle_is_awaitable():
    widget = C3DWidget(payload="{}")

    async def scenario():
        handle = widget.submit("reset")
        asyncio.get_running_loop().call_soon(
            lambda: setattr(widget, "command_results", [{"id": handle.id, "ok": False, "output": ["bad"]}])
        )
        return await handle

    result = asyncio.run(scenario())
    assert result == CommandResult(False, ["bad"])


def test_wait_timeout_leaves_no_waiter_and_the_handle_stays_awaitable():
    widget = C3DWidget(payload="{}")

    async def scenario():
        handle = widget.submit("orient")
        with pytest.raises(CNotebookError, match="did not complete"):
            await handle.wait(timeout=0.01)
        assert handle._waiters == []
        widget.command_results = [{"id": handle.id, "ok": True, "output": ["late"]}]
        # Awaiting twice after the result arrived returns the same result each time.
        assert await handle == CommandResult(True, ["late"])
        assert await handle.wait(timeout=0.01) == CommandResult(True, ["late"])

    asyncio.run(scenario())


def test_done_callback_error_is_logged_and_later_callbacks_still_run(caplog):
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    seen = []
    handle.add_done_callback(_boom)
    handle.add_done_callback(seen.append)
    with caplog.at_level(logging.ERROR, logger="cnotebook"):
        widget.command_results = [{"id": handle.id, "ok": True, "output": []}]
    assert seen == [handle] and handle.done
    assert "callback exploded" in caplog.text


# ---------------------------------------------------------------------------
# Picks
# ---------------------------------------------------------------------------


def test_pick_callbacks_and_last_pick():
    widget = C3DWidget(payload="{}")
    events = []
    widget.on_pick(events.append)
    widget.picked = {"seq": 1, "atom": {"serial": 5, "resn": "LIG"}, "modifiers": {"shift": False}}
    assert isinstance(events[0], PickEvent) and events[0].atom["serial"] == 5
    assert widget.last_pick is events[0]


def test_pick_callback_error_is_logged_and_later_callbacks_still_run(caplog):
    widget = C3DWidget(payload="{}")
    events = []
    widget.on_pick(_boom)
    widget.on_pick(events.append)
    with caplog.at_level(logging.ERROR, logger="cnotebook"):
        widget.picked = {"seq": 7, "atom": {"serial": 1}, "modifiers": {}}
    assert [event.seq for event in events] == [7]
    assert widget.last_pick is not None and widget.last_pick.seq == 7
    assert "callback exploded" in caplog.text
    # The observer survived, so the next pick is still delivered.
    widget.picked = {"seq": 8, "atom": {"serial": 2}, "modifiers": {}}
    assert [event.seq for event in events] == [7, 8]


# ---------------------------------------------------------------------------
# Screenshots
# ---------------------------------------------------------------------------


def test_screenshot_future_resolves_bytes():
    widget = C3DWidget(payload="{}")

    async def scenario():
        future = widget.request_screenshot()
        seq = widget.screenshot_request
        asyncio.get_running_loop().call_soon(
            lambda: setattr(widget, "screenshot", {"seq": seq, "png_base64": base64.b64encode(b"abc").decode()})
        )
        return await asyncio.wait_for(future, 1)

    assert asyncio.run(scenario()) == b"abc"


def test_pre_display_screenshot_requests_coalesce():
    widget = C3DWidget(payload="{}")

    async def scenario():
        first = widget.request_screenshot()
        second = widget.request_screenshot()
        assert widget.screenshot_request == 2
        # After connecting, the front end answers only the highest outstanding sequence.
        asyncio.get_running_loop().call_soon(
            lambda: setattr(widget, "screenshot", {"seq": 2, "png_base64": base64.b64encode(b"xyz").decode()})
        )
        return await asyncio.gather(asyncio.wait_for(first, 1), asyncio.wait_for(second, 1))

    assert asyncio.run(scenario()) == [b"xyz", b"xyz"]
    assert widget._screenshot_futures == {}


def test_screenshot_answer_leaves_later_requests_pending():
    widget = C3DWidget(payload="{}")

    async def scenario():
        first = widget.request_screenshot()
        second = widget.request_screenshot()
        widget.screenshot = {"seq": 1, "png_base64": base64.b64encode(b"one").decode()}
        assert await asyncio.wait_for(first, 1) == b"one"
        assert not second.done() and list(widget._screenshot_futures) == [2]
        widget.screenshot = {"seq": 2, "png_base64": base64.b64encode(b"two").decode()}
        assert await asyncio.wait_for(second, 1) == b"two"

    asyncio.run(scenario())


def test_cancelled_screenshot_future_is_skipped():
    widget = C3DWidget(payload="{}")

    async def scenario():
        first = widget.request_screenshot()
        second = widget.request_screenshot()
        first.cancel()
        widget.screenshot = {"seq": 2, "png_base64": base64.b64encode(b"png").decode()}
        assert first.cancelled()
        assert await asyncio.wait_for(second, 1) == b"png"
        assert widget._screenshot_futures == {}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "message",
    [
        {"seq": 2, "error": "canvas is not ready"},
        {"seq": 2, "png_base64": ""},
        {"seq": 2, "png_base64": "not base64!"},
    ],
)
def test_screenshot_failure_rejects_pending_futures_once(message):
    widget = C3DWidget(payload="{}")

    async def scenario():
        first = widget.request_screenshot()
        second = widget.request_screenshot()
        widget.screenshot = message
        assert widget._screenshot_futures == {}
        for future in (first, second):
            with pytest.raises(CNotebookError, match="[Ss]creenshot"):
                await future
        # A repeated failure message must not settle the same futures twice.
        widget.screenshot = {**message, "seq": 3}

    asyncio.run(scenario())


def test_request_screenshot_requires_a_running_loop():
    widget = C3DWidget(payload="{}")
    with pytest.raises(RuntimeError, match="running event loop"):
        widget.request_screenshot()
    # A failed request must not leave the front end capturing a frame nobody awaits.
    assert widget.screenshot_request == 0
    assert widget._screenshot_futures == {}


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def test_set_view_marks_origin():
    widget = C3DWidget(payload="{}")
    widget.set_view([1, 2, 3])
    assert widget.view == [1.0, 2.0, 3.0] and widget.view_origin == "python"
