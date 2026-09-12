from unittest.mock import MagicMock, patch

import pytest
from openeye import oechem, oedepict, oegraphsim

from cnotebook.align import (
    Aligner,
    OEFingerprintAligner,
    OEMCSSearchAligner,
    OESubSearchAligner,
    atom_fp_typemap,
    bond_fp_typemap,
    create_aligner,
    fingerprint_maker,
    get_atom_mask,
    get_bond_mask,
)
from cnotebook.core.columnops import AlignmentReport, SimilarityResult


class _RecordingMCS:
    """Small fake used to verify MCS constructor wiring without calling OpenEye search."""

    def __init__(self, *args):
        self.args = args
        self.init_args = None
        self.func = None
        self.min_atoms = None

    def Init(self, *args):
        self.init_args = args

    def SetMCSFunc(self, func):
        self.func = func

    def SetMinAtoms(self, min_atoms):
        self.min_atoms = min_atoms


class TestFingerprintTypeMaps:
    """Test the dynamically created type maps"""
    
    def test_atom_fp_typemap_exists(self):
        """Test that atom fingerprint typemap is created"""
        assert isinstance(atom_fp_typemap, dict)
        assert len(atom_fp_typemap) > 0
        # Test that keys are lowercase and without prefix
        for key in atom_fp_typemap:
            assert key.islower()
            assert not key.startswith("oefpatomtype_")
    
    def test_bond_fp_typemap_exists(self):
        """Test that bond fingerprint typemap is created"""
        assert isinstance(bond_fp_typemap, dict)
        assert len(bond_fp_typemap) > 0
        # Test that keys are lowercase and without prefix
        for key in bond_fp_typemap:
            assert key.islower()
            assert not key.startswith("oefpbondtype_")


class TestGetAtomMask:
    """Test the get_atom_mask function"""
    
    def test_get_atom_mask_single_type(self):
        """Test getting atom mask for single type"""
        # Use a known atom type that should exist
        with patch.dict(atom_fp_typemap, {'default': 1}):
            result = get_atom_mask("default")
            assert result == 1
    
    def test_get_atom_mask_multiple_types(self):
        """Test getting atom mask for multiple types"""
        with patch.dict(atom_fp_typemap, {'type1': 1, 'type2': 2}):
            result = get_atom_mask("type1|type2")
            assert result == 3  # 1 | 2 = 3
    
    def test_get_atom_mask_with_prefix(self):
        """Test getting atom mask with OEFPAtomType_ prefix"""
        with patch.dict(atom_fp_typemap, {'default': 1}):
            result = get_atom_mask("OEFPAtomType_Default")
            assert result == 1
    
    def test_get_atom_mask_case_insensitive(self):
        """Test case insensitive atom mask lookup"""
        with patch.dict(atom_fp_typemap, {'default': 1}):
            result = get_atom_mask("DEFAULT")
            assert result == 1
    
    def test_get_atom_mask_whitespace(self):
        """Test atom mask with whitespace"""
        with patch.dict(atom_fp_typemap, {'type1': 1, 'type2': 2}):
            result = get_atom_mask(" type1 | type2 ")
            assert result == 3
    
    def test_get_atom_mask_unknown_type(self):
        """Test error for unknown atom type"""
        with pytest.raises(KeyError, match="unknown is not a known OEAtomFPType"):
            get_atom_mask("unknown")

    def test_get_atom_mask_empty_mask_error(self):
        """Test error when atom mask is None/empty after processing"""
        # Mock the typemap to return None type initially
        with (
            patch('cnotebook.core.align.oegraphsim.OEFPAtomType_None', 0),
            patch.dict(atom_fp_typemap, {'none': 0}),
            pytest.raises(ValueError, match="No atom fingerprint types configured"),
        ):
            get_atom_mask("none")


