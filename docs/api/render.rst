render
======

.. automodule:: cnotebook.render
   :members:
   :undoc-members:
   :show-inheritance:

Rendering Functions
-------------------

The ``render`` module provides core functions for converting OpenEye molecules
to HTML representations.

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

Render a molecule with optional SMARTS highlighting.

.. code-block:: python

    from cnotebook.render import render_molecule

    # Basic rendering
    render_molecule(mol)

    # With SMARTS highlighting
    render_molecule(mol, smarts="c1ccccc1")
