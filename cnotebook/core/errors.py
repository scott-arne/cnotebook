"""Warning and error types shared across cnotebook."""

from __future__ import annotations

import logging
import warnings

log = logging.getLogger("cnotebook")


class CNotebookWarning(UserWarning):
    """Warning category for every user-facing cnotebook message."""


class CNotebookError(Exception):
    """Base class for errors raised by cnotebook."""


def warn(message: str, *, stacklevel: int = 2) -> None:
    """Emit *message* as a :class:`CNotebookWarning`.

    :param message: Text shown to the user.
    :param stacklevel: Frames to skip so the warning points at the caller's caller.
    """
    warnings.warn(message, CNotebookWarning, stacklevel=stacklevel + 1)


def _report(message: str, *, stacklevel: int = 2) -> None:
    """Emit *message* as a :class:`CNotebookWarning` that cannot become an exception.

    Some callers cannot let a warning filter decide whether they raise: a post-import
    hook runs inside somebody else's ``exec_module``, and a module ``__getattr__`` owes
    its caller an ``AttributeError``. Under ``warnings.simplefilter("error",
    CNotebookWarning)`` or ``-W error`` an ordinary :func:`warn` would surface there as a
    raised warning, aborting an import that had otherwise succeeded.

    The warning is emitted first, so with the default filters the message reaches the
    user exactly as :func:`warn` would deliver it. Only the promoted exception is
    swallowed, and the same text is then logged at WARNING so a session running with
    warnings as errors still learns what failed. ``KeyboardInterrupt`` and
    ``SystemExit`` are not :class:`Exception` subclasses, so they keep propagating.

    :param message: Text shown to the user.
    :param stacklevel: Frames to skip so the warning points at the caller's caller.
    """
    try:
        warn(message, stacklevel=stacklevel + 1)
    except Exception:  # noqa: BLE001 - a filter promoted the warning; the message still has to land
        log.warning("%s", message)
