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


def test_core_never_imports_a_notebook_runtime():
    # cnotebook.core is the layer that knows only the OpenEye Toolkits and the standard
    # library; a module that reaches for IPython or marimo -- including the private
    # display helpers, whose whole job is to look for them -- does not belong in it.
    import ast
    from pathlib import Path

    import cnotebook.core

    forbidden = {"IPython", "marimo", "cnotebook._display_support"}
    offenders = []
    for path in sorted(Path(cnotebook.core.__path__[0]).rglob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            # A lazy import inside a function is still a dependency of the layer, so the
            # whole tree is walked rather than just the module body.
            offenders += [f"{path.name}:{node.lineno} {name}" for name in names
                          if name.split(".")[0] in forbidden or name in forbidden]
    assert offenders == []


def test_core_imports_with_no_notebook_runtime_installed():
    # The static check above cannot see an import hidden behind a try/except, and
    # oefastapi installs neither notebook runtime, so prove the layer really loads.
    import subprocess
    import sys

    code = (
        "import builtins, pkgutil, sys\n"
        "real = builtins.__import__\n"
        "def guard(name, *args, **kwargs):\n"
        "    if name.split('.')[0] in ('IPython', 'marimo'): raise ImportError(name)\n"
        "    return real(name, *args, **kwargs)\n"
        "builtins.__import__ = guard\n"
        "import cnotebook.core\n"
        "for info in pkgutil.iter_modules(cnotebook.core.__path__):\n"
        "    __import__('cnotebook.core.' + info.name)\n"
        "print('IPython' in sys.modules, 'marimo' in sys.modules)\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("False False")
