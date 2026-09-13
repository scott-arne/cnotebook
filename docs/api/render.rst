render
======

.. automodule:: cnotebook.core.render
   :members:
   :undoc-members:
   :show-inheritance:

Rendering Functions
-------------------

The ``render`` module provides core functions for converting OpenEye molecules
to HTML representations. ``cnotebook.render`` re-exports every name on this
page, so ``from cnotebook.render import render_molecule`` and
``from cnotebook.core.render import render_molecule`` are the same import.

Key Functions
-------------

oemol_to_html
^^^^^^^^^^^^^

Convert an OpenEye molecule to an HTML representation (PNG or SVG image).

.. code-block:: python

    from cnotebook.render import oemol_to_html
    from cnotebook.context import CNotebookContext

    ctx = CNotebookContext(width=200, height=200, image_format="svg")
    html = oemol_to_html(mol, ctx=ctx)

render_molecule
^^^^^^^^^^^^^^^

Render a molecule to image bytes. Keyword arguments beyond ``format`` are
:class:`~cnotebook.core.context.CNotebookContext` options applied to this call
only; an unknown name raises ``TypeError``.

.. code-block:: python

    from cnotebook.render import render_molecule

    # Basic rendering
    png = render_molecule(mol)

    # With per-call rendering options
    svg = render_molecule(mol, format="svg", width=400, height=400)