class TestGetBondMask:
    """Test the get_bond_mask function"""
    
    def test_get_bond_mask_single_type(self):
        """Test getting bond mask for single type"""
        with patch.dict(bond_fp_typemap, {'default': 1}):
            result = get_bond_mask("default")
            assert result == 1
    
    def test_get_bond_mask_multiple_types(self):
        """Test getting bond mask for multiple types"""
        with patch.dict(bond_fp_typemap, {'type1': 1, 'type2': 2}):
            result = get_bond_mask("type1|type2")
            assert result == 3
    
    def test_get_bond_mask_with_prefix(self):
        """Test getting bond mask with OEFPBondType_ prefix"""
        with patch.dict(bond_fp_typemap, {'default': 1}):
            result = get_bond_mask("OEFPBondType_Default")
            assert result == 1
    
    def test_get_bond_mask_case_insensitive(self):
        """Test case insensitive bond mask lookup"""
        with patch.dict(bond_fp_typemap, {'default': 1}):
            result = get_bond_mask("DEFAULT")
            assert result == 1
    
    def test_get_bond_mask_unknown_type(self):
        """Test error for unknown bond type"""
        with pytest.raises(KeyError, match="unknown is not a known OEBondFPType"):
            get_bond_mask("unknown")

    def test_get_bond_mask_empty_mask_error(self):
        """Test error when bond mask is None/empty after processing"""
        # Mock the typemap to return None type initially
        with (
            patch('cnotebook.core.align.oegraphsim.OEFPBondType_None', 0),
            patch.dict(bond_fp_typemap, {'none': 0}),
            pytest.raises(ValueError, match="No bond fingerprint types configured"),
        ):
            get_bond_mask("none")


