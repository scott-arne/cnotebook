"""PEP 440 version comparison shared by the optional-backend guards.

The pandas, polars and marimo adapters each refuse to attach to a backend older
than their floor. They all decide that here so that one reading of PEP 440
ordering applies everywhere.
"""

from __future__ import annotations

import re

# The optional segments of a PEP 440 version. The epoch is matched so that it can be
# ignored: the guarded projects do not use one, and a project that starts using epochs
# only ever moves forward, which is the side of the comparison that already attaches.
_VERSION_RE = re.compile(
    r"""
    v?
    (?:\d+!)?                                                   # epoch, ignored
    (?P<release>\d+(?:\.\d+)*)
    (?P<pre>[-._]?(?:a|b|c|rc|alpha|beta|pre|preview)[-._]?\d*)?
    (?P<post>[-._]?(?:post|rev|r)[-._]?\d*|-\d+)?
    (?P<dev>[-._]?dev[-._]?\d*)?
    (?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?                         # local version
    $
    """,
    re.VERBOSE | re.IGNORECASE | re.ASCII,
)


def at_least(version: str, minimum: tuple[int, ...] | str) -> bool:
    """
    Check whether an installed version is *minimum* or later, in PEP 440 order.

    ``packaging`` is not a declared dependency of cnotebook, so a smaller parse of the
    same grammar stands in when it cannot be imported. The two agree on the spellings a
    release can take: ``0.4.0.post1``, ``0.4.0-1`` and ``0.4.0-r1`` are all after
    ``0.4.0``, while ``0.4.0rc1`` and ``0.4.0.dev1`` are before it.

    :param version: Installed version string.
    :param minimum: Release to compare against, as a tuple of numbers or as the
        dotted release string that spells the same tuple.
    :returns: ``True`` when *version* is that release or later.
    :raises ValueError: When either string cannot be read as a version.
    """
    floor = minimum if isinstance(minimum, tuple) else tuple(int(part) for part in minimum.split("."))
    try:
        # Deliberately optional: packaging is not a cnotebook dependency, and the branch
        # below is the whole point of the try. Do not turn this into a hard import.
        from packaging.version import Version
    except ImportError:
        match = _VERSION_RE.fullmatch(version.strip())
        if match is None:
            raise ValueError(f"cannot read a release number from {version!r}") from None
        release = tuple(int(part) for part in match.group("release").split("."))
        # 0.4 and 0.4.0 are the same release, so compare over a common length.
        width = max(len(release), len(floor))
        padded = release + (0,) * (width - len(release))
        floor_release = floor + (0,) * (width - len(floor))
        if padded != floor_release:
            return padded > floor_release
        # At the floor's own release: a pre-release comes before it, and so does a
        # development build, unless it is a development build of a post-release.
        return not (match.group("pre") or (match.group("dev") and not match.group("post")))
    # InvalidVersion is a ValueError, so a malformed version reaches the caller's handler.
    return Version(version) >= Version(".".join(map(str, floor)))
