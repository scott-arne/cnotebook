"""Tests for the post-import hooks that attach cnotebook to optional dependencies.

Every import in the process passes through the finder these hooks install, so the
tests below are as much about what it must *not* disturb -- unregistered names,
packages, namespace packages, failed imports, reloads -- as about the callbacks
themselves.
"""

import importlib
import logging
import os
import subprocess
import sys
import textwrap
import threading
import types
import warnings
from importlib.machinery import ModuleSpec
from pathlib import Path

import pytest

from cnotebook import _hooks
from cnotebook.core.errors import CNotebookWarning

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)

# Throwaway modules the fixture writes; every test starts and ends with them unimported.
_FAKE_NAMES = ("hookdummy", "hookcb", "hookbroken", "hookpkg", "hookpkg.sub", "hookns", "hookns.leaf",
               "hookselfimport", "hookslow", "hookcircular", "hookwrapped", "hookinmemory")

_CALLBACKS = """
import sys
import threading
import time

CALLS = []

# Set by the cross-thread test to the ident of the thread that will register the hook.
REGISTRAR_IDENT = None
STARTED = threading.Event()


def wait_until_blocked_on(ident, module_name, timeout=10.0):
    \"\"\"Block until thread *ident* is parked on *module_name*'s import lock.

    The import system records what each thread is waiting for, which is the only
    handshake that says "the other thread has reached the import and is stuck on us"
    without guessing at a duration.

    :param ident: Thread ident to watch.
    :param module_name: Module whose import lock the thread should be waiting on.
    :param timeout: Seconds to wait before giving up.
    :returns: True if the thread was seen blocked before the deadline.
    \"\"\"
    from importlib._bootstrap import _blocking_on

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        blocked = _blocking_on.get(ident)
        # Python 3.12 records every lock a thread waits on; 3.11 records the one lock.
        locks = blocked if isinstance(blocked, list) else [blocked] if blocked else []
        if any(getattr(lock, "name", None) == module_name for lock in locks):
            return True
        time.sleep(0.001)
    return False


def attach():
    import hookdummy

    CALLS.append(hookdummy.VALUE)


def slow_attach():
    # Read the module out of sys.modules rather than importing it: importing would wait
    # on the module lock by itself and hide whether the hook did the waiting.
    CALLS.append(("attached", getattr(sys.modules["hookslow"], "VALUE", None)))


def second():
    CALLS.append("second")


def one():
    CALLS.append("one")


def two():
    CALLS.append("two")


def note_package():
    CALLS.append("hookpkg")


def note_broken():
    CALLS.append("hookbroken")


def boom():
    raise RuntimeError("nope")
"""


def _forget_fakes() -> None:
    """Drop the throwaway modules from ``sys.modules``."""
    for name in _FAKE_NAMES:
        sys.modules.pop(name, None)


def _run_child(code: str, **env_overrides) -> subprocess.CompletedProcess:
    """Run *code* in a fresh interpreter that imports this checkout's cnotebook.

    :param code: Python source to run with ``-c``.
    :param env_overrides: Environment variables to set for the child.
    :returns: The completed process.
    """
    env = {**os.environ, **env_overrides}
    env["PYTHONPATH"] = os.pathsep.join(part for part in (_REPO_ROOT, env.get("PYTHONPATH")) if part)
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env=env, cwd=_REPO_ROOT, check=False)


@pytest.fixture()
def fake_packages(tmp_path, monkeypatch):
    """Throwaway modules to hook, with the finder's process-wide state isolated.

    The finder, its registry and ``sys.meta_path`` all outlive a single test, so each
    is snapshotted: a callback registered here must not survive into the next test, and
    the hooks cnotebook itself registered must survive this whole module.
    """
    (tmp_path / "hookdummy.py").write_text("VALUE = 1\n")
    (tmp_path / "hookbroken.py").write_text("raise ImportError('hookbroken cannot load')\n")
    (tmp_path / "hookcb.py").write_text(textwrap.dedent(_CALLBACKS))
    package = tmp_path / "hookpkg"
    package.mkdir()
    (package / "__init__.py").write_text("VALUE = 2\n")
    (package / "sub.py").write_text("VALUE = 3\n")
    namespace = tmp_path / "hookns"  # no __init__.py: a namespace package
    namespace.mkdir()
    (namespace / "leaf.py").write_text("VALUE = 4\n")

    monkeypatch.syspath_prepend(str(tmp_path))
    # Start from a finder that is registered for nothing and not installed, whatever the
    # session did before; monkeypatch puts the real registry and meta path back afterwards.
    monkeypatch.setattr(sys, "meta_path", [f for f in sys.meta_path if f is not _hooks._FINDER])
    monkeypatch.setattr(_hooks._FINDER, "_callbacks", {})
    monkeypatch.setattr(_hooks._FINDER, "_pending", {})
    monkeypatch.setattr(_hooks._FINDER, "_installed", False)
    _forget_fakes()
    yield
    _forget_fakes()


