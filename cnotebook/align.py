"""Backward-compatible shim. Implementation moved to cnotebook.core.align."""

from cnotebook.core.align import *  # noqa: F401,F403
from cnotebook.core.align import (  # noqa: F401
    Aligner,
    OEFingerprintAligner,
    OEMCSSearchAligner,
    OESubSearchAligner,
    create_aligner,
    fingerprint_maker,
)
