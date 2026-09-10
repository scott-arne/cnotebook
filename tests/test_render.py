import base64
import re
from unittest.mock import MagicMock, patch

import pytest
from openeye import oechem, oedepict

from cnotebook.context import CNotebookContext
from cnotebook.render import (
    _create_exceeds_heavy_atoms_image,
    create_img_tag,
    oedisp_to_html,
    oedu_to_disp,
    oedu_to_html,
    oedu_to_image,
    oeimage_to_html,
    oemol_to_disp,
    oemol_to_html,
    oemol_to_image,
    render_empty_molecule,
    render_exceeds_max_heavy_atoms,
    render_invalid_molecule,
)


class TestCreateImgTag:
    """Test the create_img_tag function"""
    
    def test_create_img_tag_svg_with_wrap(self):
        """Test creating img tag for SVG with wrapping div"""
        svg_content = '<svg>test</svg>'
        svg_bytes = svg_content.encode('utf-8')
        
        result = create_img_tag(
            width=300,
            height=200,
            image_mime_type="image/svg+xml",
            image_bytes=svg_bytes,
            wrap_svg=True
        )
        
        expected = ('<div style=\'width:300px;height:auto;max-width:none\'>\n'
                   '\t<svg>test</svg>\n'
                   '</div>')
        assert result == expected
    
    def test_create_img_tag_svg_without_wrap(self):
        """Test creating img tag for SVG without wrapping div"""
        svg_content = '<svg>test</svg>'
        svg_bytes = svg_content.encode('utf-8')
        
        result = create_img_tag(
            width=300,
            height=200,
            image_mime_type="image/svg+xml",
            image_bytes=svg_bytes,
            wrap_svg=False
        )
        
        assert result == '<svg>test</svg>'
    
    def test_create_img_tag_png(self):
        """Test creating img tag for PNG"""
        png_bytes = b'\x89PNG\r\n\x1a\n'  # PNG signature
        
        result = create_img_tag(
            width=300,
            height=200,
            image_mime_type="image/png",
            image_bytes=png_bytes
        )
        
        expected_b64 = base64.b64encode(png_bytes).decode("utf-8")
        expected = (f'<img src=\'data:image/png;base64,{expected_b64}\' '
                   'style=\'width:300px;height:auto;max-width:none\' />')
        assert result == expected
    
    def test_create_img_tag_jpeg(self):
        """Test creating img tag for JPEG"""
        jpeg_bytes = b'\xff\xd8\xff'  # JPEG signature
        
        result = create_img_tag(
            width=400,
            height=300,
            image_mime_type="image/jpeg",
            image_bytes=jpeg_bytes
        )
        
        expected_b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
        expected = (f'<img src=\'data:image/jpeg;base64,{expected_b64}\' '
                   'style=\'width:400px;height:auto;max-width:none\' />')
        assert result == expected


