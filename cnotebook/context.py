"""Backward-compatible shim. The implementation now lives in cnotebook.core.context."""

from cnotebook.core.context import *  # noqa: F401,F403
from cnotebook.core.context import (  # noqa: F401
    DEFERRED,
    CNotebookContext,
    DeferredValue,
    RenderContext,
    _Deferred,
    cnotebook_context,
    pass_cnotebook_context,
    create_local_context,
    get_series_context,
)
