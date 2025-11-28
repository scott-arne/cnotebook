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
    """
    Base class for a 2D molecule aligner
    """
    def __call__(self, mol_or_disp: oechem.OEMolBase | oedepict.OE2DMolDisplay) -> bool:

        # Get the molecule
        mol = mol_or_disp if isinstance(mol_or_disp, oechem.OEMolBase) else mol_or_disp.GetMolecule()

        # If the molecule validates against the aligner
        if self.validate(mol):
            return self.align(mol)

        return False

    @abstractmethod
    def align(self, mol: oechem.OEMolBase) -> bool:
        raise NotImplementedError

    @abstractmethod
    def validate(self, mol: oechem.OEMolBase) -> bool:
        raise NotImplementedError


class OESubSearchAligner(Aligner):
    """
    2D molecule substructure alignment
    """
    def __init__(self, ref: oechem.OESubSearch | oechem.OEMolBase, **_kwargs):

        # Reference molecule with 2D coordinates
        self.refmol = None

        # In the future, make these configurable
        self.alignment_options = oedepict.OEAlignmentOptions()

        if isinstance(ref, oechem.OESubSearch):
            self.ss = oechem.OESubSearch(ref)

        elif isinstance(ref, oechem.OEQMol):
            self.refmol = ref.CreateCopy()
            self.ss = oechem.OESubSearch(self.refmol)

        else:
            self.refmol = oechem.OEQMol(ref)
            self.refmol.BuildExpressions(oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)
            self.ss = oechem.OESubSearch(self.refmol)

    def validate(self, mol: oechem.OEMolBase) -> bool:
        """
        Validate that the molecule has a match to this substructure search
        :param mol: Molecule to search
        :return: True if there is a match to this substructure search
        """
        oechem.OEPrepareSearch(mol, self.ss)
        return self.ss.SingleMatch(mol)

    def align(self, mol: oechem.OEMolBase) -> bool:
        """
        Align to this substructure trying the following

        1. If we had a reference molecule, then try to maximize the alignment to that reference molecule using the
           OpenEye multiple aligner (this works VERY WELL even if there are multiple matches to the reference)

        2. Standard aligned depiction, which fails if there are multiple matches to the substructure

        :param mol: Molecule to align
        :return: True if the alignment was successful
        """
        ok = False

        if self.refmol is not None:
            oechem.OEPrepareSearch(mol, self.ss)
            ok = oedepict.OEPrepareMultiAlignedDepiction(
                mol,
                self.refmol,
                self.ss.Match(mol)
            )

        if not ok:

            alignres = oedepict.OEPrepareAlignedDepiction(
                mol,
                self.ss,
                self.alignment_options
            )

            ok = alignres.IsValid()

        return ok


class OEMCSSearchAligner(Aligner):
    """
    2D molecule MCS alignment
    """
    def __init__(
            self,
            ref: oechem.OEMCSSearch | oechem.OEMolBase,
            *,
            func: Literal["atoms", "bonds", "atoms_and_cycles", "bonds_and_cycles"] = "bonds_cycles",
            min_atoms: int = 1,
            **_kwargs
    ):

        self.refmol = None

        # In the future, make these configurable
        self.alignment_options = oedepict.OEAlignmentOptions()

        if isinstance(ref, oechem.OEMCSSearch):
            self.mcss = oechem.OEMCSSearch(ref)

        else:
            self.refmol = ref.CreateCopy()

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
        Validate that a maximum common substructure exists in a query molecule (within a threshold)
        :param mol: Molecule to search
        :return: True if the molecule contains the maximum common substructure
        """
        return self.mcss.SingleMatch(mol)

    def align(self, mol: oechem.OEMolBase) -> bool:
        ok = False

        if self.refmol is not None:

            ok = oedepict.OEPrepareMultiAlignedDepiction(
                mol,
                self.refmol,
                self.mcss.Match(mol)
            )

        if not ok:

            alignres = oedepict.OEPrepareAlignedDepiction(
                mol,
                self.mcss,
                self.alignment_options
            )

            ok = alignres.IsValid()

        return ok


class OEFingerprintAligner(Aligner):
    """
    Fingerprint aligner
    """
    # Just using the default tree fingerprint type for the alignment

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
        # Simiarity threshold to apply alignment
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
        self.refmol = refmol.CreateCopy()
        self.reffp = None
        self.fptype = None

        if self.refmol.IsValid():
            self.reffp = self.make_fp(self.refmol)
            self.fptype = self.reffp.GetFPTypeBase()

    def validate(self, mol: oechem.OEMolBase) -> bool:
        if self.reffp is None:
            return False

        fp = self.make_fp(mol)
        return oegraphsim.OETanimoto(fp, self.reffp) >= self.threshold

    def align(self, mol: oechem.OEMolBase) -> bool:
        if self.fptype is None:
            return False

        overlaps = oegraphsim.OEGetFPOverlap(mol, self.refmol, self.fptype)
        return oedepict.OEPrepareMultiAlignedDepiction(mol, self.refmol, overlaps)


# Substructure aligners
_ALIGNERS = {
    "substructure": OESubSearchAligner,
    "fingerprint": OEFingerprintAligner,
    "mcss": OEMCSSearchAligner
}


def create_aligner(
        ref: oechem.OESubSearch | oechem.OEMCSSearch | oechem.OEMolBase,
        method: Literal["ss", "substructure", "mcss", "fp", "fingerprint"] = None,
        **kwargs
) -> Aligner:
    """
    Add a depiction reference to the rendering current context
    :param ref: Alignment reference
    :param method: Alignment method
    :param kwargs: Keyword arguments for the aligner
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
            raise ValueError(f'Unknown depiction alignment method: {method}')

    # -----------------------------------------------------------------------------
    # Cases where we do not care about the method, because it can only be one thing
    # -----------------------------------------------------------------------------
    if isinstance(ref, oechem.OESubSearch):

        if method is not None and method != "ss":
            log.warning("Ignoring requested alignment method %s for oechem.OESubSearch object", method)

        return OESubSearchAligner(ref, **kwargs)

    elif isinstance(ref, oechem.OEMCSSearch):

        if method is not None and method != "mcss":
            log.warning("Ignoring requested alignment method %s for oechem.OEMCSSearch object", method)

        return OEMCSSearchAligner(ref, **kwargs)

    # -----------------------------------------------------------------------------
    # Ambiguous cases
    # -----------------------------------------------------------------------------

    elif isinstance(ref, oechem.OEQMol):

        if method is not None:
            return _ALIGNERS[method](ref, **kwargs)

        # Default is substructure search with an OEQMol
        else:
            log.debug("Using default substructure aligner for oechem.OEQMol alignment reference")
            return OESubSearchAligner(ref, **kwargs)

    elif isinstance(ref, oechem.OEMolBase):

        if method is not None:
            return _ALIGNERS[method](ref, **kwargs)

        # Default is fingerprint aligner
        else:
            log.debug("Using default fingerprint aligner for oechem.OEMolBase alignment reference")
            return OEFingerprintAligner(ref, **kwargs)
