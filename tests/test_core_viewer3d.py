import json
import warnings
from pathlib import Path

from openeye import oechem

from cnotebook.core import viewer3d
from cnotebook.core.convert import convert_molecule
from cnotebook.core.errors import CNotebookWarning


def _benzene():
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CNotebookWarning)
        return convert_molecule(mol, name="benzene")


def test_build_init_payload_single_molecule_smart_ui():
    payload = viewer3d.build_init_payload(
        [_benzene()], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    # One molecule => no panels, and orient defaults to True.
    assert payload["ui"] == {"sidebar": False, "menubar": False, "console": False}
    assert payload["orient"] is True
    assert payload["molecules"][0]["name"] == "benzene"
    assert payload["theme"] == "auto"


def test_render_html_sets_container_size_and_inlines_payload():
    payload = viewer3d.build_init_payload(
        [_benzene()], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    html = viewer3d.render_html(payload, width=640, height=480)
    assert "window.__C3D_INIT__" in html
    assert "3Dmol" in html  # the 3Dmol.js bundle is inlined
    # Container sizing applied to the standalone document root.
    assert "width: 640px" in html or "width:640px" in html
    assert "height: 480px" in html or "height:480px" in html


def test_render_html_escapes_script_breakout():
    # A molecule name containing </script> must not break out of the inline script.
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CNotebookWarning)
        md = convert_molecule(mol, name="</script><script>alert(1)</script>")
    payload = viewer3d.build_init_payload(
        [md], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    html = viewer3d.render_html(payload, width=640, height=480)
    # The literal closing tag must be escaped, not present verbatim in the payload script.
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e" in html


_VECTORS_PATH = Path("tests/js/fixtures/script_json_vectors.json")


def _script_json_vectors():
    """Load the escaping vectors shared with the JavaScript suite."""
    return json.loads(_VECTORS_PATH.read_text())


def test_script_json_vectors_pin_the_forbidden_set():
    # Dropping a character from the fixture must fail here and in the JS suite, not
    # quietly weaken both.
    assert _script_json_vectors()["forbidden"] == ["<", ">", "&", chr(0x2028), chr(0x2029)]


def test_escape_script_json_vectors():
    spec = _script_json_vectors()
    for case in spec["cases"]:
        out = viewer3d.escape_script_json(case["input"])
        for bad in spec["forbidden"]:
            assert bad not in out, f"{bad!r} survived in {out!r}"
        assert json.loads(out) == case["input"]


def test_escape_script_json_matches_the_javascript_expectations():
    # The same fixture pins the JS escaper, so a byte-for-byte comparison here is
    # what keeps the two implementations one contract rather than two dialects.
    spec = _script_json_vectors()
    for case in spec["cases"]:
        assert viewer3d.escape_script_json(case["input"]) == case["expected"]


def test_escape_script_json_is_pure_ascii_for_every_vector():
    for case in _script_json_vectors()["cases"]:
        out = viewer3d.escape_script_json(case["input"])
        assert out.isascii(), f"non-ASCII survived in {out!r}"
        assert out.isprintable()


def test_render_html_stays_encodable_with_a_lone_surrogate_name():
    # os.fsdecode of a non-UTF-8 filename produces lone surrogates. If they reached the
    # payload text raw, the documented export (open(...).write(html)) and any HTTP
    # consumer would raise UnicodeEncodeError.
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", CNotebookWarning)
        md = convert_molecule(mol, name="mol_\udce9")
    payload = viewer3d.build_init_payload(
        [md], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    html = viewer3d.render_html(payload, width=640, height=480)
    assert "\\udce9" in html
    html.encode("utf-8")  # would raise UnicodeEncodeError on a raw surrogate


def test_render_html_embeds_the_public_escaper_output():
    payload = viewer3d.build_init_payload(
        [_benzene()], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    html = viewer3d.render_html(payload, width=640, height=480)
    assert f"window.__C3D_INIT__ = {viewer3d.escape_script_json(payload)};" in html


def test_bundled_gui_exposes_host_api():
    # Resolve the bundle from the imported package, not the cwd, so the test always
    # reads the assets that ship with the code under test.
    bundle_path = Path(viewer3d.__file__).parent / "static" / "3dmol-gui.js"
    bundle = bundle_path.read_text()
    assert "window.c3d" in bundle or "c3d=" in bundle, f"no host API in {bundle_path}"
    assert '"0.4.0"' in bundle or "0.4.0" in bundle, f"no 0.4.0 marker in {bundle_path}"
