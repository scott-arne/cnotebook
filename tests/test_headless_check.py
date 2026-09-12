"""Unit tests for the headless smoke check's judgement logic.

Loading the documents needs a browser; deciding whether a loaded document passed does
not. These tests drive ``scripts/headless_check.py`` with synthetic shell runs, so a
regression in the pass/fail rules is caught by the default suite rather than only by
the ``browser``-marked test on a machine that happens to have a shell installed.
"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

# noinspection PyPackageRequirements
from invoke.context import Context

_ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path) -> ModuleType:
    """Load a module that lives outside the package, by path.

    Neither ``scripts/headless_check.py`` nor ``tasks.py`` is importable as part of the
    ``cnotebook`` package, and both are deliberately kept out of it.

    :param name: Name to give the module.
    :param path: File to load.
    :returns: The loaded module.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, as importlib documents: @dataclass resolves the
    # defining module through sys.modules while the class body is being processed.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_CHECK = _load("headless_check", _ROOT / "scripts" / "headless_check.py")

_C3D_DOM = "<html><body><pre>Loaded 3 molecule(s) from initialization</pre></body></html>"
_C3D_PROBE = (
    "CNOTEBOOK_SMOKE c3d ok version=0.4.0 "
    "members=execute,getView,setView,getState,getSelection,pngDataUrl,on"
)
_MOLGRID_DOM = "<html><body>" + '<div class="cn-molgrid-card"><svg></svg></div>' * 3 + "</body></html>"
_MOLGRID_PROBE = "CNOTEBOOK_SMOKE molgrid-probe cards=3 images=3"


def _console(text: str, severity: str = "INFO") -> str:
    """Format one page console line the way Chromium writes it to stderr.

    :param text: The message the page logged.
    :param severity: Chromium's log severity for the line.
    :returns: A single stderr line.
    """
    return f'[0912/043307.268039:{severity}:CONSOLE:9] "{text}", source: file:///page.html (9)'


def _run(dom: str, stderr: str, *, returncode: int | None = 0, timed_out: bool = False):
    """Build a synthetic shell run.

    :param dom: The dumped DOM.
    :param stderr: The shell's stderr.
    :param returncode: Process exit status.
    :param timed_out: Whether the hard timeout killed the run.
    :returns: The ``_ShellRun`` the check judges.
    """
    return _CHECK._ShellRun(returncode, dom, stderr, timed_out)


def test_console_error_trap_report_fails_the_document(tmp_path, capsys):
    """Test the trap's own report condemns the run even at INFO severity."""
    stderr = "\n".join(
        [_console(_C3D_PROBE), _console("CNOTEBOOK_SMOKE console error: deliberate failure")]
    )

    assert _CHECK._check_c3d(_run(_C3D_DOM, stderr), tmp_path) is False
    out = capsys.readouterr().out
    assert "CNOTEBOOK_SMOKE c3d fail" in out
    assert "console error:" in out and "deliberate failure" in out


def test_error_severity_console_line_fails_the_document(tmp_path):
    """Test a line Chromium itself logged at ERROR severity is an offender."""
    stderr = "\n".join([_console(_C3D_PROBE), _console("something the page never saw", "ERROR")])

    assert _CHECK._console_errors(stderr) == [_console("something the page never saw", "ERROR")]
    assert _CHECK._check_c3d(_run(_C3D_DOM, stderr), tmp_path) is False


def test_swiftshader_performance_message_is_ignored(tmp_path):
    """Test the software rasteriser's own console noise does not fail a document."""
    noise = _console("GL Driver Message (OpenGL, Performance, GL_CLOSE_PATH_NV): stall")
    stderr = "\n".join([_console(_C3D_PROBE), noise])

    assert _CHECK._console_errors(stderr) == []
    assert _CHECK._check_c3d(_run(_C3D_DOM, stderr), tmp_path) is True


def test_process_level_gpu_error_is_not_a_console_line(tmp_path):
    """Test browser-level stderr never reaches the console rule."""
    process_level = (
        "[0912/043307.000000:ERROR:gpu/command_buffer/service/gl_utils.cc:430] "
        "[.WebGL-0x1] GL Driver Message"
    )
    stderr = "\n".join([_console(_C3D_PROBE), process_level])

    assert _CHECK._console_errors(stderr) == []
    assert _CHECK._check_c3d(_run(_C3D_DOM, stderr), tmp_path) is True


def test_c3d_host_api_version_mismatch_fails(tmp_path, capsys):
    """Test a host API of the wrong version fails even though the probe said ok."""
    probe = _C3D_PROBE.replace("version=0.4.0", "version=0.3.0")

    assert _CHECK._check_c3d(_run(_C3D_DOM, _console(probe)), tmp_path) is False
    assert "host API version mismatch" in capsys.readouterr().out


def test_c3d_missing_probe_line_fails(tmp_path, capsys):
    """Test a document whose probe never reported cannot pass on its DOM marker."""
    assert _CHECK._check_c3d(_run(_C3D_DOM, ""), tmp_path) is False
    assert "expected 1 host API probe line, got 0" in capsys.readouterr().out