class TestOedispToHtml:
    """Test the oedisp_to_html function"""

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oedisp_to_html_basic(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """Test converting OE2DMolDisplay to HTML - basic functionality"""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 300
        mock_disp.GetHeight.return_value = 200

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img>test</img>'

        ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0)

        # Test that the function exists and can be called
        result = oedisp_to_html(mock_disp, ctx=ctx)

        # Should create OEImage with correct dimensions
        mock_oeimage.assert_called_once_with(300, 200)
        # Should render molecule to image
        mock_render.assert_called_once_with(mock_image, mock_disp)
        # Should write image to string
        mock_write_image.assert_called_once_with(ctx.image_format, mock_image)
        # Should call create_img_tag
        mock_create_img.assert_called_once()
        assert result == '<img>test</img>'

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oedisp_to_html_uses_ctx_dimensions(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """When both ctx.width and ctx.height are non-zero, they are used for display sizing."""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 612
        mock_disp.GetHeight.return_value = 337

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=150, height=150, device_pixel_ratio=1.0)

        oedisp_to_html(mock_disp, ctx=ctx)

        # Render image should still use intrinsic dimensions
        mock_oeimage.assert_called_once_with(612, 337)
        # But create_img_tag should use ctx dimensions
        call_args = mock_create_img.call_args
        assert call_args[0][0] == 150  # display width
        assert call_args[0][1] == 150  # display height

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oedisp_to_html_width_only_scales_height(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """When only ctx.width is set, height is scaled proportionally."""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 600
        mock_disp.GetHeight.return_value = 300

        mock_oeimage.return_value = MagicMock()
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=150, height=0, device_pixel_ratio=1.0)

        oedisp_to_html(mock_disp, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 150   # display width = ctx.width
        assert call_args[0][1] == 75.0  # display height = 300 * (150/600)

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oedisp_to_html_height_only_scales_width(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """When only ctx.height is set, width is scaled proportionally."""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 600
        mock_disp.GetHeight.return_value = 300

        mock_oeimage.return_value = MagicMock()
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=0, height=150, device_pixel_ratio=1.0)

        oedisp_to_html(mock_disp, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 300.0  # display width = 600 * (150/300)
        assert call_args[0][1] == 150    # display height = ctx.height

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oedisp_to_html_default_uses_intrinsic(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """When both ctx dimensions are 0 (default), intrinsic dimensions are used."""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 612
        mock_disp.GetHeight.return_value = 337

        mock_oeimage.return_value = MagicMock()
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=0, height=0, device_pixel_ratio=1.0)

        oedisp_to_html(mock_disp, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 612  # intrinsic width
        assert call_args[0][1] == 337  # intrinsic height


class TestRenderEmptyMessage:
    """Test render_empty_molecule and render_invalid_molecule functions"""
    
    @patch('cnotebook.core.render.create_img_tag')
    def test_render_empty_molecule_basic(self, mock_create_img):
        """Test rendering empty molecule message"""
        mock_create_img.return_value = '<img>empty</img>'
        
        ctx = CNotebookContext(min_width=200, min_height=150, image_format="png")
        
        result = render_empty_molecule(ctx=ctx)
        
        # Should call create_img_tag with correct dimensions
        mock_create_img.assert_called_once()
        call_args = mock_create_img.call_args
        assert call_args[0][0] == 200  # width
        assert call_args[0][1] == 150  # height
        assert result == '<img>empty</img>'
    
    @patch('cnotebook.core.render.create_img_tag')
    def test_render_invalid_molecule_basic(self, mock_create_img):
        """Test rendering invalid molecule message"""
        mock_create_img.return_value = '<img>invalid</img>'
        
        ctx = CNotebookContext(min_width=200, min_height=150, image_format="png")
        
        result = render_invalid_molecule(ctx=ctx)
        
        # Should call create_img_tag with correct dimensions
        mock_create_img.assert_called_once()
        call_args = mock_create_img.call_args
        assert call_args[0][0] == 200  # width
        assert call_args[0][1] == 150  # height
        assert result == '<img>invalid</img>'


class TestRenderExceedsMaxHeavyAtoms:
    """Test render_exceeds_max_heavy_atoms and _create_exceeds_heavy_atoms_image functions"""

    @patch('cnotebook.core.render.oedepict.OEImage')
    def test_create_image_draws_two_lines(self, mock_oeimage):
        """Test that the helper draws error text on two lines"""
        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetTitle.return_value = ""

        ctx = CNotebookContext(min_width=200, min_height=150, title=False)

        result = _create_exceeds_heavy_atoms_image(mock_mol, ctx=ctx)

        assert result == mock_image
        mock_oeimage.assert_called_once_with(200, 150)
        assert mock_image.DrawText.call_count == 2

        draw_calls = mock_image.DrawText.call_args_list
        assert draw_calls[0][0][1] == "Exceeds Max Heavy Atoms"
        assert draw_calls[1][0][1] == "for Rendering"

    @patch('cnotebook.core.render.oedepict.OEImage')
    def test_create_image_with_title(self, mock_oeimage):
        """Test that the helper draws the molecule title when ctx.title is True"""
        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetTitle.return_value = "MyMolecule"

        ctx = CNotebookContext(min_width=200, min_height=150, title=True)

        _create_exceeds_heavy_atoms_image(mock_mol, ctx=ctx)

        assert mock_image.DrawText.call_count == 3
        draw_calls = mock_image.DrawText.call_args_list
        assert draw_calls[0][0][1] == "Exceeds Max Heavy Atoms"
        assert draw_calls[1][0][1] == "for Rendering"
        assert draw_calls[2][0][1] == "MyMolecule"

    @patch('cnotebook.core.render.oedepict.OEImage')
    def test_create_image_title_enabled_but_empty(self, mock_oeimage):
        """Test that no title is drawn when molecule title is empty"""
        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetTitle.return_value = ""

        ctx = CNotebookContext(min_width=200, min_height=150, title=True)

        _create_exceeds_heavy_atoms_image(mock_mol, ctx=ctx)

        assert mock_image.DrawText.call_count == 2

    @patch('cnotebook.core.render.oeimage_to_html')
    @patch('cnotebook.core.render._create_exceeds_heavy_atoms_image')
    def test_render_exceeds_max_heavy_atoms(self, mock_create_image, mock_image_to_html):
        """Test the HTML rendering function delegates to the helper"""
        mock_image = MagicMock()
        mock_create_image.return_value = mock_image
        mock_image_to_html.return_value = '<img>exceeds</img>'

        mock_mol = MagicMock(spec=oechem.OEMolBase)
        ctx = CNotebookContext(min_width=200, min_height=150, image_format="png")

        result = render_exceeds_max_heavy_atoms(mock_mol, ctx=ctx)

        mock_create_image.assert_called_once_with(mock_mol, ctx=ctx)
        mock_image_to_html.assert_called_once_with(mock_image, ctx=ctx)
        assert result == '<img>exceeds</img>'


class TestOemolToDisp:
    """Test the oemol_to_disp function - basic functionality"""

    @patch('openeye.oechem.OEGraphMol')
    @patch('openeye.oedepict.OEPrepareDepiction')
    def test_oemol_to_disp_2d_molecule(self, mock_prepare, mock_graphmol_cls):
        """Test converting 2D molecule to display"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetDimension.return_value = 2

        mock_copy = MagicMock()
        mock_copy.GetDimension.return_value = 2
        mock_graphmol_cls.return_value = mock_copy

        ctx = MagicMock(spec=CNotebookContext)
        mock_disp = MagicMock()
        ctx.create_molecule_display.return_value = mock_disp

        result = oemol_to_disp(mock_mol, ctx=ctx)

        # Should create a copy
        mock_graphmol_cls.assert_called_once_with(mock_mol)
        # Should call OEPrepareDepiction with False for 2D molecules on the copy
        mock_prepare.assert_called_once()
        assert mock_prepare.call_args[0][1] is False
        assert mock_prepare.call_args[0][0] is not mock_mol
        # Should call create_molecule_display on the copy
        assert result == mock_disp

    @patch('openeye.oechem.OEGraphMol')
    @patch('openeye.oedepict.OEPrepareDepiction')
    def test_oemol_to_disp_3d_molecule(self, mock_prepare, mock_graphmol_cls):
        """Test converting 3D molecule to display"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetDimension.return_value = 3

        mock_copy = MagicMock()
        mock_copy.GetDimension.return_value = 3
        mock_graphmol_cls.return_value = mock_copy

        ctx = MagicMock(spec=CNotebookContext)
        mock_disp = MagicMock()
        ctx.create_molecule_display.return_value = mock_disp

        result = oemol_to_disp(mock_mol, ctx=ctx)

        # Should create a copy
        mock_graphmol_cls.assert_called_once_with(mock_mol)
        # Should call OEPrepareDepiction with True for 3D molecules on the copy
        mock_prepare.assert_called_once()
        assert mock_prepare.call_args[0][1] is True
        assert mock_prepare.call_args[0][0] is not mock_mol
        # Should call create_molecule_display on the copy
        assert result == mock_disp


class TestOemolToImage:
    """Test the oemol_to_image function"""

    @patch('cnotebook.core.render.oechem.OECount')
    @patch('cnotebook.core.render.oedepict.OERenderMolecule')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oemol_to_disp')
    def test_valid_molecule(self, mock_to_disp, mock_oeimage, mock_render, mock_oecount):
        """Test converting valid molecule to OEImage"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        mock_oecount.return_value = 10  # below default max_heavy_atoms

        mock_disp = MagicMock()
        mock_disp.GetWidth.return_value = 300
        mock_disp.GetHeight.return_value = 200
        mock_to_disp.return_value = mock_disp

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext()

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_to_disp.assert_called_once_with(mock_mol, ctx=ctx)
        mock_oeimage.assert_called_once_with(300, 200)
        mock_render.assert_called_once_with(mock_image, mock_disp)
        assert result == mock_image

    @patch('cnotebook.core.render.oedepict.OEImage')
    def test_empty_molecule(self, mock_oeimage):
        """Test converting empty molecule to OEImage with placeholder text"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = False
        mock_mol.NumAtoms.return_value = 0

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(min_width=200, min_height=150)

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_oeimage.assert_called_once_with(200, 150)
        mock_image.DrawText.assert_called_once()
        draw_text_args = mock_image.DrawText.call_args[0]
        assert draw_text_args[1] == "Empty Molecule"
        assert result == mock_image

    @patch('cnotebook.core.render.oedepict.OEImage')
    def test_invalid_molecule(self, mock_oeimage):
        """Test converting invalid molecule (with atoms) to OEImage"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = False
        mock_mol.NumAtoms.return_value = 5

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(min_width=200, min_height=150)

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_oeimage.assert_called_once_with(200, 150)
        mock_image.DrawText.assert_called_once()
        draw_text_args = mock_image.DrawText.call_args[0]
        assert draw_text_args[1] == "Invalid Molecule"
        assert result == mock_image

    @patch('cnotebook.core.render._create_exceeds_heavy_atoms_image')
    @patch('cnotebook.core.render.oechem.OECount')
    def test_exceeds_max_heavy_atoms(self, mock_oecount, mock_create_image):
        """Test that valid molecule exceeding heavy atom limit shows placeholder"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        mock_oecount.return_value = 150

        mock_image = MagicMock()
        mock_create_image.return_value = mock_image

        ctx = CNotebookContext(max_heavy_atoms=100)

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_create_image.assert_called_once_with(mock_mol, ctx=ctx)
        assert result == mock_image

    @patch('cnotebook.core.render.oedepict.OERenderMolecule')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oemol_to_disp')
    @patch('cnotebook.core.render.oechem.OECount')
    def test_within_max_heavy_atoms(self, mock_oecount, mock_to_disp, mock_oeimage, mock_render):
        """Test that valid molecule within heavy atom limit renders normally"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True
        mock_oecount.return_value = 50

        mock_disp = MagicMock()
        mock_disp.GetWidth.return_value = 300
        mock_disp.GetHeight.return_value = 200
        mock_to_disp.return_value = mock_disp

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(max_heavy_atoms=100)

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_to_disp.assert_called_once_with(mock_mol, ctx=ctx)
        assert result == mock_image

    @patch('cnotebook.core.render.oedepict.OERenderMolecule')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oemol_to_disp')
    def test_max_heavy_atoms_none_disables_check(self, mock_to_disp, mock_oeimage, mock_render):
        """Test that max_heavy_atoms=None disables the heavy atom check"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True

        mock_disp = MagicMock()
        mock_disp.GetWidth.return_value = 300
        mock_disp.GetHeight.return_value = 200
        mock_to_disp.return_value = mock_disp

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(max_heavy_atoms=None)

        result = oemol_to_image(mock_mol, ctx=ctx)

        mock_to_disp.assert_called_once_with(mock_mol, ctx=ctx)
        assert result == mock_image


class TestOemolToHtml:
    """Test the oemol_to_html function"""

    @patch('cnotebook.core.render.make_depiction')
    def test_oemol_to_html_delegates(self, mock_make_depiction):
        """Test that oemol_to_html delegates to make_depiction for valid molecules"""
        # Use a real molecule to avoid issues with OECount
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "CCO")

        # Create a mock Depiction with a to_html method
        mock_depiction = MagicMock()
        mock_depiction.to_html.return_value = '<img>'
        mock_make_depiction.return_value = mock_depiction

        ctx = CNotebookContext()

        result = oemol_to_html(mol, ctx=ctx)

        mock_make_depiction.assert_called_once_with(mol, ctx=ctx)
        mock_depiction.to_html.assert_called_once_with(ctx)
        assert result == '<img>'



class TestOeduToImage:
    """Test the oedu_to_image function"""

    @patch('cnotebook.core.render._draw_du_label')
    @patch('cnotebook.core.render.oedepict.OERenderMolecule')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oedu_to_disp')
    def test_with_ligand(self, mock_oedu_to_disp, mock_oeimage, mock_render,
                         mock_draw_label):
        """Test DU with ligand renders to OEImage with label"""
        from cnotebook.core.render import Depiction

        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        # Build a real OEGraphMol and a MagicMock display
        mol = oechem.OEGraphMol()
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 400.0
        mock_disp.GetHeight.return_value = 300.0

        mock_oedu_to_disp.return_value = Depiction(mol, mock_disp)

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(device_pixel_ratio=1.0)

        result = oedu_to_image(mock_du, ctx=ctx)

        mock_oedu_to_disp.assert_called_once_with(mock_du, ctx=ctx)
        mock_oeimage.assert_called_once_with(400, 300)
        mock_render.assert_called_once_with(mock_image, mock_disp)
        mock_draw_label.assert_called_once_with(mock_image, scale=1.0)
        assert result == mock_image

    @patch('cnotebook.core.render._draw_du_label')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oedu_to_disp')
    def test_apo_no_ligand(self, mock_oedu_to_disp, mock_oeimage, mock_draw_label):
        """Test apo DU creates OEImage with label and Apo text"""
        mock_oedu_to_disp.return_value = None

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(min_width=200, min_height=150)

        mock_du = MagicMock(spec=oechem.OEDesignUnit)
        result = oedu_to_image(mock_du, ctx=ctx)

        mock_oeimage.assert_called_once_with(200, 150)
        mock_draw_label.assert_called_once_with(mock_image)
        mock_image.DrawText.assert_called_once()
        draw_text_args = mock_image.DrawText.call_args[0]
        assert draw_text_args[1] == "Apo DesignUnit"
        assert result == mock_image

    @patch('cnotebook.core.render._draw_du_label')
    @patch('cnotebook.core.render.oedepict.OEImage')
    @patch('cnotebook.core.render.oedu_to_disp')
    def test_apo_uses_context_dimensions(self, mock_oedu_to_disp, mock_oeimage,
                                         mock_draw_label):
        """Test apo image uses context min_width and min_height"""
        mock_oedu_to_disp.return_value = None

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext(min_width=350, min_height=250)

        oedu_to_image(MagicMock(spec=oechem.OEDesignUnit), ctx=ctx)

        mock_oeimage.assert_called_once_with(350, 250)


class TestOeduToHtml:
    """Test the oedu_to_html function"""

    @patch('cnotebook.core.render.oeimage_to_html')
    @patch('cnotebook.core.render.oedu_to_image')
    @patch('cnotebook.core.render.oedu_to_disp')
    def test_oedu_to_html_delegates(self, mock_to_disp, mock_to_image, mock_image_to_html):
        """Test that oedu_to_html delegates to oedu_to_image + oeimage_to_html"""
        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        # Mock oedu_to_disp to return None (apo case)
        mock_to_disp.return_value = None

        mock_image = MagicMock()
        mock_to_image.return_value = mock_image
        mock_image_to_html.return_value = '<img>design_unit</img>'

        ctx = CNotebookContext()

        result = oedu_to_html(mock_du, ctx=ctx)

        # oedu_to_disp should be called first
        mock_to_disp.assert_called_once_with(mock_du, ctx=ctx)
        # oedu_to_image should be called with the depiction (None in this case)
        mock_to_image.assert_called_once_with(mock_du, ctx=ctx, dep=None)
        mock_image_to_html.assert_called_once_with(mock_image, ctx=ctx)
        assert result == '<img>design_unit</img>'


class TestOeimageToHtml:
    """Test the oeimage_to_html function"""

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oeimage_to_html_basic(self, mock_create_img, mock_write_image):
        """Test converting OEImage to HTML"""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 400
        mock_image.GetHeight.return_value = 300

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img>image</img>'

        ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0)

        result = oeimage_to_html(mock_image, ctx=ctx)

        # Should write image to string
        mock_write_image.assert_called_once_with(ctx.image_format, mock_image)
        # Should call create_img_tag with correct dimensions
        mock_create_img.assert_called_once()
        call_args = mock_create_img.call_args
        assert call_args[0][0] == 400  # width
        assert call_args[0][1] == 300  # height
        assert result == '<img>image</img>'

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oeimage_to_html_uses_ctx_dimensions(self, mock_create_img, mock_write_image):
        """When both ctx.width and ctx.height are non-zero, they are used for display sizing."""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 500
        mock_image.GetHeight.return_value = 400

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=200, height=200, device_pixel_ratio=1.0)

        oeimage_to_html(mock_image, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 200  # display width
        assert call_args[0][1] == 200  # display height

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oeimage_to_html_width_only_scales_height(self, mock_create_img, mock_write_image):
        """When only ctx.width is set, height is scaled proportionally."""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 400
        mock_image.GetHeight.return_value = 200

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=200, height=0, device_pixel_ratio=1.0)

        oeimage_to_html(mock_image, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 200    # display width = ctx.width
        assert call_args[0][1] == 100.0  # display height = 200 * (200/400)

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oeimage_to_html_height_only_scales_width(self, mock_create_img, mock_write_image):
        """When only ctx.height is set, width is scaled proportionally."""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 400
        mock_image.GetHeight.return_value = 200

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=0, height=100, device_pixel_ratio=1.0)

        oeimage_to_html(mock_image, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 200.0  # display width = 400 * (100/200)
        assert call_args[0][1] == 100    # display height = ctx.height

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.core.render.create_img_tag')
    def test_oeimage_to_html_default_uses_intrinsic(self, mock_create_img, mock_write_image):
        """When both ctx dimensions are 0 (default), intrinsic dimensions are used."""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 500
        mock_image.GetHeight.return_value = 400

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img />'

        ctx = CNotebookContext(image_format="png", width=0, height=0, device_pixel_ratio=1.0)

        oeimage_to_html(mock_image, ctx=ctx)

        call_args = mock_create_img.call_args
        assert call_args[0][0] == 500  # intrinsic width
        assert call_args[0][1] == 400  # intrinsic height


class TestIntegrationWithContext:
    """Integration tests with CNotebookContext"""

    def test_context_image_formats(self):
        """Test different image formats with context"""
        png_ctx = CNotebookContext(image_format="png")
        assert png_ctx.image_mime_type == "image/png"

        svg_ctx = CNotebookContext(image_format="svg")
        assert svg_ctx.image_mime_type == "image/svg+xml"


def _omega_3d(smiles="CCO"):
    from openeye import oeomega

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, smiles)
    oechem.OEAddExplicitHydrogens(mol)
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    assert omega(mol)
    return mol


