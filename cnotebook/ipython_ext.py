"""IPython formatter registration for bare OpenEye objects and, by name, for DataFrames."""

import logging
from typing import Any

from openeye import oechem, oedepict

from .core.render import oedisp_to_html, oedu_to_html, oeimage_to_html, oemol_to_html

try:
    from IPython.core.getipython import get_ipython as _get_ipython
except ModuleNotFoundError:  # IPython is optional
    _get_ipython = None  # type: ignore[assignment]

log = logging.getLogger("cnotebook")

# IPython matches a deferred printer on the class's ``__module__`` and ``__name__``, and both
# libraries have moved the module their DataFrame reports: pandas 3 says "pandas" where
# pandas 2 said "pandas.core.frame". Registering every name a supported release uses costs an
# inert dict entry for the ones that never match, and is what keeps the match working across
# the whole supported range without importing either library to ask.
_PANDAS_DATAFRAME_NAMES = (("pandas", "DataFrame"), ("pandas.core.frame", "DataFrame"))
_POLARS_DATAFRAME_NAMES = (("polars", "DataFrame"), ("polars.dataframe.frame", "DataFrame"))


def _html_formatter() -> Any:
    """Return the active shell's ``text/html`` formatter.

    :returns: The formatter, or ``None`` when no IPython shell with a display formatter
        is running.
    """
    shell = _get_ipython() if _get_ipython is not None else None
    if shell is None or shell.display_formatter is None:
        return None
    # pyright reads the traitlets descriptor as ``object``, so the guard above cannot
    # teach it what the attribute holds.
    return shell.display_formatter.formatters["text/html"]  # pyright: ignore[reportAttributeAccessIssue]


def register_ipython_formatters() -> None:
    """Register HTML formatters for the OpenEye types cnotebook can draw.

    Calls are idempotent: a type someone else has already claimed is left alone.
    """
    html_formatter = _html_formatter()
    if html_formatter is None:
        log.debug("[cnotebook] no IPython shell; formatters not registered")
        return
    for typ, func in ((oechem.OEMolBase, oemol_to_html), (oedepict.OE2DMolDisplay, oedisp_to_html),
                      (oechem.OEDesignUnit, oedu_to_html), (oedepict.OEImage, oeimage_to_html)):
        try:
            # lookup() answers for type(obj), so asking it about a class reports on the
            # metaclass and never finds the registration; lookup_by_type() is the guard.
            html_formatter.lookup_by_type(typ)
        except KeyError:
            html_formatter.for_type(typ, func)


def _render_pandas(df: Any) -> str:
    """Render a pandas DataFrame through cnotebook, or through pandas if that is not possible.

    :param df: Frame IPython asked to format.
    :returns: HTML for the frame.
    """
    try:
        from cnotebook.pandas_ext import render_dataframe
    except ImportError:
        return df._repr_html_()
    return render_dataframe(df)


def _render_polars(df: Any) -> str:
    """Render a polars DataFrame through cnotebook, or through polars if that is not possible.

    :param df: Frame IPython asked to format.
    :returns: HTML for the frame.
    """
    try:
        from cnotebook.polars_ext import render_polars_dataframe
    except ImportError:
        return df._repr_html_()
    return render_polars_dataframe(df)


def register_dataframe_formatters_by_name() -> None:
    """Register DataFrame HTML formatters by type name, so neither library is imported.

    The renderers import their adapter on the first frame they are handed, which cannot
    happen before the frame's own library is imported.
    """
    html_formatter = _html_formatter()
    if html_formatter is None:
        return
    for names, func in ((_PANDAS_DATAFRAME_NAMES, _render_pandas),
                        (_POLARS_DATAFRAME_NAMES, _render_polars)):
        for module, name in names:
            html_formatter.for_type_by_name(module, name, func)
