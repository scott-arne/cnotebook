"""Sphinx configuration for CNotebook documentation."""

import os
import re
import sys

from sphinx.ext.autodoc.mock import _MockObject

# Add project root to path for autodoc
sys.path.insert(0, os.path.abspath(".."))


def _package_version() -> str:
    """Read ``__version__`` out of the package source.

    The package cannot be imported here: ``conf.py`` runs before the autodoc mocks
    are installed, so importing it would require OpenEye. ``vrzn`` rewrites the
    single assignment this reads, which keeps the documented version in step with
    the release without a second string to bump.

    :returns: The version string declared in ``cnotebook/__init__.py``.
    :raises RuntimeError: When the assignment is missing.
    """
    source = os.path.join(os.path.abspath(".."), "cnotebook", "__init__.py")
    with open(source, encoding="utf-8") as handle:
        match = re.search(r"""^__version__\s*=\s*["']([^"']+)["']""", handle.read(), re.MULTILINE)
    if match is None:
        raise RuntimeError(f"No __version__ assignment found in {source}")
    return match.group(1)


# Project information
project = "CNotebook"
copyright = "2024, Scott Arne Johnson"
author = "Scott Arne Johnson"
release = _package_version()
version = release

# General configuration
extensions = [
    "sphinx_iframes",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
    "sphinx_rtd_theme",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "plans", "superpowers"]

# Napoleon settings for Google/NumPy style docstrings
napoleon_google_docstring = False
napoleon_numpy_docstring = False
napoleon_use_param = True
napoleon_use_rtype = True
napoleon_use_ivar = True

# Autodoc settings
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}
autodoc_typehints = "description"
# The docs build runs without OpenEye or the optional notebook/DataFrame libraries; autodoc imports
# cnotebook against these mocks. Keep the list in sync with the imports in the package.
autodoc_mock_imports = [
    "openeye", "openeye.oechem", "openeye.oedepict", "openeye.oegraphsim", "openeye.oegrapheme",
    "openeye.oeomega", "openeye.oegrid",
    "numpy", "pandas", "oepandas", "oepandas.pandas_extensions", "polars", "oepolars", "oepolars.extensions",
    "anywidget", "traitlets", "marimo", "IPython", "IPython.core.getipython", "IPython.display",
]


def _mock_union(self, other):
    """Return the left operand so ``X | Y`` over mocked names yields a mock.

    :param self: The mocked operand the union is built from.
    :param other: The other operand, which is a mock as well and carries no extra information.
    :returns: ``self``, which autodoc renders as the mocked name.
    """
    return self


# A mocked attribute is an instance, not a class, so a module-level ``X | Y`` type alias written
# over mocked names (cnotebook.core.helpers.HighlightColors) raises TypeError and autodoc then
# fails to import the whole package. Give the mock the union operators so such aliases evaluate.
_MockObject.__or__ = _mock_union
_MockObject.__ror__ = _mock_union

# Intersphinx mapping
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "pandas": ("https://pandas.pydata.org/docs/", None),
    "polars": ("https://pola-rs.github.io/polars/py-polars/html/", None),
}

# HTML output options
html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_theme_options = {
    "navigation_depth": 4,
    "collapse_navigation": False,
    "sticky_navigation": True,
}

# Source suffix
source_suffix = ".rst"

# Master document
master_doc = "index"

def setup(app):
    app.add_css_file('css/custom.css')
