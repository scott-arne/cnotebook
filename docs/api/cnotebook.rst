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

Use the ``get_env()`` function to retrieve environment information:

.. code-block:: python

    import cnotebook

    env = cnotebook.get_env()
    if env.pandas_available:
        print(f"Pandas {env.pandas_version} is available")

.. py:function:: get_env() -> CNotebookEnvInfo

   Returns a singleton instance containing information about available
   backends and environments. The environment is detected once at module
   load time and the same object is returned on subsequent calls.

.. py:class:: CNotebookEnvInfo

   Environment information for CNotebook. All properties are read-only.

   .. py:attribute:: pandas_available
      :type: bool

      Whether Pandas and OEPandas are available.

   .. py:attribute:: pandas_version
      :type: str

      Pandas version string, or empty string if not available.

   .. py:attribute:: polars_available
      :type: bool

      Whether Polars and OEPolars are available.

   .. py:attribute:: polars_version
      :type: str

      Polars version string, or empty string if not available.

   .. py:attribute:: ipython_available
      :type: bool

      Whether IPython is available and active.

   .. py:attribute:: ipython_version
      :type: str

      IPython version string, or empty string if not available.

   .. py:attribute:: marimo_available
      :type: bool

      Whether Marimo is available and running in notebook mode.

   .. py:attribute:: marimo_version
      :type: str

      Marimo version string, or empty string if not available.

   .. py:attribute:: molgrid_available
      :type: bool

      Whether MolGrid is available (requires anywidget).

   .. py:attribute:: is_jupyter_notebook
      :type: bool

      Whether running in a Jupyter notebook environment.

   .. py:attribute:: is_marimo_notebook
      :type: bool

      Whether running in a Marimo notebook environment.
