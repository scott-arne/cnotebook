import logging
from openeye import oechem, oedepict
from .render import (
    CNotebookContext,
    pass_cnotebook_context,
    oemol_to_html,
    oedisp_to_html,
    oeimage_to_html,
    render_molecule_grid  # Re-export for backward compatibility
)

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    ipython_present = False

log = logging.getLogger("cnotebook")


########################################################################################################################
# Register iPython formatters
########################################################################################################################

if ipython_present:

    def register_ipython_formatters():
        """
        Register formatters for OpenEye types here that can be rendered. Calls to this function are idempotent.
        """
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']

            try:
                _ = html_formatter.lookup(oechem.OEMolBase)
            except KeyError:
                html_formatter.for_type(oechem.OEMolBase, oemol_to_html)

            try:
                _ = html_formatter.lookup(oedepict.OE2DMolDisplay)
            except KeyError:
                html_formatter.for_type(oedepict.OE2DMolDisplay, oedisp_to_html)

            try:
                _ = html_formatter.lookup(oedepict.OEImage)
            except KeyError:
                html_formatter.for_type(oedepict.OEImage, oeimage_to_html)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register iPython extension")

else:

    # iPython is not present, so we do not register formatters for OpenEye objects
    def register_ipython_formatters():
        pass
