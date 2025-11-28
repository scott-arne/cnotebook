import pytest
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict, oegraphsim
from cnotebook.align import (
    get_atom_mask,
    get_bond_mask,
    fingerprint_maker,
    Aligner,
    OESubSearchAligner,
    OEMCSSearchAligner,
    OEFingerprintAligner,
    create_aligner,
    atom_fp_typemap,
    bond_fp_typemap
)


class TestFingerprintTypeMaps:
    """Test the dynamically created type maps"""
    
    def test_atom_fp_typemap_exists(self):
        """Test that atom fingerprint typemap is created"""
        assert isinstance(atom_fp_typemap, dict)
        assert len(atom_fp_typemap) > 0
        # Test that keys are lowercase and without prefix
        for key in atom_fp_typemap.keys():
            assert key.islower()
            assert not key.startswith("oefpatomtype_")
    
    def test_bond_fp_typemap_exists(self):
        """Test that bond fingerprint typemap is created"""
        assert isinstance(bond_fp_typemap, dict)
        assert len(bond_fp_typemap) > 0
        # Test that keys are lowercase and without prefix
        for key in bond_fp_typemap.keys():
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


class TestFingerprintMaker:
    """Test the fingerprint_maker function - logic only"""
    
    def test_fingerprint_maker_returns_callable(self):
        """Test that fingerprint_maker returns a callable function"""
        with patch.dict(atom_fp_typemap, {'default': 1}):
            with patch.dict(bond_fp_typemap, {'default': 2}):
                maker = fingerprint_maker(
                    fptype="path",
                    num_bits=1024,
                    min_distance=0,
                    max_distance=5,
                    atom_type="default",
                    bond_type="default"
                )
        
        assert callable(maker)
    
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


class TestOESubSearchAligner:
    """Test the OESubSearchAligner class - basic functionality only"""
    
    def test_validate_method_exists(self):
        """Test that validation method exists"""
        aligner = OESubSearchAligner.__new__(OESubSearchAligner)
        aligner.ss = MagicMock()
        
        mock_mol = MagicMock()
        # Just test that the method can be called
        assert hasattr(aligner, 'validate')
        assert callable(aligner.validate)
    
    def test_align_method_exists(self):
        """Test that align method exists"""
        aligner = OESubSearchAligner.__new__(OESubSearchAligner)
        aligner.ss = MagicMock()
        aligner.refmol = None
        aligner.alignment_options = MagicMock()
        
        assert hasattr(aligner, 'align')
        assert callable(aligner.align)


class TestOEMCSSearchAligner:
    """Test the OEMCSSearchAligner class - basic functionality only"""
    
    def test_validate_method_exists(self):
        """Test that validation method exists"""
        aligner = OEMCSSearchAligner.__new__(OEMCSSearchAligner)
        aligner.mcss = MagicMock()
        
        assert hasattr(aligner, 'validate')
        assert callable(aligner.validate)
    
    def test_alignment_method_exists(self):
        """Test that align method exists"""
        aligner = OEMCSSearchAligner.__new__(OEMCSSearchAligner)
        aligner.mcss = MagicMock()
        
        assert hasattr(aligner, 'align')
        assert callable(aligner.align)


class TestOEFingerprintAligner:
    """Test the OEFingerprintAligner class - basic functionality only"""
    
    @patch('cnotebook.align.fingerprint_maker')
    def test_init_with_invalid_refmol(self, mock_fp_maker):
        """Test initialization with invalid reference molecule"""
        mock_refmol = MagicMock(spec=oechem.OEMolBase)
        mock_refmol.CreateCopy.return_value = mock_refmol
        mock_refmol.IsValid.return_value = False
        
        mock_make_fp = MagicMock()
        mock_fp_maker.return_value = mock_make_fp
        
        aligner = OEFingerprintAligner(mock_refmol)
        
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
    
    @patch('cnotebook.align.OESubSearchAligner')
    def test_create_aligner_subsearch(self, mock_aligner_class):
        """Test creating aligner with OESubSearch"""
        mock_ss = MagicMock(spec=oechem.OESubSearch)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner
        
        result = create_aligner(mock_ss, method="fingerprint")  # Method should be ignored
        
        mock_aligner_class.assert_called_once_with(mock_ss)
        assert result == mock_aligner
    
    @patch('cnotebook.align.OEMCSSearchAligner')
    def test_create_aligner_mcssearch(self, mock_aligner_class):
        """Test creating aligner with OEMCSSearch"""
        mock_mcss = MagicMock(spec=oechem.OEMCSSearch)
        mock_aligner = MagicMock()
        mock_aligner_class.return_value = mock_aligner
        
        result = create_aligner(mock_mcss, method="substructure")  # Method should be ignored
        
        mock_aligner_class.assert_called_once_with(mock_mcss)
        assert result == mock_aligner
    
    @patch('cnotebook.align.OEFingerprintAligner')
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
    
    def test_create_aligner_unknown_method(self):
        """Test error for unknown alignment method"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        
        with pytest.raises(ValueError, match="Unknown depiction alignment method: unknown"):
            create_aligner(mock_mol, method="unknown")
    
    @patch('cnotebook.align.log.warning')
    def test_create_aligner_method_warning_subsearch(self, mock_log_warning):
        """Test warning when method conflicts with OESubSearch"""
        mock_ss = MagicMock(spec=oechem.OESubSearch)
        
        with patch('cnotebook.align.OESubSearchAligner'):
            create_aligner(mock_ss, method="mcss")
            mock_log_warning.assert_called_once()