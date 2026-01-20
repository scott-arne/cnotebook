import logging
import typing
import polars as pl
import oepolars as oeplr
from openeye import oechem, oedepict, oegraphsim, oegrapheme
from .context import pass_cnotebook_context, get_series_context
from typing import Iterable, Literal
from .helpers import escape_brackets, create_structure_highlighter
from .align import fingerprint_maker
from .render import (
    CNotebookContext,
    oemol_to_disp,
    oedisp_to_html,
    render_invalid_molecule,
    render_empty_molecule
)

# Only register iPython formatters if that is present
try:
    # noinspection PyProtectedMember,PyPackageRequirements
    from IPython import get_ipython
    ipython_present = True
except ModuleNotFoundError:
    ipython_present = False

if typing.TYPE_CHECKING:
    from .context import CNotebookContext

log = logging.getLogger("cnotebook")


def create_mol_formatter(*, ctx: CNotebookContext) -> typing.Callable[[oechem.OEMolBase], str]:
    """
    Closure that creates a function that renders an OEMol to HTML
    :param ctx: CNotebook rendering context
    :return: Function that renders molecules to HTML
    """
    def _oemol_to_html(mol: oechem.OEMolBase):
        if isinstance(mol, oechem.OEMolBase):

            # Render valid molecules
            if mol.IsValid():
                # Create the display object
                disp = oemol_to_disp(mol, ctx=ctx)

                # Apply display callbacks
                if ctx.callbacks is not None:
                    for callback in ctx.callbacks:
                        callback(disp)

                # Render into the string stream
                return oedisp_to_html(disp)

            # Empty molecule
            elif mol.NumAtoms() == 0:
                return render_empty_molecule(ctx=ctx)

            # Invalid molecule
            else:
                return render_invalid_molecule(ctx=ctx)

        return str(mol)

    return _oemol_to_html


@pass_cnotebook_context
def create_disp_formatter(
        *,
        callbacks: list[typing.Callable[[oedepict.OE2DMolDisplay], None]] | None = None,
        ctx: CNotebookContext
) -> typing.Callable[[oedepict.OE2DMolDisplay], str]:
    """
    Closure that creates a function that renders an OE2DMolDisplay to HTML
    :param ctx: Render context
    :param callbacks: List of callbacks to modify the rendering of the molecule
    :return: Function that renders display objects to HTML
    """

    def _oedisp_to_html(disp: oedepict.OE2DMolDisplay) -> str:

        if isinstance(disp, oedepict.OE2DMolDisplay) and disp.IsValid():
            # Copy the display, as not to modify the original with callbacks
            disp_to_render = oedepict.OE2DMolDisplay(disp)

            # Apply display callbacks
            if callbacks is not None:
                for callback in callbacks:
                    callback(disp_to_render)

            return oedisp_to_html(disp_to_render, ctx=ctx)
        return str(disp)

    return _oedisp_to_html


def escape_formatter(obj: typing.Any) -> str:
    return escape_brackets(str(obj))