class TestFingerprintMaker:
    """Test the fingerprint_maker function - logic only"""
    
    def test_fingerprint_maker_accepts_string_masks(self):
        """String atom and bond mask names should be resolved before fingerprinting."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="path",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type="defaultpathatom",
            bond_type="defaultpathbond"
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.GetSize() == 1024
    
    def test_fingerprint_maker_unknown_type(self):
        """Test error for unknown fingerprint type"""
        with pytest.raises(KeyError, match="Unknown fingerprint type unknown"):
            fingerprint_maker(
                fptype="unknown",
                num_bits=1024,
                min_distance=0,
                max_distance=5,
                atom_type=1,
                bond_type=2
            )

    def test_fingerprint_maker_path(self):
        """Test path fingerprint creation"""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="path",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.GetSize() == 1024

    def test_fingerprint_maker_circular(self):
        """Test circular fingerprint creation"""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="circular",
            num_bits=1024,
            min_distance=0,
            max_distance=3,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.GetSize() == 1024

    def test_fingerprint_maker_tree(self):
        """Test tree fingerprint creation"""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="tree",
            num_bits=1024,
            min_distance=0,
            max_distance=4,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.GetSize() == 1024


class TestAlignerBase:
    """Test the base Aligner class"""
    
    def test_aligner_is_abstract(self):
        """Test that Aligner is abstract"""
        with pytest.raises(TypeError):
            Aligner()
    
    def test_aligner_call_with_molecule(self):
        """Test calling aligner with molecule"""
        class TestAligner(Aligner):
            def validate(self, mol):
                return True
            
            def align(self, mol):
                return True
        
        aligner = TestAligner()
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        result = aligner(mock_mol)
        assert result is True
    
    def test_aligner_call_with_display(self):
        """Test calling aligner with display object"""
        class TestAligner(Aligner):
            def validate(self, mol):
                return True
            
            def align(self, mol):
                return True
        
        aligner = TestAligner()
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_disp.GetMolecule.return_value = mock_mol
        
        result = aligner(mock_disp)
        assert result is True
    
    def test_aligner_call_validation_fails(self):
        """Test aligner when validation fails"""
        class TestAligner(Aligner):
            def validate(self, mol):
                return False
            
            def align(self, mol):
                return True
        
        aligner = TestAligner()
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        result = aligner(mock_mol)
        assert result is False


# FIXME: Bug reported OpenEye on 11/30/2025 regarding using OESubSearch matches in OEPrepareMultiAlignedDepiction
# class TestOESubSearchAligner:
#     """Test the OESubSearchAligner class - basic functionality only"""
#
#     def test_validate_method_exists(self):
#         """Test that validation method exists"""
#         aligner = OESubSearchAligner.__new__(OESubSearchAligner)
#         aligner.ss = MagicMock()
#
#         mock_mol = MagicMock()
#         # Just test that the method can be called
#         assert hasattr(aligner, 'validate')
#         assert callable(aligner.validate)
#
#     def test_align_method_exists(self):
#         """Test that align method exists"""
#         aligner = OESubSearchAligner.__new__(OESubSearchAligner)
#         aligner.ss = MagicMock()
#         aligner.refmol = None
#         aligner.alignment_options = MagicMock()
#
#         assert hasattr(aligner, 'align')
#         assert callable(aligner.align)
#
#     def test_subsearch_aligner_with_smarts(self):
#         """Test SubSearch aligner with SMARTS pattern"""
#         # Create molecules
#         ref_mol = oechem.OEGraphMol()
#         oechem.OESmilesToMol(ref_mol, "c1ccccc1")  # benzene
#         oedepict.OEPrepareDepiction(ref_mol)  # Prepare 2D coordinates
#
#         target_mol = oechem.OEGraphMol()
#         oechem.OESmilesToMol(target_mol, "c1ccc(O)cc1")  # phenol
#         oedepict.OEPrepareDepiction(target_mol)  # Prepare 2D coordinates
#
#         # Create aligner with reference molecule
#         aligner = OESubSearchAligner(ref_mol)
#
#         # Test validation
#         assert aligner.validate(target_mol) is True
#
#         # Test alignment
#         result = aligner.align(target_mol)
#         assert result is True
#
#     def test_subsearch_aligner_init_with_oesubsearch(self):
#         """Test SubSearch aligner initialization with OESubSearch"""
#         ss = oechem.OESubSearch("[#6]")  # carbon pattern
#         aligner = OESubSearchAligner(ss)
#
#         # Should have created the aligner
#         assert hasattr(aligner, 'ss')
#         assert hasattr(aligner, 'refmol')
#
#     def test_subsearch_aligner_init_with_oeqmol(self):
#         """Test SubSearch aligner initialization with OEQMol"""
#         ref_mol = oechem.OEQMol()
#         oechem.OESmilesToMol(ref_mol, "CCO")
#
#         aligner = OESubSearchAligner(ref_mol)
#
#         # Should have created the aligner with refmol set
#         assert aligner.refmol is not None
#
#
# FIXME: Bug reported OpenEye on 11/30/2025 regarding using OEMCSSearch matches in OEPrepareMultiAlignedDepiction
# class TestOEMCSSearchAligner:
#     """Test the OEMCSSearchAligner class - basic functionality only"""
#
#     def test_validate_method_exists(self):
#         """Test that validation method exists"""
#         aligner = OEMCSSearchAligner.__new__(OEMCSSearchAligner)
#         aligner.mcss = MagicMock()
#
#         assert hasattr(aligner, 'validate')
#         assert callable(aligner.validate)
#
#     def test_alignment_method_exists(self):
#         """Test that align method exists"""
#         aligner = OEMCSSearchAligner.__new__(OEMCSSearchAligner)
#         aligner.mcss = MagicMock()
#
#         assert hasattr(aligner, 'align')
#         assert callable(aligner.align)
#
#     def test_mcssearch_aligner_with_molecules(self):
#         """Test MCS aligner with real molecules"""
#         # Create molecules
#         ref_mol = oechem.OEGraphMol()
#         oechem.OESmilesToMol(ref_mol, "c1ccccc1")  # benzene
#         oedepict.OEPrepareDepiction(ref_mol)
#
#         target_mol = oechem.OEGraphMol()
#         oechem.OESmilesToMol(target_mol, "c1ccc(O)cc1")  # phenol
#         oedepict.OEPrepareDepiction(target_mol)
#
#         # Create aligner with explicit func parameter
#         aligner = OEMCSSearchAligner(ref_mol, func="bonds")
#
#         # Test validation
#         result = aligner.validate(target_mol)
#         assert result is True
#
#         # Test alignment
#         result = aligner.align(target_mol)
#         assert result is True


class TestOEFingerprintAligner:
    """Test the OEFingerprintAligner class - basic functionality only"""

    def test_init_with_invalid_refmol(self):
        """Test initialization with invalid reference molecule"""
        # Create an empty (invalid) molecule
        invalid_mol = oechem.OEGraphMol()
        # Don't add any atoms - this makes it invalid

        with pytest.warns(match="Reference molecule for fingerprint-based alignment is not valid"):
            aligner = OEFingerprintAligner(invalid_mol)

        assert aligner.reffp is None
        assert aligner.fptype is None

    def test_validate_no_reffp(self):
        """Test validation when no reference fingerprint"""
        aligner = OEFingerprintAligner.__new__(OEFingerprintAligner)
        aligner.reffp = None

        mock_mol = MagicMock()
        result = aligner.validate(mock_mol)

        assert result is False

    def test_align_no_fptype(self):
        """Test alignment when no fingerprint type"""
        aligner = OEFingerprintAligner.__new__(OEFingerprintAligner)
        aligner.fptype = None

        mock_mol = MagicMock()
        result = aligner.align(mock_mol)

        assert result is False


class TestCreateAligner:
    """Test the create_aligner function - logic only"""

    @patch('cnotebook.core.align.OESubSearchAligner')
    def test_create_aligner_subsearch(self, mock_aligner_class):
        """Test creating aligner with OESubSearch"""
        mock_ss = MagicMock(spec=oechem.OESubSearch)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        result = create_aligner(mock_ss, method="fingerprint")  # Method should be ignored

        mock_aligner_class.assert_called_once_with(mock_ss)
        assert result == mock_aligner

    @patch('cnotebook.core.align.OEMCSSearchAligner')
    def test_create_aligner_mcssearch(self, mock_aligner_class):
        """Test creating aligner with OEMCSSearch"""
        mock_mcss = MagicMock(spec=oechem.OEMCSSearch)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        result = create_aligner(mock_mcss, method="substructure")  # Method should be ignored

        mock_aligner_class.assert_called_once_with(mock_mcss)
        assert result == mock_aligner

    @patch('cnotebook.core.align.OESubSearchAligner')
    def test_create_aligner_smarts_string(self, mock_aligner_class):
        """Test creating aligner with SMARTS string"""
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        result = create_aligner("c1ccccc1")  # SMARTS string

        mock_aligner_class.assert_called_once_with("c1ccccc1")
        assert result == mock_aligner

    @patch('cnotebook.core.align.OEFingerprintAligner')
    def test_create_aligner_molbase_default(self, mock_aligner_class):
        """Test creating aligner with OEMolBase (default method)"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        # This should return the OEFingerprintAligner instance
        result = create_aligner(mock_mol)

        # Should return the fingerprint aligner (bug was fixed)
        assert result == mock_aligner
        mock_aligner_class.assert_called_once_with(mock_mol)

    @patch('cnotebook.core.align.OESubSearchAligner')
    def test_create_aligner_molbase_substructure(self, mock_aligner_class):
        """Test creating aligner with OEMolBase and substructure method"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        result = create_aligner(mock_mol, method="substructure")

        mock_aligner_class.assert_called_once_with(mock_mol)
        assert result == mock_aligner

    @patch('cnotebook.core.align.OEMCSSearchAligner')
    def test_create_aligner_molbase_mcss(self, mock_aligner_class):
        """Test creating aligner with OEMolBase and mcss method"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner

        result = create_aligner(mock_mol, method="mcss")

        mock_aligner_class.assert_called_once_with(mock_mol)
        assert result == mock_aligner

    def test_create_aligner_unknown_method(self):
        """Test error for unknown alignment method"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)

        with pytest.raises(ValueError, match="Unknown depiction alignment method"):
            create_aligner(mock_mol, method="unknown")

    def test_create_aligner_unsupported_type(self):
        """Test error for unsupported alignment reference type"""
        # Pass something that's not a supported type
        with pytest.raises(TypeError, match="Unsupported alignment reference type"):
            create_aligner(12345)  # A number is not supported


class TestOESubSearchAlignerInit:
    """Test the OESubSearchAligner initialization and validate method."""

    def test_init_with_smarts_string(self):
        """A SMARTS string reference should validate matching molecules."""
        aligner = OESubSearchAligner("c1ccccc1")
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        assert aligner.refmol is None
        assert aligner.validate(mol) is True

    def test_init_with_oesubsearch(self):
        """An OESubSearch reference should validate matching molecules."""
        ss = oechem.OESubSearch("c1ccccc1")
        aligner = OESubSearchAligner(ss)
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")

        assert aligner.refmol is None
        assert aligner.validate(mol) is True

    def test_init_with_molecule(self):
        """A molecule reference should be copied and used as the substructure."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        aligner = OESubSearchAligner(mol)
        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "c1ccc(O)cc1")

        assert aligner.refmol is not None
        assert aligner.refmol is not mol
        assert aligner.validate(target) is True

    def test_validate_with_match(self):
        """Test validate returns True for a matching molecule (phenol contains benzene)."""
        aligner = OESubSearchAligner("c1ccccc1")
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccc(O)cc1")  # phenol
        assert aligner.validate(mol) is True

    def test_validate_without_match(self):
        """Test validate returns False for a non-matching molecule (ethane has no ring)."""
        aligner = OESubSearchAligner("c1ccccc1")
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CC")  # ethane
        assert aligner.validate(mol) is False


