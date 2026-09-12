"""C3D: 3D molecule viewer for Jupyter and Marimo notebooks."""

from typing import TYPE_CHECKING, Any

from cnotebook.c3d.c3d import C3D

if TYPE_CHECKING:
    # Redundant aliases: these names are re-exported for type checkers, which cannot
    # see the __getattr__ below, but they stay out of __all__ (see the comment there).
    from cnotebook.c3d.widget import C3DWidget as C3DWidget
    from cnotebook.c3d.widget import CommandHandle as CommandHandle
    from cnotebook.c3d.widget import CommandResult as CommandResult
    from cnotebook.c3d.widget import PickEvent as PickEvent

# The live-widget names below are importable from this package by name, but they are
# deliberately absent from __all__: a star import would resolve every name in it, which
# would import anywidget and defeat the point of resolving them lazily.
__all__ = ["C3D"]

# The live-widget names live in a module that imports anywidget, which the static
# viewer does not need, so they are resolved only when a caller asks for one.
_WIDGET_EXPORTS = frozenset({"C3DWidget", "CommandHandle", "CommandResult", "PickEvent"})


def __getattr__(name: str) -> Any:
    """Import the live-widget types on first use (PEP 562).

    :param name: Attribute requested on this package.
    :returns: The requested widget type.
    :raises AttributeError: If *name* is not exported here.
    :raises ImportError: If the widget types are requested without anywidget installed.
    """
    if name in _WIDGET_EXPORTS:
        from cnotebook.c3d import widget

        return getattr(widget, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