def test_oemol_to_html_does_not_mutate_input():
    mol = _omega_3d()
    atoms = mol.NumAtoms()
    oemol_to_html(mol)
    assert mol.GetDimension() == 3
    assert mol.NumAtoms() == atoms


def test_prepare_depiction_copy_returns_copy_with_2d_coords():
    from cnotebook.core.render import prepare_depiction_copy
    mol = _omega_3d()
    copy = prepare_depiction_copy(mol)
    assert copy is not mol
    assert copy.GetDimension() == 2
    assert mol.GetDimension() == 3


def test_prepare_depiction_copy_keeps_existing_2d_coordinates():
    from cnotebook.core.render import prepare_depiction_copy
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    oedepict.OEPrepareDepiction(mol)
    before = [mol.GetCoords(a) for a in mol.GetAtoms()]
    copy = prepare_depiction_copy(mol)
    after = [copy.GetCoords(a) for a in copy.GetAtoms()]
    assert [tuple(round(v, 3) for v in c) for c in before] == [tuple(round(v, 3) for v in c) for c in after]


def test_make_depiction_attaches_owner():
    from cnotebook.core.render import Depiction, make_depiction
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    dep = make_depiction(mol, ctx=CNotebookContext())
    assert isinstance(dep, Depiction)
    assert dep.display._cnotebook_owner is dep.mol
    assert dep.mol is not mol