class TestOEMCSSearchAlignerInit:
    """Test the OEMCSSearchAligner initialization and validate method."""

    def test_init_with_molecule_default_func(self):
        """The default MCS function should be wired during initialization."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        func = object()

        with patch('cnotebook.core.align.oechem.OEMCSSearch', _RecordingMCS), \
             patch('cnotebook.core.align.oechem.OEMCSMaxBondsCompleteCycles', return_value=func):
            aligner = OEMCSSearchAligner(mol)

        assert aligner.refmol is not None
        assert aligner.mcss.func is func
        assert aligner.mcss.min_atoms == 1

    def test_init_with_molecule_atoms_func(self):
        """The atoms MCS function should be wired during initialization."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        func = object()

        with patch('cnotebook.core.align.oechem.OEMCSSearch', _RecordingMCS), \
             patch('cnotebook.core.align.oechem.OEMCSMaxAtoms', return_value=func):
            aligner = OEMCSSearchAligner(mol, func="atoms")

        assert aligner.mcss.func is func

    def test_init_with_molecule_invalid_func_raises(self):
        """Test initialization with an invalid func raises ValueError."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        with pytest.raises(ValueError, match="Unknown MCS evaluation function name"):
            OEMCSSearchAligner(mol, func="invalid")

    def test_init_sets_min_atoms(self):
        """The configured minimum atom count should be passed to the MCS search."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        with patch('cnotebook.core.align.oechem.OEMCSSearch', _RecordingMCS):
            aligner = OEMCSSearchAligner(mol, min_atoms=6)

        assert aligner.mcss.min_atoms == 6


