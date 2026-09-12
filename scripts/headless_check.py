"""Boot the static C3D and MolGrid documents in a headless Chromium shell.

The static documents are the only part of cnotebook that no Python test can
exercise: they are HTML, and their front ends only run in a browser. This check
renders both documents, loads each one in the Playwright headless shell and
exits 0 only when every document passed every check, so ``invoke smoke`` and
``tests/test_browser_smoke.py`` can trust the exit status.

A document passes when all of the following hold:

* the shell exits 0 within the hard timeout,
* its page logged no console error lines (see :data:`_CONSOLE_TEXT_ERROR_RES` and
  the trap injected by :func:`_with_trap`),
* the expected markers are in the dumped DOM, with the counts they carry, and
* an injected probe reported on the live page: the ``window.c3d`` host API and
  the molecules the viewer actually loaded for C3D, the rendered card and image
  elements for MolGrid.

Usage::

    python scripts/headless_check.py [--shell <path>] [--out <dir>] [--verbose]

With no ``--shell`` the newest shell under the Playwright cache is used. With
``--out`` the generated documents, dumped DOMs, stderr logs and screenshots are
kept in that directory for inspection; otherwise they land in a temporary one
that is removed when every document passed and kept when one did not.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # Annotations only; the runtime imports are deferred (see below).
    from openeye import oechem

# Running a script by path does not put the repository on sys.path, so `import
# cnotebook` would resolve through whatever editable install is active; inside a git
# worktree that is the main checkout rather than this tree. Prepending the repository
# root makes the check exercise the code it ships with. The openeye and cnotebook
# imports live in the functions that need them, both because they have to run after
# this line and so `invoke smoke` can call discover_shell() without loading the
# toolkits.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

#: Where Playwright caches the headless shell on macOS; the build number varies.
SHELL_GLOB = (
    "~/Library/Caches/ms-playwright/chromium_headless_shell-*"
    "/chrome-headless-shell-mac-arm64/chrome-headless-shell"
)

_SMOKE_PREFIX = "CNOTEBOOK_SMOKE"

#: Host API contract the C3D probe checks (3dmol-js-gui 0.4.0, spec section C1).
_HOST_API_VERSION = "0.4.0"
_HOST_API_MEMBERS = (
    "execute",
    "getView",
    "setView",
    "getState",
    "getSelection",
    "pngDataUrl",
    "on",
)

#: Molecules embedded in both documents: phenol, ethanol, aspirin.
_SMILES = ("c1ccccc1O", "CCO", "CC(=O)Oc1ccccc1C(=O)O")
#: How many of them the C3D document is built from. Named because the same number is
#: both what the document is given and what the live viewer is required to report back.
_C3D_MOLECULES = 1

# Chromium writes page console output to stderr as
# `[pid/time:SEVERITY:CONSOLE:line] "text", source: <url> (line)`. Everything else on
# stderr is the browser talking about itself -- the process-level `ERROR:` lines from
# gl_utils.cc under SwiftShader, or the screenshot's "N bytes written" -- and says
# nothing about the document, so only console lines are judged.
_CONSOLE_LINE_RE = re.compile(r":CONSOLE:\d+\]")
# A console line fails the check when Chromium logged it at ERROR or FATAL severity, or
# when its message matches one of the text signatures. The severity cannot carry the rule
# on its own: this shell logs console.error() and uncaught exceptions at INFO severity,
# so an ERROR-only pattern would pass a page that is on fire. The trap injected into
# every document (see _TRAP_JS) is the precise signal; the rest is the net under it, for
# what the page never sees because the browser logged it (blocked subresources, CSP
# violations). The text signatures are matched against the message alone, so an artifact
# directory whose name contains "error" cannot condemn every line through the `source:`
# suffix.
_CONSOLE_SEVERITY_RE = re.compile(r":(?:ERROR|FATAL):CONSOLE:")
# The signatures are deliberately narrow, so nothing needs an exemption list: the one
# piece of console noise these runs produce is SwiftShader's "GL Driver Message (OpenGL,
# Performance, ...): GPU stall due to ReadPixels", which matches none of them and is
# pinned as a non-offender by the unit tests.
_CONSOLE_TEXT_ERROR_RES = (
    re.compile(rf"^{_SMOKE_PREFIX} console error:"),
    re.compile(r"(?i)\b(?:uncaught|unhandled)\b"),
    re.compile(r"(?i)\berrors?\b"),
)
# A marker line as it reaches stderr, quoted inside Chromium's console format.
_MARKER_RE = re.compile(rf'"({_SMOKE_PREFIX} [^"]*)"')

# The GUI terminal prints this once the init payload is applied. The count is captured
# and compared with _C3D_MOLECULES rather than matched as bare digits, because the line
# is printed from the length of the payload and not from what reached the scene: a
# molecule whose load threw is reported to the terminal and then counted here anyway.
# Capturing the digits also keeps the bundle's own source, which the dumped DOM carries,
# from satisfying the pattern: it reads `Loaded ${n.length} molecule(s) ...`.
_C3D_LOADED_RE = re.compile(r"Loaded (\d+) molecule\(s\) from initialization")
# Rendered cards, matched on the attribute rather than the bare class name, which also
# appears in the stylesheet and in the module source the document inlines.
_CARD_RE = re.compile(r'class="cn-molgrid-card[ "]')
_SVG_RE = re.compile(r"<svg\b")

# Injected into the head of a copy of every document, ahead of the page's own scripts,
# so console.error() calls and uncaught exceptions are reported under a marker the check
# can match exactly rather than guessed at from Chromium's log severity.
_TRAP_JS = """
(function () {
  var PREFIX = "__PREFIX__";
  function report(text) {
    console.log(PREFIX + " console error: " + text);
  }
  var original = console.error;
  console.error = function () {
    report(Array.prototype.map.call(arguments, String).join(" "));
    return original.apply(console, arguments);
  };
  window.addEventListener("error", function (event) {
    report("window error: " + ((event && (event.message || event.type)) || "unknown"));
  });
  window.addEventListener("unhandledrejection", function (event) {
    report("unhandled rejection: " + String((event && event.reason) || "unknown"));
  });
})();
"""

# The probe reports on the host API after the page settles. It is injected into a copy
# of the C3D document because the API is the contract the static viewer exists to offer,
# and a page that merely loads without console errors proves nothing about it.
_C3D_PROBE_JS = """
const MEMBERS = __MEMBERS__;
const PREFIX = "__PREFIX__";
const TIMEOUT_MS = __TIMEOUT_MS__;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function probe() {
  // The API is installed during the GUI module's start-up, which may finish after this
  // module runs, so poll for it before asking it anything.
  const deadline = Date.now() + TIMEOUT_MS;
  while (typeof window.c3d === "undefined" && Date.now() < deadline) {
    await sleep(25);
  }
  if (typeof window.c3d !== "object" || window.c3d === null) {
    return `fail reason=no-host-api typeof=${typeof window.c3d}`;
  }
  if (typeof (window.c3d.ready || {}).then !== "function") {
    return "fail reason=ready-not-thenable";
  }
  let timer;
  const expired = new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error("ready-timeout")), Math.max(0, deadline - Date.now()));
  });
  try {
    await Promise.race([window.c3d.ready, expired]);
  } finally {
    clearTimeout(timer);
  }
  const missing = MEMBERS.filter((name) => typeof window.c3d[name] !== "function");
  if (missing.length > 0) {
    return `fail reason=missing-members missing=${missing.join(",")}`;
  }
  // `ready` resolving only means the init payload was applied. The GUI's loader catches
  // a per-molecule failure, prints it to the page's own terminal and carries on, so the
  // scene is the only honest witness: getState() lists what is loaded, by name.
  const state = window.c3d.getState();
  const objects = state && Array.isArray(state.objects) ? state.objects.length : -1;
  return `ok version=${window.c3d.version} members=${MEMBERS.join(",")} objects=${objects}`;
}

