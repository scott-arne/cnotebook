import pytest
import base64
from unittest.mock import MagicMock, patch
from openeye import oechem, oedepict
from cnotebook.render import (
    create_img_tag,
    oedisp_to_html,
    render_empty_molecule,
    render_invalid_molecule,
    oemol_to_disp,
    oemol_to_image,
    oemol_to_html,
    oedu_to_disp,
    oedu_to_image,
    oedu_to_html,
    oeimage_to_html
)
from cnotebook.context import CNotebookContext


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
        
        expected = ('<div style=\'width:300px;max-width:300px;height:200px;max-height:200px\'>\n'
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
                   'style=\'width:300px;max-width:300px;height:200px;max-height:200px\' />')
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
                   'style=\'width:400px;max-width:400px;height:300px;max-height:300px\' />')
        assert result == expected


class TestOedispToHtml:
    """Test the oedisp_to_html function"""

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('openeye.oedepict.OERenderMolecule')
    @patch('openeye.oedepict.OEImage')
    @patch('cnotebook.render.create_img_tag')
    def test_oedisp_to_html_basic(self, mock_create_img, mock_oeimage, mock_render, mock_write_image):
        """Test converting OE2DMolDisplay to HTML - basic functionality"""
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 300
        mock_disp.GetHeight.return_value = 200

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image
        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img>test</img>'

        ctx = CNotebookContext(image_format="png", structure_scale=oedepict.OEScale_Default)

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


class TestRenderEmptyMessage:
    """Test render_empty_molecule and render_invalid_molecule functions"""
    
    @patch('cnotebook.render.create_img_tag')
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
    
    @patch('cnotebook.render.create_img_tag')
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


class TestOemolToDisp:
    """Test the oemol_to_disp function - basic functionality"""

    @patch('openeye.oedepict.OEPrepareDepiction')
    def test_oemol_to_disp_2d_molecule(self, mock_prepare):
        """Test converting 2D molecule to display"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetDimension.return_value = 2

        ctx = MagicMock(spec=CNotebookContext)
        mock_disp = MagicMock()
        ctx.create_molecule_display.return_value = mock_disp

        result = oemol_to_disp(mock_mol, ctx=ctx)

        # Should call OEPrepareDepiction with False for 2D molecules
        mock_prepare.assert_called_once_with(mock_mol, False)
        # Should call create_molecule_display
        ctx.create_molecule_display.assert_called_once_with(mock_mol)
        assert result == mock_disp

    @patch('openeye.oedepict.OEPrepareDepiction')
    def test_oemol_to_disp_3d_molecule(self, mock_prepare):
        """Test converting 3D molecule to display"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.GetDimension.return_value = 3

        ctx = MagicMock(spec=CNotebookContext)
        mock_disp = MagicMock()
        ctx.create_molecule_display.return_value = mock_disp

        result = oemol_to_disp(mock_mol, ctx=ctx)

        # Should call OEPrepareDepiction with True for 3D molecules
        mock_prepare.assert_called_once_with(mock_mol, True)
        # Should call create_molecule_display
        ctx.create_molecule_display.assert_called_once_with(mock_mol)
        assert result == mock_disp


