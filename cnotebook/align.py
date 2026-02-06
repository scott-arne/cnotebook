import logging
from typing import Callable, Literal
from abc import ABCMeta, abstractmethod
from openeye import oegraphsim, oechem, oedepict

log = logging.getLogger("cnotebook")


########################################################################################################################
# Fingerprint generation
########################################################################################################################

# Dynamic creation of a typemap for OpenEye atom type fingerprints
atom_fp_typemap = dict(
    (x.replace("OEFPAtomType_", "").lower(), getattr(oegraphsim, x))
    for x in list(filter(lambda x: x.startswith("OEFPAtomType_"), dir(oegraphsim)))
)

# Dynamic creation of a typemap for OpenEye bond type fingerprints
bond_fp_typemap = dict(
    (x.replace("OEFPBondType_", "").lower(), getattr(oegraphsim, x))
    for x in list(filter(lambda x: x.startswith("OEFPBondType_"), dir(oegraphsim)))
)


def get_atom_mask(atom_type):
    """
    Get the OEFingerprint atom type masks from "|" delimited strings

    The atom_type string is composed of "|" delimted members from the OEFPAtomType_ namespace. These are
    case-insensitive and only optionally need to be prefixed by "OEFPAtomType_".

    :param atom_type: Delimited string of OEFPAtomTypes
    :return: Bitmask for OpenEye fingerprint atom types
    :rtype: int
    """
    atom_mask = oegraphsim.OEFPAtomType_None
    for m in atom_type.split("|"):
        mask = atom_fp_typemap.get(m.strip().lower().replace("oefpatomtype_", ""), None)
        if mask is None:
            raise KeyError(f'{m} is not a known OEAtomFPType')
        atom_mask |= mask
    # Check validity
    if atom_mask == oegraphsim.OEFPAtomType_None:
        raise ValueError("No atom fingerprint types configured")
    return atom_mask


def get_bond_mask(bond_type):
    """
    Get the OEFingerprint bond type masks from "|" delimited strings

    The bond_type string is composed of "|" delimted members from the OEFPBondType_ namespace. These are
    case-insensitive and only optionally need to be prefixed by "OEFPBondType_".

    :param bond_type: Delimited string of OEFPBondTypes
    :return: Bitmask for OpenEye fingerprint bond types
    :rtype: int
    """
    # Bond mask
    bond_mask = oegraphsim.OEFPBondType_None
    for m in bond_type.split("|"):
        mask = bond_fp_typemap.get(m.strip().lower().replace("oefpbondtype_", ""), None)
        if mask is None:
            raise KeyError(f'{m} is not a known OEBondFPType')
        bond_mask |= mask
    # Check validity
    if bond_mask == oegraphsim.OEFPBondType_None:
        raise ValueError("No bond fingerprint types configured")
    return bond_mask


def fingerprint_maker(
        fptype: str,
        num_bits: int,
        min_distance: int,
        max_distance: int,
        atom_type: str | int,
        bond_type: str | int
) -> Callable[[oechem.OEMolBase], oegraphsim.OEFingerPrint]:
    """
    Create a function that generates a fingerprint from a molecule
    :param fptype: Fingerprint type
    :param num_bits: Number of bits in the fingerprint
    :param min_distance: Minimum distance/radius for path/circular/tree
    :param max_distance: Maximum distance/radius for path/circular/tree
    :param atom_type: Atom type string delimited by "|" OR int bitmask from the oegraphsim.OEFPAtomType_ namespace
    :param bond_type: Bond type string delimited by "|" OR int bitmask from the oegraphsim.OEFPBondType_ namespace
    :return: Function that generates a fingerprint from a molecule
    """
    # Be forgiving with case
    _fptype = fptype.lower()

    # Convert atom type and bond type strings to masks if necessary
    atom_mask = get_atom_mask(atom_type) if isinstance(atom_type, str) else atom_type
    bond_mask = get_bond_mask(bond_type) if isinstance(bond_type, str) else bond_type
    if _fptype == "path":
        def _make_path_fp(mol):
            fp = oegraphsim.OEFingerPrint()
            oegraphsim.OEMakePathFP(fp, mol, num_bits, min_distance, max_distance, atom_mask, bond_mask)
            return fp
        return _make_path_fp
    elif _fptype == "circular":
        def _make_circular_fp(mol):
            fp = oegraphsim.OEFingerPrint()
            oegraphsim.OEMakeCircularFP(fp, mol, num_bits, min_distance, max_distance, atom_mask, bond_mask)
            return fp
        return _make_circular_fp
    elif _fptype == "tree":
        def _make_tree_fp(mol):
            fp = oegraphsim.OEFingerPrint()
            oegraphsim.OEMakeTreeFP(fp, mol, num_bits, min_distance, max_distance, atom_mask, bond_mask)
            return fp
        return _make_tree_fp
    elif _fptype == "maccs":
        def _make_maccs(mol):
            fp = oegraphsim.OEFingerPrint()
            oegraphsim.OEMakeMACCS166FP(fp, mol)
            return fp
        return _make_maccs
    elif _fptype == "lingo":
        def _make_lingo(mol):
            fp = oegraphsim.OEFingerPrint()
            oegraphsim.OEMakeLingoFP(fp, mol)
            return fp
        return _make_lingo
    raise KeyError(f'Unknown fingerprint type {fptype} (valid: path / tree / circular / maccs / lingo)')


