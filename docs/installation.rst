Installation
============

Requirements
------------

CNotebook requires:

- Python 3.11 or later
- OpenEye Toolkits (2025.2.1 or later) with a valid license

Optional dependencies for DataFrame support:

- **Pandas support**: ``pandas>=2.2.2`` and ``oepandas>=3.3.0``
- **Polars support**: ``polars>=1.44.1`` and ``oepolars>=0.4.0``

The pandas floor is ``2.2.2`` rather than ``2.2.0``: pandas 2.2.0 and 2.2.1 declare
``numpy<2`` while ``oepandas>=3.3.0`` declares ``numpy>=2.0.0``, so no environment can
hold both halves of the extra with an older pandas.

Optional dependencies for notebook widgets (the ``notebook`` extra):

- ``anywidget>=0.9.0``
- ``ipython>=8.0.0``
- ``marimo>=0.13.0``

Installing CNotebook
--------------------

Install from PyPI:

.. code-block:: bash

    pip install cnotebook

Or install from source:

.. code-block:: bash

    git clone https://github.com/your-repo/cnotebook.git
    cd cnotebook
    pip install -e .

Installing Optional Dependencies
--------------------------------

For Pandas DataFrame support:

.. code-block:: bash

    pip install "cnotebook[pandas]"

For Polars DataFrame support:

.. code-block:: bash

    pip install "cnotebook[polars]"

To install both DataFrame backends:

.. code-block:: bash

    pip install "cnotebook[dataframes]"

For the interactive widgets (C3D and MolGrid in a notebook):

.. code-block:: bash

    pip install "cnotebook[notebook]"

CNotebook will automatically detect which backends are available and use them
accordingly.

OpenEye Toolkits License
------------------------

CNotebook requires a valid OpenEye Toolkits license (http://eyesopen.com/). Ensure your
license file is properly configured before using CNotebook. Refer to the OpenEye
documentation for license configuration details. Note that OpenEye offers free toolit
licenses to academic institutions.

Verifying Installation
----------------------

To verify your installation is working correctly:

.. code-block:: python

    import cnotebook
    from openeye import oechem

    # Check available backends
    env = cnotebook.get_env()
    print(f"Pandas available: {env.pandas_available} ({env.pandas_version})")
    print(f"Polars available: {env.polars_available} ({env.polars_version})")
    print(f"IPython available: {env.ipython_available} ({env.ipython_version})")
    print(f"Marimo available: {env.marimo_available} ({env.marimo_version})")
    print(f"MolGrid available: {env.molgrid_available}")


You should see something similar, depending on your environment and the
notebook that you are using:

.. code-block:: text

    Pandas available: True (3.0.0)
    Polars available: True (1.37.1)
    IPython available: True (9.9.0)
    Marimo available: False ()
    MolGrid available: True
