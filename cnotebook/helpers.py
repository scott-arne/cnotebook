import re
from typing import Callable
from openeye import oechem, oedepict


def escape_html(val):
    """
    Perform the same HTML escaping done by Pandas for displaying in Notebooks
    :param val: Value to escape
    :return: Escaped value (if val was a string)
    """
    if isinstance(val, str):
        return val.replace("&", r"&amp;").replace("<", r"&lt;").replace(">", r"&gt;")
    return val


def escape_brackets(val):
    """
    Escapes only HTML brackets
    :param val: Value to escape
    :return: Escaped value (if string)
    """
    if isinstance(val, str):
        return val.replace("<", r"&lt;").replace(">", r"&gt;")
    return val


# Remove conformer identifier from compound ID
CONFORMER_ID_REGEX = re.compile(r'(.*?)_\d+$')


def remove_omega_conformer_id(val):
    """
    Remove the conformer ID from a compound identifier
    :param val: Value
    :return: Processed value
    """
    if isinstance(val, str):
        m = re.search(CONFORMER_ID_REGEX, val)
        if m is not None:
            return m.group(1)
    return val


def create_structure_highlighter(
        query: str | oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol,
        color: oechem.OEColor = oechem.OEColor(oechem.OELightBlue),
        style: int = oedepict.OEHighlightStyle_Stick
) -> Callable[[oedepict.OE2DMolDisplay], None]:
    """
    Closure that creates a callback to highlight SMARTS patterns or MCSS results in a molecule
    :param query: SMARTS pattern, oechem.OESubSearch, or oechem.OEMCSSearch object
    :param color: Highlight color
    :param style: Highlight style
    :return: Function that highlights structures
    """

    if isinstance(query, (str, oechem.OEQMol)):
        ss = oechem.OESubSearch(query)

    elif not isinstance(query, (oechem.OESubSearch, oechem.OEMCSSearch)):
        raise TypeError(f'Cannot create structure highlighter with object pattern of type {type(query).__name__}')

    # Create the callback as a closure
    def _structure_highlighter(disp: oedepict.OE2DMolDisplay):
        for match in ss.Match(disp.GetMolecule(), True):
            oedepict.OEAddHighlighting(disp, color, style, match)

    return _structure_highlighter