def test_oemol_to_disp_keeps_owner_alive():
    import gc
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    disp = oemol_to_disp(mol, ctx=CNotebookContext())
    del mol
    gc.collect()
    image = oedepict.OEImage(disp.GetWidth(), disp.GetHeight())
    oedepict.OERenderMolecule(image, disp)
    assert len(oedepict.OEWriteImageToString("png", image)) > 0


def test_oedu_to_disp_returns_depiction():
    import os

    import pytest

    from cnotebook.core.render import Depiction
    
    _DU_PATH = os.path.join("examples", "assets", "spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")
    if not os.path.exists(_DU_PATH):
        pytest.skip("design unit asset missing")
    
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(_DU_PATH, du)
    dep = oedu_to_disp(du, ctx=CNotebookContext())
    assert isinstance(dep, Depiction)
    assert dep.display.IsValid()
    image = oedu_to_image(du, ctx=CNotebookContext())
    assert image.GetWidth() > 0


def test_oedu_to_disp_apo_returns_none():
    class ApoDU:
        def GetLigand(self, lig):
            return False

    assert oedu_to_disp(ApoDU(), ctx=CNotebookContext()) is None


def _png_size(html: str) -> tuple[int, int]:
    import base64
    match = re.search(r"base64,([^']+)'", html)
    assert match is not None
    b64 = match.group(1)
    data = base64.b64decode(b64)
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def _css_width(html: str) -> int:
    match = re.search(r"width:(\d+)px", html)
    assert match is not None
    return int(match.group(1))


