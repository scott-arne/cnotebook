"""Tests for the PEP 440 guard shared by the optional-backend adapters."""

import sys

import pytest

from cnotebook.core.versions import at_least

# The same cases tests/test_polars_ext.py pins for the tuple floor. A floor may be spelled
# either way - polars and marimo pass a tuple, pandas passes the dotted string - so both
# spellings have to reach the same verdict, with and without ``packaging`` installed.
VERSION_CASES = [
    ("0.4.0", True),
    ("0.3.9", False),
    ("0.4.0.dev1", False),
    ("0.4.0rc1", False),
    ("0.4.0.post1", True),
    ("0.4.0-1", True),
    ("0.4.0post1", True),
    ("0.4.0-r1", True),
    ("0.4.0.post1.dev1", True),
    ("0.4.0+corp", True),
    ("1!0.4.0", True),
    # An epoch outranks the release, and an explicit epoch 0 is the same as none at all.
    # 1!0.1 and 1!0.3.0 are the discriminating pair: their releases are below the floor.
    ("1!0.1", True),
    ("1!0.3.0", True),
    ("0!0.3.0", False),
    ("0!0.4.0", True),
    # Release segments shorter or longer than the floor, and the v prefix
    ("0.4", True),
    ("1", True),
    ("v0.4.0", True),
]


@pytest.mark.parametrize("without_packaging", [False, True], ids=["packaging", "fallback"])
@pytest.mark.parametrize(("version", "at_or_after"), VERSION_CASES)
def test_string_floor_matches_the_tuple_floor(monkeypatch, version, at_or_after, without_packaging):
    """A dotted-string floor orders versions exactly as the equivalent tuple floor does."""
    if without_packaging:
        # A None entry in sys.modules makes the import of packaging fail
        monkeypatch.setitem(sys.modules, "packaging.version", None)

    assert at_least(version, "0.4.0") is at_or_after
    assert at_least(version, (0, 4, 0)) is at_or_after


@pytest.mark.parametrize("without_packaging", [False, True], ids=["packaging", "fallback"])
def test_unreadable_version_is_rejected_for_either_floor(monkeypatch, without_packaging):
    """An unreadable version raises for both floor spellings, so callers handle one error."""
    if without_packaging:
        monkeypatch.setitem(sys.modules, "packaging.version", None)

    with pytest.raises(ValueError):
        at_least("not-a-version", "0.4.0")
    with pytest.raises(ValueError):
        at_least("not-a-version", (0, 4, 0))
