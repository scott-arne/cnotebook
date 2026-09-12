"""Tests for the C3D anywidget bridge (traits, commands, picks, screenshots)."""

import asyncio
import base64
import gc
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


# A well formed camera: 3Dmol's getView() returns [x, y, z, zoom, qx, qy, qz, qw].
_VIEW = [1.0, 2.0, 3.0, 4.0, 0.0, 0.0, 0.0, 1.0]


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
    widget.set_view(_VIEW)
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


# name -> (trait type, element type or None, default, echo_update metadata or None)
_D1_TRAITS = {
    "payload": (traitlets.Unicode, None, "{}", None),
    "width": (traitlets.Int, None, 800, None),
    "height": (traitlets.Int, None, 500, None),
    "status": (traitlets.Unicode, None, "loading", False),
    "status_message": (traitlets.Unicode, None, "", False),
    "commands": (traitlets.List, traitlets.Dict, [], None),
    "command_results": (traitlets.List, traitlets.Dict, [], False),
    "view": (traitlets.List, traitlets.Float, [], None),
    "view_origin": (traitlets.Unicode, None, "js", None),
    "view_request": (traitlets.Int, None, 0, None),
    "picked": (traitlets.Dict, None, {}, False),
    "screenshot_request": (traitlets.Int, None, 0, None),
    "screenshot": (traitlets.Dict, None, {}, False),
}


def test_traits_match_the_d1_contract():
    """Every D1 trait: type, element type, default, sync tag and echo policy."""
    traits = C3DWidget.class_traits()
    widget = C3DWidget()
    for name, (kind, element, default, echo) in _D1_TRAITS.items():
        trait = traits[name]
        assert isinstance(trait, kind), name
        assert trait.metadata.get("sync") is True, name
        assert trait.metadata.get("echo_update") is echo, name
        if element is not None:
            assert isinstance(trait._trait, element), name
        assert getattr(widget, name) == default, name
    # Only the traits the browser writes suppress the echo; echoing those would send a
    # multi-megabyte screenshot straight back to the browser that produced it.
    suppressed = {n for n, t in traits.items() if t.metadata.get("echo_update") is False}
    assert suppressed == {"command_results", "picked", "screenshot", "status", "status_message"}


def test_browser_written_traits_are_not_echoed_back(monkeypatch):
    """The echo would return the screenshot to the very frame that produced it."""
    from ipywidgets.widgets.widget import JUPYTER_WIDGETS_ECHO

    if not JUPYTER_WIDGETS_ECHO:
        pytest.skip("ipywidgets echo is disabled in this environment")
    widget = C3DWidget(payload="{}")
    sent = []
    monkeypatch.setattr(widget, "_send", lambda msg, buffers=None: sent.append(msg))
    widget.set_state(
        {
            "screenshot": {"seq": 1, "png_base64": base64.b64encode(b"png").decode()},
            "picked": {"seq": 1, "atom": {"serial": 1}, "modifiers": {}},
            "status": "ready",
            "view": [1.0, 2.0],
        }
    )
    echoed = [msg["state"] for msg in sent if msg.get("method") == "echo_update"]
    # Only the bidirectional view trait is echoed; the browser-written ones are not.
    assert [set(state) for state in echoed] == [{"view"}]


def test_set_state_delivers_a_browser_message_batch():
    """ipywidgets' real comm entry point drives every browser-to-kernel observer."""
    widget = C3DWidget(payload="{}")

    async def scenario():
        handle = widget.submit("zoom")
        picks = []
        widget.on_pick(picks.append)
        future = widget.request_screenshot()
        widget.set_state(
            {
                "command_results": [{"id": handle.id, "ok": True, "output": ["Zoomed"]}],
                "picked": {"seq": 4, "atom": {"serial": 9}, "modifiers": {"shift": True}},
                "screenshot": {
                    "seq": widget.screenshot_request,
                    "png_base64": base64.b64encode(b"png").decode(),
                },
            }
        )
        assert handle.result == CommandResult(True, ["Zoomed"])
        assert widget.commands == []
        assert [pick.seq for pick in picks] == [4]
        assert widget.last_pick is not None and widget.last_pick.modifiers == {"shift": True}
        assert await asyncio.wait_for(future, 1) == b"png"

    asyncio.run(scenario())


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