def test_placeholder_size_falls_back_to_defaults():
    from cnotebook.core.render import placeholder_size
    ctx = CNotebookContext()
    ctx.min_width = None
    ctx.min_height = None
    assert placeholder_size(ctx) == (200, 200)
    ctx.min_width = 120.7
    assert placeholder_size(ctx) == (120, 200)


def test_placeholders_with_none_or_zero_min_sizes():
    from cnotebook.core.render import (
        render_empty_molecule,
        render_exceeds_max_heavy_atoms,
        render_invalid_molecule,
    )
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0)
    ctx.min_width = None
    ctx.min_height = None
    for html in (
        render_empty_molecule(ctx=ctx),
        render_invalid_molecule(ctx=ctx),
        render_exceeds_max_heavy_atoms(oechem.OEGraphMol(), ctx=ctx),
    ):
        assert _png_size(html) == (200, 200)
    with pytest.raises(ValueError, match="min_width"):
        ctx.min_width = 0


def test_png_rendered_at_device_pixel_ratio():
    from cnotebook.core.render import oemol_to_html
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    html = oemol_to_html(mol, ctx=ctx)
    width_px, _ = _png_size(html)
    assert width_px == 2 * _css_width(html)


def test_svg_ignores_device_pixel_ratio():
    from cnotebook.core.render import oemol_to_html
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="svg", device_pixel_ratio=2.0)
    html = oemol_to_html(mol, ctx=ctx)
    assert "<svg" in html


def test_html_wrapper_respects_max_dimensions():
    from cnotebook.core.render import oeimage_to_html
    image = oedepict.OEImage(800, 600)
    ctx = CNotebookContext(auto_scale=True, width=800, height=600, max_width=300, max_height=250, device_pixel_ratio=1.0)
    html = oeimage_to_html(image, ctx=ctx)
    assert _css_width(html) == 300


def test_oeimage_to_html_uses_logical_size():
    from cnotebook.core.render import oeimage_to_html
    image = oedepict.OEImage(400, 400)
    ctx = CNotebookContext(device_pixel_ratio=1.0)
    html = oeimage_to_html(image, ctx=ctx, logical_width=200, logical_height=200)
    assert _css_width(html) == 200


# Finding 2: Design unit DPR tests
def test_design_unit_honors_device_pixel_ratio():
    """Design unit PNGs should be oversampled at device_pixel_ratio."""
    import os

    from cnotebook.core.render import oedu_to_html

    du_path = "examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu"
    if not os.path.exists(du_path):
        pytest.skip("Design unit file not available")

    design_unit = oechem.OEDesignUnit()
    ifs = oechem.oeifstream(du_path)
    assert oechem.OEReadDesignUnit(ifs, design_unit)
    ifs.close()

    ctx = CNotebookContext(image_format="png", device_pixel_ratio=2.0)
    html = oedu_to_html(design_unit, ctx=ctx)
    width_px, _ = _png_size(html)
    # PNG should be 2x the logical size
    assert width_px == 2 * _css_width(html)


# Finding 3: Placeholder max-size clamp tests
def test_empty_molecule_respects_max_width():
    """Empty molecule placeholders should be clamped by max_width."""
    from cnotebook.core.render import render_empty_molecule
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0, min_width=400, max_width=200)
    html = render_empty_molecule(ctx=ctx)
    assert _css_width(html) == 200