def render_polars_dataframe(
        df: pl.DataFrame,
        formatters: dict | None = None,
        col_space: dict[str, float | int] | None = None,
        **kwargs
) -> str:
    """
    Render a Polars DataFrame with molecules to HTML.

    This is a native Polars implementation that renders molecule and display
    columns directly without converting to pandas.

    :param df: Polars DataFrame to render
    :param formatters: Custom formatters for displaying columns
    :param col_space: Custom column spacing
    :param kwargs: Additional keyword arguments (currently unused, kept for API compatibility)
    :return: HTML of rendered DataFrame
    """
    # Defaults are empty dictionaries for these
    formatters = formatters or {}
    col_space = col_space or {}

    # Identify molecule and display columns
    molecule_columns: set[str] = set()
    display_columns: set[str] = set()

    # Capture metadata from ORIGINAL DataFrame and create formatters
    for col in df.columns:
        dtype = df.schema[col]
        if isinstance(dtype, oeplr.MoleculeType):
            molecule_columns.add(col)

            # Get metadata from the original series via .chem.metadata
            series = df.get_column(col)
            metadata = series.chem.metadata if hasattr(series, 'chem') else {}

            # Get the cnotebook options for this column
            ctx = get_series_context(metadata)

            if col in formatters:
                log.warning(f'Overwriting existing formatter for {col} with a molecule formatter')

            formatters[col] = create_mol_formatter(ctx=ctx)

            # Record the column width
            if col in col_space:
                log.warning(f'Column spacing for {col} already defined, overwriting with molecule image width')

            col_space[col] = float(ctx.width)

        elif isinstance(dtype, oeplr.DisplayType):
            display_columns.add(col)

            # Get metadata from the original series via .chem.metadata
            series = df.get_column(col)
            metadata = series.chem.metadata if hasattr(series, 'chem') else {}

            # Get the cnotebook options for this column
            ctx = get_series_context(metadata)

            if col in formatters:
                log.warning(f'Overwriting existing formatter for {col} with a display formatter')

            formatters[col] = create_disp_formatter(ctx=ctx)

            # Calculate column width from display objects
            if len(series) > 0:
                max_width = 0
                for disp in series:
                    if isinstance(disp, oedepict.OE2DMolDisplay):
                        max_width = max(max_width, disp.GetWidth())
                col_space[col] = max(0, max_width)
            else:
                col_space[col] = 0

    if len(molecule_columns) > 0:
        log.debug(f'Detected molecule columns: {", ".join(molecule_columns)}')

    if len(display_columns) > 0:
        log.debug(f'Detected display columns: {", ".join(display_columns)}')

    # All other columns get escape formatter
    for col in df.columns:
        if col not in display_columns and col not in molecule_columns:
            if col not in formatters:
                formatters[col] = escape_formatter

    # Deep copy molecule columns to avoid modifying originals during rendering
    # Create a dictionary mapping column name to deep-copied series
    copied_molecule_series: dict[str, pl.Series] = {}
    for col in molecule_columns:
        series = df.get_column(col)
        if hasattr(series, 'chem') and hasattr(series.chem, 'deepcopy'):
            # Use oepolars deepcopy to create copies of molecules
            copied_series = series.chem.deepcopy()
            # Preserve metadata from original
            if hasattr(series, 'chem') and hasattr(series.chem, 'metadata'):
                original_metadata = series.chem.metadata
                if original_metadata and hasattr(copied_series, 'chem'):
                    copied_series.chem.metadata.update(original_metadata)
            copied_molecule_series[col] = copied_series

    # Build HTML table natively
    html_parts = ['<table border="1" class="dataframe">']

    # Header
    html_parts.append('<thead><tr style="text-align: right;">')
    for col in df.columns:
        width_style = ""
        if col in col_space:
            width_style = f' style="min-width: {col_space[col]}px;"'
        html_parts.append(f'<th{width_style}>{escape_brackets(str(col))}</th>')
    html_parts.append('</tr></thead>')

    # Body
    html_parts.append('<tbody>')
    for row_idx in range(len(df)):
        html_parts.append('<tr>')
        for col in df.columns:
            # Use copied series for molecule columns, original for others
            if col in copied_molecule_series:
                value = copied_molecule_series[col][row_idx]
            else:
                value = df[col][row_idx]

            # Apply formatter if available
            if col in formatters:
                cell_html = formatters[col](value)
            else:
                cell_html = escape_brackets(str(value))

            html_parts.append(f'<td>{cell_html}</td>')
        html_parts.append('</tr>')
    html_parts.append('</tbody>')

    html_parts.append('</table>')

    return ''.join(html_parts)


########################################################################################################################
# Series accessor methods (monkey-patched onto oepolars)
########################################################################################################################


