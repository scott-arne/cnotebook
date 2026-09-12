import logging

import pytest

from cnotebook.core.errors import CNotebookError, CNotebookWarning, warn


def test_warn_emits_cnotebook_warning():
    with pytest.warns(CNotebookWarning, match="hello"):
        warn("hello")


def test_error_and_warning_hierarchy():
    assert issubclass(CNotebookError, Exception)
    assert issubclass(CNotebookWarning, UserWarning)


def test_enable_debugging_is_idempotent():
    import cnotebook

    log = logging.getLogger("cnotebook")
    original_level = log.level

    try:
        cnotebook.enable_debugging()
        cnotebook.enable_debugging()
        debug_handlers = [h for h in log.handlers if getattr(h, "_cnotebook_debug", False)]
        assert len(debug_handlers) == 1
        assert log.level == logging.DEBUG
    finally:
        # Restore original state
        log.setLevel(original_level)
        for handler in log.handlers[:]:
            if getattr(handler, "_cnotebook_debug", False):
                log.removeHandler(handler)