probe().then(
  (result) => console.log(`${PREFIX} c3d ${result}`),
  (error) => console.log(`${PREFIX} c3d fail reason=${(error && error.message) || error}`),
);
"""

# The MolGrid equivalent. The dumped DOM is text, so counting `class="cn-molgrid-card"`
# in it would also count the same literal sitting unrendered inside a script; this probe
# counts elements in the live document, which only a real render can produce.
_MOLGRID_PROBE_JS = """
const PREFIX = "__PREFIX__";
const TIMEOUT_MS = __TIMEOUT_MS__;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const cards = () => document.querySelectorAll(".cn-molgrid-card");

async function probe() {
  // The grid renders from its embedded payload after the module boots, so wait for the
  // first card rather than reporting on an empty document.
  const deadline = Date.now() + TIMEOUT_MS;
  while (cards().length === 0 && Date.now() < deadline) {
    await sleep(25);
  }
  const images = document.querySelectorAll(".cn-molgrid-card svg, .cn-molgrid-card img");
  return `cards=${cards().length} images=${images.length}`;
}

probe().then(
  (result) => console.log(`${PREFIX} molgrid-probe ${result}`),
  (error) => console.log(`${PREFIX} molgrid-probe cards=-1 images=-1 reason=${(error && error.message) || error}`),
);
"""

#: The probe injected into each document's instrumented copy.
_PROBES = {"c3d": _C3D_PROBE_JS, "molgrid": _MOLGRID_PROBE_JS}


def _build_number(path: str) -> int:
    """Extract the Playwright build number from a cached shell path.

    :param path: A path matching :data:`SHELL_GLOB`.
    :returns: The build number, or ``-1`` when the path carries none.
    """
    match = re.search(r"chromium_headless_shell-(\d+)", path)
    return int(match.group(1)) if match else -1


def discover_shell() -> str | None:
    """Locate the newest Playwright headless shell on this machine.

    ``CNOTEBOOK_HEADLESS_SHELL`` overrides the search, so a shell installed
    elsewhere (or a different browser build) can be pointed at directly.

    :returns: Path to the shell executable, or ``None`` when none is installed.
    """
    override = os.environ.get("CNOTEBOOK_HEADLESS_SHELL")
    if override:
        return override
    # Sorted on the build number as an integer, so build 10000 beats build 1234; the
    # path is the tiebreak for anything the pattern matched without a build number.
    found = sorted(
        glob.glob(os.path.expanduser(SHELL_GLOB)),
        key=lambda path: (_build_number(path), path),
        reverse=True,
    )
    return found[0] if found else None


@dataclass(frozen=True)
class _ShellRun:
    """Outcome of one headless shell invocation.

    :param returncode: Process exit status; ``None`` when the run was killed.
    :param dom: The dumped DOM (the shell's stdout).
    :param stderr: The shell's stderr, which carries the page's console output.
    :param timed_out: Whether the hard timeout killed the run.
    """

    returncode: int | None
    dom: str
    stderr: str
    timed_out: bool


def _molecules() -> list[oechem.OEGraphMol]:
    """Build the molecules both documents are generated from.

    :returns: One molecule per entry in :data:`_SMILES`.
    """
    from openeye import oechem

    molecules = []
    for smiles in _SMILES:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mol.SetTitle(smiles)
        molecules.append(mol)
    return molecules


def _probe_script(kind: str, timeout_ms: int) -> str:
    """Render one document's probe as an injectable module script.

    :param kind: Document kind, a key of :data:`_PROBES`.
    :param timeout_ms: How long the page waits for the thing it probes.
    :returns: A ``<script type="module">`` element.
    """
    body = (
        _PROBES[kind]
        .replace("__MEMBERS__", json.dumps(list(_HOST_API_MEMBERS)))
        .replace("__PREFIX__", _SMOKE_PREFIX)
        .replace("__TIMEOUT_MS__", str(int(timeout_ms)))
    )
    return f'<script type="module">{body}</script>\n'


def _ready_timeout(budget_ms: int) -> int:
    """Choose how long a probe waits before reporting what it found.

    A probe has to report before the page's virtual time budget runs out, or the shell
    dumps the DOM and exits while the probe is still waiting, and the run then fails on
    a missing probe line instead of the real reason. The wait is 60% of the budget but
    never more than 80% of it, so even a small ``--virtual-time-budget`` still produces
    an honest ``reason=ready-timeout``.

    :param budget_ms: The page's virtual time budget, in milliseconds.
    :returns: The probe timeout in milliseconds, always below the budget.
    """
    return min(max(1000, int(budget_ms * 0.6)), max(1, int(budget_ms * 0.8)))


def _with_trap(document: str) -> str:
    """Return *document* with the console error trap installed in its head.

    The trap goes after the charset declaration -- which must stay inside the
    first bytes of the document for the encoding sniffer -- and before every
    other script, so nothing a page script logs happens before it is watched.

    :param document: A complete document.
    :returns: The instrumented copy.
    :raises ValueError: If the document carries no charset declaration to anchor on.
    """
    anchor = '<meta charset="UTF-8">'
    if anchor not in document:
        raise ValueError(f"document has no {anchor}; cannot install the console trap")
    head, tail = document.split(anchor, 1)
    trap = _TRAP_JS.replace("__PREFIX__", _SMOKE_PREFIX)
    return f"{head}{anchor}\n<script>{trap}</script>\n{tail}"


def _with_probe(document: str, kind: str, timeout_ms: int) -> str:
    """Return *document* with its probe appended to the body.

    :param document: A complete document.
    :param kind: Document kind, a key of :data:`_PROBES`.
    :param timeout_ms: Probe timeout passed to :func:`_probe_script`.
    :returns: The instrumented copy.
    :raises ValueError: If the document has no ``</body>`` to inject before.
    """
    if "</body>" not in document:
        raise ValueError(f"{kind} document has no </body>; cannot inject the probe")
    # Split on the last occurrence: the inlined bundle may well contain the text.
    head, tail = document.rsplit("</body>", 1)
    return f"{head}{_probe_script(kind, timeout_ms)}</body>{tail}"


def _write_documents(out: Path, *, ready_timeout_ms: int) -> dict[str, Path]:
    """Generate the static documents and the instrumented copies under *out*.

    The document as cnotebook produces it is kept next to the copy the shell
    loads, so a failure can be reproduced by hand without the instrumentation.

    :param out: Directory to write into.
    :param ready_timeout_ms: Probe timeout for the instrumented copies.
    :returns: Mapping of artifact name to path; the ``*_load`` entries are the
        documents the shell is pointed at.
    """
    from cnotebook.c3d import C3D
    from cnotebook.grid import MolGrid

    molecules = _molecules()
    # Both constructors resolve every option they are not given through the machine's
    # configuration (CNOTEBOOK_CONFIG or the home config file), so the fixture states
    # the ones the check asserts on. Left ambient, a configured page size below the
    # molecule count or PNG images would fail the check on the documents rather than on
    # the front ends they exist to exercise.
    viewer = C3D(width=800, height=600, theme="light")
    for molecule in molecules[:_C3D_MOLECULES]:
        viewer.add_molecule(molecule)
    documents = {
        "molgrid": MolGrid(
            molecules,
            n_items_per_page=len(molecules),
            image_format="svg",
            theme="light",
        ).to_html(),
        "c3d": viewer.to_html(),
    }
    paths = {}
    for name, document in documents.items():
        source = out / f"{name}.html"
        source.write_text(document, encoding="utf-8")
        # Every copy carries the console trap and the probe its kind is judged by.
        instrumented = _with_probe(document, name, ready_timeout_ms)
        loaded = out / f"{name}.probe.html"
        loaded.write_text(_with_trap(instrumented), encoding="utf-8")
        paths[name] = source
        paths[f"{name}_load"] = loaded
    return paths


def _run_shell(
    shell: str,
    document: Path,
    out: Path,
    *,
    name: str,
    budget_ms: int,
    timeout_s: float,
    window: tuple[int, int],
    verbose: bool,
) -> _ShellRun:
    """Load *document* once in the headless shell.

    The DOM dump and the screenshot are taken in the same run, so the page is
    booted once per document.

    :param shell: Path to the headless shell executable.
    :param document: Document to load.
    :param out: Directory for the screenshot, the DOM dump and the stderr log.
    :param name: Artifact base name.
    :param budget_ms: Virtual time budget; the shell exits when it is spent.
    :param timeout_s: Hard wall-clock timeout for the process.
    :param window: Screenshot window size in pixels.
    :param verbose: Whether to echo the command line.
    :returns: The run's outcome.
    """
    command = [
        shell,
        "--headless",
        "--disable-gpu",
        # SwiftShader is the only working GL path here: 3Dmol.js needs WebGL, and the
        # sandboxed machine has no usable GPU.
        "--use-angle=swiftshader",
        "--enable-unsafe-swiftshader",
        "--ignore-gpu-blocklist",
        # A profile per document keeps one run's singleton lock out of the next one's way.
        f"--user-data-dir={out / f'profile-{name}'}",
        "--enable-logging=stderr",
        "--v=0",
        f"--virtual-time-budget={budget_ms}",
        "--dump-dom",
        f"--screenshot={out / f'{name}.png'}",
        f"--window-size={window[0]},{window[1]}",
        document.resolve().as_uri(),
    ]
    if verbose:
        print("  $ " + " ".join(command))
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout_s, check=False
        )
    except subprocess.TimeoutExpired as exc:
        # A wedged shell must fail the check rather than hang the caller, and whatever
        # it managed to emit is still worth keeping.
        run = _ShellRun(None, _as_text(exc.stdout), _as_text(exc.stderr), True)
    else:
        run = _ShellRun(proc.returncode, proc.stdout, proc.stderr, False)
    (out / f"{name}.dom.html").write_text(run.dom, encoding="utf-8")
    (out / f"{name}.stderr.log").write_text(run.stderr, encoding="utf-8")
    return run


def _as_text(value: str | bytes | None) -> str:
    """Normalize captured output that may be bytes or missing.

    :param value: Captured stream contents.
    :returns: The contents as text, empty when nothing was captured.
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return value


def _console_message(line: str) -> str:
    """Strip Chromium's framing from a console line.

    A console line reads ``[MMDD/HHMMSS.mmm:SEVERITY:CONSOLE:12] "text", source: url (12)``;
    only ``text`` came from the page.

    :param line: One line of the shell's stderr.
    :returns: The page's message, or the whole line when the framing is unrecognised.
    """
    _, _, rest = line.partition("] ")
    message = rest.rsplit(", source: ", 1)[0] if ", source: " in rest else rest
    return message.strip().strip('"')


def _console_errors(stderr: str) -> list[str]:
    """Select the console lines that count as failures.

    :param stderr: The shell's stderr.
    :returns: The offending lines, in order.
    """
    offenders = []
    for line in stderr.splitlines():
        if _CONSOLE_LINE_RE.search(line) is None:
            continue
        message = _console_message(line)
        text_error = any(pattern.search(message) for pattern in _CONSOLE_TEXT_ERROR_RES)
        if text_error or _CONSOLE_SEVERITY_RE.search(line) is not None:
            offenders.append(line)
    return offenders


def _marker_lines(stderr: str, kind: str) -> list[str]:
    """Extract the probe's machine-readable lines from the console output.

    :param stderr: The shell's stderr.
    :param kind: Document kind the line must report on, e.g. ``"c3d"``.
    :returns: The marker payloads, without Chromium's log framing.
    """
    prefix = f"{_SMOKE_PREFIX} {kind} "
    return [m.group(1) for m in _MARKER_RE.finditer(stderr) if m.group(1).startswith(prefix)]


def _marker_values(marker: str) -> dict[str, str]:
    """Parse the ``key=value`` fields of a marker line as text.

    :param marker: A marker payload, e.g. ``"CNOTEBOOK_SMOKE c3d ok version=0.4.0"``.
    :returns: The value of every ``key=value`` token, keyed by name.
    """
    values = {}
    for token in marker.split():
        key, separator, value = token.partition("=")
        if separator:
            values[key] = value
    return values


def _marker_fields(marker: str) -> dict[str, int]:
    """Parse the integer ``key=value`` fields of a marker line.

    :param marker: A marker payload, e.g. ``"CNOTEBOOK_SMOKE molgrid-probe cards=3"``.
    :returns: The fields whose value is an integer, keyed by name.
    """
    return {
        key: int(value)
        for key, value in _marker_values(marker).items()
        if value.lstrip("-").isdigit()
    }


def _report(name: str, summary: str, problems: list[str], run: _ShellRun, out: Path) -> bool:
    """Print one document's verdict.

    :param name: Document kind, e.g. ``"molgrid"``.
    :param summary: Trailing fields of the machine-readable line.
    :param problems: Human-readable failures; empty means the document passed.
    :param run: The shell run the verdict came from.
    :param out: Artifact directory, named in the failure detail.
    :returns: Whether the document passed.
    """
    status = "ok" if not problems else "fail"
    print(f"{_SMOKE_PREFIX} {name} {status} {summary}".rstrip())
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"  exit={run.returncode} timed_out={run.timed_out} artifacts={out}")
    return not problems


