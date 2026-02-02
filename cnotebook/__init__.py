"""
CNotebook - Ergonomic chemistry visualization in notebooks.

Auto-detects available backends (Pandas/Polars) and environments (Jupyter/Marimo).
Only requires openeye-toolkits; all other dependencies are optional.
"""
import logging

# Required imports (openeye-toolkits)
from openeye import oechem, oedepict

# Core functionality that doesn't depend on backends
from .context import cnotebook_context, CNotebookContext
from .helpers import highlight_smarts

__version__ = '2.1.0'

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


# Configure handler
_handler = logging.StreamHandler()
_handler.setLevel(logging.DEBUG)
_handler.setFormatter(LevelSpecificFormatter())
log.addHandler(_handler)
log.setLevel(logging.INFO)


def enable_debugging():
    """Convenience function for enabling the debug log."""
    log.setLevel(logging.DEBUG)


########################################################################################################################
# Environment Information
########################################################################################################################

class CNotebookEnvInfo:
    """Environment information for CNotebook.

    This class provides read-only access to detected backend and environment
    availability. A singleton instance is created at module load time and
    can be retrieved via :func:`get_env`.

    All properties are read-only to ensure consistency throughout the
    application lifecycle. Availability is determined by checking if the
    version string is non-empty.
    """

    def __init__(
        self,
        pandas_version: str,
        polars_version: str,
        ipython_version: str,
        marimo_version: str,
        molgrid_available: bool,
        is_jupyter_notebook: bool,
        is_marimo_notebook: bool,
    ):
        """Create environment info (typically called once at module load).

        :param pandas_version: Detected Pandas version string, or empty if unavailable.
        :param polars_version: Detected Polars version string, or empty if unavailable.
        :param ipython_version: Detected IPython version string, or empty if unavailable.
        :param marimo_version: Detected Marimo version string, or empty if unavailable.
        :param molgrid_available: Whether MolGrid widget dependencies are available.
        :param is_jupyter_notebook: Whether running in a Jupyter notebook environment.
        :param is_marimo_notebook: Whether running in a Marimo notebook environment.
        """
        self._pandas_version = pandas_version
        self._polars_version = polars_version
        self._ipython_version = ipython_version
        self._marimo_version = marimo_version
        self._molgrid_available = molgrid_available
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
            f"jupyter={self._is_jupyter_notebook}, "
            f"marimo_nb={self._is_marimo_notebook})"
        )


def _detect_environment() -> CNotebookEnvInfo:
    """Detect available backends and environments.

    :returns: CNotebookEnvInfo instance with detection results.
    """
    pandas_version = ""
    polars_version = ""
    ipython_version = ""
    marimo_version = ""
    molgrid_available = False
    is_jupyter = False
    is_marimo = False

    # Detect molgrid (requires anywidget)
    try:
        from cnotebook.grid import molgrid, MolGrid
        molgrid_available = True
    except ImportError:
        pass

    # Detect pandas/oepandas
    try:
        import pandas as pd
        import oepandas as oepd
        pandas_version = pd.__version__
    except ImportError:
        pass

    # Detect polars/oepolars
    try:
        import polars as pl
        import oepolars as oeplr
        polars_version = pl.__version__
    except ImportError:
        pass

    # Detect iPython
    try:
        import IPython
        # noinspection PyProtectedMember
        from IPython import get_ipython
        ipy = get_ipython()
        if ipy is not None:
            ipython_version = IPython.__version__
            # Check if running in Jupyter notebook
            is_jupyter = ipy.__class__.__name__ == 'ZMQInteractiveShell'
    except (ImportError, Exception):
        pass

    # Detect Marimo
    try:
        import marimo as mo
        if mo.running_in_notebook():
            marimo_version = mo.__version__
            is_marimo = True
    except (ImportError, Exception):
        # Marimo raises exception if not running in notebook context
        pass

    return CNotebookEnvInfo(
        pandas_version=pandas_version,
        polars_version=polars_version,
        ipython_version=ipython_version,
        marimo_version=marimo_version,
        molgrid_available=molgrid_available,
        is_jupyter_notebook=is_jupyter,
        is_marimo_notebook=is_marimo,
    )


# Initialize environment detection at module load (singleton instance)
_env_info: CNotebookEnvInfo = _detect_environment()