@pytest.mark.parametrize(
    "entry",
    [
        {"id": 1.9, "ok": True, "output": []},
        {"id": 1.0, "ok": True, "output": []},
        {"id": True, "ok": True, "output": []},
        {"id": "1", "ok": True, "output": []},
        {"id": 1, "ok": "false", "output": []},
        {"id": 1, "ok": 1, "output": []},
        {"id": 1, "ok": None, "output": []},
        {"id": 1, "ok": True, "output": "Zoomed"},
        {"id": 1, "ok": True, "output": [1, 2]},
        {"id": 1, "ok": True, "output": None},
    ],
)
def test_malformed_command_results_settle_nothing(entry, caplog):
    """Nothing is coerced: a bad entry leaves the handle pending and the command queued.

    Truncating ``1.9`` would settle command 1, and ``"false"`` is truthy, so a coerced
    failure would be reported as a success.
    """
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    assert handle.id == 1
    with caplog.at_level(logging.DEBUG, logger="cnotebook"):
        widget.command_results = [entry]
    assert not handle.done
    assert [c["id"] for c in widget.commands] == [1]
    assert "malformed" in caplog.text


def test_a_result_without_output_means_no_output():
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    widget.command_results = [{"id": handle.id, "ok": True}]
    assert handle.result == CommandResult(True, [])


def test_a_malformed_result_does_not_stop_the_entries_after_it():
    """traitlets rejects a non-mapping entry today; the observer must survive one anyway."""
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    widget._on_results({"new": ["not a mapping", {"id": handle.id, "ok": True, "output": []}]})
    assert handle.result == CommandResult(True, [])


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


@pytest.mark.parametrize(
    "message",
    [
        {"seq": True, "atom": {}, "modifiers": {}},
        {"seq": 2.5, "atom": {}, "modifiers": {}},
        {"seq": "3", "atom": {}, "modifiers": {}},
        {"atom": {}, "modifiers": {}},
        {"seq": 1, "atom": "LIG", "modifiers": {}},
        {"seq": 1, "atom": {}, "modifiers": ["shift"]},
    ],
)
def test_malformed_picks_are_ignored(message, caplog):
    widget = C3DWidget(payload="{}")
    events = []
    widget.on_pick(events.append)
    with caplog.at_level(logging.DEBUG, logger="cnotebook"):
        widget.picked = message
    assert events == [] and widget.last_pick is None
    assert "malformed" in caplog.text


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


def test_screenshot_future_is_registered_before_the_request_is_published():
    """The registry already holds the future when the front end sees the new sequence."""
    widget = C3DWidget(payload="{}")
    seen = []
    widget.observe(
        lambda change: seen.append((change["new"], dict(widget._screenshot_futures))),
        names=["screenshot_request"],
    )

    async def scenario():
        future = widget.request_screenshot()
        ((seq, registry),) = seen
        assert seq == 1 and list(registry) == [1] and registry[1] is future
        future.cancel()

    asyncio.run(scenario())


def test_screenshot_answer_after_its_loop_closed_is_dropped():
    """A request that outlived its event loop must not raise out of the observer."""
    widget = C3DWidget(payload="{}")
    holder = []

    async def request():
        holder.append(widget.request_screenshot())

    # The notebook cell ends with the request outstanding, so asyncio.run closes the
    # loop the future belongs to; settling it later would raise "Event loop is closed".
    asyncio.run(request())
    assert list(widget._screenshot_futures) == [1] and holder[0].get_loop().is_closed()

    async def answer():
        widget.screenshot = {"seq": 1, "png_base64": base64.b64encode(b"late").decode()}

    asyncio.run(answer())
    assert widget._screenshot_futures == {}
    assert not holder[0].done()


def test_dropped_rejected_screenshot_future_is_not_logged_as_unretrieved(caplog):
    """A fire-and-forget request that fails must not spam the kernel log at collection."""
    widget = C3DWidget(payload="{}")
    holder = []

    async def scenario():
        holder.append(widget.request_screenshot())
        widget.screenshot = {"seq": 1, "error": "no canvas"}
        await asyncio.sleep(0)  # let the loop run the future's done callbacks

    with caplog.at_level(logging.ERROR, logger="asyncio"):
        asyncio.run(scenario())
        # asyncio keeps a rejected future flagged for logging until its exception is read.
        assert holder[0]._log_traceback is False
        holder.clear()
        gc.collect()
    assert "never retrieved" not in caplog.text


def test_request_screenshot_requires_a_running_loop():
    widget = C3DWidget(payload="{}")
    with pytest.raises(RuntimeError, match="running event loop"):
        widget.request_screenshot()
    # A failed request must not leave the front end capturing a frame nobody awaits.
    assert widget.screenshot_request == 0
    assert widget._screenshot_futures == {}


def test_unanswered_screenshot_requests_do_not_accumulate():
    """A viewer that never answers is the timeout case; it must not leak one future each."""
    widget = C3DWidget(payload="{}")

    async def scenario():
        for _ in range(100):
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(widget.request_screenshot(), 0)
        await asyncio.sleep(0)  # let any queued done callbacks run
        assert widget.screenshot_request == 100
        assert widget._screenshot_futures == {}

    asyncio.run(scenario())