def test_callback_runs_after_target_import(fake_packages):
    _hooks.on_import("hookdummy", "hookcb:attach")
    import hookcb

    assert hookcb.CALLS == []
    import hookdummy  # noqa: F401

    assert hookcb.CALLS == [1]


def test_callback_runs_immediately_when_already_imported(fake_packages):
    import hookcb
    import hookdummy  # noqa: F401

    _hooks.on_import("hookdummy", "hookcb:attach")
    assert hookcb.CALLS == [1]


def test_two_callbacks_for_one_module_both_run(fake_packages):
    _hooks.on_import("hookdummy", "hookcb:attach")
    _hooks.on_import("hookdummy", "hookcb:second")
    import hookcb
    import hookdummy  # noqa: F401

    assert hookcb.CALLS == [1, "second"]


def test_failing_callback_warns_instead_of_raising(fake_packages):
    import hookdummy  # noqa: F401

    with pytest.warns(CNotebookWarning, match="nope"):
        _hooks.on_import("hookdummy", "hookcb:boom")


def test_failing_callback_does_not_break_the_users_import(fake_packages):
    _hooks.on_import("hookdummy", "hookcb:boom")
    _hooks.on_import("hookdummy", "hookcb:second")
    import hookcb

    with pytest.warns(CNotebookWarning, match="nope"):
        import hookdummy

    assert hookdummy.VALUE == 1
    # A broken integration must not cost the ones registered after it either.
    assert hookcb.CALLS == ["second"]


def test_failing_callback_does_not_abort_the_import_under_warnings_as_errors(fake_packages, caplog):
    # The report fires from inside the watched module's own `exec_module`, so a session
    # that promotes CNotebookWarning to an exception -- `-W error`, or a test suite's
    # filters -- would otherwise see `import oepandas` fail because an adapter did. The
    # warning is demoted to a log record instead, and the import survives intact.
    _hooks.on_import("hookdummy", "hookcb:boom")

    with caplog.at_level(logging.WARNING, logger="cnotebook"), warnings.catch_warnings():
        warnings.simplefilter("error", CNotebookWarning)
        import hookdummy

    assert hookdummy.VALUE == 1
    assert sys.modules["hookdummy"] is hookdummy
    assert "hookcb:boom failed: nope" in caplog.text


def test_failing_callback_registered_after_the_import_does_not_raise_under_warnings_as_errors(
        fake_packages, caplog):
    # The same guarantee on the immediate path: registering against an already-imported
    # library happens during `import cnotebook`, which a promoted warning would abort.
    import hookdummy  # noqa: F401

    with caplog.at_level(logging.WARNING, logger="cnotebook"), warnings.catch_warnings():
        warnings.simplefilter("error", CNotebookWarning)
        _hooks.on_import("hookdummy", "hookcb:boom")

    assert "hookcb:boom failed: nope" in caplog.text


def test_unregistered_names_are_not_wrapped(fake_packages):
    # This finder sits in front of every import in the process, so a miss has to be a
    # dict lookup that answers None rather than a spec search.
    assert _hooks._FINDER.find_spec("hookdummy") is None
    assert _hooks._FINDER.find_spec("json") is None


def test_registered_but_uninstallable_module_returns_no_spec(fake_packages):
    _hooks.on_import("hooknotinstalled", "hookcb:second")

    assert _hooks._FINDER.find_spec("hooknotinstalled") is None
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("hooknotinstalled")