def get_env() -> CNotebookEnvInfo:
    """Get environment information for CNotebook.

    Returns a singleton instance containing information about available
    backends and environments. The environment is detected once at module
    load time and the same object is returned on subsequent calls.

    :returns: CNotebookEnvInfo instance with read-only properties.

    Example::

        env = cnotebook.get_env()
        if env.pandas_available:
            print(f"Pandas {env.pandas_version} is available")
    """
    return _env_info


########################################################################################################################
# Register Formatters Based on Availability
########################################################################################################################

# Import and register pandas formatters if available
if _env_info.pandas_available:
    try:
        from .pandas_ext import render_dataframe, register_pandas_formatters

        if _env_info.ipython_available:
            from .ipython_ext import register_ipython_formatters
            register_ipython_formatters()
            register_pandas_formatters()
            log.debug("[cnotebook] Registered Pandas formatters for iPython")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import/register Pandas extension: {e}")

# Import and register polars formatters if available
if _env_info.polars_available:
    try:
        from .polars_ext import render_polars_dataframe, register_polars_formatters

        if _env_info.ipython_available:
            register_polars_formatters()
            log.debug("[cnotebook] Registered Polars formatters for iPython")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import/register Polars extension: {e}")

# Import marimo extension if available
if _env_info.marimo_available:
    try:
        from . import marimo_ext
        log.debug("[cnotebook] Imported Marimo extension")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import Marimo extension: {e}")

# Export molgrid at top level if available
if _env_info.molgrid_available:
    from .grid import molgrid, MolGrid


########################################################################################################################
# Unified Display Function
########################################################################################################################

def display(obj, ctx: CNotebookContext | None = None):
    """Display an OpenEye molecule, display object, or DataFrame in the current notebook environment.

    This function provides a unified way to display chemistry objects in both Jupyter
    and Marimo notebooks. It automatically detects the environment and uses the
    appropriate display mechanism.

    :param obj: Object to display. Can be:
        - ``oechem.OEMolBase`` - OpenEye molecule
        - ``oedepict.OE2DMolDisplay`` - OpenEye display object
        - ``pandas.DataFrame`` - Pandas DataFrame (if pandas available)
        - ``polars.DataFrame`` - Polars DataFrame (if polars available)
    :param ctx: Optional rendering context. Only applied to molecules and display
        objects, not DataFrames. If None, uses the global context.
    :returns: A displayable object appropriate for the current environment.
    :raises TypeError: If the object type is not supported.

    Example::

        import cnotebook
        from openeye import oechem

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        # Display with default context
        cnotebook.display(mol)

        # Display with custom context
        ctx = cnotebook.cnotebook_context.get().copy()
        ctx.width = 300
        ctx.height = 300
        cnotebook.display(mol, ctx=ctx)
    """
    from .render import oemol_to_html, oedisp_to_html

    # Get environment info
    env = get_env()

    # Determine the context to use
    if ctx is None:
        render_ctx = cnotebook_context.get()
    else:
        render_ctx = ctx

    # Handle OpenEye molecules
    if isinstance(obj, oechem.OEMolBase):
        html = oemol_to_html(obj, ctx=render_ctx)
        return _display_html(html, env)

    # Handle OpenEye display objects
    if isinstance(obj, oedepict.OE2DMolDisplay):
        html = oedisp_to_html(obj, ctx=render_ctx)
        return _display_html(html, env)

    # Handle Pandas DataFrame (if available)
    if env.pandas_available:
        import pandas as pd
        if isinstance(obj, pd.DataFrame):
            # noinspection PyTypeChecker
            html = render_dataframe(obj, ctx=render_ctx)
            return _display_html(html, env)

    # Handle Polars DataFrame (if available)
    if env.polars_available:
        import polars as pl
        if isinstance(obj, pl.DataFrame):
            html = render_polars_dataframe(obj, ctx=render_ctx)
            return _display_html(html, env)

    raise TypeError(f"Cannot display object of type {type(obj).__name__}")


def _display_html(html: str, env: CNotebookEnvInfo):
    """Display HTML content in the appropriate notebook environment.

    :param html: HTML string to display.
    :param env: Environment info.
    :returns: Displayable object for the current environment.
    """
    # Marimo environment
    if env.is_marimo_notebook:
        import marimo as mo
        return mo.Html(html)

    # Jupyter/IPython environment
    if env.ipython_available:
        from IPython.display import HTML, display as ipy_display
        return ipy_display(HTML(html))

    # Fallback: just return the HTML string
    return html