########################################################################################################################
# Small molecule 2D structure aligners
########################################################################################################################

class Aligner(metaclass=ABCMeta):
    """Abstract base class for 2D molecule aligners.

    Aligners transform molecule 2D coordinates to align with a reference
    structure or pattern. Subclasses must implement :meth:`validate` and
    :meth:`align` methods.

    The aligner is callable - calling it with a molecule or display object
    will validate and then align the molecule if validation passes.
    """

    def __call__(self, mol_or_disp: oechem.OEMolBase | oedepict.OE2DMolDisplay) -> bool:

        # Get the molecule
        mol = mol_or_disp if isinstance(mol_or_disp, oechem.OEMolBase) else mol_or_disp.GetMolecule()

        try:
            log.debug("Aligner called for molecule: %s", oechem.OEMolToSmiles(mol) if mol else "None")
        except TypeError:
            log.debug("Aligner called for molecule: %s", mol)

        # If the molecule validates against the aligner
        if self.validate(mol):
            result = self.align(mol)
            log.debug("Alignment result: %s", result)
            return result

        log.debug("Molecule failed validation, skipping alignment")
        return False

    @abstractmethod
    def align(self, mol: oechem.OEMolBase) -> bool:
        """Align the molecule to the reference.

        :param mol: Molecule to align (will be modified in place).
        :returns: True if alignment was successful.
        """
        raise NotImplementedError

    @abstractmethod
    def validate(self, mol: oechem.OEMolBase) -> bool:
        """Validate that the molecule can be aligned.

        :param mol: Molecule to validate.
        :returns: True if the molecule can be aligned.
        """
        raise NotImplementedError


class OESubSearchAligner(Aligner):
    """Aligner using substructure search for 2D molecule alignment."""

    def __init__(self, ref: oechem.OESubSearch | oechem.OEMolBase | str, **_kwargs):
        """Create a substructure-based aligner.

        :param ref: Reference for alignment. Can be:

            - ``OESubSearch``: Pre-configured substructure search object.
            - ``OEMolBase``: Molecule to use as substructure pattern.
            - ``str``: SMARTS pattern string.

        :param _kwargs: Additional keyword arguments (ignored, for API compatibility).
        """
        # Reference molecule with 2D coordinates
        self.refmol = None

        if isinstance(ref, (oechem.OESubSearch, str)):
            self.ss = oechem.OESubSearch(ref)

        else:
            self.refmol = oechem.OEGraphMol(ref)
            # Ensure the reference molecule has proper 2D depiction coordinates
            oedepict.OEPrepareDepiction(self.refmol, False)
            self.ss = oechem.OESubSearch(self.refmol, oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)

    def validate(self, mol: oechem.OEMolBase) -> bool:
        """
        Validate that the molecule has a match to this substructure search.

        :param mol: Molecule to search.
        :returns: True if there is a match to this substructure search.
        """
        oechem.OEPrepareSearch(mol, self.ss)
        return self.ss.SingleMatch(mol)

    def align(self, mol: oechem.OEMolBase) -> bool:
        """
        Align molecule to the substructure pattern.

        :param mol: Molecule to align.
        :returns: True if the alignment was successful.
        """
        oechem.OEPrepareSearch(mol, self.ss)
        alignres = oedepict.OEPrepareAlignedDepiction(mol, self.ss)
        result = alignres.IsValid()
        log.debug("OEPrepareAlignedDepiction (substructure) returned: %s", result)
        return result


