C3D Module
==========

.. module:: cnotebook.c3d

Interactive 3D molecule viewer for Jupyter and Marimo notebooks.

C3D Class
---------

.. autoclass:: cnotebook.c3d.C3D
   :members:
   :undoc-members:
   :show-inheritance:

Live Widget Types
-----------------

``display()`` shows a live :class:`~cnotebook.c3d.widget.C3DWidget` unless static output
is requested, and ``C3D.widget`` returns it. The types below are importable by name from
``cnotebook.c3d`` (``from cnotebook.c3d import PickEvent``); they resolve lazily because
they need anywidget, which the static viewer does not.

.. autoclass:: cnotebook.c3d.widget.C3DWidget
   :members: submit, on_pick, request_screenshot, set_view, close
   :exclude-members: __init__

.. autoclass:: cnotebook.c3d.widget.CommandHandle
   :members: done, result, add_done_callback, wait
   :exclude-members: __init__

.. autoclass:: cnotebook.c3d.widget.CommandResult
   :exclude-members: __init__

.. autoclass:: cnotebook.c3d.widget.PickEvent
   :exclude-members: __init__

Conversion Utilities
--------------------

The converters that turn OpenEye objects into the viewer's payload live in
``cnotebook.core.convert``; ``cnotebook.c3d.convert`` re-exports them.

.. automodule:: cnotebook.core.convert
   :members:
   :undoc-members:
   :show-inheritance:
