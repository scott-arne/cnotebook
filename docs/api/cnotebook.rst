cnotebook
=========

.. automodule:: cnotebook
   :members:
   :undoc-members:
   :show-inheritance:

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
