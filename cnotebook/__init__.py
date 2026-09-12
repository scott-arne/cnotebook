"""
CNotebook - Ergonomic chemistry visualization in notebooks.

Auto-detects available backends (Pandas/Polars) and environments (Jupyter/Marimo).
Only requires openeye-toolkits; all other dependencies are optional.
"""
import importlib
import importlib.metadata
import importlib.util
import logging
import sys

# Required imports (openeye-toolkits)
from openeye import oechem, oedepict

# Core functionality that doesn't depend on backends
from . import _hooks
from .context import CNotebookContext, cnotebook_context
from .core.errors import warn
from .core.render import render_design_unit as render_design_unit
from .core.render import render_display as render_display
from .core.render import render_molecule as render_molecule
from .core.render import save_image as save_image
from .helpers import highlight_smarts as highlight_smarts

__version__ = '3.1.3'

# Configure logging first
log = logging.getLogger("cnotebook")


class LevelSpecificFormatter(logging.Formatter):
    """A logging formatter that uses level-specific formats.

    Uses a simple format for INFO and above, and includes the level name
    for DEBUG messages to help distinguish debug output.

    :cvar NORMAL_FORMAT: Format string for INFO and above.
    :cvar DEBUG_FORMAT: Format string for DEBUG level.
    """

    NORMAL_FORMAT = "%(message)s"
    DEBUG_FORMAT = "%(levelname)s: %(message)s"

    def __init__(self):
        """Create the formatter with the normal format as default."""
        super().__init__(fmt=self.NORMAL_FORMAT, datefmt=None, style='%')

    def format(self, record: logging.LogRecord) -> str:
        if record.levelno == logging.DEBUG:
            self._style._fmt = self.DEBUG_FORMAT
        else:
            self._style._fmt = self.NORMAL_FORMAT
        return logging.Formatter.format(self, record)


# The library never installs an output handler; applications configure logging.
log.addHandler(logging.NullHandler())


def enable_debugging() -> None:
    """Attach a stream handler with the level-specific formatter and enable DEBUG logging.

    Calling this more than once attaches a single handler.
    """
    if not any(getattr(h, "_cnotebook_debug", False) for h in log.handlers):
        handler = logging.StreamHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(LevelSpecificFormatter())
        handler._cnotebook_debug = True  # type: ignore[attr-defined]
        log.addHandler(handler)
    log.setLevel(logging.DEBUG)


from . import config as config
from .config import configure as configure
from .config import get_config as get_config

config.apply_render_defaults()


########################################################################################################################
# Environment Information
########################################################################################################################

class CNotebookEnvInfo:
    """Environment information for CNotebook.

    This class provides read-only access to detected backend and environment
    availability. An instance describes the environment at the moment
    :func:`get_env` was called; call it again after importing something new.

    All properties are read-only, so a snapshot cannot drift while it is being
    read. Availability is determined by checking if the version string is
    non-empty.
    """

    def __init__(
        self,
        pandas_version: str,
        polars_version: str,
        ipython_version: str,
        marimo_version: str,
        molgrid_available: bool,
        c3d_available: bool,
        is_jupyter_notebook: bool,
        is_marimo_notebook: bool,
    ):
        """Create an environment snapshot.

        :param pandas_version: Detected Pandas version string, or empty if unavailable.
        :param polars_version: Detected Polars version string, or empty if unavailable.
        :param ipython_version: Detected IPython version string, or empty if unavailable.
        :param marimo_version: Detected Marimo version string, or empty if unavailable.
        :param molgrid_available: Whether MolGrid widget dependencies are available.
        :param c3d_available: Whether C3D viewer dependencies are available.
        :param is_jupyter_notebook: Whether running in a Jupyter notebook environment.
        :param is_marimo_notebook: Whether running in a Marimo notebook environment.
        """
        self._pandas_version = pandas_version
        self._polars_version = polars_version
        self._ipython_version = ipython_version
        self._marimo_version = marimo_version
        self._molgrid_available = molgrid_available
        self._c3d_available = c3d_available
        self._is_jupyter_notebook = is_jupyter_notebook
        self._is_marimo_notebook = is_marimo_notebook

    @property
    def pandas_available(self) -> bool:
        """Whether Pandas and OEPandas are available."""
        return bool(self._pandas_version)

    @property
    def pandas_version(self) -> str:
        """Pandas version string, or empty string if not available."""
        return self._pandas_version

    @property
    def polars_available(self) -> bool:
        """Whether Polars and OEPolars are available."""
        return bool(self._polars_version)

    @property
    def polars_version(self) -> str:
        """Polars version string, or empty string if not available."""
        return self._polars_version

    @property
    def ipython_available(self) -> bool:
        """Whether IPython is available and active."""
        return bool(self._ipython_version)

    @property
    def ipython_version(self) -> str:
        """IPython version string, or empty string if not available."""
        return self._ipython_version

    @property
    def marimo_available(self) -> bool:
        """Whether Marimo is available and running in notebook mode."""
        return bool(self._marimo_version)

    @property
    def marimo_version(self) -> str:
        """Marimo version string, or empty string if not available."""
        return self._marimo_version

    @property
    def molgrid_available(self) -> bool:
        """Whether MolGrid is available (requires anywidget)."""
        return self._molgrid_available

    @property
    def c3d_available(self) -> bool:
        """Whether the C3D viewer module is available."""
        return self._c3d_available

    @property
    def is_jupyter_notebook(self) -> bool:
        """Whether running in a Jupyter notebook environment."""
        return self._is_jupyter_notebook

    @property
    def is_marimo_notebook(self) -> bool:
        """Whether running in a Marimo notebook environment."""
        return self._is_marimo_notebook

    def __repr__(self) -> str:
        return (
            f"CNotebookEnvInfo("
            f"pandas={self.pandas_available} ({self._pandas_version}), "
            f"polars={self.polars_available} ({self._polars_version}), "
            f"ipython={self.ipython_available} ({self._ipython_version}), "
            f"marimo={self.marimo_available} ({self._marimo_version}), "
            f"molgrid={self._molgrid_available}, "
            f"c3d={self._c3d_available}, "
            f"jupyter={self._is_jupyter_notebook}, "
            f"marimo_nb={self._is_marimo_notebook})"
        )


def _installed(name: str) -> bool:
    """Report whether *name* could be imported, without importing it.

    :param name: Top-level module name.
    :returns: True when an import of *name* would find something.
    """
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        # A package whose parent is broken, or one already in sys.modules with no spec,
        # is not something cnotebook can use either.
        return False


def _version(name: str) -> str:
    """Read a package's version, without importing the package.

    :param name: Top-level module name, also used as the distribution name.
    :returns: The version string, or empty when it cannot be determined.
    """
    # An already-imported package answers for free and answers for itself, which matters
    # for anything installed outside a distribution; otherwise fall back to the metadata.
    version = getattr(sys.modules.get(name), "__version__", "")
    if version:
        return str(version)
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _detect_environment() -> CNotebookEnvInfo:
    """Detect available backends and environments.

    Every answer comes from installed package metadata plus what the session has already
    imported, so asking the question never itself imports pandas, polars, marimo or
    anywidget.

    :returns: CNotebookEnvInfo instance with detection results.
    """
    ipython_version = ""
    is_jupyter = False
    if "IPython" in sys.modules:
        from IPython.core.getipython import get_ipython

        shell = get_ipython()
        if shell is not None:
            ipython_version = str(getattr(sys.modules["IPython"], "__version__", ""))
            is_jupyter = shell.__class__.__name__ == 'ZMQInteractiveShell'

    marimo_version = ""
    is_marimo = False
    if "marimo" in sys.modules:
        mo = sys.modules["marimo"]
        try:
            is_marimo = bool(mo.running_in_notebook())
        except Exception:  # noqa: BLE001 - marimo raises outside a notebook context, which is an answer
            is_marimo = False
        if is_marimo:
            marimo_version = str(getattr(mo, "__version__", ""))

    # A backend counts as available only with both halves installed: the dataframe
    # library and the OpenEye adapter cnotebook renders through.
    pandas_ok = _installed("pandas") and _installed("oepandas")
    polars_ok = _installed("polars") and _installed("oepolars")

    return CNotebookEnvInfo(
        pandas_version=_version("pandas") if pandas_ok else "",
        polars_version=_version("polars") if polars_ok else "",
        ipython_version=ipython_version,
        marimo_version=marimo_version,
        molgrid_available=_installed("anywidget"),
        # The C3D viewer ships with cnotebook and needs nothing optional to import.
        c3d_available=True,
        is_jupyter_notebook=is_jupyter,
        is_marimo_notebook=is_marimo,
    )


def get_env() -> CNotebookEnvInfo:
    """Get environment information for CNotebook.

    The environment is recomputed on each call, because detection is now cheap and a
    library imported after cnotebook -- which is the normal order now -- has to show up.

    :returns: CNotebookEnvInfo instance with read-only properties.

    Example::

        env = cnotebook.get_env()
        if env.pandas_available:
            print(f"Pandas {env.pandas_version} is available")
    """
    return _detect_environment()


########################################################################################################################
# Register Formatters and Integration Hooks
########################################################################################################################

def _activate_ipython() -> None:
    """Register the IPython formatters, if this session has IPython at all.

    The DataFrame formatters are registered by type name, so a session that never
    imports pandas or polars never pays for them.
    """
    if "IPython" not in sys.modules:
        return
    from .ipython_ext import (
        register_dataframe_formatters_by_name,
        register_ipython_formatters,
    )

    register_ipython_formatters()
    register_dataframe_formatters_by_name()


_activate_ipython()

# Each adapter attaches when -- and only when -- the library it adapts finishes importing,
# whether that happens before this line or long after it.
_hooks.on_import("oepandas", "cnotebook.pandas_ext:_attach")
_hooks.on_import("oepolars", "cnotebook.polars_ext:_attach")
_hooks.on_import("marimo", "cnotebook.marimo_ext:_attach")


# Optional top-level exports and the submodule that provides each. Binding them here
# would import anywidget, pandas and polars on `import cnotebook`, which is exactly the
# cost this package avoids, so each name resolves on first access instead.
_LAZY_EXPORTS = {
    "BEST_FIT_ORIENTATION": ("cnotebook.grid", "BEST_FIT_ORIENTATION"),
    "C3D": ("cnotebook.c3d", "C3D"),
    "MolGrid": ("cnotebook.grid", "MolGrid"),
    "molgrid": ("cnotebook.grid", "molgrid"),
    "render_dataframe": ("cnotebook.pandas_ext", "render_dataframe"),
    "render_polars_dataframe": ("cnotebook.polars_ext", "render_polars_dataframe"),
}
_WARNED_EXPORTS: set[str] = set()


def __getattr__(name: str):
    """Resolve an optional top-level export on first access (PEP 562).

    A submodule that cannot be imported would otherwise surface as an opaque
    ``ImportError: cannot import name '...'``, so the failure is reported once as a
    warning naming both the submodule and the underlying cause.

    :param name: Attribute being accessed on the ``cnotebook`` module.
    :returns: The resolved export, also bound on the module so the import happens once.
    :raises AttributeError: If the name is unknown, or its submodule failed to import.
    """
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute = target
    try:
        value = getattr(importlib.import_module(module_name), attribute)
    except ImportError as exc:
        message = (
            f"cnotebook.{name} is unavailable: importing {module_name} failed ({exc}). "
            f"Install the optional dependency it names, or import {module_name} directly "
            f"to see the full error."
        )
        if name not in _WARNED_EXPORTS:
            _WARNED_EXPORTS.add(name)
            warn(message)
        raise AttributeError(message) from exc

    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """List the module's attributes, including the exports that only resolve on access.

    :returns: Sorted attribute names.
    """
    return sorted(set(globals()) | set(_LAZY_EXPORTS))


########################################################################################################################
# Unified Display Function
########################################################################################################################

def display(obj, ctx: CNotebookContext | None = None, *, static: bool | None = None):
    """Display a chemistry object or frame in the current notebook environment.

    :param obj: ``OEMolBase``, ``OE2DMolDisplay``, ``OEDesignUnit``, ``OEImage``, a pandas or
        polars ``DataFrame``, or a C3D / MolGrid instance.
    :param ctx: Render context for bare objects. For frames ``None`` means "honour the
        per-column contexts"; an explicit context overrides every column.
    :param static: For C3D and MolGrid, force static (``True``) or widget (``False``) output.
    :returns: A displayable object appropriate for the environment.
    :raises TypeError: If the object type is not supported.
    """
    import inspect

    from .core.render import (
        oedisp_to_html,
        oedu_to_html,
        oeimage_to_html,
        oemol_to_html,
    )

    env = get_env()

    # Check OpenEye molecule types first
    render_ctx = ctx if ctx is not None else cnotebook_context.get()
    if isinstance(obj, oechem.OEMolBase):
        return _display_html(oemol_to_html(obj, ctx=render_ctx), env)
    if isinstance(obj, oedepict.OE2DMolDisplay):
        return _display_html(oedisp_to_html(obj, ctx=render_ctx), env)
    if isinstance(obj, oechem.OEDesignUnit):
        return _display_html(oedu_to_html(obj, ctx=render_ctx), env)
    if isinstance(obj, oedepict.OEImage):
        return _display_html(oeimage_to_html(obj, ctx=render_ctx), env)

    # Check DataFrame types before widgets (DataFrames can have display methods too).
    # A frame of either kind can only exist if its library is already imported, so the
    # isinstance check costs an import only when it could possibly succeed.
    if "pandas" in sys.modules:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            from .pandas_ext import render_dataframe as _render_dataframe
            return _display_html(_render_dataframe(obj, ctx=ctx), env)
    if "polars" in sys.modules:
        import polars as pl
        if isinstance(obj, pl.DataFrame):
            from .polars_ext import render_polars_dataframe as _render_polars_dataframe
            return _display_html(_render_polars_dataframe(obj, ctx=ctx), env)

    # Handle objects with display() method (C3D, MolGrid, or test stubs)
    if hasattr(obj, "display") and callable(obj.display):
        sig = inspect.signature(obj.display)
        accepts_static = "static" in sig.parameters
        if accepts_static:
            return obj.display(static=static)
        elif static is None:
            return obj.display()
        else:
            raise TypeError(f"{type(obj).__name__}.display() does not support the static option yet")

    raise TypeError(f"Cannot display object of type {type(obj).__name__}")


def _display_html(html: str, env: CNotebookEnvInfo):
    """Display HTML content in the appropriate notebook environment.

    :param html: HTML string to display.
    :param env: Environment info.
    :returns: Displayable object for the current environment.
    """
    # Marimo environment
    if env.is_marimo_notebook:
        import marimo as mo  # pyright: ignore[reportMissingImports]
        return mo.Html(html)

    # Jupyter/IPython environment
    if env.ipython_available:
        from IPython.display import HTML
        from IPython.display import display as ipy_display
        return ipy_display(HTML(html))

    # Fallback: just return the HTML string
    return html