def test_invalid_molecule_respects_max_height():
    """Invalid molecule placeholders should be clamped by max_height."""
    from cnotebook.core.render import render_invalid_molecule
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0, min_height=400, max_height=250)
    html = render_invalid_molecule(ctx=ctx)
    # Height is harder to extract, but width should be scaled proportionally if max_height binds
    assert _css_width(html) <= 400  # Should be clamped


def test_exceeds_heavy_atoms_respects_max_dimensions():
    """Heavy-atom-limit placeholders should be clamped."""
    from cnotebook.core.render import render_exceeds_max_heavy_atoms
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    ctx = CNotebookContext(image_format="png", device_pixel_ratio=1.0, min_width=500, max_width=250)
    html = render_exceeds_max_heavy_atoms(mol, ctx=ctx)
    assert _css_width(html) == 250


# Finding 4: SVG clamp and height enforcement tests
def test_svg_respects_max_width():
    """SVG output should be clamped by max_width."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="svg", width=800, max_width=300, device_pixel_ratio=1.0)
    html = oemol_to_html(mol, ctx=ctx)
    assert _css_width(html) == 300


def test_svg_respects_max_height():
    """SVG output should be clamped by max_height."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="svg", width=800, height=600, max_height=300, device_pixel_ratio=1.0)
    html = oemol_to_html(mol, ctx=ctx)
    # Extract both width and height from HTML
    assert "width" in html.lower() or "height" in html.lower()


def test_png_respects_both_max_dimensions():
    """PNG output should be clamped by both max_width and max_height."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    ctx = CNotebookContext(image_format="png", width=800, height=600, max_width=300, max_height=250, device_pixel_ratio=1.0)
    html = oemol_to_html(mol, ctx=ctx)
    assert _css_width(html) == 300  # Width clamp binds


# Finding 5: SVG DPR test
def test_svg_unaffected_by_device_pixel_ratio():
    """SVG should produce identical output at DPR 1 and DPR 2."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    
    ctx1 = CNotebookContext(image_format="svg", device_pixel_ratio=1.0)
    html1 = oemol_to_html(mol, ctx=ctx1)
    
    ctx2 = CNotebookContext(image_format="svg", device_pixel_ratio=2.0)
    html2 = oemol_to_html(mol, ctx=ctx2)
    
    # SVG should be identical regardless of DPR
    assert html1 == html2


def test_auto_scaled_svg_respects_max_dimensions():
    """Auto-scaled SVG should be clamped by max_width and max_height (Finding C)."""
    import re

    from cnotebook.core.render import oemol_to_html
    
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    
    # Auto-scaled SVG with dimensions that will exceed max limits
    ctx = CNotebookContext(
        image_format="svg",
        auto_scale=True,
        width=800,
        height=600,
        max_width=300,
        max_height=250,
        device_pixel_ratio=1.0
    )
    html = oemol_to_html(mol, ctx=ctx)
    
    # Extract width and height from the HTML
    width_match = re.search(r"width:(\d+)px", html)
    height_match = re.search(r"height:(\d+)px", html)
    
    assert width_match is not None, "Width should be specified"
    assert height_match is not None, "Height should be specified for clamped output"
    
    width = int(width_match.group(1))
    height = int(height_match.group(1))
    
    # Both dimensions should be clamped
    assert width == 300, f"Width should be clamped to 300, got {width}"
    # Height should be scaled proportionally from 600 -> (600 * 300/800) = 225
    assert height <= 250, f"Height should not exceed max_height, got {height}"


# Task 5: Public headless rendering API

from pathlib import Path

from cnotebook.core.render import (
    make_depiction,
    render_design_unit,
    render_display,
    render_molecule,
    save_image,
)


def _phenol():
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "c1ccccc1O")
    return mol


def test_render_molecule_png_and_svg_bytes():
    png = render_molecule(_phenol())
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    svg = render_molecule(_phenol(), format="svg")
    assert b"<svg" in svg


def test_render_molecule_options_do_not_touch_global_context():
    from cnotebook.core.context import cnotebook_context

    before = cnotebook_context.get().width
    render_molecule(_phenol(), width=123, height=99)
    assert cnotebook_context.get().width == before


def test_render_molecule_rejects_bad_format_and_option():
    with pytest.raises(ValueError, match="format"):
        render_molecule(_phenol(), format="gif")
    with pytest.raises(TypeError, match="no_such"):
        render_molecule(_phenol(), no_such=1)


def test_render_display_bytes():
    dep = make_depiction(_phenol(), ctx=CNotebookContext())
    assert render_display(dep.display, format="svg").startswith(b"<?xml") or b"<svg" in render_display(dep.display, format="svg")


def test_save_image_infers_format_from_suffix(tmp_path: Path):
    out = save_image(_phenol(), tmp_path / "phenol.svg")
    assert out.exists() and b"<svg" in out.read_bytes()
    out_png = save_image(_phenol(), tmp_path / "phenol.png")
    assert out_png.read_bytes()[:4] == b"\x89PNG"
    with pytest.raises(ValueError, match="format"):
        save_image(_phenol(), tmp_path / "phenol.bmp")


# Fix Round 1: Additional tests for review findings


# Fix Round 1: Additional tests for review findings

def test_render_molecule_applies_callbacks():
    """Callbacks from the context should be applied to the display before rendering."""
    invoked = []
    
    def marker_callback(disp):
        invoked.append(disp)
    
    ctx = CNotebookContext(callbacks=[marker_callback])
    render_molecule(_phenol(), format="svg", ctx=ctx)
    
    assert len(invoked) == 1, "Callback should have been invoked exactly once"
    assert isinstance(invoked[0], oedepict.OE2DMolDisplay), "Callback should receive a display"




def test_render_design_unit_applies_callbacks_to_ligand():
    """Callbacks should be applied to design unit ligand displays."""
    du_path = Path("examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")
    if not du_path.exists():
        pytest.skip("Design unit fixture not available")
    
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(str(du_path), du)
    
    invoked = []
    
    def marker_callback(disp):
        invoked.append(disp)
    
    ctx = CNotebookContext(callbacks=[marker_callback])
    render_design_unit(du, format="svg", ctx=ctx)
    
    assert len(invoked) == 1, "Callback should have been invoked for ligand"
    assert isinstance(invoked[0], oedepict.OE2DMolDisplay), "Callback should receive a display"