class TestOemolToImage:
    """Test the oemol_to_image function"""

    @patch('cnotebook.render.oedepict.OERenderMolecule')
    @patch('cnotebook.render.oedepict.OEImage')
    @patch('cnotebook.render.oemol_to_disp')
    def test_valid_molecule(self, mock_to_disp, mock_oeimage, mock_render):
        """Test converting valid molecule to OEImage"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)
        mock_mol.IsValid.return_value = True

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

    @patch('cnotebook.render.oedepict.OEImage')
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

    @patch('cnotebook.render.oedepict.OEImage')
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


class TestOemolToHtml:
    """Test the oemol_to_html function"""

    @patch('cnotebook.render.oeimage_to_html')
    @patch('cnotebook.render.oemol_to_image')
    def test_oemol_to_html_delegates(self, mock_to_image, mock_image_to_html):
        """Test that oemol_to_html delegates to oemol_to_image + oeimage_to_html"""
        mock_mol = MagicMock(spec=oechem.OEMolBase)

        mock_image = MagicMock()
        mock_to_image.return_value = mock_image
        mock_image_to_html.return_value = '<img>molecule</img>'

        ctx = CNotebookContext()

        result = oemol_to_html(mock_mol, ctx=ctx)

        mock_to_image.assert_called_once_with(mock_mol, ctx=ctx)
        mock_image_to_html.assert_called_once_with(mock_image, ctx=ctx)
        assert result == '<img>molecule</img>'


class TestOeduToDisp:
    """Test the oedu_to_disp function"""

    @patch('cnotebook.render.oemol_to_disp')
    @patch('cnotebook.render.oechem.OEGraphMol')
    def test_with_ligand(self, mock_graphmol_cls, mock_oemol_to_disp):
        """Test DU with a ligand returns (display, ligand) tuple"""
        mock_lig = MagicMock()
        mock_lig.NumAtoms.return_value = 10
        mock_graphmol_cls.return_value = mock_lig

        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_oemol_to_disp.return_value = mock_disp

        ctx = MagicMock(spec=CNotebookContext)

        result = oedu_to_disp(mock_du, ctx=ctx)

        mock_du.GetLigand.assert_called_once_with(mock_lig)
        mock_oemol_to_disp.assert_called_once_with(mock_lig, ctx=ctx)
        assert result == (mock_disp, mock_lig)

    @patch('cnotebook.render.oemol_to_disp')
    @patch('cnotebook.render.oechem.OEGraphMol')
    def test_without_ligand(self, mock_graphmol_cls, mock_oemol_to_disp):
        """Test DU without ligand returns None"""
        mock_lig = MagicMock()
        mock_lig.NumAtoms.return_value = 0
        mock_graphmol_cls.return_value = mock_lig

        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        ctx = MagicMock(spec=CNotebookContext)

        result = oedu_to_disp(mock_du, ctx=ctx)

        mock_du.GetLigand.assert_called_once_with(mock_lig)
        mock_oemol_to_disp.assert_not_called()
        assert result is None

    @patch('cnotebook.render.oemol_to_disp')
    @patch('cnotebook.render.oechem.OEGraphMol')
    def test_with_empty_ligand(self, mock_graphmol_cls, mock_oemol_to_disp):
        """Test DU where GetLigand returns True but ligand has 0 atoms"""
        mock_lig = MagicMock()
        mock_lig.NumAtoms.return_value = 0
        mock_graphmol_cls.return_value = mock_lig

        mock_du = MagicMock(spec=oechem.OEDesignUnit)
        mock_du.GetLigand.return_value = True

        ctx = MagicMock(spec=CNotebookContext)

        result = oedu_to_disp(mock_du, ctx=ctx)

        mock_oemol_to_disp.assert_not_called()
        assert result is None


class TestOeduToImage:
    """Test the oedu_to_image function"""

    @patch('cnotebook.render._draw_du_label')
    @patch('cnotebook.render.oedepict.OERenderMolecule')
    @patch('cnotebook.render.oedepict.OEImage')
    @patch('cnotebook.render.oedu_to_disp')
    def test_with_ligand(self, mock_oedu_to_disp, mock_oeimage, mock_render,
                         mock_draw_label):
        """Test DU with ligand renders to OEImage with label"""
        mock_du = MagicMock(spec=oechem.OEDesignUnit)
        mock_disp = MagicMock(spec=oedepict.OE2DMolDisplay)
        mock_disp.GetWidth.return_value = 400.0
        mock_disp.GetHeight.return_value = 300.0
        mock_lig = MagicMock()
        mock_oedu_to_disp.return_value = (mock_disp, mock_lig)

        mock_image = MagicMock()
        mock_oeimage.return_value = mock_image

        ctx = CNotebookContext()

        result = oedu_to_image(mock_du, ctx=ctx)

        mock_oedu_to_disp.assert_called_once_with(mock_du, ctx=ctx)
        mock_oeimage.assert_called_once_with(400.0, 300.0)
        mock_render.assert_called_once_with(mock_image, mock_disp)
        mock_draw_label.assert_called_once_with(mock_image)
        assert result == mock_image

    @patch('cnotebook.render._draw_du_label')
    @patch('cnotebook.render.oedepict.OEImage')
    @patch('cnotebook.render.oedu_to_disp')
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

    @patch('cnotebook.render._draw_du_label')
    @patch('cnotebook.render.oedepict.OEImage')
    @patch('cnotebook.render.oedu_to_disp')
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

    @patch('cnotebook.render.oeimage_to_html')
    @patch('cnotebook.render.oedu_to_image')
    def test_oedu_to_html_delegates(self, mock_to_image, mock_image_to_html):
        """Test that oedu_to_html delegates to oedu_to_image + oeimage_to_html"""
        mock_du = MagicMock(spec=oechem.OEDesignUnit)

        mock_image = MagicMock()
        mock_to_image.return_value = mock_image
        mock_image_to_html.return_value = '<img>design_unit</img>'

        ctx = CNotebookContext()

        result = oedu_to_html(mock_du, ctx=ctx)

        mock_to_image.assert_called_once_with(mock_du, ctx=ctx)
        mock_image_to_html.assert_called_once_with(mock_image, ctx=ctx)
        assert result == '<img>design_unit</img>'


class TestOeimageToHtml:
    """Test the oeimage_to_html function"""

    @patch('openeye.oedepict.OEWriteImageToString')
    @patch('cnotebook.render.create_img_tag')
    def test_oeimage_to_html_basic(self, mock_create_img, mock_write_image):
        """Test converting OEImage to HTML"""
        mock_image = MagicMock(spec=oedepict.OEImage)
        mock_image.GetWidth.return_value = 400
        mock_image.GetHeight.return_value = 300

        mock_write_image.return_value = b'fake_image_bytes'
        mock_create_img.return_value = '<img>image</img>'

        ctx = CNotebookContext(image_format="png", structure_scale=oedepict.OEScale_Default)

        result = oeimage_to_html(mock_image, ctx=ctx)

        # Should write image to string
        mock_write_image.assert_called_once_with(ctx.image_format, mock_image)
        # Should call create_img_tag with correct dimensions
        mock_create_img.assert_called_once()
        call_args = mock_create_img.call_args
        assert call_args[0][0] == 400  # width
        assert call_args[0][1] == 300  # height
        assert result == '<img>image</img>'


class TestIntegrationWithContext:
    """Integration tests with CNotebookContext"""
    
    def test_context_image_formats(self):
        """Test different image formats with context"""
        png_ctx = CNotebookContext(image_format="png")
        assert png_ctx.image_mime_type == "image/png"
        
        svg_ctx = CNotebookContext(image_format="svg")
        assert svg_ctx.image_mime_type == "image/svg+xml"
    
    def test_render_functions_exist(self):
        """Test that all render functions exist and are callable"""
        assert callable(create_img_tag)
        assert callable(oedisp_to_html)
        assert callable(render_empty_molecule)
        assert callable(render_invalid_molecule)
        assert callable(oemol_to_disp)
        assert callable(oemol_to_image)
        assert callable(oemol_to_html)
        assert callable(oedu_to_disp)
        assert callable(oedu_to_image)
        assert callable(oedu_to_html)
        assert callable(oeimage_to_html)