"""Backend-neutral column operations shared by the pandas and polars adapters.

This module starts with the report dataclasses; Task 11 adds the operations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cnotebook.core.render import Depiction


@dataclass
class AlignmentReport:
    """Outcome of aligning one column of molecules.

    :param total: Number of rows visited.
    :param aligned: Rows whose copy was aligned.
    :param skipped_none: Rows holding ``None``.
    :param skipped_invalid: Rows holding invalid molecules.
    :param failed: Row positions where the aligner returned ``False``.
    """

    total: int = 0
    aligned: int = 0
    skipped_none: int = 0
    skipped_invalid: int = 0
    failed: list[int] = field(default_factory=list)


@dataclass
class SimilarityResult:
    """Outcome of a fingerprint-similarity computation over one column.

    :param tanimotos: Tanimoto per row, ``None`` for skipped rows.
    :param reference: Reference depictions per row, ``None`` for skipped rows.
    :param target: Target depictions per row, ``None`` for skipped rows.
    """

    tanimotos: list[float | None]
    reference: list[Depiction | None]
    target: list[Depiction | None]