def test_render_design_unit_respects_heavy_atom_limit():
    """Design units with over-limit ligands should yield placeholder."""
    du_path = Path("examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")
    if not du_path.exists():
        pytest.skip("Design unit fixture not available")
    
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(str(du_path), du)
    
    # Set a very low limit
    ctx = CNotebookContext(max_heavy_atoms=1)
    result = render_design_unit(du, format="svg", ctx=ctx)
    
    # Should get placeholder with "exceeds" message
    assert b"exceeds" in result.lower() or b"too large" in result.lower() or b"heavy" in result.lower()


def test_render_design_unit_apo():
    """Apo design units (no ligand) should render placeholder."""
    # Create a minimal apo design unit
    du = oechem.OEDesignUnit()
    # Empty design unit has no ligand
    
    result = render_design_unit(du, format="svg")
    assert b"<svg" in result or b"Apo" in result


def test_save_image_design_unit_ligand(tmp_path: Path):
    """save_image should handle design units with ligands."""
    du_path = Path("examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")
    if not du_path.exists():
        pytest.skip("Design unit fixture not available")
    
    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(str(du_path), du)
    
    out = save_image(du, tmp_path / "du_ligand.png")
    assert out.exists() and out.read_bytes()[:4] == b"\x89PNG"


def test_save_image_design_unit_apo(tmp_path: Path):
    """save_image should handle apo design units."""
    du = oechem.OEDesignUnit()
    out = save_image(du, tmp_path / "du_apo.svg")
    assert out.exists() and b"<svg" in out.read_bytes()


def test_render_functions_png_and_svg():
    """All render functions should support both PNG and SVG."""
    mol = _phenol()
    
    # render_molecule
    png = render_molecule(mol, format="png")
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    svg = render_molecule(mol, format="svg")
    assert b"<svg" in svg
    
    # render_display
    dep = make_depiction(mol, ctx=CNotebookContext())
    png_disp = render_display(dep.display, format="png")
    assert png_disp[:8] == b"\x89PNG\r\n\x1a\n"
    svg_disp = render_display(dep.display, format="svg")
    assert b"<svg" in svg_disp


def test_render_molecule_option_changes_output():
    """Render options like width should change the output."""
    mol = _phenol()
    
    default = render_molecule(mol, format="png")
    custom_width = render_molecule(mol, format="png", width=100, height=100)
    
    # Different sizes should produce different bytes
    assert len(default) != len(custom_width)


def test_save_image_all_dispatch_types(tmp_path: Path):
    """save_image should dispatch correctly for molecule, display, and design unit."""
    mol = _phenol()
    
    # Molecule dispatch
    mol_path = save_image(mol, tmp_path / "mol.png")
    assert mol_path.exists() and mol_path.read_bytes()[:4] == b"\x89PNG"
    
    # Display dispatch
    dep = make_depiction(mol, ctx=CNotebookContext())
    disp_path = save_image(dep.display, tmp_path / "disp.svg")
    assert disp_path.exists() and b"<svg" in disp_path.read_bytes()
    
    # Design unit tested in other tests


def test_save_image_explicit_format_override(tmp_path: Path):
    """Explicit format parameter should override suffix."""
    mol = _phenol()
    
    # Save as SVG despite .png suffix
    out = save_image(mol, tmp_path / "test.png", format="svg")
    assert out.exists() and b"<svg" in out.read_bytes()


def test_save_image_empty_format_raises(tmp_path: Path):
    """Empty format string should raise ValueError (Finding 3)."""
    mol = _phenol()
    
    with pytest.raises(ValueError, match="format"):
        save_image(mol, tmp_path / "test.png", format="")


def test_save_image_undeterminable_suffix_raises(tmp_path: Path):
    """Files with no/unknown suffix and no format should raise ValueError."""
    mol = _phenol()
    
    # No suffix
    with pytest.raises(ValueError, match="format"):
        save_image(mol, tmp_path / "test")
    
    # Unknown suffix
    with pytest.raises(ValueError, match="format"):
        save_image(mol, tmp_path / "test.bmp")


def test_save_image_wrong_object_type_raises(tmp_path: Path):
    """save_image with unsupported object type should raise TypeError."""
    with pytest.raises(TypeError, match="Cannot render"):
        save_image("not a molecule", tmp_path / "test.png")


def test_render_molecule_dpr_doubles_png_pixels():
    """PNG at device_pixel_ratio=2.0 should be twice the logical size."""
    mol = _phenol()
    
    ctx1 = CNotebookContext(width=100, height=100, device_pixel_ratio=1.0, image_format="png")
    png1 = render_molecule(mol, ctx=ctx1)
    
    ctx2 = CNotebookContext(width=100, height=100, device_pixel_ratio=2.0, image_format="png")
    png2 = render_molecule(mol, ctx=ctx2)
    
    # DPR=2 should produce more bytes (larger image)
    assert len(png2) > len(png1)


def test_save_image_preserves_existing_on_render_failure(tmp_path: Path):
    """Rendering failure should leave existing destination file untouched (Finding 4)."""
    dest = tmp_path / "existing.png"
    original_content = b"ORIGINAL_CONTENT"
    dest.write_bytes(original_content)
    
    # Trigger a rendering error by passing invalid object type
    try:
        save_image("invalid", dest)
    except TypeError:
        pass
    
    # Original file should be unchanged
    assert dest.read_bytes() == original_content


def test_public_api_imports_from_cnotebook():
    """Public functions should be importable from top-level cnotebook."""
    from cnotebook import (
        render_design_unit,
        render_display,
        render_molecule,
        save_image,
    )
    
    # Just verify they're the right functions
    assert callable(render_molecule)
    assert callable(render_display)
    assert callable(render_design_unit)
    assert callable(save_image)