def test_wrapped_spec_keeps_package_semantics(fake_packages):
    _hooks.on_import("hookpkg", "hookcb:note_package")
    spec = _hooks._FINDER.find_spec("hookpkg")

    assert spec is not None
    # A package that lost its search locations could not import its own submodules.
    assert spec.submodule_search_locations is not None
    # get_code and is_package live on the real loader; the wrapper has to pass them on.
    assert spec.loader.is_package("hookpkg") is True
    assert spec.loader.get_code("hookpkg") is not None

    import hookcb
    import hookpkg.sub

    assert (hookpkg.VALUE, hookpkg.sub.VALUE) == (2, 3)
    # Importing a submodule imports the parent once, so the hook fires once.
    assert hookcb.CALLS == ["hookpkg"]


def test_namespace_package_target_still_imports(fake_packages):
    # A namespace package is found as a spec with no loader -- the import system attaches
    # one only afterwards -- so there is nothing to wrap and the callback cannot fire.
    # None of cnotebook's own targets is one; what matters is that the import is untouched.
    _hooks.on_import("hookns", "hookcb:second")
    import hookcb
    import hookns.leaf

    assert hookns.leaf.VALUE == 4
    assert list(hookns.__path__) == [str(Path(hookns.leaf.__file__).parent)]
    assert hookcb.CALLS == []


def test_spec_without_a_loader_is_returned_untouched(fake_packages):
    # A finder may answer with a loaderless spec. There is nothing to wrap, and answering
    # None instead would hide from the import system a module it was just told about.
    bare = ModuleSpec("hooknoloader", None)

    class Finder:
        def find_spec(self, fullname, path=None, target=None):
            return bare if fullname == "hooknoloader" else None

    sys.meta_path.append(Finder())
    _hooks.on_import("hooknoloader", "hookcb:second")

    assert _hooks._FINDER.find_spec("hooknoloader") is bare
    assert bare.loader is None


def test_callback_is_skipped_while_its_own_module_is_still_importing(fake_packages, tmp_path, recwarn):
    # cnotebook's adapters import the library they adapt, so the hook fires from inside
    # the adapter's own module body. Reaching back into a half-executed module would find
    # nothing to call; it attaches itself once its body finishes, which is the same thing.
    (tmp_path / "hookselfimport.py").write_text(textwrap.dedent("""
        import hookcb

        import hookdummy  # fires the hook registered against it, from inside this body

        def attach():
            hookcb.CALLS.append("attached")

        attach()
    """))
    _hooks.on_import("hookdummy", "hookselfimport:attach")
    import hookcb
    import hookselfimport  # noqa: F401

    assert hookcb.CALLS == ["attached"]
    assert [w for w in recwarn if issubclass(w.category, CNotebookWarning)] == []


def test_finders_ahead_of_the_hook_are_not_asked_twice(fake_packages):
    # The import machinery walks sys.meta_path in order, so by the time this finder is
    # asked, everything in front of it has already declined. Rescanning from the top would
    # repeat that work -- and would run a side-effecting finder's side effect twice.
    class Recorder:
        def __init__(self):
            self.calls = []

        def find_spec(self, fullname, path=None, target=None):
            self.calls.append(fullname)  # declines by falling off the end

    import hookcb

    _hooks.on_import("hookdummy", "hookcb:attach")
    assert sys.meta_path[0] is _hooks._FINDER
    recorder = Recorder()
    sys.meta_path.insert(0, recorder)

    import hookdummy  # noqa: F401

    assert recorder.calls.count("hookdummy") == 1
    assert hookcb.CALLS == [1]


def test_registration_during_another_threads_import_waits_for_it(fake_packages, tmp_path, recwarn):
    # A module is in sys.modules from the moment its body starts running, so a
    # registration that trusted membership alone would hand the callback a half-built
    # module. Importing it instead parks on the module lock the other thread is holding.
    (tmp_path / "hookslow.py").write_text(textwrap.dedent("""
        import hookcb

        hookcb.CALLS.append("body-start")
        hookcb.STARTED.set()
        hookcb.wait_until_blocked_on(hookcb.REGISTRAR_IDENT, "hookslow")
        hookcb.CALLS.append("body-end")

        VALUE = 5
    """))
    import hookcb

    hookcb.REGISTRAR_IDENT = threading.get_ident()
    importer = threading.Thread(target=importlib.import_module, args=("hookslow",))
    importer.start()
    try:
        assert hookcb.STARTED.wait(10), "the importing thread never reached hookslow's body"
        _hooks.on_import("hookslow", "hookcb:slow_attach")
    finally:
        importer.join(timeout=30)

    assert not importer.is_alive()
    # Exactly once, after the body finished, against the finished module.
    assert hookcb.CALLS == ["body-start", "body-end", ("attached", 5)]
    assert [w for w in recwarn if issubclass(w.category, CNotebookWarning)] == []


def test_registration_during_another_threads_import_of_a_wrapped_module_attaches_once(
        fake_packages, tmp_path, recwarn):
    # The same race as above, except something was already watching the module when the
    # import began, so its loader is wrapped. The registration lands in the pending list
    # the loader is about to drain *and* the registering thread goes on to wait for the
    # module; whichever gets there first, the callback runs exactly once.
    (tmp_path / "hookslow.py").write_text(textwrap.dedent("""
        import hookcb

        hookcb.CALLS.append("body-start")
        hookcb.STARTED.set()
        hookcb.wait_until_blocked_on(hookcb.REGISTRAR_IDENT, "hookslow")
        hookcb.CALLS.append("body-end")

        VALUE = 5
    """))
    import hookcb

    hookcb.REGISTRAR_IDENT = threading.get_ident()
    _hooks.on_import("hookslow", "hookcb:one")
    importer = threading.Thread(target=importlib.import_module, args=("hookslow",))
    importer.start()
    try:
        assert hookcb.STARTED.wait(10), "the importing thread never reached hookslow's body"
        _hooks.on_import("hookslow", "hookcb:slow_attach")
    finally:
        importer.join(timeout=30)

    assert not importer.is_alive()
    assert hookcb.CALLS == ["body-start", "body-end", "one", ("attached", 5)]
    assert [w for w in recwarn if issubclass(w.category, CNotebookWarning)] == []


def test_registration_from_inside_a_wrapped_modules_own_body_runs_once_at_the_end(
        fake_packages, tmp_path, recwarn):
    # A module that registers a hook for itself cannot have that hook run mid-body, so
    # the registration is left pending. Here the module's loader is wrapped -- something
    # registered for it before the import started -- and the drain at the end of the body
    # is what runs it, once, against the finished module.
    (tmp_path / "hookwrapped.py").write_text(textwrap.dedent("""
        from cnotebook import _hooks

        _hooks.on_import("hookwrapped", "hookcb:two")

        VALUE = 7
    """))
    import hookcb

    _hooks.on_import("hookwrapped", "hookcb:one")
    import hookwrapped

    assert hookwrapped.VALUE == 7
    assert hookcb.CALLS == ["one", "two"]
    assert [w for w in recwarn if issubclass(w.category, CNotebookWarning)] == []


def test_registration_while_a_wrapped_loader_executes_the_body_runs_it_once(fake_packages):
    # A loader that runs a module body without flagging the module as initializing -- the
    # case the import system's `_initializing` protects everywhere else -- is the sharpest
    # form of the race: the registration sees a module that looks finished and runs the
    # callback, and the loader then drains a list that still contains it.
    import hookcb

    class Inner:
        def exec_module(self, module):
            _hooks.on_import("hookinmemory", "hookcb:two")

    _hooks.on_import("hookinmemory", "hookcb:one")
    module = types.ModuleType("hookinmemory")
    sys.modules["hookinmemory"] = module
    _hooks._WrappedLoader(Inner(), _hooks._FINDER, "hookinmemory").exec_module(module)

    # "two" runs from its own registration, "one" from the drain; neither runs twice.
    assert hookcb.CALLS == ["two", "one"]


def test_registration_from_inside_the_watched_modules_own_body_is_skipped(fake_packages, tmp_path, recwarn):
    # A module that imports cnotebook from its own body is already in sys.modules and
    # still initializing, and the import system hands back the partial module rather than
    # deadlocking. There is nothing complete to attach to, so the callback is dropped --
    # quietly, because the import itself is perfectly legitimate.
    (tmp_path / "hookcircular.py").write_text(textwrap.dedent("""
        from cnotebook import _hooks

        _hooks.on_import("hookcircular", "hookcb:second")

        VALUE = 6
    """))
    import hookcb
    import hookcircular

    assert hookcircular.VALUE == 6
    assert hookcb.CALLS == []
    # The registration survives, so a later fresh import of the module still gets it.
    assert _hooks._FINDER._callbacks["hookcircular"] == ["hookcb:second"]
    assert [w for w in recwarn if issubclass(w.category, CNotebookWarning)] == []