def _shell_problems(run: _ShellRun) -> list[str]:
    """Collect the failures every document is judged on: the exit status and the console.

    :param run: The shell run to judge.
    :returns: One entry per problem, empty when the run was clean.
    """
    problems = [] if run.returncode == 0 else [_exit_problem(run)]
    # Only the first offenders are printed: a page that fails usually fails repeatedly,
    # and the full log is kept under the artifact directory either way.
    return problems + [f"console error: {line}" for line in _console_errors(run.stderr)[:20]]


def _check_c3d(run: _ShellRun, out: Path) -> bool:
    """Judge the C3D document from its run.

    :param run: The shell run to judge.
    :param out: Artifact directory.
    :returns: Whether the document passed.
    """
    problems = _shell_problems(run) + _c3d_loaded_problems(run.dom)

    markers = _marker_lines(run.stderr, "c3d")
    summary = ""
    if len(markers) != 1:
        problems.append(f"expected 1 host API probe line, got {len(markers)}: {markers}")
    else:
        # `CNOTEBOOK_SMOKE c3d <status> <fields>`; the fields become this document's
        # summary, so the caller sees the version, the members and the object count the
        # page reported.
        fields = markers[0].split(" ", 3)
        status, summary = fields[2], fields[3] if len(fields) > 3 else ""
        if status != "ok":
            problems.append(f"host API probe failed: {markers[0]}")
        else:
            problems += _c3d_probe_problems(summary, markers[0])
    return _report("c3d", summary, problems, run, out)