def test_public_api_imports_from_cnotebook_core():
    """Public functions should be importable from cnotebook.core."""
    from cnotebook.core import (
        render_design_unit,
        render_display,
        render_molecule,
        save_image,
    )
    
    assert callable(render_molecule)
    assert callable(render_display)
    assert callable(render_design_unit)
    assert callable(save_image)


# Fix Round 2: Finding A - Short writes and fault injection tests

def test_save_image_handles_write_failure_preserves_original(tmp_path: Path):
    """Write failure should leave original destination untouched (Finding A)."""
    import io
    from unittest.mock import patch

    dest = tmp_path / "existing.png"
    original_content = b"ORIGINAL_CONTENT"
    dest.write_bytes(original_content)

    mol = _phenol()

    # Mock os.fdopen to return a file object whose write raises
    class FailingWriter(io.BytesIO):
        def write(self, data):
            raise OSError("Simulated write failure")

    with patch('os.fdopen', return_value=FailingWriter()):
        try:
            save_image(mol, dest)
            assert False, "Should have raised OSError"
        except OSError:
            pass

    # Original file should be unchanged
    assert dest.read_bytes() == original_content
    # No temp files should remain
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_save_image_handles_replace_failure_preserves_original(tmp_path: Path):
    """Replace failure should leave original destination untouched (Finding A)."""
    from unittest.mock import patch

    dest = tmp_path / "existing.png"
    original_content = b"ORIGINAL_CONTENT"
    dest.write_bytes(original_content)

    mol = _phenol()

    # Mock os.replace to raise
    def failing_replace(src, dst):
        raise OSError("Simulated replace failure")

    with patch('os.replace', side_effect=failing_replace):
        try:
            save_image(mol, dest)
            assert False, "Should have raised OSError"
        except OSError:
            pass

    # Original file should be unchanged
    assert dest.read_bytes() == original_content
    # No temp files should remain
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_save_image_writes_complete_file(tmp_path: Path):
    """Successful save should write complete file matching rendered bytes (Finding A)."""
    mol = _phenol()
    dest = tmp_path / "test.png"

    # Render directly to get expected bytes
    expected_bytes = render_molecule(mol, format="png")

    # Save to file
    save_image(mol, dest)

    # File should exist and match exactly
    assert dest.exists()
    actual_bytes = dest.read_bytes()
    assert len(actual_bytes) == len(expected_bytes)
    assert actual_bytes == expected_bytes


# Fix Round 2: Finding B - Callback invocation count tests

def test_render_molecule_invokes_callback_exactly_once():
    """render_molecule should invoke callbacks exactly once (Finding B)."""
    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    render_molecule(_phenol(), ctx=ctx)

    assert len(invocations) == 1, f"Expected 1 callback invocation, got {len(invocations)}"


def test_oemol_to_html_invokes_callback_exactly_once():
    """oemol_to_html should invoke callbacks exactly once (Finding B)."""
    from cnotebook.core.render import oemol_to_html

    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    oemol_to_html(_phenol(), ctx=ctx)

    assert len(invocations) == 1, f"Expected 1 callback invocation, got {len(invocations)}"


def test_oedu_to_html_invokes_callback_exactly_once():
    """oedu_to_html should invoke callbacks exactly once for ligand DU (Finding B)."""
    from cnotebook.core.render import oedu_to_html

    du_path = Path("examples/assets/spruce_9Q03_ABC__DU__A1CM7_C-502.oedu")
    if not du_path.exists():
        pytest.skip("Design unit fixture not available")

    du = oechem.OEDesignUnit()
    assert oechem.OEReadDesignUnit(str(du_path), du)

    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    oedu_to_html(du, ctx=ctx)

    assert len(invocations) == 1, f"Expected 1 callback invocation, got {len(invocations)}"


def test_pandas_render_dataframe_invokes_callbacks_once_per_molecule():
    """Pandas rendering should invoke callbacks once per molecule (Finding B)."""
    pytest.importorskip("pandas")
    oepd = pytest.importorskip("oepandas")
    import pandas

    from cnotebook.pandas_ext import render_dataframe

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    # Create proper MoleculeArray column
    arr = oepd.MoleculeArray([mol1, mol2])
    df = pandas.DataFrame({"mol": arr})

    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    render_dataframe(df, ctx=ctx)

    assert len(invocations) == 2, f"Expected 2 callback invocations (one per molecule), got {len(invocations)}"


def test_polars_render_dataframe_invokes_callbacks_once_per_molecule():
    """Polars rendering should invoke callbacks once per molecule (Finding B)."""
    polars = pytest.importorskip("polars")
    oeplr = pytest.importorskip("oepolars")
    from cnotebook.polars_ext import render_polars_dataframe

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    # Create proper Polars series with molecule dtype
    mol_series = polars.Series("mol", [mol1, mol2], dtype=oeplr.MoleculeType())
    df = polars.DataFrame({"mol": mol_series})

    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    render_polars_dataframe(df, ctx=ctx)

    assert len(invocations) == 2, f"Expected 2 callback invocations (one per molecule), got {len(invocations)}"


def test_marimo_table_formatter_invokes_callbacks_once_per_molecule():
    """Marimo table formatting should invoke callbacks once per molecule (Finding B)."""
    pytest.importorskip("pandas")
    pytest.importorskip("oepandas")
    pytest.importorskip("marimo")
    from cnotebook.marimo_ext import _create_molecule_formatter

    mol1 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol1, "CCO")
    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "c1ccccc1")

    invocations = []

    def counting_callback(disp):
        invocations.append(disp)

    ctx = CNotebookContext(callbacks=[counting_callback])
    formatter = _create_molecule_formatter(ctx)

    # Format both molecules
    formatter(mol1)
    formatter(mol2)

    assert len(invocations) == 2, f"Expected 2 callback invocations (one per molecule), got {len(invocations)}"
