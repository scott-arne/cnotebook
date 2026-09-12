"""C3D: 3D molecule viewer for Jupyter and Marimo notebooks."""

from typing import TYPE_CHECKING, Any

from cnotebook.c3d.c3d import C3D

if TYPE_CHECKING:
    from cnotebook.c3d.widget import C3DWidget, CommandHandle, CommandResult, PickEvent

__all__ = ["C3D", "C3DWidget", "CommandHandle", "CommandResult", "PickEvent"]

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