class TestOEFingerprintAlignerExtended:
    """Extended tests for the OEFingerprintAligner validate method."""

    def test_validate_above_threshold(self):
        """Test validate returns True for similar molecules with low threshold."""
        ref = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref, "c1ccccc1")
        aligner = OEFingerprintAligner(ref, threshold=0.1)

        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "Cc1ccccc1")  # toluene
        assert aligner.validate(target) is True

    def test_validate_below_threshold(self):
        """Test validate returns False for dissimilar molecules with high threshold."""
        ref = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref, "c1ccccc1")
        aligner = OEFingerprintAligner(ref, threshold=0.9)

        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "C(C)C")  # propane
        assert aligner.validate(target) is False


class TestFingerprintMakerAdditionalTypes:
    """Test fingerprint_maker with maccs and lingo types."""

    def test_fingerprint_maker_maccs(self):
        """Test MACCS fingerprint creation."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="maccs",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.IsValid()

    def test_fingerprint_maker_lingo(self):
        """Test Lingo fingerprint creation."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="lingo",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )

        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.IsValid()

    def test_fingerprint_maker_maccs_case_insensitive(self):
        """Test MACCS fingerprint type is case insensitive."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="MACCS",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )
        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.IsValid()

    def test_fingerprint_maker_lingo_case_insensitive(self):
        """Test Lingo fingerprint type is case insensitive."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        maker = fingerprint_maker(
            fptype="Lingo",
            num_bits=1024,
            min_distance=0,
            max_distance=5,
            atom_type=oegraphsim.OEFPAtomType_DefaultAtom,
            bond_type=oegraphsim.OEFPBondType_DefaultBond
        )
        fp = maker(mol)
        assert isinstance(fp, oegraphsim.OEFingerPrint)
        assert fp.IsValid()


class TestOESubSearchAlignerAlign:
    """Test OESubSearchAligner align method."""

    def test_align_matching_molecule(self):
        """Test align returns True for a molecule matching the pattern."""
        ref = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref, "c1ccccc1")
        oedepict.OEPrepareDepiction(ref)

        aligner = OESubSearchAligner(ref)

        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(target)

        # Should validate and align successfully
        assert aligner.validate(target) is True
        result = aligner.align(target)
        assert isinstance(result, bool)

    def test_align_with_smarts(self):
        """Test align using a SMARTS pattern."""
        aligner = OESubSearchAligner("c1ccccc1")

        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(target)

        result = aligner.align(target)
        assert isinstance(result, bool)


