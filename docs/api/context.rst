context
=======

.. automodule:: cnotebook.context
   :members:
   :undoc-members:
   :show-inheritance:

CNotebookContext Class
----------------------

The ``CNotebookContext`` class manages global rendering settings for molecule
visualization.

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

- ``width``: Default image width in pixels (default: 250)
- ``height``: Default image height in pixels (default: 250)
- ``max_width``: Maximum allowed width (default: 1200)
- ``max_height``: Maximum allowed height (default: 800)

Output Format
^^^^^^^^^^^^^

- ``image_format``: Output format, either "png" or "svg" (default: "png")

Scaling
^^^^^^^

- ``scale``: Scaling factor for depictions (default: 1.0)
