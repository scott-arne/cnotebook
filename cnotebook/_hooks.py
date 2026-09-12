"""Post-import hooks: run integration code after an optional dependency finishes importing.

cnotebook has to attach itself to oepandas, oepolars and marimo, but importing any of them
to find out whether it can is exactly the cost the package is trying not to pay. A hook
registered here waits instead: the callback -- and the adapter module that holds it -- is
resolved only once the watched module has finished executing, or immediately if the session
had already imported it.
"""

from __future__ import annotations

import importlib
import importlib.abc
import logging
import os
import sys
import threading
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

from cnotebook.core.errors import _report

log = logging.getLogger("cnotebook")

# An escape hatch for anyone who cannot have a finder in front of their imports. It is read
# once, at import: a finder that is already installed cannot be taken back safely.
_DISABLED = os.environ.get("CNOTEBOOK_NO_IMPORT_HOOKS") == "1"


def _initializing(module: ModuleType | None) -> bool:
    """Report whether *module* is in the middle of executing its own body.

    A module is put in ``sys.modules`` before its body runs, so membership alone does not
    mean the module is usable. ``__spec__._initializing`` is how the import system itself
    distinguishes the two; it is read defensively so a loader that does not set it degrades
    to "finished" rather than raising.

    :param module: Module to inspect, or ``None``.
    :returns: True while the module's body is still executing.
    """
    return bool(getattr(getattr(module, "__spec__", None), "_initializing", False))


def _run(dotted: str) -> None:
    """Import and call ``"package.module:function"``.

    A callback whose own module is still executing is skipped: that happens when the
    watched module is imported *by* the callback's module, and such a module attaches
    itself at the end of its own body anyway. Calling into it here would only find the
    half of it that exists so far.

    :param dotted: Callback to resolve and call.
    """
    module_name, _, attr = dotted.partition(":")
    if _initializing(sys.modules.get(module_name)):
        return
    try:
        getattr(importlib.import_module(module_name), attr)()
    except Exception as exc:  # noqa: BLE001 - an integration failure must never break the user's import
        # Reported without raising: this runs inside the user's `import`, and a session
        # that promotes CNotebookWarning to an exception would otherwise lose the import.
        _report(f"cnotebook integration hook {dotted} failed: {exc}")


class _WrappedLoader(importlib.abc.Loader):
    """Delegates to the real loader and runs the callbacks after ``exec_module``."""

    def __init__(self, inner: importlib.abc.Loader, finder: PostImportFinder, fullname: str) -> None:
        """Wrap *inner*.

        The callbacks are read back from *finder* rather than captured here: a module is
        free to register a hook for itself from its own body, and a snapshot taken when
        the spec was found would miss it.

        :param inner: The loader the real finder chose for the module.
        :param finder: Finder holding the registrations for this module.
        :param fullname: Module this loader was chosen for.
        """
        self._inner = inner
        self._finder = finder
        self._fullname = fullname

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        """Let the real loader build the module object.

        :param spec: Spec being loaded.
        :returns: Whatever the real loader creates, or ``None`` for default creation.
        """
        create = getattr(self._inner, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module: ModuleType) -> None:
        """Execute the module, then run the callbacks nobody has run yet.

        A module that fails to execute has no integration to attach, so its exception
        propagates untouched and the callbacks do not run.

        :param module: Module to execute.
        """
        self._inner.exec_module(module)  # type: ignore[attr-defined]
        for dotted in self._finder.claim(self._fullname):
            _run(dotted)

    def load_module(self, fullname: str) -> ModuleType:
        """Hand the deprecated single-call protocol to the real loader.

        Nothing in CPython's current import path calls this, but ``Loader`` still supplies
        a default implementation, and inheriting it would load the module by a route that
        never consults the real loader at all. An explicit delegation is what keeps this
        one name from slipping past ``__getattr__``.

        :param fullname: Module to load.
        :returns: The loaded module.
        :raises NotImplementedError: If the real loader does not support this protocol.
        """
        inner = getattr(self._inner, "load_module", None)
        if inner is None:
            raise NotImplementedError(f"{type(self._inner).__name__} does not support load_module()")
        return inner(fullname)

    def __getattr__(self, name: str) -> Any:
        """Pass everything else to the real loader.

        ``get_code``, ``is_package``, ``get_source`` and ``get_resource_reader`` are part
        of the loader protocol that callers reach for; a wrapper that hid them would make
        the wrapped module behave differently from every other one.

        :param name: Attribute the caller asked the loader for.
        :returns: The real loader's attribute.
        """
        return getattr(self._inner, name)


