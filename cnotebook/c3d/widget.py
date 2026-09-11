"""anywidget bridge for the C3D viewer (traits only, whole-container reassignment)."""

from __future__ import annotations

import asyncio
import base64
import logging
from collections.abc import Callable, Generator
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import anywidget
import traitlets

from cnotebook.core.errors import CNotebookError
from cnotebook.core.viewer3d import escape_script_json

__all__ = ["C3DWidget", "CommandHandle", "CommandResult", "PickEvent"]

log = logging.getLogger("cnotebook")

_STATIC = Path(__file__).parent / "static"
_CORE_STATIC = Path(__file__).parent.parent / "core" / "static"
_ASSET_SENTINEL = '{"__cnotebook_assets__": null}'
_DEFAULT_TIMEOUT = 30.0


def _load_esm() -> str:
    """Read the widget module template and inline the viewer assets.

    The bundles are serialized with :func:`~cnotebook.core.viewer3d.escape_script_json`,
    the escaping the front end applies to its own payloads: the inlined JSON object
    literal then carries no ``<``, ``>``, ``&``, U+2028 or U+2029, and the module stays
    pure ASCII so it can always be encoded. Only that literal is script-safe; the
    template around it keeps raw ``<`` characters (``buildSrcdoc`` writes ``</script>``
    literals of its own). That is sound because anywidget loads this file as an ES
    module, never inside a script element.

    :returns: The ES module source with the asset sentinel replaced.
    :raises CNotebookError: If the template does not contain the sentinel exactly once.
    """
    template = (_STATIC / "c3d_widget.js").read_text(encoding="utf-8")
    occurrences = template.count(_ASSET_SENTINEL)
    if occurrences != 1:
        raise CNotebookError(
            f"c3d_widget.js must contain the asset sentinel exactly once (found {occurrences})"
        )
    assets = {
        "threeDmol": (_CORE_STATIC / "3Dmol-min.js").read_text(encoding="utf-8"),
        "gui": (_CORE_STATIC / "3dmol-gui.js").read_text(encoding="utf-8"),
        "css": (_CORE_STATIC / "3dmol-gui.css").read_text(encoding="utf-8"),
    }
    return template.replace(_ASSET_SENTINEL, escape_script_json(assets), 1)


def _run_callback(fn: Callable[[Any], None], value: Any, kind: str) -> None:
    """Invoke a user callback without letting it break the trait observer.

    Callbacks run inside a traitlets observer, so an exception would abort the trait
    assignment that delivered the front end's message and leave the widget's Python
    state half-applied while the browser has already moved on. The exception is
    reported through the package logger (visible at ``ERROR``) instead.

    :param fn: User callback.
    :param value: Single argument handed to the callback.
    :param kind: Short description used in the log message.
    """
    try:
        fn(value)
    except Exception:
        log.exception("cnotebook: C3D %s raised", kind)