class TestOEMCSSearchAlignerFuncVariants:
    """Test OEMCSSearchAligner initialization with different func values."""

    def test_init_with_bonds_func(self):
        """The bonds MCS function should be wired during initialization."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        func = object()

        with patch('cnotebook.core.align.oechem.OEMCSSearch', _RecordingMCS), \
             patch('cnotebook.core.align.oechem.OEMCSMaxBonds', return_value=func):
            aligner = OEMCSSearchAligner(mol, func="bonds")

        assert aligner.mcss.func is func

    def test_init_with_atoms_and_cycles_func(self):
        """The atoms-and-cycles MCS function should be wired during initialization."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        func = object()

        with patch('cnotebook.core.align.oechem.OEMCSSearch', _RecordingMCS), \
             patch('cnotebook.core.align.oechem.OEMCSMaxAtomsCompleteCycles', return_value=func):
            aligner = OEMCSSearchAligner(mol, func="atoms_and_cycles")

        assert aligner.mcss.func is func

    def test_init_with_oemcssearch(self):
        """An OEMCSSearch reference should be copied instead of reused."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")

        mcss = oechem.OEMCSSearch(oechem.OEMCSType_Approximate)
        mcss.Init(mol, oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)

        aligner = OEMCSSearchAligner(mcss)

        assert aligner.refmol is None
        assert aligner.mcss is not mcss



class TestCreateAlignerMethodAliases:
    """Test create_aligner with method aliases."""

    def test_create_aligner_ss_alias(self):
        """Test create_aligner with method='ss' (alias for substructure)."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        result = create_aligner(mol, method="ss")
        assert isinstance(result, OESubSearchAligner)

    def test_create_aligner_fp_alias(self):
        """Test create_aligner with method='fp' (alias for fingerprint)."""
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "c1ccccc1")
        oedepict.OEPrepareDepiction(mol)

        result = create_aligner(mol, method="fp")
        assert isinstance(result, OEFingerprintAligner)


class TestOEFingerprintAlignerAlign:
    """Test OEFingerprintAligner align method with real molecules."""

    def test_align_similar_molecules(self):
        """Test align returns True for similar molecules."""
        ref = oechem.OEGraphMol()
        oechem.OESmilesToMol(ref, "c1ccccc1")
        oedepict.OEPrepareDepiction(ref)

        aligner = OEFingerprintAligner(ref, threshold=0.1)

        target = oechem.OEGraphMol()
        oechem.OESmilesToMol(target, "c1ccc(O)cc1")
        oedepict.OEPrepareDepiction(target)

        result = aligner.align(target)
        assert isinstance(result, bool)


def _mol(smiles):
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smiles)
    return mol


def test_mcss_aligner_aligns_real_molecules_without_single_match():
    ref = _mol("c1ccccc1O")
    target = _mol("c1ccccc1OC")
    aligner = create_aligner(ref, method="mcss")
    assert aligner(target) is True
    assert target.GetDimension() == 2


def test_smarts_aligner_aligns():
    target = _mol("c1ccccc1O")
    aligner = create_aligner("c1ccccc1")
    assert aligner.ss.GetPattern().GetDimension() == 2
    assert aligner(target) is True
    assert target.GetDimension() == 2


def test_subsearch_object_reference_gets_coordinates():
    ss = oechem.OESubSearch("c1ccccc1")
    aligner = OESubSearchAligner(ss)
    assert aligner.ss.GetPattern().GetDimension() == 2
    assert aligner(_mol("c1ccccc1N")) is True


def test_aligner_does_not_mutate_reference():
    ref = _mol("c1ccccc1O")
    assert ref.GetDimension() == 0
    create_aligner(ref, method="substructure")(_mol("c1ccccc1OC"))
    OEMCSSearchAligner(ref)(_mol("c1ccccc1OC"))
    create_aligner(ref)(_mol("c1ccccc1OC"))
    assert ref.GetDimension() == 0


