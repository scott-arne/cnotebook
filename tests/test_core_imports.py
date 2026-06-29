def test_core_context_exports_render_context():
    from cnotebook.core.context import CNotebookContext, RenderContext
    assert RenderContext is CNotebookContext


def test_old_context_path_still_works():
    # Back-compat: the pre-extraction import path must keep resolving.
    from cnotebook.context import CNotebookContext as Old
    from cnotebook.core.context import CNotebookContext as New
    assert Old is New


def test_core_render_exports():
    from cnotebook.core.render import oemol_to_image, oeimage_to_html
    assert callable(oemol_to_image)
    assert callable(oeimage_to_html)


def test_old_render_path_still_works():
    from cnotebook.render import oemol_to_image as old
    from cnotebook.core.render import oemol_to_image as new
    assert old is new


def test_core_helpers_align_exports():
    from cnotebook.core.helpers import highlight_smarts
    from cnotebook.core.align import create_aligner
    assert callable(highlight_smarts)
    assert callable(create_aligner)


def test_old_helpers_align_paths_still_work():
    from cnotebook.helpers import highlight_smarts as old_h
    from cnotebook.core.helpers import highlight_smarts as new_h
    from cnotebook.align import create_aligner as old_a
    from cnotebook.core.align import create_aligner as new_a
    assert old_h is new_h and old_a is new_a


def test_core_convert_exports():
    from cnotebook.core.convert import MoleculeData, convert_molecule, convert_design_unit
    assert callable(MoleculeData)
    assert callable(convert_molecule)
    assert callable(convert_design_unit)


def test_old_convert_path_still_works():
    from cnotebook.c3d.convert import convert_molecule as old
    from cnotebook.core.convert import convert_molecule as new
    assert old is new
