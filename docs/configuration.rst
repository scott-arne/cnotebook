Configuration
=============

CNotebook reads a TOML configuration file once, when the package is imported, and
applies it to the global rendering context and to the defaults of ``C3D`` and
``MolGrid``. Nothing has to be configured: every key has a default, and a session
that never writes a file behaves exactly as the tables below describe.

:doc:`advanced_rendering` shows the same file in context alongside the runtime
equivalents.

Where the file is read from
---------------------------

The first of these that applies wins:

1. ``$CNOTEBOOK_CONFIG``, if it is set. The path is used as given (``~`` expanded);
   a missing file there is reported as a ``CNotebookWarning`` rather than silently
   falling through to the next candidate.
2. ``$XDG_CONFIG_HOME/cnotebook/config.toml``, if ``XDG_CONFIG_HOME`` is set and the
   file exists.
3. ``~/.config/cnotebook/config.toml``, if it exists.

``CNOTEBOOK_DISPLAY_MODE`` is applied after the file and overrides ``[display] mode``.
A value that is neither ``widget`` nor ``static`` produces a ``CNotebookWarning`` and
``widget`` is used.

An unknown section, an unknown key, a key of the wrong type and a value outside its
allowed range each produce a ``CNotebookWarning`` and are ignored; the rest of the file
still applies. A file that cannot be read or parsed produces one warning and is skipped
entirely.

File format
-----------

.. code-block:: toml

    [display]
    mode = "widget"        # or "static"

    [render]
    image_format = "svg"
    structure_scale = 0.8

    [c3d]
    width = 800
    theme = "auto"

    [molgrid]
    n_items_per_page = 24
    image_format = "svg"
    theme = "auto"

Keys
----

``[display]``
^^^^^^^^^^^^^

+----------------------+---------------------------+-------------+------------------------------------------------+
| Key                  | Type                      | Default     | Meaning                                        |
+======================+===========================+=============+================================================+
| ``mode``             | ``"widget" | "static"``   | ``"widget"``| Whether C3D and MolGrid produce a live widget  |
|                      |                           |             | or self-contained HTML.                        |
+----------------------+---------------------------+-------------+------------------------------------------------+

``[c3d]``
^^^^^^^^^

+----------------------+---------------------------------+-----------+------------------------------------------+
| Key                  | Type                            | Default   | Meaning                                  |
+======================+=================================+===========+==========================================+
| ``width``            | ``int`` > 0                     | ``800``   | Default viewer width in pixels.          |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``height``           | ``int`` > 0 or ``None``         | ``None``  | Default viewer height; ``None`` lets the |
|                      |                                 |           | viewer choose its own aspect ratio.      |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``theme``            | ``"auto" | "light" | "dark"``   | ``"auto"``| Viewer colour theme; ``auto`` follows    |
|                      |                                 |           | the notebook.                            |
+----------------------+---------------------------------+-----------+------------------------------------------+

``[molgrid]``
^^^^^^^^^^^^^

+----------------------+---------------------------------+-----------+------------------------------------------+
| Key                  | Type                            | Default   | Meaning                                  |
+======================+=================================+===========+==========================================+
| ``n_items_per_page`` | ``int`` > 0                     | ``24``    | Cells shown on one page of the grid.     |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``image_format``     | ``"svg" | "png"``               | ``"svg"`` | Format of the depiction in each cell.    |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``theme``            | ``"auto" | "light" | "dark"``   | ``"auto"``| Grid colour theme; ``auto`` follows the  |
|                      |                                 |           | notebook.                                |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``width``            | ``int`` > 0                     | ``260``   | Cell width in pixels.                    |
+----------------------+---------------------------------+-----------+------------------------------------------+
| ``height``           | ``int`` > 0                     | ``240``   | Cell height in pixels.                   |
+----------------------+---------------------------------+-----------+------------------------------------------+

``[render]``
^^^^^^^^^^^^

``[render]`` accepts any writable :class:`~cnotebook.core.context.CNotebookContext`
option by name and applies it to the global context at import. The option names,
types and defaults are the table in :doc:`rendering`; the validation is the context's
own, so a value the context rejects is reported as a ``CNotebookWarning`` and skipped.

``callbacks`` is the one exception: TOML cannot express a callable, so a
``render.callbacks`` key in the file is rejected with a warning whatever its value. Set
callbacks on the context in Python, or pass them to :func:`cnotebook.configure`.

Changing settings at runtime
----------------------------

:func:`cnotebook.configure` changes the same settings without a file. Render options
are applied to the global context immediately; ``c3d`` and ``molgrid`` options become
the defaults for objects created afterwards, and objects that already exist are
unaffected.

.. code-block:: python

    import cnotebook

    cnotebook.configure(
        display_mode="static",
        c3d={"width": 640},
        molgrid={"n_items_per_page": 12},
        image_format="svg",
    )

``configure`` validates everything before it applies anything: an unknown key raises
``KeyError`` and an unacceptable value raises ``ValueError``, and in both cases no
setting has changed. This is the difference from the configuration file, which warns
and carries on.

:func:`cnotebook.get_config` returns the effective configuration as a ``Config``
dataclass with the ``render``, ``display_mode``, ``c3d`` and ``molgrid`` fields.

.. code-block:: python

    import cnotebook

    cfg = cnotebook.get_config()
    print(cfg.display_mode, cfg.molgrid["n_items_per_page"])

To apply a rendering option to one block only rather than to the whole session, use
``render_options``; see :ref:`temporary-options`.
