"""Tests for the packaging metadata that CI and the release read out of ``pyproject.toml``."""

import glob
import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_metadata():
    """The supported Python versions, the extras and their floors, and the package data all agree."""
    data = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text())
    project = data["project"]
    classifiers = project["classifiers"]
    assert "Programming Language :: Python :: 3.10" not in classifiers
    for minor in ("3.11", "3.12", "3.13"):
        assert f"Programming Language :: Python :: {minor}" in classifiers
    extras = project["optional-dependencies"]
    assert not any(dep.startswith("jinja2") for dep in extras["notebook"])
    assert any(dep.startswith("anywidget>=0.9") for dep in extras["notebook"])
    assert any(dep.startswith("marimo>=0.13") for dep in extras["notebook"])
    assert any(dep.startswith("oepolars>=0.4") for dep in extras["polars"])
    assert any(dep.startswith("polars>=1.44") for dep in extras["polars"])
    assert any(dep.startswith("oepandas>=3.3") for dep in extras["pandas"])
    for dep in ("ruff", "mypy", "invoke", "build", "twine", "pytest"):
        assert any(d.startswith(dep) for d in extras["dev"])
    for pattern in data["tool"]["setuptools"]["package-data"]["cnotebook"]:
        if "*" in pattern:
            assert glob.glob(str(_REPO_ROOT / "cnotebook" / pattern)), pattern
