"""Boot the static MolGrid and C3D documents in a headless Chromium shell.

The module carries the ``browser`` marker and is deselected by the default
``addopts``; run it with ``-m browser`` or through ``invoke smoke``. The check
itself lives in ``scripts/headless_check.py`` so the task and this test judge
the documents by exactly the same rules.
"""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.browser

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "headless_check.py"


def _load_check():
    """Load the check as a module so discovery is defined in exactly one place.

    The script is not importable as ``scripts.headless_check``; loading it by path
    keeps this test and ``invoke smoke`` looking for the shell by the same rule, so
    the two cannot drift into silently skipping.

    :returns: The ``headless_check`` module.
    """
    spec = importlib.util.spec_from_file_location("headless_check", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, as importlib documents: @dataclass resolves the
    # defining module through sys.modules while the class body is being processed.
    sys.modules["headless_check"] = module
    spec.loader.exec_module(module)
    return module


_SHELL = _load_check().discover_shell()


@pytest.mark.skipif(_SHELL is None, reason="Playwright headless shell not installed")
def test_static_documents_boot_without_console_errors(tmp_path: Path) -> None:
    """Test both static documents boot, expose the host API and render their cards."""
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--shell", str(_SHELL), "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
        # Every browser run already carries its own hard timeout; this one only bounds
        # a wedged interpreter, so a hung check fails the test instead of the session.
        timeout=600,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    # The machine-readable lines are the evidence that the pages actually ran: a
    # document that merely loads without console errors would pass on markers alone.
    assert "CNOTEBOOK_SMOKE c3d ok version=0.4.0" in result.stdout
    assert (
        "members=execute,getView,setView,getState,getSelection,pngDataUrl,on objects=1"
        in result.stdout
    )
    assert "CNOTEBOOK_SMOKE molgrid ok" in result.stdout