def _series_highlight(
        self,
        pattern: Iterable[str] | str | oechem.OESubSearch | Iterable[oechem.OESubSearch],
        *,
        color: oechem.OEColor = oechem.OEColor(oechem.OELightBlue),
        style: int = oedepict.OEHighlightStyle_Stick,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | None = None,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None
) -> None:
    """
    Highlight chemical features in a structure.

    The pattern argument can be:
        - SMARTS pattern
        - oechem.OESubSearch or oechem.OEMCSSearch object
        - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

    :param pattern: Pattern(s) to highlight in the molecule
    :param color: Highlight color
    :param style: Highlight style
    :param ref: Optional reference for alignment
    :param method: Optional alignment method
    :return: None
    """
    # Check dtype
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "highlight only works on molecule columns (oepolars.MoleculeType). If this column has "
            "molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get / create a series context and save it (because we are modifying it locally)
    ctx = get_series_context(self.metadata, save=True)

    # ********************************************************************************
    # Highlighting
    # ********************************************************************************

    # Case: Pattern is a single SMARTS string or oechem.OESubSearch object
    if isinstance(pattern, (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)):
        ctx.add_callback(
            create_structure_highlighter(
                query=pattern,
                color=color,
                style=style
            )
        )

    # Case: Pattern is an iterable
    elif isinstance(pattern, Iterable):
        for element in pattern:

            # Element is a SMARTS string or oechem.OESubSearch object
            if isinstance(element, (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)):
                ctx.add_callback(
                    create_structure_highlighter(
                        query=element,
                        color=color,
                        style=style
                    )
                )

            # Unknown element
            else:
                raise TypeError(f'Do not know how to add molecule highlight for type {type(element).__name__}')

    # Case: Pattern is an unknown type
    else:
        raise TypeError(f'Do not know how to add molecule highlight for type {type(pattern).__name__}')

    # ********************************************************************************
    # Alignment
    # ********************************************************************************

    if ref is not None:
        # Only apply alignment if align_depictions method is available
        if hasattr(self, 'align_depictions'):
            self.align_depictions(ref=ref, method=method)
        else:
            log.warning("align_depictions not available; ref parameter ignored")


def _series_reset_depictions(self) -> None:
    """
    Reset depiction callbacks for a molecule series.

    This clears any highlight callbacks that have been added to the series metadata.
    """
    # Clear the cnotebook context from metadata
    _ = self.metadata.pop("cnotebook", None)


def _series_recalculate_depiction_coordinates(
        self,
        *,
        clear_coords: bool = True,
        add_depiction_hydrogens: bool = True,
        perceive_bond_stereo: bool = True,
        suppress_explicit_hydrogens: bool = True,
        orientation: int = oedepict.OEDepictOrientation_Default
) -> None:
    """
    Recalculate the depictions for a molecule series.

    See the following link for more information:
    https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

    :param clear_coords: Clear existing 2D coordinates
    :param add_depiction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens
    :param orientation: Preferred 2D orientation
    """
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "recalculate_depiction_coordinates only works on molecule columns (oepolars.MoleculeType). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Create the depiction options
    opts = oedepict.OEPrepareDepictionOptions()
    opts.SetClearCoords(clear_coords)
    opts.SetAddDepictionHydrogens(add_depiction_hydrogens)

    for mol in self._series.to_list():
        if isinstance(mol, oechem.OEMolBase):
            oedepict.OEPrepareDepiction(mol, opts)


def _series_align_depictions(
        self,
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | oechem.OEQMol | Literal["first"],
        method: Literal["substructure", "ss", "mcss", "fp", "fingerprint"] | None = None,
        **kwargs
) -> None:
    """
    Align the 2D coordinates of molecules in a series.

    :param ref: Alignment reference (molecule, "first", or search object)
    :param method: Alignment method
    :param kwargs: Keyword arguments for aligner
    """
    if not isinstance(self._series.dtype, oeplr.MoleculeType):
        raise TypeError(
            "align_depictions only works on molecule columns (oepolars.MoleculeType). If this "
            "column has molecules, use series.chem.as_molecule() to convert to a molecule column first."
        )

    # Get molecule list from series
    mols = self._series.to_list()

    # Handle "first" reference
    if isinstance(ref, str) and ref == "first":
        for mol in mols:
            if mol is not None and mol.IsValid():
                ref = mol.CreateCopy()
                break
        else:
            log.warning("No valid molecule found in series for depiction alignment")
            return

    # Suppress alignment warnings (there are lots of needless warnings)
    level = oechem.OEThrow.GetLevel()
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Error)

    # noinspection PyBroadException
    try:
        # Create the aligner
        from .align import create_aligner
        aligner = create_aligner(ref=ref, method=method, **kwargs)

        for mol in mols:
            if mol is not None:
                _ = aligner(mol)

    except Exception:
        # We don't care if the aligners fail - it just results in unaligned structures (NBD)
        pass

    # Restore OEThrow level
    oechem.OEThrow.SetLevel(level)


# Monkey-patch onto oepolars SeriesChemNamespace
from oepolars.namespaces.series import SeriesChemNamespace
SeriesChemNamespace.highlight = _series_highlight
SeriesChemNamespace.reset_depictions = _series_reset_depictions
SeriesChemNamespace.recalculate_depiction_coordinates = _series_recalculate_depiction_coordinates
SeriesChemNamespace.align_depictions = _series_align_depictions


########################################################################################################################
# DataFrame accessor methods (monkey-patched onto oepolars)
########################################################################################################################

# Regular expression for splitting SMARTS patterns
import re
SMARTS_DELIMITER_RE = re.compile(r'\s*[|\r\n\t]+\s*')

# Store the fingerprint tag for fingerprint_similarity
_fingerprint_overlap_tag = oechem.OEGetTag("fingerprint_overlap")


class ColorBondByOverlapScore(oegrapheme.OEBondGlyphBase):
    """
    Color molecule by bond overlap score:
    https://docs.eyesopen.com/toolkits/cookbook/python/depiction/simcalc.html
    """
    def __init__(self, cg, tag):
        oegrapheme.OEBondGlyphBase.__init__(self)
        self.colorg = cg
        self.tag = tag

    # noinspection PyPep8Naming
    def RenderGlyph(self, disp, bond):

        bdisp = disp.GetBondDisplay(bond)
        if bdisp is None or not bdisp.IsVisible():
            return False

        if not bond.HasData(self.tag):
            return False

        linewidth = disp.GetScale() / 3.0
        color = self.colorg.GetColorAt(bond.GetData(self.tag))
        pen = oedepict.OEPen(color, color, oedepict.OEFill_Off, linewidth)

        adispB = disp.GetAtomDisplay(bond.GetBgn())
        adispE = disp.GetAtomDisplay(bond.GetEnd())

        layer = disp.GetLayer(oedepict.OELayerPosition_Below)
        layer.DrawLine(adispB.GetCoords(), adispE.GetCoords(), pen)

        return True

    # noinspection PyPep8Naming
    def ColorBondByOverlapScore(self):
        return ColorBondByOverlapScore(self.colorg, self.tag).__disown__()


def _dataframe_reset_depictions(self, *, molecule_columns: str | Iterable[str] | None = None) -> None:
    """
    Reset depiction callbacks for one or more molecule columns in the DataFrame.

    :param molecule_columns: Optional molecule column(s) to reset. If None, resets all molecule columns.
    """
    columns = set()
    if molecule_columns is None:
        columns.update(self._df.columns)

    elif isinstance(molecule_columns, str):
        columns.add(molecule_columns)

    else:
        columns.update(molecule_columns)

    # Filter invalid and non-molecule columns
    for col in filter(
        lambda c: c in self._df.columns and isinstance(self._df.schema[c], oeplr.MoleculeType),
        columns
    ):
        self._df.get_column(col).chem.reset_depictions()


def _dataframe_recalculate_depiction_coordinates(
        self,
        *,
        molecule_columns: str | Iterable[str] | None = None,
        clear_coords: bool = True,
        add_depiction_hydrogens: bool = True,
        perceive_bond_stereo: bool = True,
        suppress_explicit_hydrogens: bool = True,
        orientation: int = oedepict.OEDepictOrientation_Default
) -> None:
    """
    Recalculate the depictions for one or more molecule series in a DataFrame. If molecule_columns is None,
    which is the default, then all molecule columns will have their depictions recalculated.

    See the following link for more information:
    https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

    :param molecule_columns: Optional molecule column(s) to have depictions recalculated
    :param clear_coords: Clear existing 2D coordinates
    :param add_depiction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens
    :param orientation: Preferred 2D orientation
    """
    if molecule_columns is None:
        molecule_columns = set()

        for col in self._df.columns:
            if isinstance(self._df.schema[col], oeplr.MoleculeType):
                molecule_columns.add(col)

    elif isinstance(molecule_columns, str):
        molecule_columns = {molecule_columns}

    else:
        molecule_columns = set(molecule_columns)

    # Recalculate the column depictions
    for col in molecule_columns:

        if col in self._df.columns:
            if isinstance(self._df.schema[col], oeplr.MoleculeType):
                self._df.get_column(col).chem.recalculate_depiction_coordinates(
                    clear_coords=clear_coords,
                    add_depiction_hydrogens=add_depiction_hydrogens,
                    perceive_bond_stereo=perceive_bond_stereo,
                    suppress_explicit_hydrogens=suppress_explicit_hydrogens,
                    orientation=orientation
                )

            else:
                log.warning(f'Column {col} does not have a MoleculeType')

        else:
            log.warning(f'{col} not found in DataFrame columns: ({", ".join(self._df.columns)})')


def _dataframe_highlight_using_column(
        self,
        molecule_column: str,
        pattern_column: str,
        *,
        highlighted_column: str = "highlighted_substructures",
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | None = None,
        alignment_opts: oedepict.OEAlignmentOptions | None = None,
        prepare_opts: oedepict.OEPrepareDepictionOptions | None = None,
        inplace: bool = False
) -> pl.DataFrame:
    """
    Highlight molecules based on the value of another column. The column produced is a DisplayType column, so
    the results are not suitable for other molecular calculations.

    The other column can contain:
        - Comma or whitespace delimited string of SMARTS patterns
        - oechem.OESubSearch or oechem.OEMCSSearch object
        - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

    :param molecule_column: Name of the molecule column
    :param pattern_column: Name of the pattern column
    :param highlighted_column: Optional name of the column with highlighted structures
    :param ref: Optional reference for aligning depictions
    :param alignment_opts: Optional depiction alignment options (oedepict.OEAlignmentOptions)
    :param prepare_opts: Optional depiction preparation options (oedepict.OEPrepareDepictionOptions)
    :param inplace: If True, returns the modified DataFrame (note: Polars DataFrames are immutable)
    :return: Modified DataFrame with highlighted column
    """
    df = self._df

    if molecule_column not in df.columns:
        raise KeyError(f'{molecule_column} not found in DataFrame columns: ({", ".join(df.columns)})')

    if not isinstance(df.schema[molecule_column], oeplr.MoleculeType):
        raise TypeError(
            f"highlight_using_column only works on molecule columns (oepolars.MoleculeType). If {molecule_column}"
            " has molecules, use df.chem.as_molecule() to convert to a molecule column first."
        )

    if pattern_column not in df.columns:
        raise KeyError(f'{pattern_column} not found in DataFrame columns: ({", ".join(df.columns)})')

    # Create the display objects
    displays = []

    # Get the rendering context for creating the displays
    series = df.get_column(molecule_column)
    metadata = series.chem.metadata if hasattr(series, 'chem') else {}
    ctx = get_series_context(metadata)

    for row_idx in range(len(df)):
        mol = df[molecule_column][row_idx]
        patterns = df[pattern_column][row_idx]

        if isinstance(mol, oechem.OEMolBase) and mol.IsValid():

            # Create the display
            disp = oemol_to_disp(mol, ctx=ctx)

            # Highlight
            substructures = []

            # Parse different patterns
            if isinstance(patterns, str):
                for pattern in re.split(SMARTS_DELIMITER_RE, patterns):
                    ss = oechem.OESubSearch(pattern)
                    if ss.IsValid():
                        substructures.append(ss)

            elif isinstance(patterns, oechem.OESubSearch):
                if patterns.IsValid():
                    substructures.append(patterns)

            elif isinstance(patterns, Iterable):

                for p in patterns:

                    if isinstance(p, str):
                        for pattern in re.split(SMARTS_DELIMITER_RE, p):
                            ss = oechem.OESubSearch(pattern)
                            if ss.IsValid():
                                substructures.append(ss)

                    elif isinstance(p, oechem.OESubSearch):
                        if p.IsValid():
                            substructures.append(p)

                    else:
                        log.warning(f'Do not know how to highlight using: {type(p).__name__}')

            elif patterns is not None:
                log.warning(f'Do not know how to highlight using: {type(patterns).__name__}')

            # Apply substructure highlights
            highlight = oedepict.OEHighlightOverlayByBallAndStick(oechem.OEGetLightColors())

            for ss in substructures:
                oedepict.OEAddHighlightOverlay(disp, highlight, ss.Match(mol, True))

            displays.append(disp)

        else:
            displays.append(None)

    # Create the new column with DisplayType (must instantiate the type)
    display_series = pl.Series(highlighted_column, displays, dtype=oeplr.DisplayType())

    # Add the column to the DataFrame
    result = df.with_columns(display_series)

    return result


