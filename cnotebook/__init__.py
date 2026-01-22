"""
CNotebook - Ergonomic chemistry visualization in notebooks.

Auto-detects available backends (Pandas/Polars) and environments (Jupyter/Marimo).
Only requires openeye-toolkits; all other dependencies are optional.
"""
import logging

# Required imports (openeye-toolkits)
from openeye import oechem, oedepict

# Core functionality that doesn't depend on backends
from .render import render_molecule_grid
from .context import cnotebook_context

__version__ = '2.0.0'

# Configure logging first
log = logging.getLogger("cnotebook")


class LevelSpecificFormatter(logging.Formatter):
    """A logging formatter that uses level-specific formats."""
    NORMAL_FORMAT = "%(message)s"
    DEBUG_FORMAT = "%(levelname)s: %(message)s"

    def __init__(self):
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
# Backend and Environment Detection
########################################################################################################################

# Detection flags
_pandas_available = False
_polars_available = False
_ipython_available = False
_marimo_available = False
_molgrid_available = False

# Detect molgrid (requires anywidget)
try:
    from cnotebook.molgrid import molgrid, MolGrid
    _molgrid_available = True
except ImportError:
    pass

# Detect pandas/oepandas
try:
    import pandas as _pd
    import oepandas as _oepd
    _pandas_available = True
    del _pd, _oepd
except ImportError:
    pass

# Detect polars/oepolars
try:
    import polars as _pl
    import oepolars as _oeplr
    _polars_available = True
    del _pl, _oeplr
except ImportError:
    pass

# Detect iPython (Jupyter)
try:
    from IPython import get_ipython as _get_ipython
    if _get_ipython() is not None:
        _ipython_available = True
    del _get_ipython
except ImportError:
    pass

# Detect Marimo
try:
    import marimo as _mo
    if _mo.running_in_notebook():
        _marimo_available = True
    del _mo
except (ImportError, Exception):
    # Marimo raises exception if not running in notebook context
    pass


########################################################################################################################
# Helper Functions
########################################################################################################################

def is_jupyter_notebook() -> bool:
    """Check if running in a Jupyter notebook environment."""
    try:
        from IPython import get_ipython
        shell = get_ipython().__class__.__name__
        return shell == 'ZMQInteractiveShell'
    except Exception:
        return False


def is_marimo_notebook() -> bool:
    """Check if running in a Marimo notebook environment."""
    try:
        import marimo as mo
        return mo.running_in_notebook()
    except Exception:
        return False


########################################################################################################################
# Register Formatters Based on Availability
########################################################################################################################

# Import and register pandas formatters if available
if _pandas_available:
    try:
        from .pandas_ext import render_dataframe, register_pandas_formatters

        if _ipython_available:
            from .ipython_ext import register_ipython_formatters
            register_ipython_formatters()
            register_pandas_formatters()
            log.debug("[cnotebook] Registered Pandas formatters for iPython")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import/register Pandas extension: {e}")

# Import and register polars formatters if available
if _polars_available:
    try:
        from .polars_ext import render_polars_dataframe, register_polars_formatters

        if _ipython_available:
            register_polars_formatters()
            log.debug("[cnotebook] Registered Polars formatters for iPython")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import/register Polars extension: {e}")

# Import marimo extension if available
if _marimo_available:
    try:
        from . import marimo_ext
        log.debug("[cnotebook] Imported Marimo extension")
    except Exception as e:
        log.warning(f"[cnotebook] Failed to import Marimo extension: {e}")
