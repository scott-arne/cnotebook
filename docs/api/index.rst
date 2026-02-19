API Reference
=============

This section provides detailed API documentation for all CNotebook modules.

.. toctree::
   :maxdepth: 2

   cnotebook
   molgrid
   c3d
   context
   render
   pandas_ext
   polars_ext

Module Overview
---------------

Core Modules
^^^^^^^^^^^^

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Module
     - Description
   * - :doc:`cnotebook`
     - Main package with automatic rendering setup
   * - :doc:`context`
     - Global rendering context and configuration
   * - :doc:`render`
     - Core rendering functions for molecules

Visualization
^^^^^^^^^^^^^

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Module
     - Description
   * - :doc:`molgrid`
     - Interactive molecule grid visualization
   * - :doc:`c3d`
     - Interactive 3D molecule viewer (3Dmol.js)

DataFrame Extensions
^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 30 70
   :header-rows: 1

   * - Module
     - Description
   * - :doc:`pandas_ext`
     - Pandas DataFrame integration
   * - :doc:`polars_ext`
     - Polars DataFrame integration