def test_a_later_request_survives_an_older_futures_cleanup():
    """Cleanup is keyed to the exact future, so a request under a reused key is kept."""
    widget = C3DWidget(payload="{}")

    async def scenario():
        stale = widget.request_screenshot()
        stale.cancel()
        await asyncio.sleep(0)
        assert widget._screenshot_futures == {}
        fresh = widget.request_screenshot()
        assert widget._screenshot_futures == {2: fresh}
        # An older future's callback replayed against a reused sequence is a no-op.
        widget._forget_screenshot(2, stale)
        assert widget._screenshot_futures == {2: fresh}
        widget.screenshot = {"seq": 2, "png_base64": base64.b64encode(b"ok").decode()}
        assert await asyncio.wait_for(fresh, 1) == b"ok"

    asyncio.run(scenario())


def test_close_fails_pending_screenshot_requests():
    widget = C3DWidget(payload="{}")

    async def scenario():
        future = widget.request_screenshot()
        widget.close()
        assert widget._screenshot_futures == {}
        # The rejection is read inside close(), so a caller who never awaits it gets no
        # "Future exception was never retrieved" traceback in the kernel log.
        assert future.done() and future._log_traceback is False
        with pytest.raises(CNotebookError, match="widget closed"):
            await future
        widget.close()  # closing twice settles nothing and must not raise

    asyncio.run(scenario())


def test_close_leaves_a_request_whose_loop_has_gone():
    """Settling a future on a closed loop would raise out of close()."""
    widget = C3DWidget(payload="{}")
    holder = []

    async def request():
        holder.append(widget.request_screenshot())

    asyncio.run(request())
    assert list(widget._screenshot_futures) == [1]
    widget.close()
    assert widget._screenshot_futures == {}
    assert not holder[0].done()


def test_close_fails_pending_commands():
    """The comm goes with the widget, so a queued command can never be answered."""
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    seen = []
    handle.add_done_callback(seen.append)
    widget.close()
    assert handle.done and handle.result == CommandResult(False, ["widget closed"])
    assert seen == [handle] and widget._handles == {}
    widget.close()  # closing twice settles nothing and must not raise


def test_close_settles_a_command_submitted_from_a_done_callback():
    """Closing runs done callbacks, and one of them may submit; that must not hang."""
    widget = C3DWidget(payload="{}")
    first = widget.submit("zoom")
    late = []
    first.add_done_callback(lambda _handle: late.append(widget.submit("center")))
    widget.close()
    assert first.result == CommandResult(False, ["widget closed"])
    assert late[0].done and late[0].result == CommandResult(False, ["widget closed"])
    assert widget._handles == {}


def test_close_clears_the_command_queue():
    """Nothing can answer the queue now, and a second view must not replay it."""
    widget = C3DWidget(payload="{}")
    widget.submit("zoom")
    assert [c["command"] for c in widget.commands] == ["zoom"]
    widget.close()
    assert widget.commands == []


def test_work_offered_after_close_is_refused_rather_than_left_pending():
    widget = C3DWidget(payload="{}")
    widget.close()

    handle = widget.submit("zoom")
    assert handle.done and handle.result == CommandResult(False, ["widget closed"])
    assert widget.commands == [] and widget._handles == {}

    async def request_a_screenshot():
        with pytest.raises(CNotebookError, match="widget closed"):
            await widget.request_screenshot()

    asyncio.run(request_a_screenshot())
    assert widget._screenshot_futures == {}

    with pytest.raises(CNotebookError, match="widget closed"):
        widget.set_view(_VIEW)


def test_close_leaves_a_command_waiter_whose_loop_has_gone():
    """Settling a waiter on a closed loop would raise out of close()."""
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")
    holder = []

    async def abandon_a_waiter():
        # What is left behind when the loop that ran `await handle` closed before the
        # waiter could be removed, e.g. a cell whose task was still pending.
        future = asyncio.get_running_loop().create_future()
        handle._waiters.append(future)
        holder.append(future)

    asyncio.run(abandon_a_waiter())
    widget.close()
    assert handle.done and not holder[0].done()


@pytest.mark.parametrize("seq", [True, 1.0, "1", None])
def test_screenshots_without_a_plain_integer_sequence_are_ignored(seq, caplog):
    widget = C3DWidget(payload="{}")

    async def scenario():
        future = widget.request_screenshot()
        with caplog.at_level(logging.DEBUG, logger="cnotebook"):
            widget.screenshot = {"seq": seq, "png_base64": base64.b64encode(b"png").decode()}
        assert not future.done() and widget._screenshot_futures == {1: future}
        assert "without a sequence" in caplog.text
        future.cancel()

    asyncio.run(scenario())


