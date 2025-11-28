import re
import logging
import typing
import pandas as pd
import oepandas as oepd
from pandas.api.extensions import register_dataframe_accessor, register_series_accessor
from typing import Iterable, Any, Literal, Hashable
from openeye import oechem, oedepict, oegraphsim, oegrapheme
from copy import copy as shallow_copy
from .context import pass_cnotebook_context, get_series_context
from .helpers import escape_brackets, create_structure_highlighter
from .align import create_aligner, fingerprint_maker
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


SMARTS_DELIMITER_RE = re.compile(r'\s*[|\r\n\t]+\s*')

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
    Closure that creates a function that renders an OEMol to HTML
    :param ctx: Render context
    :param callbacks: List of callbacks to modify the rendering of the molecule
    :return: Function that renders molecules to HTML
    """

    def _oedisp_to_html(disp: oedepict.OE2DMolDisplay) -> str:

        if isinstance(disp, oedepict.OE2DMolDisplay) and disp.IsValid():
            # Copy the display, as not to modify the original with callbacks
            # TODO: Update with ctx
            disp_to_render = oedepict.OE2DMolDisplay(disp)

            # Apply display callbacks
            if callbacks is not None:
                for callback in callbacks:
                    callback(disp_to_render)

            return oedisp_to_html(disp_to_render, ctx=ctx)
        return str(disp)

    return _oedisp_to_html


def escape_formatter(obj: Any) -> str:
    return escape_brackets(str(obj))


def render_dataframe(
        df: pd.DataFrame,
        formatters: dict | None = None,
        col_space: dict[str, float | int] | None = None,
        **kwargs
) -> str:
    """
    Render a DataFrame with molecules
    :param df: DataFrame to render
    :param formatters: Custom formatters for displaying columns
    :param col_space: Custom column spacing
    :param kwargs: Additional keyword arguments for DataFrame.to_html
    :return: HTML of rendered DataFrame
    """
    # Defaults are empty dictionaries for these
    formatters = formatters or {}
    col_space = col_space or {}

    # Render columns with MoleculeDtype
    molecule_columns = set()

    for col in df.columns:
        if isinstance(df.dtypes[col], oepd.MoleculeDtype):
            molecule_columns.add(col)

    # We need to copy both the DataFrame and the molecules, because we modify them in-place to render them
    df = df.copy()

    for col in molecule_columns:
        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = df[col].array
        assert isinstance(arr, oepd.MoleculeArray)
        df[col] = pd.Series(arr.deepcopy(), index=df[col].index, dtype=oepd.MoleculeDtype())

    # ---------------------------------------------------
    # Molecule columns
    # ---------------------------------------------------

    if len(molecule_columns) > 0:
        log.debug(f'Detected molecule columns: {", ".join(molecule_columns)}')

    # Create formatters for each column
    for col in molecule_columns:

        # Create the formatter for this column
        if col in formatters:
            log.warning(f'Overwriting existing formatter for {col} with a molecule formatter')

        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = df[col].array
        assert isinstance(arr, oepd.MoleculeArray)

        # Get the cnotebook options for this column
        ctx = get_series_context(arr.metadata)

        formatters[col] = create_mol_formatter(ctx=ctx)

        # Record the column width
        if col in col_space:
            log.warning(f'Column spacing for {col} already defined by overwriting with molecule image width')

        col_space[col] = float(ctx.width)

    # ---------------------------------------------------
    # Display columns
    # ---------------------------------------------------

    # Render columns with DisplayDtype
    display_columns = set()

    for col in df.columns:
        if isinstance(df.dtypes[col], oepd.DisplayDtype):
            display_columns.add(col)

    if len(display_columns) > 0:
        log.debug(f'Detected display columns: {", ".join(display_columns)}')

    for col in display_columns:

        # Get the underlying display array
        # Direct assignment to help IDE understand this is a DisplayArray
        arr = df[col].array
        assert isinstance(arr, oepd.DisplayArray)

        # Get column metadata
        ctx = get_series_context(arr.metadata)

        formatters[col] = create_disp_formatter(ctx=ctx)

        if len(arr) > 0:
            col_space[col] = max(disp.GetWidth() for disp in arr if isinstance(disp, oedepict.OE2DMolDisplay))
            col_space[col] = max(0, col_space[col])
        else:
            col_space[col] = 0

    # ---------------------------------------------------
    # All other columns
    # ---------------------------------------------------

    for col in df.columns:
        if col not in display_columns and col not in molecule_columns:
            formatters[col] = escape_formatter

    return df.to_html(escape=False, formatters=formatters, col_space=col_space, **kwargs)


########################################################################################################################
# Register Pandas formatters
########################################################################################################################

if ipython_present:

    def register_pandas_formatters():
        """
        Modify how the notebook is told how to display Pandas Dataframes - this actually is more flexible because it
        will still work with other custom changes to to_html().

        Note: Calls to this function are idempotent.
        """
        ipython_instance = get_ipython()

        if ipython_instance is not None:
            html_formatter = ipython_instance.display_formatter.formatters['text/html']
            try:
                formatter = html_formatter.lookup(pd.DataFrame)
                if formatter is not render_dataframe:
                    html_formatter.for_type(pd.DataFrame, render_dataframe)
            except KeyError:
                html_formatter.for_type(pd.DataFrame, render_dataframe)
        else:
            log.debug("[cnotebook] iPython installed but not in use - cannot register pandas extension")

else:

    # iPython is not present, so we do not register a Pandas formatter
    def register_pandas_formatters():
        pass


########################################################################################################################
# Series accessors
########################################################################################################################

@register_series_accessor("highlight")
class SeriesHighlightAccessor:
    def __init__(self, pandas_obj: pd.Series):
        if not isinstance(pandas_obj.dtype, oepd.MoleculeDtype):
            raise TypeError(
                "subsearch only works on molecule columns (oepandas.MoleculeDtype). If this column has "
                "molecules, use pd.Series.as_molecule to convert to a molecule column first."
            )

        self._obj = pandas_obj

    def __call__(
            self,
            pattern: Iterable[str] | str | oechem.OESubSearch | Iterable[oechem.OESubSearch],
            *,
            color: oechem.OEColor = oechem.OEColor(oechem.OELightBlue),
            style: int = oedepict.OEHighlightStyle_Stick,
            ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEQMol | Literal["first"] | oechem.OEMolBase | None = None,  # noqa
            method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] | None = None
    ) -> None:
        """
        Highlight chemical features in a structure

        The pattern argument can be:
            - SMARTS pattern
            - oechem.OESubSearch or oechem.OEMCSSearch object
            - Iterable of SMARTS patterns, oechem.OESubSearch, and/or oechem.OEMCSSearch objects

        :param pattern: Pattern(s) to highlight in the molecule
        :param color: Highlight color
        :param style: Highlight style
        :return: Callback to highlight the pattern(s) in the molecule
        """
        # Get the molecule array
        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = self._obj.array
        assert isinstance(arr, oepd.MoleculeArray)

        # Get / create a series context and save it (because we are modifying it locally)
        ctx = get_series_context(arr.metadata, save=True)

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
            self._obj.align_depictions(ref=ref, method=method)


@register_series_accessor("recalculate_depiction_coordinates")
class SeriesRecalculateDepictionCoordinatesAccessor:
    def __init__(self, pandas_obj: pd.Series):
        if not isinstance(pandas_obj.dtype, oepd.MoleculeDtype):
            raise TypeError(
                "recalculate_depiction_coordinates only works on molecule columns (oepandas.MoleculeDtype). If this "
                "column has molecules, use pd.Series.as_molecule to convert to a molecule column first."
            )

        self._obj = pandas_obj

    def __call__(
            self,
            *,
            clear_coords: bool = True,
            add_depction_hydrogens: bool = True,
            perceive_bond_stereo: bool = True,
            suppress_explicit_hydrogens: bool = True,
            orientation: int = oedepict.OEDepictOrientation_Default
    ) -> None:
        """
        Recalculate the depictions for a molecule series.

        See the following link for more information:
        https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

        :param clear_coords: Clear existing 2D coordinates
        :param add_depction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
        :param perceive_bond_stereo: Perceive wedge/hash bond stereo
        :param suppress_explicit_hydrogens: Suppress explicit hydrogens
        :param orientation: Preferred 2D orientation
        """
        # Create the depiction options
        opts = oedepict.OEPrepareDepictionOptions()
        opts.SetClearCoords(clear_coords)
        opts.SetAddDepictionHydrogens(add_depction_hydrogens)

        for mol in self._obj.array:
            if isinstance(mol, oechem.OEMolBase):
                oedepict.OEPrepareDepiction(mol, opts)


@register_series_accessor("reset_depictions")
class SeriesResetDepictionsAccessor:
    def __init__(self, pandas_obj: pd.Series):
        self._obj = pandas_obj

    def __call__(self) -> None:
        """
        Reset depiction callbacks for a molecule series
        """
        # Check if array has metadata attribute (should be true for oepandas arrays)
        if hasattr(self._obj.array, "metadata"):
            # Direct assignment to help IDE understand this has metadata
            arr = self._obj.array
            assert isinstance(arr, oepd.MoleculeArray)
            _ = arr.metadata.pop("cnotebook", None)


@register_series_accessor("align_depictions")
class SeriesAlignDepictionsAccessor:
    def __init__(self, pandas_obj: pd.Series):
        if not isinstance(pandas_obj.dtype, oepd.MoleculeDtype):
            raise TypeError(
                "align_depictions only works on molecule columns (oepandas.MoleculeDtype). If this "
                "column has molecules, use pd.Series.as_molecule to convert to a molecule column first."
            )

        self._obj = pandas_obj

    def __call__(
            self,
            ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | oechem.OEQMol | Literal["first"],
            method: Literal["substructure", "ss", "mcss", "fp", "fingerprint"] | None = None,
            **kwargs
    ) -> None:
        """
        Align the 2D coordinates of molecules
        :param align: Alignment reference
        :param kwargs: Keyword arguments for aligner
        :return: Aligned molecule depictions
        """
        # Get the rendering context for creating the displays

        # TODO: Maybe do this smarter so that you know if the context is column-level, which means you could copy that
        #       context into the new DisplayArray that you'll create below? Or even link the contexts?

        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = self._obj.array
        assert isinstance(arr, oepd.MoleculeArray)

        if isinstance(ref, str) and ref == "first":
            for mol in arr:
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
            aligner = create_aligner(ref=ref, method=method)

            for mol in arr:
                _ = aligner(mol)

        except Exception:
            # We don't care if the aligners fail - it just results in unaligned structures (NBD)
            pass

        # Restore OEThrow
        finally:
            oechem.OEThrow.SetLevel(level)


########################################################################################################################
# DataFrame accessors
########################################################################################################################

@register_dataframe_accessor("recalculate_depiction_coordinates")
class SeriesRecalculateDepictionCoordinatesAccessor:
    def __init__(self, pandas_obj: pd.DataFrame):
        self._obj = pandas_obj

    def __call__(
            self,
            *,
            molecule_columns: str | Iterable[str] | None = None,
            clear_coords: bool = True,
            add_depction_hydrogens: bool = True,
            perceive_bond_stereo: bool = True,
            suppress_explicit_hydrogens: bool = True,
            orientation: int = oedepict.OEDepictOrientation_Default
    ) -> None:
        """
        Recalculate the depictions for a one or more molecule series in a DataFrame. If molecule_columns is None,
        which is the default, then all molecule columns will have their depictions recalculated

        See the following link for more information:
        https://docs.eyesopen.com/toolkits/python/depicttk/OEDepictClasses/OEPrepareDepictionOptions.html

        :param molecule_columns: Optional molecule column(s) to have depictions recalculated
        :param clear_coords: Clear existing 2D coordinates
        :param add_depction_hydrogens: Add explicit depiction hydrogens for faithful stereo depiction, etc.
        :param perceive_bond_stereo: Perceive wedge/hash bond stereo
        :param suppress_explicit_hydrogens: Suppress explicit hydrogens
        :param orientation: Preferred 2D orientation
        """
        if molecule_columns is None:
            molecule_columns = set()

            for col in self._obj.columns:
                if isinstance(self._obj.dtypes[col], oepd.MoleculeDtype):
                    molecule_columns.add(col)

        elif isinstance(molecule_columns, str):
            molecule_columns = {molecule_columns}

        else:
            molecule_columns = set(molecule_columns)

        # Recalculate the column depictions
        for col in molecule_columns:

            if col in self._obj.columns:
                if isinstance(self._obj.dtypes[col], oepd.MoleculeDtype):
                    self._obj[col].recalculate_depiction_coordinates(
                        clear_coords=clear_coords,
                        add_depction_hydrogens=add_depction_hydrogens,
                        perceive_bond_stereo=perceive_bond_stereo,
                        suppress_explicit_hydrogens=suppress_explicit_hydrogens,
                        orientation=orientation
                    )

                else:
                    log.warning(f'Column {col} does not have a MoleculeDtype')

            else:
                log.warning(f'{col} not found in DataFrame columns: ({", ".join(self._obj.columns)})')
                molecule_columns.remove(col)


@register_dataframe_accessor("reset_depictions")
class SeriesResetDepictionsAccessor:
    def __init__(self, pandas_obj: pd.DataFrame):
        self._obj = pandas_obj

    def __call__(self, *, molecule_columns: str | Iterable[str] | None = None) -> None:
        """
        Reset depiction callbacks for one or more columns
        """
        columns = set()
        if molecule_columns is None:
            columns.update(self._obj.columns)

        elif isinstance(molecule_columns, str):
            columns.add(molecule_columns)

        else:
            columns.update(molecule_columns)

        # Filter invalid and non-molecule columns
        for col in filter(
            lambda c: c in self._obj.columns and isinstance(self._obj[c].dtype, oepd.MoleculeDtype),
            columns
        ):
            self._obj[col].reset_depictions()


@register_dataframe_accessor("highlight_using_column")
class HighlightUsingColumnAccessor:
    def __init__(self, pandas_obj: pd.DataFrame):
        self._obj = pandas_obj

    def __call__(
            self,
            molecule_column: str,
            pattern_column: str,
            *,
            highlighted_column: str = "highlighted_substructures",
            ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase | None = None,
            alignment_opts: oedepict.OEAlignmentOptions | None = None,
            prepare_opts: oedepict.OEPrepareDepictionOptions | None = None,
            inplace: bool = False
    ) -> pd.DataFrame:
        """
        Highlight molecules based on the value of another column. The column produced is a DisplayArray column, so
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
        :param inplace: Modify the DataFrame in place
        :return: Modified DataFrame
        """
        # Object we are operating on
        df = self._obj if inplace else self._obj.copy()

        if molecule_column not in df.columns:
            raise KeyError(f'{molecule_column} not found in DataFrame columns: ({", ".join(df.columns)}')

        if not isinstance(df[molecule_column].dtype, oepd.MoleculeDtype):
            raise TypeError(
                f"highlight_using_column only works on molecule columns (oepandas.MoleculeDtype). If {molecule_column}"
                " has molecules, use pd.Series.as_molecule to convert to a molecule column first."
            )

        if pattern_column not in df.columns:
            raise KeyError(f'{pattern_column} not found in DataFrame columns: ({", ".join(df.columns)}')

        # Create the display objects
        indexes = []
        displays = []

        # Get the rendering context for creating the displays
        # TODO: Maybe do this smarter so that you know if the context is column-level, which means you could copy that
        #       context into the new DisplayArray that you'll create below? Or even link the contexts?
        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = df[molecule_column].array
        assert isinstance(arr, oepd.MoleculeArray)
        ctx = get_series_context(arr.metadata)

        for idx, row in df.iterrows():
            indexes.append(idx)

            mol = row[molecule_column]
            if isinstance(mol, oechem.OEMolBase):

                # Create the display
                disp = oemol_to_disp(mol, ctx=ctx)

                # Highlight
                substructures = []
                patterns = row[pattern_column]

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

                else:
                    log.warning(f'Do not know how to highlight using: {type(patterns).__name__}')

                # Apply substructure highlights
                highlight = oedepict.OEHighlightOverlayByBallAndStick(oechem.OEGetLightColors())

                for ss in substructures:
                    oedepict.OEAddHighlightOverlay(disp, highlight, ss.Match(mol, True))

                displays.append(disp)

            else:
                displays.append(None)

        df[highlighted_column] = pd.Series(displays, index=indexes, dtype=oepd.DisplayDtype())
        return df


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


@register_dataframe_accessor("fingerprint_similarity")
class FingerprintSimilaritySeriesAccessor:
    def __init__(self, pandas_obj: pd.DataFrame):
        self._obj = pandas_obj
        self._tag = oechem.OEGetTag("fingerprint_overlap")

    def __call__(
            self,
            molecule_column: str,
            ref: oechem.OEMolBase | None = None,
            *,
            tanimoto_column="fingerprint_tanimoto",
            reference_similarity_column="reference_similarity",
            target_similarity_column="target_similarity",
            fptype: str = "tree",
            num_bits: int = 4096,
            min_distance: int = 0,
            max_distance: int = 4,
            atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
            bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond,
            inplace: bool = False
    ) -> pd.DataFrame:
        """
        Color molecules by fingerprint similarity
        :param ref: Reference molecule
        :param fptype: Fingerprint type
        :param num_bits: Number of bits in the fingerprint
        :param min_distance: Minimum distance/radius for path/circular/tree
        :param max_distance: Maximum distance/radius for path/circular/tree
        :param atom_type: Atom type string delimited by "|" OR int bitmask from the oegraphsim.OEFPAtomType_ namespace
        :param bond_type: Bond type string delimited by "|" OR int bitmask from the oegraphsim.OEFPBondType_ namespace
        :return:
        """
        # Preprocess
        df = self._obj if inplace else self._obj.copy()

        if molecule_column not in df.columns:
            raise KeyError(f'Molecule column not found in DataFrame: {molecule_column}')

        if not isinstance(df[molecule_column].dtype, oepd.MoleculeDtype):
            raise TypeError("Column {} does not have dtype oepd.MoleculeDtype ({})".format(
                molecule_column, str(df[molecule_column].dtype)))

        # Get the context
        # Direct assignment to help IDE understand this is a MoleculeArray
        arr = self._obj[molecule_column].array
        assert isinstance(arr, oepd.MoleculeArray)
        ctx = get_series_context(arr.metadata)

        # If we're using the first molecule as our reference
        if ref is None:
            for mol in arr:  # type: oechem.OEMol
                if mol.IsValid():
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

        # Create the display objects
        ref_displays = []
        targ_displays = []

        # FIXME: See now below regarding the fact we have to cache the reference and target molecule copies
        ref_molecules = []
        targ_molecules = []

        tanimotos = []
        index = []

        for idx, mol in df[molecule_column].items():  # type: Hashable, oechem.OEMol
            index.append(idx)
            if mol is not None and mol.IsValid():

                # Copy the molecules, because we're modifying them
                targ_mol = oechem.OEMol(mol)
                ref_mol = oechem.OEMol(ref)

                # FIXME: See now below regarding the fact we have to cache the reference and target molecule copies
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
                        bond.SetData(self._tag, targ_bonds[bond.GetIdx()])

                    for bond in ref_mol.GetBonds():
                        bond.SetData(self._tag, ref_bonds[bond.GetIdx()])

                    # noinspection PyTypeChecker
                    maxvalue = max((0, max(targ_bonds), max(ref_bonds)))

                    # Create the color gradient
                    colorg = oechem.OELinearColorGradient()
                    colorg.AddStop(oechem.OEColorStop(0.0, oechem.OEPinkTint))
                    colorg.AddStop(oechem.OEColorStop(1.0, oechem.OEYellow))
                    colorg.AddStop(oechem.OEColorStop(maxvalue, oechem.OEDarkGreen))

                    # Function that will color the bonds
                    bondglyph = ColorBondByOverlapScore(colorg, self._tag)

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
                    ref_displays.append(None)
                    targ_displays.append(None)

            # Molecule was invalid
            else:
                ref_displays.append(None)
                targ_displays.append(None)

        # Add the columns
        df[tanimoto_column] = pd.Series(
            tanimotos,
            index=index,
            dtype=float
        )

        # FIXME: Submitted to OpenEye as Case #00037423
        #        We need to keep the copies of the molecules that we made above, or they will be garbage collected
        #        and the OE2DMolDisplay objects will segfault. We'll keep those in the metadata now for the arrays.
        ref_arr = oepd.DisplayArray(ref_displays, metadata={"molecules": ref_molecules})
        targ_arr = oepd.DisplayArray(targ_displays, metadata={"molecules": targ_molecules})

        df[reference_similarity_column] = pd.Series(
            ref_arr,
            index=shallow_copy(index),
            dtype=oepd.DisplayDtype()
        )

        df[target_similarity_column] = pd.Series(
            targ_arr,
            index=shallow_copy(index),
            dtype=oepd.DisplayDtype()
        )

        return df
