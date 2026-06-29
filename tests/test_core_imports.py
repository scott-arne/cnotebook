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
