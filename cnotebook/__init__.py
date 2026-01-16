import logging
from .pandas_ext import render_dataframe
from .context import cnotebook_context
from .ipython_ext import register_ipython_formatters as _register_ipython_formatters
from .render import render_molecule_grid

# Only import formatter registration from the Pandas module, otherwise have users import functionality from there
# to avoid confusion
from cnotebook.pandas_ext import register_pandas_formatters as _register_pandas_formatters

__version__ = '1.2.0'

###########################################

def is_jupyter_notebook() -> bool:
    # noinspection PyBroadException
    try:
        from IPython import get_ipython
        shell = get_ipython().__class__.__name__

        if shell == 'ZMQInteractiveShell':
            return True   # Jupyter notebook or qtconsole

        elif shell == 'TerminalInteractiveShell':
            return False  # Terminal running IPython

        else:
            return False  # Other type (?)

    except Exception:
        return False      # Probably standard Python interpreter


def is_marimo_notebook() -> bool:
    # noinspection PyBroadException
    try:
        # noinspection PyUnresolvedReferences
        import marimo as mo
        return mo.running_in_notebook()

    except Exception:
        return False


# Register the formatters
# Note: All registration function calls are idempotent
if is_jupyter_notebook():
    _register_ipython_formatters()
    _register_pandas_formatters()

elif is_marimo_notebook():
    from . import marimo_ext

# Configure logging
log = logging.getLogger("cnotebook")


class LevelSpecificFormatter(logging.Formatter):
    """
    A logging formatter
    """
    NORMAL_FORMAT = "%(message)s"
    DEBUG_FORMAT = "%(levelname)s: %(message)s"

    def __init__(self):
        super().__init__(fmt=self.NORMAL_FORMAT, datefmt=None, style='%')

    def format(self, record: logging.LogRecord) -> str:
        """
        Format a log record for printing
        :param record: Record to format
        :return: Formatted record
        """
        if record.levelno == logging.DEBUG:
            self._style._fmt = self.DEBUG_FORMAT
        else:
            self._style._fmt = self.NORMAL_FORMAT

        # Call the original formatter class to do the grunt work
        result = logging.Formatter.format(self, record)

        return result


############################
# Example of how to use it #
############################

ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)

ch.setFormatter(LevelSpecificFormatter())
log.addHandler(ch)

log.setLevel(logging.INFO)


def enable_debugging():
    """
    Convenience function for enabling the debug log
    """
    log.setLevel(logging.DEBUG)
