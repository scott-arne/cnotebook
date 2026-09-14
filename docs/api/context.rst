context
=======

.. automodule:: cnotebook.core.context
   :members:
   :undoc-members:
   :show-inheritance:

CNotebookContext Class
----------------------

The ``CNotebookContext`` class manages global rendering settings for molecule
visualization. ``cnotebook.context`` re-exports every name on this page, so
``from cnotebook.context import render_options`` and
``from cnotebook.core.context import render_options`` are the same import.

Usage
-----

.. code-block:: python

    import cnotebook

    # Get the global context
    ctx = cnotebook.cnotebook_context.get()

    # Modify settings
    ctx.width = 300
    ctx.height = 300
    ctx.image_format = "svg"

    # Reset to defaults
    ctx.reset()

Configuration Options
---------------------

Image Dimensions
^^^^^^^^^^^^^^^^

- ``width``: Image width in pixels; ``0`` lets the structure scale decide (default: 0)
- ``height``: Image height in pixels; ``0`` lets the structure scale decide (default: 0)
- ``min_width``: Minimum image width enforced under ``auto_scale`` (default: 200.0)
- ``min_height``: Minimum image height enforced under ``auto_scale`` (default: 200.0)
- ``max_width``: Maximum allowed width, or ``None`` for no limit (default: None)
- ``max_height``: Maximum allowed height, or ``None`` for no limit (default: None)

Output Format
^^^^^^^^^^^^^

- ``image_format``: Output format, either "png" or "svg" (default: "png")
- ``device_pixel_ratio``: Raster oversampling factor for PNG output (default: 2.0)

Scaling
^^^^^^^

- ``structure_scale``: Multiplier on OpenEye's default structure scale (default: 0.6)
- ``auto_scale``: Size the structure to fill the canvas instead (default: False)
- ``atom_label_font_scale``: Scale factor for atom labels (default: 1.15)
- ``title_font_scale``: Scale factor for the title font (default: 1.0)

The full table of options, including the ones not listed here, is in
:doc:`../rendering`.

Deferring to the Global Context
-------------------------------

Every option of a local context can hold the sentinel below instead of a value, which is
why the constructor parameters above are typed ``float | _Deferred``. Reading a deferred
option returns the global context's value at that moment.
:func:`~cnotebook.core.context.create_local_context` leaves every option it is not given
deferred, and :meth:`CNotebookContext.copy` preserves deferral.

.. py:data:: DEFERRED

   Sentinel meaning "take this option from the global context".