def test_import_failure_propagates_and_skips_callbacks(fake_packages):
    _hooks.on_import("hookbroken", "hookcb:note_broken")
    import hookcb

    with pytest.raises(ImportError, match="hookbroken cannot load"):
        import hookbroken  # noqa: F401

    assert hookcb.CALLS == []


def test_reload_of_a_hooked_module_does_not_raise(fake_packages):
    _hooks.on_import("hookdummy", "hookcb:attach")
    import hookcb
    import hookdummy

    importlib.reload(hookdummy)

    assert hookdummy.VALUE == 1
    # A reload re-runs the body through the wrapped loader, which finds nothing left to
    # claim: a registration is consumed once, so the integration is not attached twice.
    assert hookcb.CALLS == [1]


def test_finder_is_installed_once_and_only_when_needed(fake_packages):
    # An already-imported target has nothing to wait for, so it buys no finder.
    _hooks.on_import("sys", "hookcb:second")
    assert _hooks._FINDER not in sys.meta_path

    _hooks.on_import("hookdummy", "hookcb:attach")
    _hooks.on_import("hookpkg", "hookcb:note_package")

    assert sys.meta_path.count(_hooks._FINDER) == 1
    # In front of the standard finders, or the loader would already be chosen.
    assert sys.meta_path[0] is _hooks._FINDER


def test_disabled_finder_still_runs_callbacks_for_imported_modules(fake_packages, monkeypatch):
    monkeypatch.setattr(_hooks, "_DISABLED", True)
    _hooks.on_import("sys", "hookcb:second")
    import hookcb

    assert hookcb.CALLS == ["second"]
    assert _hooks._FINDER not in sys.meta_path


def test_wrapped_loader_delegates_create_module():
    sentinel = types.ModuleType("sentinel")

    class Inner:
        def create_module(self, spec):
            return sentinel

        def exec_module(self, module):
            pass

    class WithoutCreateModule:
        def exec_module(self, module):
            pass

    assert _hooks._WrappedLoader(Inner(), _hooks._FINDER, "hookdummy").create_module(None) is sentinel
    assert _hooks._WrappedLoader(WithoutCreateModule(), _hooks._FINDER, "hookdummy").create_module(None) is None


def test_wrapped_loader_delegates_load_module():
    # `Loader` supplies a default `load_module`, and inheriting it would load the module
    # by a route that never consults the real loader at all.
    sentinel = types.ModuleType("sentinel")

    class Inner:
        def __init__(self):
            self.loaded = []

        def exec_module(self, module):
            pass

        def load_module(self, fullname):
            self.loaded.append(fullname)
            return sentinel

    class WithoutLoadModule:
        def exec_module(self, module):
            pass

    inner = Inner()
    assert _hooks._WrappedLoader(inner, _hooks._FINDER, "hookdummy").load_module("hookdummy") is sentinel
    assert inner.loaded == ["hookdummy"]

    with pytest.raises(NotImplementedError, match="WithoutLoadModule"):
        _hooks._WrappedLoader(WithoutLoadModule(), _hooks._FINDER, "hookdummy").load_module("hookdummy")


def test_env_var_disables_finder():
    code = ("import cnotebook, sys; from cnotebook import _hooks; "
            "print(any(isinstance(f, _hooks.PostImportFinder) for f in sys.meta_path))")
    out = _run_child(code, CNOTEBOOK_NO_IMPORT_HOOKS="1")

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("False")


def test_finder_is_installed_without_the_env_var():
    code = ("import cnotebook, sys; from cnotebook import _hooks; "
            "print(any(isinstance(f, _hooks.PostImportFinder) for f in sys.meta_path))")
    env = {k: v for k, v in os.environ.items() if k != "CNOTEBOOK_NO_IMPORT_HOOKS"}
    env["PYTHONPATH"] = os.pathsep.join(part for part in (_REPO_ROOT, env.get("PYTHONPATH")) if part)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, cwd=_REPO_ROOT, check=False)

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("True")