def _c3d_loaded_problems(dom: str) -> list[str]:
    """Judge the load line the GUI terminal left in the dumped DOM.

    :param dom: The dumped DOM.
    :returns: One entry per problem, empty when the line reported the expected count.
    """
    counts = [int(count) for count in _C3D_LOADED_RE.findall(dom)]
    if not counts:
        return ["DOM marker missing: no 'Loaded <n> molecule(s) from initialization'"]
    return [
        f"DOM reported 'Loaded {count} molecule(s)', expected {_C3D_MOLECULES}"
        for count in counts
        if count != _C3D_MOLECULES
    ]


def _c3d_probe_problems(summary: str, marker: str) -> list[str]:
    """Judge what the host API probe reported about the live viewer.

    The version is compared as a whole value rather than searched for as text, so
    ``0.4.0-beta``, ``10.4.0`` and ``0.4.0.1`` are all mismatches. The object count is
    the one signal that the molecules reached the scene: the terminal's "Loaded n
    molecule(s)" line is printed from the init payload even when every entry in it
    failed to load, and ``ready`` resolves either way.

    :param summary: The marker's trailing fields.
    :param marker: The whole marker line, quoted in the failure detail.
    :returns: One entry per problem, empty when the viewer matched the contract.
    """
    problems = []
    version = _marker_values(summary).get("version")
    if version != _HOST_API_VERSION:
        problems.append(
            f"host API version mismatch: expected {_HOST_API_VERSION}, "
            f"got {version} in {marker!r}"
        )
    objects = _marker_fields(summary).get("objects")
    if objects != _C3D_MOLECULES:
        problems.append(
            f"live viewer holds {objects} loaded molecule(s), expected "
            f"{_C3D_MOLECULES} in {marker!r}"
        )
    return problems


