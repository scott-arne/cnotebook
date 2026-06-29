def test_core_context_exports_render_context():
    from cnotebook.core.context import CNotebookContext, RenderContext
    assert RenderContext is CNotebookContext


def test_old_context_path_still_works():
    # Back-compat: the pre-extraction import path must keep resolving.
    from cnotebook.context import CNotebookContext as Old
    from cnotebook.core.context import CNotebookContext as New
    assert Old is New
