"""Backend-neutral column operations shared by the pandas and polars adapters.

The dataclasses report the outcome of an operation; the functions below are the
single implementation that every DataFrame accessor delegates to. Operations
never modify a caller's molecules: they work on copies and hand the replacements
back through :meth:`ColumnAdapter.replace_molecules`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Protocol

from openeye import oechem, oedepict, oegrapheme, oegraphsim

from cnotebook.core.align import create_aligner, fingerprint_maker
from cnotebook.core.context import CNotebookContext, create_local_context
from cnotebook.core.errors import warn
from cnotebook.core.helpers import create_structure_highlighter
from cnotebook.core.render import Depiction, make_depiction

# Cell values may hold several SMARTS patterns separated by pipes, commas, or whitespace
SMARTS_DELIMITER_RE = re.compile(r"\s*[|\r\n\t,]+\s*")

_PATTERN_TYPES = (str, oechem.OESubSearch, oechem.OEMCSSearch, oechem.OEQMol)
_OVERLAY_STYLES = ("overlay_default", "overlay_ball_and_stick")
_fingerprint_overlap_tag = oechem.OEGetTag("fingerprint_overlap")


@dataclass
class AlignmentReport:
    """Outcome of aligning one column of molecules.

    :param total: Number of rows visited.
    :param aligned: Rows whose copy was aligned.
    :param skipped_none: Rows holding ``None``.
    :param skipped_invalid: Rows holding invalid molecules.
    :param failed: Row positions where the aligner returned ``False``.
    """

    total: int = 0
    aligned: int = 0
    skipped_none: int = 0
    skipped_invalid: int = 0
    failed: list[int] = field(default_factory=list)


@dataclass
class SimilarityResult:
    """Outcome of a fingerprint-similarity computation over one column.

    :param tanimotos: Tanimoto per row, ``None`` for skipped rows.
    :param reference: Reference depictions per row, ``None`` for skipped rows.
    :param target: Target depictions per row, ``None`` for skipped rows.
    """

    tanimotos: list[float | None]
    reference: list[Depiction | None]
    target: list[Depiction | None]


class ColumnAdapter(Protocol):
    """What the column operations need from a backend column."""

    name: str

    def molecules(self) -> list[oechem.OEMolBase | None]: ...
    def replace_molecules(self, mols: list[oechem.OEMolBase | None]) -> None: ...
    def get_context(self, *, create: bool) -> CNotebookContext | None: ...
    def set_context(self, ctx: CNotebookContext) -> None: ...
    def clear_context(self) -> None: ...
    def set_alignment_report(self, report: AlignmentReport) -> None: ...


def _copy(mol: oechem.OEMolBase) -> oechem.OEMolBase:
    return oechem.OEQMol(mol) if isinstance(mol, oechem.OEQMolBase) else oechem.OEGraphMol(mol)


def _column_context(col: ColumnAdapter) -> CNotebookContext:
    """The column's context, created on demand.

    :param col: Column adapter.
    :returns: The adapter's context, or a fresh local one when it declined to create it.
    """
    ctx = col.get_context(create=True)
    return ctx if ctx is not None else create_local_context()


def parse_color(value: Any) -> oechem.OEColor | oechem.OEColorIter:
    """Accept an ``OEColor``, an ``OEColorIter`` or a ``#RRGGBB`` string.

    :param value: Color to interpret.
    :returns: The color or color iterator to highlight with.
    :raises ValueError: For strings that are not ``#RRGGBB``.
    :raises TypeError: For other types.
    """
    if isinstance(value, (oechem.OEColor, oechem.OEColorIter)):
        return value
    if isinstance(value, str):
        match = re.fullmatch(r"#([0-9a-fA-F]{2})([0-9a-fA-F]{2})([0-9a-fA-F]{2})", value.strip())
        if not match:
            raise ValueError(f"Colors given as strings must look like #RRGGBB (got {value!r})")
        return oechem.OEColor(*(int(part, 16) for part in match.groups()))
    raise TypeError(f"Unsupported color type {type(value).__name__}")


def highlight(
    col: ColumnAdapter, pattern: Any, *, color: Any = None, style: Any = "overlay_default",
    ref: Any = None, method: str | None = None, **align_kwargs: Any,
) -> AlignmentReport | None:
    """Add highlight callbacks for *pattern* to the column context; optionally align.

    The highlights live on the column context, so the molecules keep their own
    coordinates and every render applies the callbacks exactly once.

    :param col: Column adapter.
    :param pattern: SMARTS, ``OESubSearch``, ``OEMCSSearch``, ``OEQMol`` or an iterable of those.
    :param color: Highlight color(s); see :func:`parse_color`.
    :param style: Highlight style name or ``OEHighlightStyle`` constant.
    :param ref: Alignment reference forwarded to :func:`align_depictions` when given.
    :param method: Alignment method.
    :param align_kwargs: Extra aligner options.
    :returns: The alignment report when *ref* was given, else ``None``.
    :raises TypeError: For unsupported pattern types.
    """
    if isinstance(pattern, _PATTERN_TYPES):
        patterns: list[Any] | None = [pattern]
    elif isinstance(pattern, Iterable):
        patterns = list(pattern)
    else:
        patterns = None
    if patterns is None or any(not isinstance(p, _PATTERN_TYPES) for p in patterns):
        raise TypeError(
            "highlight patterns must be SMARTS strings, OESubSearch, OEMCSSearch or OEQMol objects"
        )

    ctx = _column_context(col)
    parsed_color = None if color is None else parse_color(color)
    for item in patterns:
        ctx.add_callback(create_structure_highlighter(query=item, color=parsed_color, style=style))
    col.set_context(ctx)

    if ref is not None:
        return align_depictions(col, ref, method=method, **align_kwargs)
    return None


def align_depictions(
    col: ColumnAdapter, ref: Any, method: str | None = None, **kwargs: Any
) -> AlignmentReport:
    """Align copies of the column's molecules to *ref* and commit them.

    :param col: Column adapter.
    :param ref: Molecule, SMARTS, search object, or ``"first"``.
    :param method: Alignment method.
    :param kwargs: Extra aligner options.
    :returns: The report (also stored through ``set_alignment_report``).
    """
    mols = col.molecules()
    report = AlignmentReport(total=len(mols))

    if isinstance(ref, str) and ref == "first":
        first = next((m for m in mols if m is not None and m.IsValid()), None)
        if first is None:
            warn(f"No valid molecule found in column {col.name!r} for depiction alignment")
            col.set_alignment_report(report)
            return report
        ref = _copy(first)

    # Alignment is chatty about molecules it cannot match; only real errors are useful here
    level = oechem.OEThrow.GetLevel()
    oechem.OEThrow.SetLevel(oechem.OEErrorLevel_Error)
    try:
        # create_aligner validates the method name itself and raises for anything unknown
        aligner = create_aligner(ref, method=method, **kwargs)  # type: ignore[arg-type]
        out: list[oechem.OEMolBase | None] = []
        for position, mol in enumerate(mols):
            if mol is None:
                report.skipped_none += 1
                out.append(None)
                continue
            if not mol.IsValid():
                report.skipped_invalid += 1
                out.append(mol)
                continue
            copy = _copy(mol)
            if aligner(copy):
                report.aligned += 1
            else:
                report.failed.append(position)
            out.append(copy)
    finally:
        oechem.OEThrow.SetLevel(level)

    col.replace_molecules(out)
    col.set_alignment_report(report)
    if report.failed:
        warn(
            f"Depiction alignment failed for {len(report.failed)} of {report.total} rows in column "
            f"{col.name!r} (positions {report.failed[:10]})"
        )
    return report


def set_render_options(col: ColumnAdapter, **options: Any) -> None:
    """Apply context options to the column context, creating it if needed.

    :param col: Column adapter.
    :param options: ``CNotebookContext`` attribute names and values.
    :raises TypeError: If an option is not a context attribute.
    """
    for name in options:
        if not isinstance(getattr(CNotebookContext, name, None), property):
            raise TypeError(f"Unknown render option {name!r}")
    ctx = _column_context(col)
    for name, value in options.items():
        setattr(ctx, name, value)
    col.set_context(ctx)


def reset_depictions(col: ColumnAdapter) -> None:
    """Remove the column context entirely.

    :param col: Column adapter.
    """
    col.clear_context()


def clear_formatting_rules(col: ColumnAdapter) -> None:
    """Drop the column's callbacks, keeping other options.

    :param col: Column adapter.
    """
    ctx = col.get_context(create=False)
    if ctx is not None:
        ctx.reset_callbacks()
        col.set_context(ctx)


def recalculate_depiction_coordinates(
    col: ColumnAdapter, *, clear_coords: bool = True, add_depiction_hydrogens: bool = True,
    perceive_bond_stereo: bool = True, suppress_explicit_hydrogens: bool = True,
    orientation: int = oedepict.OEDepictOrientation_Default,
) -> None:
    """Recompute 2D coordinates on copies and commit them.

    :param col: Column adapter.
    :param clear_coords: Discard existing 2D coordinates.
    :param add_depiction_hydrogens: Add explicit depiction hydrogens.
    :param perceive_bond_stereo: Perceive wedge/hash bond stereo.
    :param suppress_explicit_hydrogens: Suppress explicit hydrogens.
    :param orientation: Preferred 2D orientation.
    """
    opts = oedepict.OEPrepareDepictionOptions()
    opts.SetClearCoords(clear_coords)
    opts.SetAddDepictionHydrogens(add_depiction_hydrogens)
    opts.SetPerceiveBondStereo(perceive_bond_stereo)
    opts.SetSuppressHydrogens(suppress_explicit_hydrogens)
    opts.SetDepictOrientation(orientation)

    out: list[oechem.OEMolBase | None] = []
    for mol in col.molecules():
        if isinstance(mol, oechem.OEMolBase):
            copy = _copy(mol)
            oedepict.OEPrepareDepiction(copy, opts)
            out.append(copy)
        else:
            out.append(mol)
    col.replace_molecules(out)


def _parse_patterns(value: Any) -> list[oechem.OESubSearch]:
    """Turn a cell value into substructure searches (invalid entries are dropped).

    :param value: Delimited SMARTS, an ``OESubSearch``, an iterable of those, or ``None``.
    :returns: The usable substructure searches.
    """
    if value is None:
        return []
    if isinstance(value, oechem.OESubSearch):
        return [value] if value.IsValid() else []
    if isinstance(value, str):
        searches = [oechem.OESubSearch(p) for p in SMARTS_DELIMITER_RE.split(value) if p]
        return [s for s in searches if s.IsValid()]
    if isinstance(value, Iterable):
        found: list[oechem.OESubSearch] = []
        for item in value:
            found.extend(_parse_patterns(item))
        return found
    warn(f"Do not know how to highlight using: {type(value).__name__}")
    return []


def build_highlight_column(
    mols: list[Any], patterns: list[Any], *, colors: list[Any] | None = None,
    style: Any = "overlay_default", ctx: CNotebookContext,
) -> list[Depiction | None]:
    """Depict each molecule with its row's patterns highlighted.

    The displays are built without *ctx*'s callbacks: they are stored in a
    display column and the formatters apply that column's callbacks at render time.

    :param mols: Molecules (``None``/invalid rows yield ``None``).
    :param patterns: Per-row patterns (delimited SMARTS, searches, iterables, or ``None``).
    :param colors: Optional per-row colors; ``None`` entries use light colors.
    :param style: Highlight style.
    :param ctx: Render context for the displays.
    :returns: Depictions aligned with *mols*.
    """
    use_overlay = isinstance(style, str) and style in _OVERLAY_STYLES
    result: list[Depiction | None] = []
    for position, mol in enumerate(mols):
        if not isinstance(mol, oechem.OEMolBase) or not mol.IsValid():
            result.append(None)
            continue

        depiction = make_depiction(mol, ctx=ctx, apply_callbacks=False)
        color = (
            parse_color(colors[position])
            if colors is not None and colors[position] is not None
            else oechem.OEGetLightColors()
        )
        searches = _parse_patterns(patterns[position])

        # A single colour cannot drive the overlay highlighter, so those rows fall back below
        if use_overlay and not isinstance(color, oechem.OEColor):
            highlighter = oedepict.OEHighlightOverlayByBallAndStick(color)
            for search in searches:
                oedepict.OEAddHighlightOverlay(
                    depiction.display, highlighter, search.Match(depiction.mol, True)
                )
        else:
            # Plain highlighting takes one colour and one OEHighlightStyle constant
            if isinstance(color, oechem.OEColor):
                single = color
            else:
                single = next(iter(color), oechem.OEColor(oechem.OELightBlue))
            style_int = oedepict.OEHighlightStyle_BallAndStick if isinstance(style, str) else style
            for search in searches:
                for match in search.Match(depiction.mol, True):
                    oedepict.OEAddHighlighting(depiction.display, single, style_int, match)

        result.append(depiction)
    return result


class ColorBondByOverlapScore(oegrapheme.OEBondGlyphBase):
    """Bond glyph colouring bonds by fingerprint overlap score.

    See https://docs.eyesopen.com/toolkits/cookbook/python/depiction/simcalc.html
    """

    def __init__(self, cg: oechem.OELinearColorGradient, tag: int):
        """Create the glyph.

        :param cg: Colour gradient mapping overlap scores to colours.
        :param tag: OEChem data tag holding the per-bond overlap score.
        """
        oegrapheme.OEBondGlyphBase.__init__(self)
        self.colorg = cg
        self.tag = tag

    # OpenEye callback names are PascalCase by contract
    def RenderGlyph(self, disp, bond):
        bdisp = disp.GetBondDisplay(bond)
        if bdisp is None or not bdisp.IsVisible() or not bond.HasData(self.tag):
            return False
        color = self.colorg.GetColorAt(bond.GetData(self.tag))
        pen = oedepict.OEPen(color, color, oedepict.OEFill_Off, disp.GetScale() / 3.0)
        layer = disp.GetLayer(oedepict.OELayerPosition_Below)
        layer.DrawLine(
            disp.GetAtomDisplay(bond.GetBgn()).GetCoords(),
            disp.GetAtomDisplay(bond.GetEnd()).GetCoords(),
            pen,
        )
        return True

    def ColorBondByOverlapScore(self):
        return ColorBondByOverlapScore(self.colorg, self.tag).__disown__()


def _append_skipped_row(result: SimilarityResult) -> None:
    """Pad every list of *result* with a ``None`` for a row that has no similarity."""
    result.tanimotos.append(None)
    result.reference.append(None)
    result.target.append(None)


def fingerprint_similarity(
    mols: list[Any], ref: oechem.OEMolBase | None, *, fptype: str = "tree", num_bits: int = 4096,
    min_distance: int = 0, max_distance: int = 4,
    atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
    bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond, ctx: CNotebookContext,
) -> SimilarityResult:
    """Tanimoto and overlap-coloured depictions of each molecule against *ref*.

    :param mols: Molecules; ``None``/invalid rows produce ``None`` entries.
    :param ref: Reference molecule; the first valid molecule when ``None``.
    :param fptype: Fingerprint type ("path", "tree", "circular", "maccs" or "lingo").
    :param num_bits: Number of bits in the fingerprint.
    :param min_distance: Minimum distance/radius for path/circular/tree fingerprints.
    :param max_distance: Maximum distance/radius for path/circular/tree fingerprints.
    :param atom_type: Fingerprint atom types (``OEFPAtomType_`` bitmask or delimited names).
    :param bond_type: Fingerprint bond types (``OEFPBondType_`` bitmask or delimited names).
    :param ctx: Render context for the displays.
    :returns: :class:`SimilarityResult` aligned with *mols*.
    """
    empty = SimilarityResult([None] * len(mols), [None] * len(mols), [None] * len(mols))
    if ref is None:
        ref = next((m for m in mols if isinstance(m, oechem.OEMolBase) and m.IsValid()), None)
        if ref is None:
            warn("No valid reference molecule available for fingerprint similarity")
            return empty
    if not ref.IsValid():
        warn("Reference molecule is not valid")
        return empty

    make_fp = fingerprint_maker(fptype=fptype, num_bits=num_bits, min_distance=min_distance,
                                max_distance=max_distance, atom_type=atom_type, bond_type=bond_type)
    ref_fp = make_fp(ref)
    if not ref_fp.IsValid():
        warn("Fingerprint from reference molecule is invalid")
        return empty

    tag = _fingerprint_overlap_tag
    result = SimilarityResult([], [], [])
    for mol in mols:
        if not isinstance(mol, oechem.OEMolBase) or not mol.IsValid():
            _append_skipped_row(result)
            continue

        # Both molecules are copied: they are modified and then owned by their displays
        target_mol = oechem.OEMol(mol)
        ref_mol = oechem.OEMol(ref)
        target_fp = make_fp(target_mol)
        if not target_fp.IsValid():
            _append_skipped_row(result)
            continue

        result.tanimotos.append(oegraphsim.OETanimoto(ref_fp, target_fp))

        # Score each bond by how many fingerprint overlaps it takes part in
        target_bonds = [0] * target_mol.GetMaxBondIdx()
        ref_bonds = [0] * ref_mol.GetMaxBondIdx()
        for match in oegraphsim.OEGetFPOverlap(ref_mol, target_mol, ref_fp.GetFPTypeBase()):
            for bond in match.GetPatternBonds():
                ref_bonds[bond.GetIdx()] += 1
            for bond in match.GetTargetBonds():
                target_bonds[bond.GetIdx()] += 1
        for bond in target_mol.GetBonds():
            bond.SetData(tag, target_bonds[bond.GetIdx()])
        for bond in ref_mol.GetBonds():
            bond.SetData(tag, ref_bonds[bond.GetIdx()])

        maxvalue = max(0, max(target_bonds, default=0), max(ref_bonds, default=0))
        gradient = oechem.OELinearColorGradient()
        gradient.AddStop(oechem.OEColorStop(0.0, oechem.OEPinkTint))
        gradient.AddStop(oechem.OEColorStop(1.0, oechem.OEYellow))
        gradient.AddStop(oechem.OEColorStop(maxvalue, oechem.OEDarkGreen))
        glyph = ColorBondByOverlapScore(gradient, tag)

        oedepict.OEPrepareDepiction(ref_mol, False)
        oedepict.OEPrepareDepiction(target_mol, False)
        # The overlap iterator is consumed above, so ask for a fresh one to align with
        overlaps = oegraphsim.OEGetFPOverlap(ref_mol, target_mol, ref_fp.GetFPTypeBase())
        oedepict.OEPrepareMultiAlignedDepiction(target_mol, ref_mol, overlaps)

        # Displays are built without context callbacks; the formatters apply those per render
        ref_dep = Depiction(ref_mol, ctx.create_molecule_display(ref_mol))
        target_dep = Depiction(target_mol, ctx.create_molecule_display(target_mol))
        oegrapheme.OEAddGlyph(ref_dep.display, glyph, oechem.IsTrueBond())
        oegrapheme.OEAddGlyph(target_dep.display, glyph, oechem.IsTrueBond())
        result.reference.append(ref_dep)
        result.target.append(target_dep)
    return result