def _check_molgrid(run: _ShellRun, out: Path, *, items: int) -> bool:
    """Judge the MolGrid document from its run.

    :param run: The shell run to judge.
    :param out: Artifact directory.
    :param items: Number of molecules embedded in the document.
    :returns: Whether the document passed.
    """
    problems = _shell_problems(run)
    cards = len(_CARD_RE.findall(run.dom))
    images = len(_SVG_RE.findall(run.dom))
    if cards != items:
        problems.append(f"expected {items} rendered cards, found {cards}")
    if images != items:
        problems.append(f"expected {items} embedded images, found {images}")
    problems += _molgrid_probe_problems(run, items=items)
    summary = f"items={items} cards={cards} images={images}"
    return _report("molgrid", summary, problems, run, out)


def _molgrid_probe_problems(run: _ShellRun, *, items: int) -> list[str]:
    """Judge what the MolGrid probe counted in the live document.

    The dumped DOM is text, so the counts taken from it would also be satisfied by a
    page that renders nothing and merely holds the card markup as a string inside a
    script. The probe counts elements through ``querySelectorAll`` instead, which only
    a real render can satisfy.

    :param run: The shell run to judge.
    :param items: Number of molecules embedded in the document.
    :returns: One entry per problem, empty when the live DOM matched.
    """
    markers = _marker_lines(run.stderr, "molgrid-probe")
    if len(markers) != 1:
        return [f"expected 1 MolGrid probe line, got {len(markers)}: {markers}"]
    counts = _marker_fields(markers[0])
    return [
        f"live DOM reported {field}={counts.get(field)}, expected {items}"
        for field in ("cards", "images")
        if counts.get(field) != items
    ]