class OEMCSSearchAligner(Aligner):
    """Aligner using Maximum Common Substructure (MCS) search for 2D molecule alignment."""

    def __init__(
            self,
            ref: oechem.OEMCSSearch | oechem.OEMolBase,
            *,
            func: Literal["atoms", "bonds", "atoms_and_cycles", "bonds_and_cycles"] = "bonds_and_cycles",
            min_atoms: int = 1,
            **_kwargs
    ):
        """Create an MCS-based aligner.

        :param ref: Reference for alignment. Can be:

            - ``OEMCSSearch``: Pre-configured MCS search object.
            - ``OEMolBase``: Reference molecule for MCS calculation.

        :param func: MCS evaluation function to use:

            - ``"atoms"``: Maximize atom count.
            - ``"bonds"``: Maximize bond count.
            - ``"atoms_and_cycles"``: Maximize atoms while preserving complete cycles.
            - ``"bonds_and_cycles"``: Maximize bonds while preserving complete cycles.

        :param min_atoms: Minimum number of atoms required in the MCS.
        :param _kwargs: Additional keyword arguments (ignored, for API compatibility).
        """
        self.refmol = None

        if isinstance(ref, oechem.OEMCSSearch):
            self.mcss = oechem.OEMCSSearch(ref)

        else:
            self.refmol = ref.CreateCopy()
            # Ensure the reference molecule has proper 2D depiction coordinates
            oedepict.OEPrepareDepiction(self.refmol, False)

            # Currently just using default parameters
            self.mcss = oechem.OEMCSSearch(oechem.OEMCSType_Approximate)
            self.mcss.Init(self.refmol, oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)

            if func == "atoms":
                self.mcss.SetMCSFunc(oechem.OEMCSMaxAtoms())
            elif func == "bonds":
                self.mcss.SetMCSFunc(oechem.OEMCSMaxBonds())
            elif func == "atoms_and_cycles":
                self.mcss.SetMCSFunc(oechem.OEMCSMaxAtomsCompleteCycles())
            elif func == "bonds_and_cycles":
                self.mcss.SetMCSFunc(oechem.OEMCSMaxBondsCompleteCycles())
            else:
                raise ValueError(f'Unknown MCS evaluation function name: {func}')

            # Other options
            self.mcss.SetMinAtoms(min_atoms)

    def validate(self, mol: oechem.OEMolBase) -> bool:
        """
        Validate that a maximum common substructure exists in a query molecule.

        :param mol: Molecule to search.
        :returns: True if the molecule contains the maximum common substructure.
        """
        return self.mcss.SingleMatch(mol)

    def align(self, mol: oechem.OEMolBase) -> bool:
        """
        Align molecule using the maximum common substructure.

        :param mol: Molecule to align.
        :returns: True if the alignment was successful.
        """
        alignres = oedepict.OEPrepareAlignedDepiction(mol, self.mcss)
        result = alignres.IsValid()
        log.debug("OEPrepareAlignedDepiction (MCS) returned: %s", result)
        return result


class OEFingerprintAligner(Aligner):
    """Aligner using fingerprint similarity and overlap for 2D molecule alignment.

    This aligner uses molecular fingerprints to identify common structural
    features between molecules and aligns based on the fingerprint overlap.
    """

    def __init__(
            self,
            refmol: oechem.OEMolBase,
            *,
            threshold: float = 0.4,
            fptype: str = "tree",
            num_bits: int = 4096,
            min_distance: int = 0,
            max_distance: int = 4,
            atom_type: str | int = oegraphsim.OEFPAtomType_DefaultTreeAtom,
            bond_type: str | int = oegraphsim.OEFPBondType_DefaultTreeBond
    ):
        """Create a fingerprint-based aligner.

        :param refmol: Reference molecule for alignment.
        :param threshold: Minimum Tanimoto similarity required to attempt alignment.
        :param fptype: Fingerprint type ("path", "circular", or "tree").
        :param num_bits: Number of bits in the fingerprint.
        :param min_distance: Minimum path/radius distance for fingerprint.
        :param max_distance: Maximum path/radius distance for fingerprint.
        :param atom_type: Atom type for fingerprint generation. Can be an integer
            constant or a string name (e.g., "default", "aromaticity").
        :param bond_type: Bond type for fingerprint generation. Can be an integer
            constant or a string name (e.g., "default", "inring").
        """
        # Similarity threshold to apply alignment
        self.threshold = threshold

        # Fingerprint maker
        self.make_fp = fingerprint_maker(
            fptype=fptype,
            num_bits=num_bits,
            min_distance=min_distance,
            max_distance=max_distance,
            atom_type=atom_type,
            bond_type=bond_type

        )

        # Reference molecule and fingerprint
        self.refmol = oechem.OEGraphMol(refmol)
        self.reffp = None
        self.fptype = None

        if self.refmol.IsValid():
            # Ensure the reference molecule has proper 2D depiction coordinates (but retain existing coordinates)
            oedepict.OEPrepareDepiction(self.refmol, False)
            self.reffp = self.make_fp(self.refmol)
            self.fptype = self.reffp.GetFPTypeBase()

        else:
            log.warning("Reference molecule for fingerprint-based alignment is not valid")

    def validate(self, mol: oechem.OEMolBase) -> bool:
        if self.reffp is None:
            return False

        fp = self.make_fp(mol)
        sim = oegraphsim.OETanimoto(fp, self.reffp)
        log.debug("Fingerprint Tanimoto similarity: %.3f (threshold: %.3f)", sim, self.threshold)
        return sim >= self.threshold

    def align(self, mol: oechem.OEMolBase) -> bool:
        if self.fptype is None:
            return False

        overlaps = oegraphsim.OEGetFPOverlap(self.refmol, mol, self.fptype)
        result = oedepict.OEPrepareMultiAlignedDepiction(mol, self.refmol, overlaps)

        log.debug("OEPrepareMultiAlignedDepiction (FP) returned: %s", result)
        return result


# Aligners registry
_ALIGNERS = {
    "substructure": OESubSearchAligner,
    "fingerprint": OEFingerprintAligner,
    "mcss": OEMCSSearchAligner
}


def create_aligner(
        ref: oechem.OEMolBase | oechem.OESubSearch | oechem.OEMCSSearch | str,
        method: Literal["substructure", "ss", "mcss", "fp", "fingerprint"] = None,
        **kwargs
) -> Aligner:
    """
    Create an aligner for the given reference.

    :param ref: Alignment reference - can be a molecule, substructure search, MCS search, or SMARTS string.
    :param method: Alignment method ("substructure"/"ss", "mcss", "fingerprint"/"fp").
        If None, the method is auto-detected based on the reference type.
    :param kwargs: Keyword arguments passed to the aligner constructor.
    :returns: Configured aligner instance.
    """
    # Normalize the method
    if method is not None:
        _method = method.lower()

        if _method in ("substructure", "ss"):
            method = "substructure"
        elif _method in ("fingerprint", "fp"):
            method = "fingerprint"
        elif _method == "mcss":
            method = "mcss"
        else:
            raise ValueError(
                f'Unknown depiction alignment method: {method}. Valid options: '
                '"substructure"/"ss", "mcss", "fingerprint"/"fp".'
            )

    # Auto-detect method based on reference type if not specified
    if isinstance(ref, str):
        # SMARTS string - use substructure aligner
        log.debug("Using substructure aligner for SMARTS string alignment reference")
        return OESubSearchAligner(ref, **kwargs)

    elif isinstance(ref, oechem.OESubSearch):
        log.debug("Using substructure aligner for oechem.OESubSearch alignment reference")
        return OESubSearchAligner(ref, **kwargs)

    elif isinstance(ref, oechem.OEMCSSearch):
        log.debug("Using MCS aligner for oechem.OEMCSSearch alignment reference")
        return OEMCSSearchAligner(ref, **kwargs)

    elif isinstance(ref, oechem.OEMolBase):
        # Use specified method or default to fingerprint
        if method == "substructure":
            log.debug("Using substructure aligner for oechem.OEMolBase alignment reference")
            return OESubSearchAligner(ref, **kwargs)
        elif method == "mcss":
            log.debug("Using MCS aligner for oechem.OEMolBase alignment reference")
            return OEMCSSearchAligner(ref, **kwargs)
        else:
            # Default to fingerprint aligner for molecules
            log.debug("Using fingerprint aligner for oechem.OEMolBase alignment reference")
            return OEFingerprintAligner(ref, **kwargs)

    else:
        raise TypeError(f'Unsupported alignment reference type: {type(ref)}.')
