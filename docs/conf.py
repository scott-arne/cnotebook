"""Sphinx configuration for CNotebook documentation."""

import os
import sys

# Add project root to path for autodoc
sys.path.insert(0, os.path.abspath(".."))

# Project information
project = "CNotebook"
copyright = "2024, Scott Arne Johnson"
author = "Scott Arne Johnson"
release = "2.0.0"

# General configuration
extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinx.ext.autosummary",
    "sphinx_rtd_theme",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "plans"]

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
# Note: OpenEye libraries (openeye, oechem, oedepict, oepandas, oepolars) are NOT mocked
# so that autodoc can extract docstrings. Ensure OE_LICENSE is set when building docs.
# IPython is mocked to avoid TerminalIPythonApp issues during doc builds.
autodoc_mock_imports = [
    "marimo",
    "anywidget",
    "traitlets",
    "IPython",
]

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