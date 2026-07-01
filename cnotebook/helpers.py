"""Backward-compatible shim. Implementation moved to cnotebook.core.helpers."""

from cnotebook.core.helpers import *  # noqa: F401,F403
from cnotebook.core.helpers import (  # noqa: F401
    HighlightColors,
    create_structure_highlighter,
    escape_brackets,
    escape_html,
    highlight_smarts,
    remove_omega_conformer_id,
)
