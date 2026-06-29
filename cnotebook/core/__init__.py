"""Dependency-light rendering engine shared by cnotebook and oefastapi.

Imports here require only the OpenEye Toolkits and the standard library.
"""

from cnotebook.core.context import CNotebookContext, RenderContext

__all__ = ["CNotebookContext", "RenderContext"]