def test_duplicate_answers_from_a_second_view_are_ignored():
    """Every view mirrors every command and answers every screenshot request.

    Two views of one widget are two independent viewer documents, so the kernel is told
    each outcome once per view. The first answer settles the handle and the futures; the
    later ones must be dropped rather than settle anything twice or raise in the observer.
    """
    widget = C3DWidget(payload="{}")
    handle = widget.submit("zoom")

    async def scenario():
        future = widget.request_screenshot()
        widget.command_results = [{"id": handle.id, "ok": True, "output": ["first view"]}]
        widget.screenshot = {"seq": 1, "png_base64": base64.b64encode(b"first").decode()}
        assert await asyncio.wait_for(future, 1) == b"first"

        widget.command_results = [{"id": handle.id, "ok": False, "output": ["second view"]}]
        widget.screenshot = {"seq": 1, "png_base64": base64.b64encode(b"second").decode()}
        assert handle.result == CommandResult(True, ["first view"])
        assert widget.commands == [] and widget._screenshot_futures == {}

    asyncio.run(scenario())


# ---------------------------------------------------------------------------
# View
# ---------------------------------------------------------------------------


def test_set_view_marks_origin():
    widget = C3DWidget(payload="{}")
    widget.set_view(_VIEW)
    assert widget.view == _VIEW and widget.view_origin == "python"


def test_set_view_counts_requests_so_an_unchanged_camera_still_reaches_the_frame():
    widget = C3DWidget(payload="{}")
    widget.set_view(_VIEW)
    assert widget.view_request == 1
    # traitlets drops an assignment equal to the current value, so re-applying a stored
    # camera after the user moved it would notify nobody. The counter is what the front
    # end observes, and it always moves.
    seen = []
    widget.observe(lambda change: seen.append(change["new"]), names="view_request")
    widget.set_view(list(_VIEW))
    assert widget.view_request == 2 and seen == [2]
    assert widget.view == _VIEW and widget.view_origin == "python"


@pytest.mark.parametrize(
    "bad",
    [
        [1.0, 2.0, 3.0],
        [*_VIEW, 9.0],
        [*_VIEW[:7], "1"],
        [*_VIEW[:7], float("nan")],
        [*_VIEW[:7], float("inf")],
        [*_VIEW[:7], True],
        "12345678",
        # Both iterate into eight numbers: bytes yield their byte values and a mapping
        # yields its keys, so either would be adopted as a camera nobody asked for.
        b"12345678",
        dict.fromkeys(range(8)),
        None,
        42,
    ],
)
def test_set_view_rejects_a_view_the_frame_could_not_apply(bad):
    widget = C3DWidget(payload="{}")
    with pytest.raises(ValueError):
        widget.set_view(bad)
    # A rejected request leaves nothing half applied: no camera, no origin, no request.
    assert widget.view == [] and widget.view_origin == "js" and widget.view_request == 0


def test_set_view_accepts_integer_coordinates():
    widget = C3DWidget(payload="{}")
    widget.set_view([1, 2, 3, 4, 0, 0, 0, 1])
    assert widget.view == _VIEW


def test_set_view_accepts_any_sequence_of_eight_numbers():
    """A saved camera is as likely to be a tuple or a numpy row as a list."""
    numpy = pytest.importorskip("numpy")
    for view in (tuple(_VIEW), (coordinate for coordinate in _VIEW), numpy.array(_VIEW)):
        widget = C3DWidget(payload="{}")
        widget.set_view(view)
        assert widget.view == _VIEW and widget.view_request == 1


def test_set_view_accepts_numpy_rows_of_any_numeric_dtype():
    """Only float64 is a Python float; a float32 or int64 row is a camera all the same."""
    numpy = pytest.importorskip("numpy")
    for dtype in (numpy.float32, numpy.float64, numpy.int64, numpy.int32):
        widget = C3DWidget(payload="{}")
        widget.set_view(numpy.array(_VIEW, dtype=dtype))
        assert widget.view == _VIEW and widget.view_request == 1

    # The wider type check must not cost the finiteness one.
    widget = C3DWidget(payload="{}")
    with pytest.raises(ValueError, match="finite"):
        widget.set_view(numpy.array([*_VIEW[:7], numpy.float32("nan")]))
    # A numpy bool row is eight values, but none of them is a coordinate.
    with pytest.raises(ValueError, match="numbers"):
        widget.set_view(numpy.ones(8, dtype=bool))
    assert widget.view == [] and widget.view_request == 0
