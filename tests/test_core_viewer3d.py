from cnotebook.core.convert import convert_molecule
from cnotebook.core import viewer3d
from openeye import oechem


def _benzene():
    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "c1ccccc1")
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
    md = convert_molecule(mol, name="</script><script>alert(1)</script>")
    payload = viewer3d.build_init_payload(
        [md], [], ui=None, ui_explicit=False,
        theme="auto", background=None, zoom_to=None, orient=None,
    )
    html = viewer3d.render_html(payload, width=640, height=480)
    # The literal closing tag must be escaped, not present verbatim in the payload script.
    assert "</script><script>alert(1)" not in html
    assert "\\u003c/script\\u003e" in html
