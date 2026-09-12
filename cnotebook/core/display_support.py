"""Environment detection and durable file writing shared by the notebook views.

The C3D viewer and the molecule grid both have to answer the same two questions -- is
there a front end that could draw a widget, and how is a document written so a failed
write cannot destroy the previous one -- and both used to answer them with their own
copy of these helpers.
"""

from __future__ import annotations

import functools
import os
import stat
import sys
import tempfile
from pathlib import Path

from cnotebook.core.errors import CNotebookError

__all__ = [
    "apply_output_permissions",
    "default_file_mode",
    "has_display_frontend",
    "is_marimo",
    "prepare_target",
    "write_atomically",
]


def is_marimo() -> bool:
    """Check whether this process is running inside a marimo notebook.

    Both halves matter: marimo must be imported *and* a marimo runtime must be active,
    so a plain script that happens to import marimo is not mistaken for a notebook.

    :returns: True when a marimo notebook is running.
    """
    if "marimo" not in sys.modules:
        return False
    try:
        import marimo as mo  # type: ignore[import-not-found]  # pyright: ignore[reportMissingImports]

        return mo.running_in_notebook()
    except (ImportError, AttributeError):
        return False


def has_display_frontend() -> bool:
    """Check whether something in this process could render a widget.

    A widget is a message to a front end, not a value: without one it has nothing to
    draw into and shows as a bare repr. A terminal IPython session counts as no front
    end even though it has a shell, because it has no widget manager. The kernel shell
    is recognized the same way :func:`cnotebook.get_env` recognizes it, by class name,
    but through the MRO so a front end that subclasses it (Colab does) still counts.
    The check is made per call rather than once at import, because a session can
    acquire a shell after cnotebook loads.

    :returns: True when a marimo notebook or a Jupyter kernel shell is running.
    """
    if is_marimo():
        return True
    try:
        from IPython.core.getipython import get_ipython
    except ImportError:
        return False
    shell = get_ipython()
    if shell is None:
        return False
    return any(cls.__name__ == "ZMQInteractiveShell" for cls in type(shell).__mro__)


def prepare_target(path: str | os.PathLike[str]) -> Path:
    """Validate that *path* can be written and return it as a :class:`~pathlib.Path`.

    The directory is checked before any work is done so a mistyped path fails
    immediately rather than after a whole grid has been rendered or a 30 s wait for
    the front end.

    :param path: Destination file.
    :returns: The destination as a path.
    :raises CNotebookError: If the destination's directory does not exist.
    """
    target = Path(path)
    directory = target.parent
    if not directory.is_dir():
        raise CNotebookError(f"Cannot write {target}: the directory {directory} does not exist")
    return target


@functools.cache
def default_file_mode() -> int:
    """Return the permissions a plain ``open(path, "wb")`` would give a new file.

    The umask can only be read by setting it, which is process-global and therefore
    momentarily wrong for every other thread. The answer is cached so that window is
    opened once per process instead of once per saved file; a program that changes its
    umask mid-run is not worth reopening it for.

    :returns: The mode bits for a newly created output file.
    """
    umask = os.umask(0)
    os.umask(umask)
    return 0o666 & ~umask


def apply_output_permissions(temporary: Path, target: Path) -> None:
    """Give the temporary file the permissions the finished document should have.

    :func:`tempfile.mkstemp` creates its file 0600 because temporary files may hold
    secrets. A saved document is an ordinary output file, so it takes the mode of the
    file it replaces, or the mode a plain ``open()`` would have produced.

    :param temporary: The file about to be moved into place.
    :param target: The destination, which may or may not exist yet.
    """
    try:
        mode = stat.S_IMODE(target.stat().st_mode)
    except OSError:
        mode = default_file_mode()
    os.chmod(temporary, mode)


def write_atomically(path: str | os.PathLike[str], data: bytes) -> Path:
    """Write *data* to *path* so a failed write never leaves a truncated file.

    The bytes go to a temporary file in the destination directory and are moved onto the
    target with :func:`os.replace`, which is atomic within one filesystem. A reader
    therefore sees either the previous file or the complete new one, and an interrupted
    write leaves the previous document in place.

    :param path: Destination file.
    :param data: Bytes to write.
    :returns: The destination path.
    :raises CNotebookError: If the destination's directory does not exist.
    :raises OSError: If the write or the move fails.
    """
    target = prepare_target(path)
    descriptor, temporary = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
        apply_output_permissions(Path(temporary), target)
        os.replace(temporary, target)
    except BaseException:
        # os.replace consumed the temporary file on success; on any failure it is still
        # there, and a stray dot-file next to the user's output is its own small bug.
        Path(temporary).unlink(missing_ok=True)
        raise
    return target
