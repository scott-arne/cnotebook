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
import os
import sys
from collections.abc import Sequence
from importlib.machinery import ModuleSpec
from types import ModuleType
from typing import Any

from cnotebook.core.errors import warn

# An escape hatch for anyone who cannot have a finder in front of their imports. It is read
# once, at import: a finder that is already installed cannot be taken back safely.
_DISABLED = os.environ.get("CNOTEBOOK_NO_IMPORT_HOOKS") == "1"


def _run(dotted: str) -> None:
    """Import and call ``"package.module:function"``.

    A callback whose own module is still executing is skipped: that happens when the
    watched module is imported *by* the callback's module, and such a module attaches
    itself at the end of its own body anyway. Calling into it here would only find the
    half of it that exists so far.

    :param dotted: Callback to resolve and call.
    """
    module_name, _, attr = dotted.partition(":")
    partial = sys.modules.get(module_name)
    if partial is not None and getattr(getattr(partial, "__spec__", None), "_initializing", False):
        return
    try:
        getattr(importlib.import_module(module_name), attr)()
    except Exception as exc:  # noqa: BLE001 - an integration failure must never break the user's import
        warn(f"cnotebook integration hook {dotted} failed: {exc}")


class _WrappedLoader(importlib.abc.Loader):
    """Delegates to the real loader and runs the callbacks after ``exec_module``."""

    def __init__(self, inner: importlib.abc.Loader, callbacks: list[str]) -> None:
        """Wrap *inner*.

        :param inner: The loader the real finder chose for the module.
        :param callbacks: Dotted callbacks to run once the module has executed.
        """
        self._inner = inner
        self._callbacks = callbacks

    def create_module(self, spec: ModuleSpec) -> ModuleType | None:
        """Let the real loader build the module object.

        :param spec: Spec being loaded.
        :returns: Whatever the real loader creates, or ``None`` for default creation.
        """
        create = getattr(self._inner, "create_module", None)
        return create(spec) if create is not None else None

    def exec_module(self, module: ModuleType) -> None:
        """Execute the module, then run the callbacks.

        A module that fails to execute has no integration to attach, so its exception
        propagates untouched and the callbacks do not run.

        :param module: Module to execute.
        """
        self._inner.exec_module(module)  # type: ignore[attr-defined]
        for dotted in list(self._callbacks):
            _run(dotted)

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
        self._callbacks: dict[str, list[str]] = {}
        self._installed = False

    def register(self, module_name: str, dotted: str) -> None:
        """Run *dotted* once *module_name* has been imported.

        :param module_name: Top-level module to watch.
        :param dotted: Callback in ``"package.module:function"`` form.
        """
        self._callbacks.setdefault(module_name, []).append(dotted)
        if module_name in sys.modules:
            # There is nothing left to wait for, so this buys no finder either.
            _run(dotted)
            return
        if not self._installed and not _DISABLED:
            sys.meta_path.insert(0, self)
            self._installed = True

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
        spec.loader = _WrappedLoader(spec.loader, self._callbacks[fullname])
        return spec

    def _find_real_spec(self, fullname: str, path: Sequence[str] | None,
                        target: ModuleType | None) -> ModuleSpec | None:
        """Ask the other finders where the module actually is.

        :param fullname: Dotted name being imported.
        :param path: Parent package search path.
        :param target: Module being reloaded, when this is a reload.
        :returns: The first spec another finder offers, or ``None``.
        """
        for finder in list(sys.meta_path):
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