class PostImportFinder(importlib.abc.MetaPathFinder):
    """Meta-path finder that wraps the loaders of the modules cnotebook watches."""

    def __init__(self) -> None:
        # `_callbacks` is the registration record and outlives every run; `_pending`
        # holds the registrations that have not run yet, and is what the two callers
        # who could each run a registration compete for under `_lock`.
        self._lock = threading.Lock()
        self._callbacks: dict[str, list[str]] = {}
        self._pending: dict[str, list[str]] = {}
        self._installed = False

    def register(self, module_name: str, dotted: str) -> None:
        """Run *dotted* once *module_name* has been imported.

        :param module_name: Top-level module to watch.
        :param dotted: Callback in ``"package.module:function"`` form.
        """
        with self._lock:
            self._callbacks.setdefault(module_name, []).append(dotted)
            self._pending.setdefault(module_name, []).append(dotted)
        if module_name in sys.modules:
            # There is nothing left to wait for, so this buys no finder either.
            self._run_now(module_name, dotted)
            return
        with self._lock:
            if not self._installed and not _DISABLED:
                sys.meta_path.insert(0, self)
                self._installed = True

    def claim(self, module_name: str, dotted: str | None = None) -> list[str]:
        """Take registrations for *module_name* out of the pending list.

        Two callers can reach the same registration: the wrapped loader draining the
        list once the module's body has run, and a :meth:`register` call that appended
        to the list and then parked on that module's import lock. Claiming is what makes
        one of them the owner. A claim is never given back -- a callback that raised has
        still been attempted, and a callback that ran must not run twice, because a
        registration duplicated into a process-wide registry is exactly the damage this
        guards against.

        :param module_name: Watched module.
        :param dotted: A single registration to claim, or ``None`` for every pending one.
        :returns: The callbacks this call owns, in registration order.
        """
        with self._lock:
            pending = self._pending.get(module_name)
            if not pending:
                return []
            if dotted is None:
                del self._pending[module_name]
                return pending
            if dotted not in pending:
                return []
            pending.remove(dotted)
            if not pending:
                del self._pending[module_name]
            return [dotted]

    def _run_now(self, module_name: str, dotted: str) -> None:
        """Run *dotted* for a module that is already in ``sys.modules``.

        Being in ``sys.modules`` does not mean the module has finished executing, and the
        two ways it can still be running need different answers. If another thread is
        mid-import, importing it here parks on that module's lock until the other thread is
        done, so the callback still meets a complete module. If instead this thread is
        inside that body -- the watched module imported cnotebook during its own
        initialization -- the import system hands back the partial module rather than
        deadlocking, and there is nothing complete to attach to.

        Waiting is also why the callback is claimed rather than simply run: while this
        call was parked on the module lock, the loader executing that module reached the
        end of the body and drained the same registration.

        In the circular case the registration is left pending. If something had already
        registered for that module before its import began its loader is wrapped, and
        that loader claims the registration when the body ends, so the callback still
        runs -- just not from here. Otherwise the finder is never consulted for a name
        that is already in ``sys.modules``, and the callback cannot fire until something
        imports the watched module afresh.

        :param module_name: Watched module, already present in ``sys.modules``.
        :param dotted: Callback in ``"package.module:function"`` form.
        """
        if _initializing(sys.modules.get(module_name)):
            try:
                importlib.import_module(module_name)
            except Exception as exc:  # noqa: BLE001 - the importer owns this failure, not the hook
                # Non-raising for the same reason as `_run`: this can be reached from
                # inside an import, and a promoted warning would replace the real error.
                _report(f"cnotebook integration hook {dotted} skipped: importing {module_name} failed: {exc}")
                return
            if _initializing(sys.modules.get(module_name)):
                log.debug("[cnotebook] %s is importing cnotebook from its own body; hook %s runs when that "
                          "body ends if its loader was wrapped, and otherwise not until %s is imported again",
                          module_name, dotted, module_name)
                return
        if self.claim(module_name, dotted):
            _run(dotted)

    def find_spec(self, fullname: str, path: Sequence[str] | None = None,
                  target: ModuleType | None = None) -> ModuleSpec | None:
        """Return the real spec with its loader wrapped, for watched modules only.

        Every import in the process passes through here, so a name nobody is watching
        costs one dict lookup.

        :param fullname: Dotted name being imported.
        :param path: Parent package search path, or ``None`` for a top-level import.
        :param target: Module being reloaded, when this is a reload.
        :returns: The wrapped spec, the untouched spec when there is no loader to wrap,
            or ``None`` when this finder has nothing to say.
        """
        if fullname not in self._callbacks:
            return None
        spec = self._find_real_spec(fullname, path, target)
        if spec is None:
            return None
        if spec.loader is None or not hasattr(spec.loader, "exec_module"):
            # A namespace package has no loader to wrap. Its callbacks never fire, but
            # nothing about the import changes either.
            return spec
        spec.loader = _WrappedLoader(spec.loader, self, fullname)
        return spec

    def _find_real_spec(self, fullname: str, path: Sequence[str] | None,
                        target: ModuleType | None) -> ModuleSpec | None:
        """Ask the other finders where the module actually is.

        The scan resumes after this finder's own place on the meta path. Everything ahead
        of it has already been asked by the import machinery and declined, so asking again
        would only repeat a filesystem walk -- and would run a side-effecting finder twice.

        :param fullname: Dotted name being imported.
        :param path: Parent package search path.
        :param target: Module being reloaded, when this is a reload.
        :returns: The first spec another finder offers, or ``None``.
        """
        finders = list(sys.meta_path)
        try:
            start = finders.index(self) + 1
        except ValueError:
            # Not on the meta path at all: a direct call, or the env-var escape hatch. In
            # that case nobody has been asked yet, so the whole list is fair game.
            start = 0
        for finder in finders[start:]:
            if finder is self or not hasattr(finder, "find_spec"):
                continue
            spec = finder.find_spec(fullname, path, target)
            if spec is not None:
                return spec
        return None


_FINDER = PostImportFinder()


def on_import(module_name: str, dotted_callback: str) -> None:
    """Run ``dotted_callback`` (``"pkg.module:function"``) once *module_name* has been imported.

    :param module_name: Top-level module to watch (e.g. ``"oepandas"``).
    :param dotted_callback: Callable to run afterwards; its module is imported only then.
    """
    _FINDER.register(module_name, dotted_callback)
