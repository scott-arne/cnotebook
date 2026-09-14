core
====

``cnotebook.core`` is the backend-neutral layer: it imports only the OpenEye
toolkits and the Python standard library, and it holds the code the pandas,
polars and marimo adapters share. The two largest core modules have pages of
their own: :doc:`render` documents ``cnotebook.core.render`` and :doc:`context`
documents ``cnotebook.core.context``.

cnotebook.core.table
--------------------

Backend-neutral table rendering: cell tokens, row windows and the markup writer
used by any adapter without a native HTML writer.

.. automodule:: cnotebook.core.table
   :members:
   :undoc-members:
   :show-inheritance:

cnotebook.core.columnops
------------------------

The single implementation of the column operations (highlighting, alignment,
depiction resets) that every DataFrame accessor delegates to.

.. automodule:: cnotebook.core.columnops
   :members:
   :undoc-members:
   :show-inheritance:

cnotebook.core.formatters
-------------------------

Cell formatters shared by the pandas, polars and marimo adapters.

.. automodule:: cnotebook.core.formatters
   :members:
   :undoc-members:
   :show-inheritance:

cnotebook.core.errors
---------------------

The warning category and the error base class shared by every cnotebook message.
Filter the warnings with the standard ``warnings`` module:

.. code-block:: python

    import warnings
    from cnotebook.core.errors import CNotebookWarning

    warnings.simplefilter("ignore", CNotebookWarning)

.. automodule:: cnotebook.core.errors
   :members: CNotebookWarning, CNotebookError, warn
   :show-inheritance:

cnotebook.config
----------------

Configuration defaults: the TOML file, the environment variables and
:func:`~cnotebook.config.configure`. See :doc:`../configuration` for the file
format and the discovery order.

.. automodule:: cnotebook.config
   :members:
   :undoc-members:
   :show-inheritance:
