"""Tests for the packaging metadata that CI and the release read out of ``pyproject.toml``.

CI installs the extras by name and builds its matrix from the classifiers, so the assertions here
are exact rather than existence checks: an entry that is dropped, added or re-floored has to fail
in this suite rather than in a job that only runs on a tag.
"""

import glob
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

_REPO_ROOT = Path(__file__).resolve().parent.parent

_REQUIRES_PYTHON = ">=3.11"

# Every ``Programming Language :: Python`` classifier the project claims, checked as a set so a
# version advertised on PyPI but absent from ``requires-python`` and the CI matrix cannot slip in.
_PYTHON_CLASSIFIERS = {
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Programming Language :: Python :: 3.13",
    "Programming Language :: Python :: 3 :: Only",
}

_PANDAS_EXTRA = {"pandas": ">=2.2.0", "oepandas": ">=3.3.0"}
_POLARS_EXTRA = {"polars": ">=1.44.1", "oepolars": ">=0.4.0"}

_EXTRAS = {
    "pandas": _PANDAS_EXTRA,
    "polars": _POLARS_EXTRA,
    # The dataframes extra exists to install both adapters at once, so it is their merge and
    # nothing else; a floor that drifts from the single-library extra is the failure to catch.
    "dataframes": _PANDAS_EXTRA | _POLARS_EXTRA,
    "notebook": {"anywidget": ">=0.9.0", "ipython": ">=8.0.0", "marimo": ">=0.13.0"},
    "test": {"pytest": "", "pytest-cov": ""},
    "dev": {"invoke": "", "build": "", "twine": "", "pytest": "", "ruff": "~=0.16.6", "mypy": "~=2.3.1"},
}

_PACKAGE_DATA = ["py.typed", "grid/static/*", "c3d/static/*", "core/static/*"]


def _pyproject():
    """Parse the project's packaging metadata.

    :returns: The contents of ``pyproject.toml``, read from the repository root rather than from
        the working directory, so the suite gives the same answer wherever it is launched.
    """
    return tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())


def _requirements(specifications):
    """Summarise one extra's dependency list.

    :param specifications: Requirement strings of a single extra.
    :returns: Canonical distribution name mapped to its version specifier, so the comparison sees
        the whole constraint -- an added ceiling, or one contradicting the floor -- rather than a
        prefix of the name.
    """
    return {canonicalize_name(req.name): str(req.specifier) for req in map(Requirement, specifications)}


def test_pyproject_metadata():
    """The interpreter floor and the advertised Python versions are the ones the release supports."""
    project = _pyproject()["project"]
    assert project["requires-python"] == _REQUIRES_PYTHON
    advertised = {c for c in project["classifiers"] if c.startswith("Programming Language :: Python ::")}
    assert advertised == _PYTHON_CLASSIFIERS


def test_optional_dependencies():
    """Each extra holds exactly the distributions, and the floors, that CI and the release install."""
    extras = _pyproject()["project"]["optional-dependencies"]
    assert set(extras) == set(_EXTRAS)
    for name, expected in _EXTRAS.items():
        assert _requirements(extras[name]) == expected, name


def test_package_data_ships_the_static_assets():
    """The declared package data is the expected list, and every entry still resolves to a file."""
    patterns = _pyproject()["tool"]["setuptools"]["package-data"]["cnotebook"]
    assert patterns == _PACKAGE_DATA
    for pattern in patterns:
        if "*" in pattern:
            assert glob.glob(str(_REPO_ROOT / "cnotebook" / pattern)), pattern
        else:
            assert (_REPO_ROOT / "cnotebook" / pattern).is_file(), pattern