def test_timed_out_run_fails(tmp_path, capsys):
    """Test a shell killed by the hard timeout is a failure, not a silent pass."""
    run = _run(_C3D_DOM, _console(_C3D_PROBE), returncode=None, timed_out=True)

    assert _CHECK._check_c3d(run, tmp_path) is False
    assert "the shell did not finish before the hard timeout" in capsys.readouterr().out


def test_molgrid_live_dom_counts_and_markup_pass(tmp_path):
    """Test a real render satisfies both the dumped DOM and the live probe."""
    run = _run(_MOLGRID_DOM, _console(_MOLGRID_PROBE))

    assert _CHECK._check_molgrid(run, tmp_path, items=3) is True


def test_molgrid_markup_without_a_probe_line_fails(tmp_path, capsys):
    """Test card markup that no probe counted cannot pass the check.

    This is the page that renders nothing and only holds the card literals in a
    script: the dumped DOM counts are satisfied, the live document is empty.
    """
    run = _run(f"<html><body><script>const t = '{_MOLGRID_DOM}';</script></body></html>", "")

    assert _CHECK._check_molgrid(run, tmp_path, items=3) is False
    assert "expected 1 MolGrid probe line, got 0" in capsys.readouterr().out


def test_molgrid_probe_counts_must_match_the_item_count(tmp_path, capsys):
    """Test cards without their images fail even when the dumped DOM agrees."""
    run = _run(_MOLGRID_DOM, _console("CNOTEBOOK_SMOKE molgrid-probe cards=3 images=0"))

    assert _CHECK._check_molgrid(run, tmp_path, items=3) is False
    assert "live DOM reported images=0, expected 3" in capsys.readouterr().out


def test_ready_timeout_stays_below_the_time_budget():
    """Test the probe can always report before the page's budget is spent."""
    for budget in (500, 1000, 2000, 10000):
        assert 0 < _CHECK._ready_timeout(budget) < budget
    # The default budget leaves the probe the intended six seconds.
    assert _CHECK._ready_timeout(10000) == 6000


def test_discover_shell_prefers_the_highest_build_number(monkeypatch, tmp_path):
    """Test discovery compares build numbers as integers, not as text."""
    monkeypatch.delenv("CNOTEBOOK_HEADLESS_SHELL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    cache = tmp_path / "Library" / "Caches" / "ms-playwright"
    shells = {}
    for build in (1217, 1234, 10000):
        shell = (
            cache
            / f"chromium_headless_shell-{build}"
            / "chrome-headless-shell-mac-arm64"
            / "chrome-headless-shell"
        )
        shell.parent.mkdir(parents=True)
        shell.write_text("#!/bin/sh\n", encoding="utf-8")
        shells[build] = shell

    assert _CHECK.discover_shell() == str(shells[10000])


def test_discover_shell_honours_the_environment_override(monkeypatch, tmp_path):
    """Test CNOTEBOOK_HEADLESS_SHELL wins over whatever is cached."""
    monkeypatch.setenv("CNOTEBOOK_HEADLESS_SHELL", str(tmp_path / "elsewhere" / "shell"))

    assert _CHECK.discover_shell() == str(tmp_path / "elsewhere" / "shell")


def test_discover_shell_reports_nothing_when_none_is_installed(monkeypatch, tmp_path):
    """Test an empty cache is reported as no shell rather than guessed at."""
    monkeypatch.delenv("CNOTEBOOK_HEADLESS_SHELL", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert _CHECK.discover_shell() is None


def test_invoke_smoke_skips_when_no_shell_is_installed(monkeypatch, capsys):
    """Test `invoke smoke` says why it did nothing and runs no check."""
    # The task imports `headless_check` by name, so the patched module has to be the
    # one that import resolves to.
    monkeypatch.setitem(sys.modules, "headless_check", _CHECK)
    monkeypatch.setattr(_CHECK, "discover_shell", lambda: None)
    tasks = _load("cnotebook_tasks", _ROOT / "tasks.py")
    context = MagicMock(spec=Context)

    assert tasks.smoke(context) is None
    context.run.assert_not_called()
    assert "No headless shell found" in capsys.readouterr().out


def test_invoke_smoke_runs_the_check_when_a_shell_is_found(monkeypatch, capsys):
    """Test the discovered shell is passed to the script, quoted."""
    monkeypatch.setitem(sys.modules, "headless_check", _CHECK)
    monkeypatch.setattr(_CHECK, "discover_shell", lambda: "/shells/chrome headless shell")
    tasks = _load("cnotebook_tasks", _ROOT / "tasks.py")
    context = MagicMock(spec=Context)

    tasks.smoke(context)

    command = context.run.call_args.args[0]
    assert "headless_check.py" in command
    assert "--shell '/shells/chrome headless shell'" in command
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize(
    ("marker", "expected"),
    [
        ("CNOTEBOOK_SMOKE molgrid-probe cards=3 images=3", {"cards": 3, "images": 3}),
        ("CNOTEBOOK_SMOKE molgrid-probe cards=-1 images=-1 reason=boom", {"cards": -1, "images": -1}),
        ("CNOTEBOOK_SMOKE molgrid-probe cards=x", {}),
    ],
)
def test_marker_fields_reads_only_integer_fields(marker, expected):
    """Test the marker parser ignores anything that is not a `key=<int>` pair."""
    assert _CHECK._marker_fields(marker) == expected