def _exit_problem(run: _ShellRun) -> str:
    """Describe a shell run that did not exit cleanly.

    :param run: The failed run.
    :returns: A one-line description.
    """
    if run.timed_out:
        return "the shell did not finish before the hard timeout"
    return f"the shell exited {run.returncode}"


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse the command line.

    :param argv: Arguments to parse, or ``None`` for ``sys.argv``.
    :returns: The parsed arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--shell", default=None, help="headless shell executable (default: newest cached)")
    parser.add_argument("--out", default=None, help="directory for the documents, DOMs, logs and screenshots")
    parser.add_argument("--timeout", type=float, default=180.0, help="hard timeout per document, in seconds")
    parser.add_argument(
        "--virtual-time-budget",
        type=int,
        default=10000,
        help="page time budget, in milliseconds; the injected probes wait at most 80%% of it",
    )
    parser.add_argument("--verbose", action="store_true", help="print the environment and the command lines")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Run the check.

    :param argv: Arguments to parse, or ``None`` for ``sys.argv``.
    :returns: 0 when every document passed, 1 when one failed, 2 on a usage error.
    """
    args = _parse_args(argv)
    shell = args.shell or discover_shell()
    if shell is None:
        print(
            f"No headless shell found under {SHELL_GLOB}.\n"
            "Install one with `npx playwright install chromium-headless-shell` "
            "or point CNOTEBOOK_HEADLESS_SHELL at an executable.",
            file=sys.stderr,
        )
        return 2
    if not os.access(shell, os.X_OK):
        print(f"Headless shell is not executable: {shell}", file=sys.stderr)
        return 2

    temporary = args.out is None
    out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="cnotebook-smoke-"))
    out.mkdir(parents=True, exist_ok=True)
    if args.verbose:
        import cnotebook

        # Which cnotebook this is answers the question the artifacts cannot: a stale
        # editable install renders documents that are not the ones under test.
        print(f"cnotebook: {cnotebook.__file__} ({cnotebook.__version__})")
        print(f"shell: {shell}")
    print(f"artifacts: {out}")

    documents = _write_documents(out, ready_timeout_ms=_ready_timeout(args.virtual_time_budget))

    runs = {
        name: _run_shell(
            shell,
            documents[f"{name}_load"],
            out,
            name=name,
            budget_ms=args.virtual_time_budget,
            timeout_s=args.timeout,
            window=window,
            verbose=args.verbose,
        )
        for name, window in (("c3d", (900, 700)), ("molgrid", (1280, 900)))
    }
    # Both documents are judged before returning, so one failure does not hide the other.
    passed = [
        _check_c3d(runs["c3d"], out),
        _check_molgrid(runs["molgrid"], out, items=len(_SMILES)),
    ]
    if not all(passed):
        print(f"artifacts kept at {out}")
        return 1
    if temporary:
        # A run leaves about 11 MB behind, most of it the two Chromium profiles. A
        # passing run has nothing left to inspect, so only failures keep their evidence.
        shutil.rmtree(out, ignore_errors=True)
        print(f"removed temporary artifacts: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
