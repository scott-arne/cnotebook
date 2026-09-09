"""Warning and error types shared across cnotebook."""

from __future__ import annotations

import warnings


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
