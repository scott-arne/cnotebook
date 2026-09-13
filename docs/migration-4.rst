Migrating to CNotebook 4.0
==========================

Each item carries the identifier used in the changelog.

Display and output
------------------

- **M01** MolGrid no longer displays from its constructor: call ``grid.display()``.
- **M02** C3D and MolGrid default to widget output: use ``display(static=True)``, ``to_html()``, ``save()`` or ``configure(display_mode="static")`` for self-contained HTML.
- **M03** ``cnotebook.display(df)`` honours column settings; pass ``ctx=`` to override every column.
- **M04** DataFrame output truncates like pandas and polars; ``render_dataframe(df, max_rows=0)`` renders all rows.
- **M22** Live outputs are ``MolGridWidget`` and ``C3DWidget`` instances rather than iframe HTML.

Molecules and depictions
------------------------

- **M05** Displaying a molecule no longer mutates it; 3D coordinates and hydrogens survive display.
- **M06** pandas ``align_depictions`` and ``recalculate_depiction_coordinates`` replace column molecules with copies; keep your own references if you relied on in-place mutation.
- **M07** ``series.chem.align_depictions`` returns an ``AlignmentReport`` (previously ``None``).
- **M15** ``oedu_to_disp`` returns a ``Depiction`` (``.display`` and ``.mol``) instead of a tuple.
- **M17** The DataFrame ``recalculate_depiction_coordinates`` keyword is ``add_depiction_hydrogens``.

DataFrames
----------

- **M08** polars accessor methods return new frames: ``df = df.chem.highlight("mol", "c1ccccc1")``.
- **M09** polars support requires ``oepolars>=0.4.0``.
- **M10** ``series.chem.molgrid(frame=df)`` replaces the automatic DataFrame discovery. This is the pandas
  form; the polars series accessor has no ``frame`` parameter, so use ``df.chem.molgrid("mol")`` to include
  the frame's other columns.
- **M16** ``render_dataframe`` ignores ``escape=`` (with a warning) and merges caller formatters.
- **M23** polars frames whose molecule columns carry different render tokens cannot be concatenated; call ``df.chem.reset_depictions()`` on both frames before ``pl.concat``/``vstack``, or apply settings after concatenating.

Rendering context
-----------------

- **M11** ``structure_scale <= 0`` raises ``ValueError``; use ``auto_scale=True``.
- **M12** Invalid context options raise ``ValueError`` at assignment time.
- **M21** PNG output is rasterised at ``device_pixel_ratio`` 2; set it to ``1.0`` to restore the old size.

Warnings, logging and imports
-----------------------------

- **M13** User-facing warnings are ``CNotebookWarning``; filter them with the ``warnings`` module.
  Import the class from ``cnotebook.core.errors``; it is not an attribute of the top-level package.
- **M14** No stream handler is attached to the ``cnotebook`` logger; call ``cnotebook.enable_debugging()`` for console logging.
- **M18** Integrations attach through post-import hooks; import order no longer matters; ``CNOTEBOOK_NO_IMPORT_HOOKS=1`` opts out.
  The hooks fire on ``oepandas``, ``oepolars`` and ``marimo``, so ``import pandas`` alone does not attach ``df.chem``.
- **M19** ``get_env()`` reports the current state on each call.
- **M20** Unavailable optional exports raise ``AttributeError``, so ``hasattr`` works.

Concatenating polars frames
---------------------------

M23 is the one that most often shows up as an error rather than a difference in output.
A molecule column's polars dtype carries a token identifying its render settings, so two
frames whose molecule columns were rendered with different settings have different dtypes
and ``pl.concat`` raises ``SchemaError``:

.. code-block:: text

    polars.exceptions.SchemaError: type Extension(PyExtensionType(name='molecule'), Object)
    is incompatible with expected type Extension(PyExtensionType(name='molecule',
    metadata='4731ee...'), Object)

Clear the settings on both sides first:

.. code-block:: python

    combined = pl.concat([
        left.chem.reset_depictions("mol"),
        right.chem.reset_depictions("mol"),
    ])
    combined = combined.chem.set_render_options("mol", width=300)

Applying the render options after the concatenation, as above, keeps one token across the
whole result.