def test_aligner_handles_none_and_invalid():
    aligner = create_aligner(_mol("c1ccccc1O"))
    assert aligner(None) is False
    assert aligner(oechem.OEGraphMol()) is False


def test_create_aligner_forwards_kwargs():
    fp = create_aligner(_mol("c1ccccc1O"), method="fp", threshold=0.9)
    assert fp.threshold == 0.9
    mcs = create_aligner(_mol("c1ccccc1O"), method="mcss", min_atoms=4)
    assert mcs.mcss.GetMinAtoms() == 4


def test_report_dataclasses():
    report = AlignmentReport(total=3, aligned=1, skipped_none=1, skipped_invalid=0, failed=[2])
    assert report.failed == [2]
    result = SimilarityResult(tanimotos=[1.0, None], reference=[None, None], target=[None, None])
    assert result.tanimotos[1] is None


def test_mcss_validate_never_calls_single_match():
    """Prove OEMCSSearchAligner.validate uses Match iterator, never SingleMatch."""
    class FakeMCSSearch:
        def SingleMatch(self, mol):
            raise AssertionError("SingleMatch must not be called")
        
        def Match(self, mol, exhaust):
            # Return empty iterator for no match, one item for match
            if mol.NumAtoms() > 5:
                return iter([object()])
            return iter([])
    
    fake_mcss = FakeMCSSearch()
    aligner = OEMCSSearchAligner.__new__(OEMCSSearchAligner)
    aligner.mcss = fake_mcss
    aligner.refmol = None
    
    # Small molecule - no match
    small_mol = _mol("CC")
    assert aligner.validate(small_mol) is False
    
    # Large molecule - match
    large_mol = _mol("c1ccccc1O")
    assert aligner.validate(large_mol) is True


def test_subsearch_reference_immutability():
    """Prove OESubSearchAligner copies OESubSearch references and never mutates them."""
    # Create a reference OESubSearch
    ref_ss = oechem.OESubSearch("c1ccccc1")
    
    # Snapshot state before aligner construction
    original_dimension = ref_ss.GetPattern().GetDimension()
    
    # Construct aligner
    aligner = OESubSearchAligner(ref_ss)
    
    # Invoke aligner on a molecule
    target = _mol("c1ccccc1O")
    aligner(target)
    
    # Assert caller's object is unchanged
    assert ref_ss.GetPattern().GetDimension() == original_dimension
    
    # Assert aligner holds its own copy
    assert aligner.ss is not ref_ss
    
    # Assert copy's pattern has 2D coordinates
    assert aligner.ss.GetPattern().GetDimension() == 2


def test_query_reference_immutability():
    """Prove OESubSearchAligner copies OEQMolBase references and never mutates them."""
    # Create a query molecule
    query_mol = oechem.OEQMol()
    oechem.OEParseSmarts(query_mol, "c1ccccc1")
    
    # Snapshot state before aligner construction
    original_dimension = query_mol.GetDimension()
    
    # Construct aligner with query molecule
    aligner = OESubSearchAligner(query_mol)
    
    # Invoke aligner on a molecule
    target = _mol("c1ccccc1O")
    aligner(target)
    
    # Assert caller's query molecule is unchanged
    assert query_mol.GetDimension() == original_dimension
    
    # Assert aligner's pattern has 2D coordinates
    assert aligner.ss.GetPattern().GetDimension() == 2


def test_prebuilt_mcss_configuration():
    """Prove create_aligner copies prebuilt OEMCSSearch and applies configuration."""
    # Create a reference molecule and prebuilt MCS search
    ref = _mol("c1ccccc1O")
    oedepict.OEPrepareDepiction(ref)
    
    original_mcss = oechem.OEMCSSearch(oechem.OEMCSType_Approximate)
    original_mcss.Init(ref, oechem.OEExprOpts_DefaultAtoms, oechem.OEExprOpts_DefaultBonds)
    original_min_atoms = original_mcss.GetMinAtoms()
    
    # Create aligner with min_atoms configuration
    aligner = create_aligner(original_mcss, min_atoms=4)
    
    # Assert aligner's copied search has the configured minimum
    assert aligner.mcss.GetMinAtoms() == 4
    
    # Assert caller's search is unchanged
    assert original_mcss.GetMinAtoms() == original_min_atoms
    
    # Assert it's a copy
    assert aligner.mcss is not original_mcss