def _protocol_int(value: Any) -> int | None:
    """Read a protocol id or sequence number exactly as the transport delivers one.

    A JSON integer always arrives as an :class:`int`, so nothing is coerced: a float such
    as ``1.9`` would truncate onto a different command's id, a numeric string means the
    front end sent the wrong type, and :class:`bool` is an ``int`` in Python but never a
    sequence number. Each of those is rejected instead.

    :param value: The raw trait member.
    :returns: The integer, or ``None`` when the value is not a plain integer.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _retrieve_exception(future: asyncio.Future[bytes]) -> None:
    """Mark a rejected screenshot future's exception as seen.

    A caller may request a screenshot and never await the future (a capture taken for
    its side effect, or a cell that moved on). asyncio logs "Future exception was never
    retrieved" when such a future is garbage collected, which would put a traceback in
    the kernel log for a failure the caller chose to ignore. Reading the exception here
    clears that flag; a caller who does await the future still gets the
    :class:`~cnotebook.core.errors.CNotebookError`.

    :param future: The settled screenshot future.
    """
    if not future.cancelled():
        future.exception()


def _decode_screenshot(data: dict[str, Any]) -> bytes:
    """Decode a ``screenshot`` message published by the front end.

    :param data: ``{"seq": int, "png_base64": str}``, or ``{"seq": int, "error": str}``
        when the capture failed.
    :returns: The PNG bytes.
    :raises CNotebookError: When the message reports a failure or carries no usable image.
    """
    error = data.get("error")
    if error:
        raise CNotebookError(f"Screenshot failed: {error}")
    encoded = data.get("png_base64") or ""
    if not encoded:
        raise CNotebookError("Screenshot failed: the front end returned no image data")
    try:
        return base64.b64decode(encoded, validate=True)
    except (TypeError, ValueError) as exc:
        raise CNotebookError(f"Screenshot failed: image data is not valid base64 ({exc})") from exc


@dataclass
class CommandResult:
    """Outcome of one GUI command.

    :ivar ok: Whether the front end accepted the command.
    :ivar output: Terminal lines the command produced.
    """

    ok: bool
    output: list[str]


@dataclass
class PickEvent:
    """An atom pick reported by the viewer.

    :ivar seq: Monotonically increasing sequence number assigned by the front end.
    :ivar atom: The 3Dmol atom record.
    :ivar modifiers: Keyboard modifiers held during the click.
    """

    seq: int
    atom: dict[str, Any]
    modifiers: dict[str, Any]


def _parse_result(item: Any) -> tuple[int, CommandResult] | None:
    """Validate one ``command_results`` entry.

    Nothing is coerced, because every plausible coercion is a silent protocol bug:
    ``1.9`` would settle command 1, and the string ``"false"`` is truthy, so a failed
    command would be reported as a success. A missing ``output`` is the only latitude
    given, and it means no terminal output.

    :param item: One entry of the ``command_results`` trait.
    :returns: The command id and its result, or ``None`` when the entry is malformed.
    """
    if not isinstance(item, dict):
        return None
    command_id = _protocol_int(item.get("id"))
    ok = item.get("ok")
    output = item.get("output", [])
    if command_id is None or not isinstance(ok, bool):
        return None
    if not isinstance(output, list) or not all(isinstance(line, str) for line in output):
        return None
    return command_id, CommandResult(ok, list(output))


class CommandHandle:
    """Pending result of :meth:`C3DWidget.submit`; awaitable.

    The handle settles exactly once, when the front end publishes a result for its id.
    ``await handle`` and :meth:`wait` are equivalent; both may be used repeatedly and
    return immediately once the result has arrived.
    """

    def __init__(self, command_id: int, command: str) -> None:
        """Create a handle for a submitted command.

        :param command_id: Protocol id assigned by the widget.
        :param command: The terminal command line that was submitted.
        """
        self.id = command_id
        self.command = command
        self._result: CommandResult | None = None
        self._callbacks: list[Callable[[CommandHandle], None]] = []
        self._waiters: list[asyncio.Future[CommandResult]] = []

    @property
    def done(self) -> bool:
        """:returns: Whether the result has arrived."""
        return self._result is not None

    @property
    def result(self) -> CommandResult | None:
        """:returns: The result, or ``None`` while the command is outstanding."""
        return self._result

    def add_done_callback(self, fn: Callable[[CommandHandle], None]) -> None:
        """Call *fn(handle)* when the result arrives (immediately if it already has).

        :param fn: Callback taking the handle; an exception from it is logged, not raised.
        """
        if self._result is not None:
            _run_callback(fn, self, "command callback")
        else:
            self._callbacks.append(fn)

    def _resolve(self, result: CommandResult) -> None:
        """Settle the handle and hand *result* to every waiter and callback.

        :param result: The outcome reported by the front end.
        """
        if self._result is not None:
            return
        self._result = result
        for future in self._waiters:
            if not future.done():
                future.set_result(result)
        self._waiters.clear()
        callbacks, self._callbacks = self._callbacks, []
        for fn in callbacks:
            _run_callback(fn, self, "command callback")

    async def wait(self, timeout: float = _DEFAULT_TIMEOUT) -> CommandResult:
        """Await the result.

        :param timeout: Seconds before :class:`~cnotebook.core.errors.CNotebookError` is raised.
        :returns: The command result.
        :raises CNotebookError: When the front end does not answer within *timeout*.
        """
        if self._result is not None:
            return self._result
        future: asyncio.Future[CommandResult] = asyncio.get_running_loop().create_future()
        self._waiters.append(future)
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            raise CNotebookError(
                f"Command {self.command!r} did not complete within {timeout} s"
            ) from exc
        finally:
            # However the await ended, the waiter must go: a timed out or cancelled wait
            # would otherwise leave a dead future for a result that can still arrive.
            if future in self._waiters:
                self._waiters.remove(future)

    def __await__(self) -> Generator[Any, None, CommandResult]:
        """:returns: Iterator delegating to :meth:`wait` with the default timeout."""
        return self.wait().__await__()


class C3DWidget(anywidget.AnyWidget):
    """Live C3D viewer: one iframe per instance, state exchanged through traits.

    Every field that crosses the kernel boundary is a synced trait, and containers are
    always reassigned rather than mutated in place so traitlets sees the change. The ES
    module is built once, when this class is created, from the shipped template and the
    ``core/static`` bundles; instances never touch the filesystem.
    """

    _esm = _load_esm()

    # ipywidgets echoes every browser-originated trait update straight back to the
    # browser (JUPYTER_WIDGETS_ECHO is on by default), which would return a multi-megabyte
    # base64 screenshot to the frame that just produced it. The traits only the front end
    # writes therefore opt out; the ones Python writes, and the bidirectional view pair,
    # keep the default so other views of the same widget stay in step.
    payload = traitlets.Unicode("{}").tag(sync=True)
    width = traitlets.Int(800).tag(sync=True)
    height = traitlets.Int(500).tag(sync=True)
    status = traitlets.Unicode("loading").tag(sync=True, echo_update=False)
    status_message = traitlets.Unicode("").tag(sync=True, echo_update=False)
    commands = traitlets.List(traitlets.Dict()).tag(sync=True)
    command_results = traitlets.List(traitlets.Dict()).tag(sync=True, echo_update=False)
    view = traitlets.List(traitlets.Float()).tag(sync=True)
    view_origin = traitlets.Unicode("js").tag(sync=True)
    picked = traitlets.Dict().tag(sync=True, echo_update=False)
    screenshot_request = traitlets.Int(0).tag(sync=True)
    screenshot = traitlets.Dict().tag(sync=True, echo_update=False)

    def __init__(self, **kwargs: Any) -> None:
        """Create the widget.

        :param kwargs: Initial trait values, e.g. ``payload``, ``width``, ``height``.
        """
        super().__init__(**kwargs)
        self._next_id = 1
        self._handles: dict[int, CommandHandle] = {}
        self._pick_callbacks: list[Callable[[PickEvent], None]] = []
        self._screenshot_futures: dict[int, asyncio.Future[bytes]] = {}
        self.last_pick: PickEvent | None = None
        self.observe(self._on_results, names=["command_results"])
        self.observe(self._on_picked, names=["picked"])
        self.observe(self._on_screenshot, names=["screenshot"])

    def submit(self, command: str) -> CommandHandle:
        """Queue a GUI terminal command.

        :param command: Terminal command line, e.g. ``"zoom resn LIG"``.
        :returns: Handle resolved when the front end reports the result.
        """
        handle = CommandHandle(self._next_id, command)
        self._next_id += 1
        self._handles[handle.id] = handle
        self.commands = [*self.commands, {"id": handle.id, "command": command}]
        return handle

    def _on_results(self, change: dict[str, Any]) -> None:
        """Settle the handles the front end answered and shorten the command queue.

        Results for ids that are unknown, already settled, or malformed are dropped:
        the front end replays its whole result list, so duplicates are expected, and a
        bad entry must not stop the remaining ones from being delivered.

        :param change: traitlets change notification for ``command_results``.
        """
        done_ids: set[int] = set()
        for item in change["new"]:
            parsed = _parse_result(item)
            if parsed is None:
                log.debug("cnotebook: ignoring malformed C3D command result: %r", item)
                continue
            command_id, result = parsed
            done_ids.add(command_id)
            handle = self._handles.pop(command_id, None)
            if handle is not None:
                handle._resolve(result)
        if done_ids:
            self.commands = [
                c for c in self.commands if _protocol_int(c.get("id")) not in done_ids
            ]

    def on_pick(self, fn: Callable[[PickEvent], None]) -> None:
        """Register *fn* to receive :class:`PickEvent` objects.

        :param fn: Callback taking the event; an exception from it is logged, not raised.
        """
        self._pick_callbacks.append(fn)

    def _on_picked(self, change: dict[str, Any]) -> None:
        """Publish a pick to :attr:`last_pick` and the registered callbacks.

        :param change: traitlets change notification for ``picked``.
        """
        data = change["new"] or {}
        if not data:
            return
        seq = _protocol_int(data.get("seq"))
        atom = data.get("atom", {})
        modifiers = data.get("modifiers", {})
        if seq is None or not isinstance(atom, dict) or not isinstance(modifiers, dict):
            log.debug("cnotebook: ignoring malformed C3D pick: %r", data)
            return
        event = PickEvent(seq, dict(atom), dict(modifiers))
        self.last_pick = event
        for fn in list(self._pick_callbacks):
            _run_callback(fn, event, "pick callback")

    def request_screenshot(self) -> asyncio.Future[bytes]:
        """Ask the front end for a PNG; the future resolves to the bytes.

        Requests coalesce: the front end answers the highest outstanding sequence with
        the current frame, and that answer resolves every request at or below it.

        :returns: Future resolved with the PNG bytes, or rejected with
            :class:`~cnotebook.core.errors.CNotebookError` when the capture fails.
        :raises RuntimeError: When there is no running event loop to attach the future to.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "C3DWidget.request_screenshot() needs a running event loop; await it from "
                "async code (a Jupyter or marimo notebook cell already runs one)."
            ) from exc
        future: asyncio.Future[bytes] = loop.create_future()
        seq = self.screenshot_request + 1
        future.add_done_callback(partial(self._forget_screenshot, seq))
        # Register before publishing the request so an answer can never arrive first.
        self._screenshot_futures[seq] = future
        self.screenshot_request = seq
        return future

    def _forget_screenshot(self, seq: int, future: asyncio.Future[bytes]) -> None:
        """Drop a settled screenshot request from the registry.

        Runs on every completion, including the cancellation :func:`asyncio.wait_for`
        performs when a request times out. Without it a viewer that never connects - the
        very case that produces those timeouts - would leave one dead future registered
        per request. The entry is removed only while it still holds *this* future, so a
        later request that reused the sequence key survives an older callback.

        :param seq: The sequence number the future was registered under.
        :param future: The settled future.
        """
        if self._screenshot_futures.get(seq) is future:
            del self._screenshot_futures[seq]
        _retrieve_exception(future)

    def close(self) -> None:
        """Close the widget, failing every screenshot request it can no longer answer.

        The front end goes away with the comm, so an outstanding request would otherwise
        hang until its timeout. Futures that are already settled, or whose event loop has
        gone, are left alone.
        """
        pending = list(self._screenshot_futures.items())
        self._screenshot_futures.clear()
        for seq, future in pending:
            if future.done() or future.get_loop().is_closed():
                continue
            future.set_exception(CNotebookError("Screenshot failed: widget closed"))
            # The done callback that would retrieve this is queued on the loop, which may
            # never turn again after a close; read it now so asyncio logs no traceback.
            _retrieve_exception(future)
            log.debug("cnotebook: failed C3D screenshot request %d, the widget closed", seq)
        super().close()

    def _on_screenshot(self, change: dict[str, Any]) -> None:
        """Resolve every screenshot request the front end's answer covers.

        :param change: traitlets change notification for ``screenshot``.
        """
        data = change["new"] or {}
        if not data:
            return
        acknowledged = _protocol_int(data.get("seq"))
        if acknowledged is None:
            log.debug("cnotebook: ignoring C3D screenshot without a sequence: %r", data)
            return
        pending = sorted(seq for seq in self._screenshot_futures if seq <= acknowledged)
        if not pending:
            return
        try:
            png = _decode_screenshot(data)
        except CNotebookError as exc:
            reason: str | None = str(exc)
            png = b""
        else:
            reason = None
        for seq in pending:
            future = self._screenshot_futures.pop(seq)
            # A future the caller already cancelled is skipped; popping it keeps every
            # request settled at most once, however many messages mention its sequence.
            if future.done():
                continue
            if future.get_loop().is_closed():
                # The cell that asked has ended. Settling the future would schedule its
                # callbacks on a dead loop, and that RuntimeError would escape this
                # observer and abort the trait assignment for every other request.
                log.debug("cnotebook: dropping C3D screenshot %d, its event loop is closed", seq)
                continue
            if reason is None:
                future.set_result(png)
            else:
                future.set_exception(CNotebookError(reason))

    def set_view(self, view: list[float]) -> None:
        """Push a 3Dmol view array to the front end.

        :param view: The 3Dmol view array to apply.
        """
        self.view_origin = "python"
        self.view = [float(v) for v in view]
