cnotebook
=========

.. automodule:: cnotebook
   :members:
   :undoc-members:
   :show-inheritance:
   :exclude-members: __weakref__, C3D, MolGrid

Package Overview
----------------

The ``cnotebook`` package provides automatic molecule rendering in Jupyter and
Marimo notebooks. Simply importing the package registers formatters for OpenEye
molecule objects.

Usage
-----

.. code-block:: python

    import cnotebook
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    mol  # Automatically rendered as chemical structure

Lazy and Optional Exports
-------------------------

``C3D``, ``MolGrid``, ``molgrid``, ``BEST_FIT_ORIENTATION``, ``render_dataframe``
and ``render_polars_dataframe`` are resolved on first access (PEP 562), so
``import cnotebook`` never imports anywidget, pandas or polars. Each name stays
reachable as an attribute whether or not its backend is installed; a backend that
fails to import is reported once as a ``CNotebookWarning`` and the attribute
lookup then raises ``AttributeError``.

``render_dataframe`` and ``render_polars_dataframe`` are dropped from ``__all__``
when their backend is not installed, which keeps ``from cnotebook import *``
working in an environment without pandas or polars.

Module Attributes
-----------------

.. py:data:: cnotebook_context

   Global context variable for rendering configuration. Access the context using
   ``cnotebook_context.get()``.

Environment Detection
---------------------

Use the :func:`~cnotebook.get_env` function to retrieve environment information:

.. code-block:: python

    import cnotebook

    env = cnotebook.get_env()
    if env.pandas_available:
        print(f"Pandas {env.pandas_version} is available")
