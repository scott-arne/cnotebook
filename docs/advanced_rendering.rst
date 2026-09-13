Advanced Rendering
==================

Configuration file
------------------

At import CNotebook reads ``$CNOTEBOOK_CONFIG`` if it is set, and otherwise the single
path ``<root>/cnotebook/config.toml``, where ``<root>`` is ``$XDG_CONFIG_HOME`` when that
variable is set and ``~/.config`` when it is not. Setting ``XDG_CONFIG_HOME`` therefore
takes ``~/.config`` out of play entirely:

.. code-block:: toml

    [render]
    image_format = "svg"
    structure_scale = 0.8

    [display]
    mode = "widget"        # or "static"

    [c3d]
    width = 800
    theme = "auto"

    [molgrid]
    n_items_per_page = 24
    image_format = "svg"
    theme = "auto"

Unknown keys and invalid values produce a ``CNotebookWarning`` and are ignored.
``CNOTEBOOK_DISPLAY_MODE`` overrides the display mode.
``cnotebook.configure(display_mode="static", c3d={"width": 640}, image_format="svg")``
changes the same settings at runtime for objects created afterwards. The full key table
is in :doc:`configuration`.

Temporary options
-----------------

.. code-block:: python

    from cnotebook import display
    from cnotebook.context import render_options

    with render_options(width=300, height=300, auto_scale=True):
        display(mol)

``render_options`` is exported from ``cnotebook.context`` (and from
``cnotebook.core.context``); it is not an attribute of the top-level ``cnotebook``
package.

HiDPI output
------------

PNG images are rasterised at ``device_pixel_ratio`` (default 2) times their CSS size. Set
``cnotebook.cnotebook_context.get().device_pixel_ratio = 1.0`` to restore 1:1 rasters.

Headless rendering
------------------

.. code-block:: python

    from cnotebook import render_molecule, save_image

    png = render_molecule(mol, format="png", width=400)
    save_image(mol, "mol.svg")

Import hooks
------------

Importing ``cnotebook`` imports none of pandas, polars or marimo. Accessor methods attach the moment
``oepandas``, ``oepolars`` or ``marimo`` is imported, in any order. Set ``CNOTEBOOK_NO_IMPORT_HOOKS=1`` to
disable the import hook; integrations then attach only for libraries already imported when cnotebook loads.

The accessors come from ``oepandas`` and ``oepolars``, not from ``pandas`` and ``polars``:
``import pandas`` alone leaves ``df.chem`` unattached, and ``import oepandas`` attaches it.

Display modes
-------------

C3D and MolGrid show live widgets by default (small notebook outputs, atom picks, selections). Static
self-contained HTML is available through ``display(static=True)``, ``to_html()`` and ``save(path)``, or by
setting the display mode to ``"static"``. Live outputs need a running kernel and do not appear in static
renders such as GitHub's notebook preview; saving JupyterLab widget state re-embeds the viewer assets.

Warnings and logging
--------------------

Every user-facing warning is a ``CNotebookWarning`` from :mod:`cnotebook.core.errors`,
emitted with ``warnings.warn``, so the standard library filters control them. The
``cnotebook`` logger gets no stream handler at import; ``cnotebook.enable_debugging()``
attaches one.
