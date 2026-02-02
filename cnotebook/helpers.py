import logging
import re
from typing import Callable, Literal, Sequence
from openeye import oechem, oedepict

log = logging.getLogger("cnotebook")


# Type alias for highlight style
HighlightStyle = int | Literal["overlay_default", "overlay_ball_and_stick"]

# Type alias for highlight colors
HighlightColors = oechem.OEColor | oechem.OEColorIter


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
        color: HighlightColors | None = None,
        style: HighlightStyle = "overlay_default"
) -> Callable[[oedepict.OE2DMolDisplay], None]:
    """
    Closure that creates a callback to highlight SMARTS patterns or MCSS results in a molecule.

    :param query: SMARTS pattern, oechem.OESubSearch, or oechem.OEMCSSearch object.
    :param color: Highlight color(s). Can be a single oechem.OEColor or an oechem.OEColorIter
        (e.g., oechem.OEGetLightColors()). Defaults to oechem.OEGetLightColors().
    :param style: Highlight style. Can be an int (OEHighlightStyle constant) or a string
        ("overlay_default", "overlay_ball_and_stick"). Defaults to "overlay_default".
    :returns: Callback function that highlights structures.
    """
    # Default color
    if color is None:
        color = oechem.OEGetLightColors()

    # Create the substructure search object
    if isinstance(query, (str, oechem.OEQMol)):
        ss = oechem.OESubSearch(query)
    elif isinstance(query, (oechem.OESubSearch, oechem.OEMCSSearch)):
        ss = query
    else:
        raise TypeError(f'Cannot create structure highlighter with object pattern of type {type(query).__name__}')

    # Determine highlighting approach based on style
    use_overlay = isinstance(style, str) and style in ("overlay_default", "overlay_ball_and_stick")

    # Check if color is compatible with overlay
    if use_overlay and isinstance(color, oechem.OEColor):
        log.warning(
            "Overlay coloring is not compatible with a single oechem.OEColor. Falling back to standard highlighting")
        use_overlay = False
        style = oedepict.OEHighlightStyle_BallAndStick

    if use_overlay:
        # Overlay highlighting with color iterator
        highlight = oedepict.OEHighlightOverlayByBallAndStick(color)

        def _overlay_highlighter(disp: oedepict.OE2DMolDisplay):
            oedepict.OEAddHighlightOverlay(disp, highlight, ss.Match(disp.GetMolecule(), True))

        return _overlay_highlighter

    else:
        # Traditional highlighting with OEHighlightStyle int
        # For traditional highlighting, we need a single color
        if isinstance(color, oechem.OEColor):
            highlight_color = color
        else:
            # Get first color from iterator for traditional highlighting
            highlight_color = oechem.OELightBlue
            for c in color:
                highlight_color = c
                break

        def _structure_highlighter(disp: oedepict.OE2DMolDisplay):
            for match in ss.Match(disp.GetMolecule(), True):
                oedepict.OEAddHighlighting(disp, highlight_color, style, match)

        return _structure_highlighter


def highlight_smarts(
    mol: oechem.OEMolBase,
    smarts: str | Sequence[str],
    color: oechem.OEColor | Sequence[oechem.OEColor] = oechem.OEColor(oechem.OELightBlue),
    style: int | Sequence[int] = oedepict.OEHighlightStyle_Stick,
    opts: oedepict.OE2DMolDisplayOptions | None = None,
) -> oedepict.OE2DMolDisplay:
    """Highlight SMARTS patterns in a molecule and return a display object.

    :param mol: OpenEye molecule to highlight.
    :param smarts: SMARTS pattern or sequence of SMARTS patterns to highlight.
    :param color: Highlight color or sequence of colors. If a single color, it is
        applied to all patterns. If a sequence, must match length of smarts.
    :param style: Highlight style or sequence of styles. If a single style, it is
        applied to all patterns. If a sequence, must match length of smarts.
    :param opts: Display options. If None, default options are used.
    :returns: OE2DMolDisplay object with highlighted substructures.
    :raises ValueError: If color/style sequence length doesn't match smarts length.

    Example::

        from openeye import oechem
        import cnotebook

        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc2c(c1)nc(n2)N")

        # Single color/style for all patterns
        disp = cnotebook.highlight_smarts(mol, ["ncn", "c1ccccc1"])

        # Different colors for each pattern
        disp = cnotebook.highlight_smarts(
            mol,
            ["ncn", "c1ccccc1"],
            color=[oechem.OEColor(oechem.OELightBlue), oechem.OEColor(oechem.OEPink)]
        )
    """
    # Prepare molecule for depiction
    oedepict.OEPrepareDepiction(mol)

    # Create display options if not provided
    if opts is None:
        opts = oedepict.OE2DMolDisplayOptions()

    # Create display object
    disp = oedepict.OE2DMolDisplay(mol, opts)

    # Normalize smarts to a list
    if isinstance(smarts, str):
        smarts = [smarts]

    n_patterns = len(smarts)

    # Normalize colors to a list
    if isinstance(color, oechem.OEColor):
        colors = [color] * n_patterns
    else:
        colors = list(color)
        if len(colors) != n_patterns:
            raise ValueError(
                f"Length of color sequence ({len(colors)}) must match "
                f"length of smarts sequence ({n_patterns})"
            )

    # Normalize styles to a list
    if isinstance(style, int):
        styles = [style] * n_patterns
    else:
        styles = list(style)
        if len(styles) != n_patterns:
            raise ValueError(
                f"Length of style sequence ({len(styles)}) must match "
                f"length of smarts sequence ({n_patterns})"
            )

    # Highlight all patterns with corresponding color and style
    for pattern, c, s in zip(smarts, colors, styles):
        subs = oechem.OESubSearch(pattern)
        for match in subs.Match(mol, True):
            oedepict.OEAddHighlighting(disp, c, s, match)

    return disp