def _dataframe_fingerprint_similarity(
        self,
        molecule_column: str,
        ref: oechem.OEMolBase | None = None,
        *,
        tanimoto_column: str = "fingerprint_tanimoto",
        reference_similarity_column: str = "reference_similarity",
        target_similarity_column: str = "target_similarity",
        fptype: str = "tree",
        num_bits: int = 4096,
        min_distance: int = 0,
        max_distance: int = 4,
        atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
        bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond,
        inplace: bool = False
) -> pl.DataFrame:
    """
    Color molecules by fingerprint similarity.

    :param molecule_column: Name of the molecule column
    :param ref: Reference molecule (if None, uses first valid molecule)
    :param tanimoto_column: Name of the tanimoto score column
    :param reference_similarity_column: Name of the reference display column
    :param target_similarity_column: Name of the target display column
    :param fptype: Fingerprint type
    :param num_bits: Number of bits in the fingerprint
    :param min_distance: Minimum distance/radius for path/circular/tree
    :param max_distance: Maximum distance/radius for path/circular/tree
    :param atom_type: Atom type bitmask
    :param bond_type: Bond type bitmask
    :param inplace: Not used (Polars DataFrames are immutable), kept for API compatibility
    :return: DataFrame with similarity columns
    """
    tag = _fingerprint_overlap_tag
    df = self._df

    if molecule_column not in df.columns:
        raise KeyError(f'Molecule column not found in DataFrame: {molecule_column}')

    if not isinstance(df.schema[molecule_column], oeplr.MoleculeType):
        raise TypeError(
            f"Column {molecule_column} does not have MoleculeType ({df.schema[molecule_column]})"
        )

    # Get the context for rendering
    series = df.get_column(molecule_column)
    metadata = series.chem.metadata if hasattr(series, 'chem') else {}
    ctx = get_series_context(metadata)

    # Get molecule list
    mols = series.to_list()

    # If we're using the first molecule as our reference
    if ref is None:
        for mol in mols:
            if mol is not None and mol.IsValid():
                ref = mol
                break
        else:
            log.warning(f'No valid reference molecules to use for alignment in column {molecule_column}')
            return df

    # Check reference molecule
    if not ref.IsValid():
        log.warning("Reference molecule is not valid")
        return df

    # Fingerprint maker
    make_fp = fingerprint_maker(
        fptype=fptype,
        num_bits=num_bits,
        min_distance=min_distance,
        max_distance=max_distance,
        atom_type=atom_type,
        bond_type=bond_type
    )

    # Make the reference fingerprint
    ref_fp = make_fp(ref)

    if not ref_fp.IsValid():
        log.warning("Fingerprint from reference molecule is invalid")
        return df

    # Create the display objects and scores
    ref_displays = []
    targ_displays = []
    ref_molecules = []  # Cache to prevent GC
    targ_molecules = []  # Cache to prevent GC
    tanimotos = []

    for mol in mols:
        if mol is not None and mol.IsValid():

            # Copy the molecules, because we're modifying them
            targ_mol = oechem.OEMol(mol)
            ref_mol = oechem.OEMol(ref)

            # Cache molecules to prevent GC
            targ_molecules.append(targ_mol)
            ref_molecules.append(ref_mol)

            # Create the fingerprint
            targ_fp = make_fp(targ_mol)
            if targ_fp.IsValid():

                # Add the tanimoto
                tanimotos.append(oegraphsim.OETanimoto(ref_fp, targ_fp))

                # Calculate the similarity
                targ_bonds = oechem.OEUIntArray(targ_mol.GetMaxBondIdx())
                ref_bonds = oechem.OEUIntArray(ref_mol.GetMaxBondIdx())

                # Overlaps
                overlaps = oegraphsim.OEGetFPOverlap(ref_mol, targ_mol, ref_fp.GetFPTypeBase())

                for match in overlaps:
                    for bond in match.GetPatternBonds():
                        ref_bonds[bond.GetIdx()] += 1
                    for bond in match.GetTargetBonds():
                        targ_bonds[bond.GetIdx()] += 1

                for bond in targ_mol.GetBonds():
                    bond.SetData(tag, targ_bonds[bond.GetIdx()])

                for bond in ref_mol.GetBonds():
                    bond.SetData(tag, ref_bonds[bond.GetIdx()])

                # noinspection PyTypeChecker
                maxvalue = max((0, max(targ_bonds), max(ref_bonds)))

                # Create the color gradient
                colorg = oechem.OELinearColorGradient()
                colorg.AddStop(oechem.OEColorStop(0.0, oechem.OEPinkTint))
                colorg.AddStop(oechem.OEColorStop(1.0, oechem.OEYellow))
                colorg.AddStop(oechem.OEColorStop(maxvalue, oechem.OEDarkGreen))

                # Function that will color the bonds
                bondglyph = ColorBondByOverlapScore(colorg, tag)

                # Align the molecules
                overlaps = oegraphsim.OEGetFPOverlap(ref_mol, targ_mol, ref_fp.GetFPTypeBase())
                oedepict.OEPrepareMultiAlignedDepiction(targ_mol, ref_mol, overlaps)

                # Create the displays
                ref_disp = oemol_to_disp(ref_mol, ctx=ctx)
                targ_disp = oemol_to_disp(targ_mol, ctx=ctx)

                # Color the displays
                oegrapheme.OEAddGlyph(ref_disp, bondglyph, oechem.IsTrueBond())
                oegrapheme.OEAddGlyph(targ_disp, bondglyph, oechem.IsTrueBond())

                ref_displays.append(ref_disp)
                targ_displays.append(targ_disp)

            # Fingerprint was invalid
            else:
                tanimotos.append(None)
                ref_displays.append(None)
                targ_displays.append(None)

        # Molecule was invalid
        else:
            tanimotos.append(None)
            ref_displays.append(None)
            targ_displays.append(None)

    # Create the columns
    tanimoto_series = pl.Series(tanimoto_column, tanimotos, dtype=pl.Float64)
    ref_series = pl.Series(reference_similarity_column, ref_displays, dtype=oeplr.DisplayType())
    targ_series = pl.Series(target_similarity_column, targ_displays, dtype=oeplr.DisplayType())

    # Store molecule references in metadata to prevent GC (same as pandas version)
    ref_series.chem.metadata["molecules"] = ref_molecules
    targ_series.chem.metadata["molecules"] = targ_molecules

    # Add the columns to the DataFrame
    result = df.with_columns([tanimoto_series, ref_series, targ_series])

    return result


# Monkey-patch onto oepolars DataFrameChemNamespace
from oepolars.namespaces.dataframe import DataFrameChemNamespace
DataFrameChemNamespace.reset_depictions = _dataframe_reset_depictions
DataFrameChemNamespace.recalculate_depiction_coordinates = _dataframe_recalculate_depiction_coordinates
DataFrameChemNamespace.highlight_using_column = _dataframe_highlight_using_column
DataFrameChemNamespace.fingerprint_similarity = _dataframe_fingerprint_similarity


########################################################################################################################
# Register Polars formatters
########################################################################################################################

if ipython_present:

    def register_polars_formatters():
        """
        Register Polars DataFrame formatters for iPython/Jupyter display.

        This registers render_polars_dataframe as the HTML formatter for
        Polars DataFrames in iPython environments.

        Note: Calls to this function are idempotent.
        """
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']
            try:
                formatter = html_formatter.lookup(pl.DataFrame)
                if formatter is not render_polars_dataframe:
                    html_formatter.for_type(pl.DataFrame, render_polars_dataframe)
            except KeyError:
                html_formatter.for_type(pl.DataFrame, render_polars_dataframe)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register polars extension")

else:

    # iPython is not present, so we do not register a Polars formatter
    def register_polars_formatters():
        pass
