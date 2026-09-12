"""Tests for the post-import hooks that attach cnotebook to optional dependencies.

Every import in the process passes through the finder these hooks install, so the
tests below are as much about what it must *not* disturb -- unregistered names,
packages, namespace packages, failed imports, reloads -- as about the callbacks
themselves.
"""

import importlib
import os
import subprocess
import sys
import textwrap
import types
from importlib.machinery import ModuleSpec
from pathlib import Path

import pytest

from cnotebook import _hooks
from cnotebook.core.errors import CNotebookWarning

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)

# Throwaway modules the fixture writes; every test starts and ends with them unimported.
_FAKE_NAMES = ("hookdummy", "hookcb", "hookbroken", "hookpkg", "hookpkg.sub", "hookns", "hookns.leaf",
               "hookselfimport")

_CALLBACKS = """
CALLS = []


def attach():
    import hookdummy

    CALLS.append(hookdummy.VALUE)


def second():
    CALLS.append("second")


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
    assert hookcb.CALLS == [1, 1]


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

    assert _hooks._WrappedLoader(Inner(), []).create_module(None) is sentinel
    assert _hooks._WrappedLoader(WithoutCreateModule(), []).create_module(None) is None


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
