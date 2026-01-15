import pandas as pd
from openeye import oechem, oedepict
from .context import cnotebook_context
from .render import oemol_to_html, oedisp_to_html, oeimage_to_html
from .pandas_ext import render_dataframe

def _display_mol(self: oechem.OEMolBase):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oemol_to_html(self, ctx=ctx)

oechem.OEMolBase._mime_ = _display_mol


def _display_display(self: oedepict.OE2DMolDisplay):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oedisp_to_html(self, ctx=ctx)

oedepict.OE2DMolDisplay.__mime__ = _display_display


def _display_image(self: oedepict.OEImage):
    ctx = cnotebook_context.get().copy()
    # Allow user's image_format preference (SVG or PNG)
    return "text/html", oeimage_to_html(self, ctx=ctx)

oedepict.OEImage.__mime__ = _display_image

def display_dataframe(self: pd.DataFrame):
    ctx = cnotebook_context.get().copy()
    return render_dataframe(df=self, formatters=None, col_space=None)

pd.DataFrame.__mime__ = display_dataframe
