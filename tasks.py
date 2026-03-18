import json
import re
import shutil
import sys
# noinspection PyPackageRequirements
from invoke.tasks import task
from pathlib import Path

ROOT = Path(__file__).parent.absolute()

@task
def test(c):
    """Run the test suite with pytest"""
    c.run(f"{sys.executable} -m pytest tests/")


@task
def build(c):
    """Build distribution packages"""
    c.run("rm -rf dist")
    c.run(f"{sys.executable} -m build")


@task
def upload(c):
    """Upload package to PyPI (requires PyPI credentials configured)"""
    c.run("rm -rf dist")
    c.run(f"{sys.executable} -m build")
    c.run(f"{sys.executable} -m twine upload dist/*")


@task
def publish(c):
    c.run(f"cd {ROOT} && rm -rf dist/ && {sys.executable} -m build --wheel && {sys.executable} -m twine upload dist/*")


@task
def docs(c):
    """Build Sphinx documentation"""
    docs_dir = ROOT / "docs"
    build_dir = docs_dir / "_build"
    c.run(f"cd {docs_dir} && {sys.executable} -m sphinx -b html . {build_dir}/html")


@task(pre=[docs])
def serve_docs(c, port=8000, watch=False):
    """Serve Sphinx documentation locally.

    :param port: Port to serve on (default: 8000).
    :param watch: Watch for changes and auto-rebuild (requires sphinx-autobuild).
    """
    docs_dir = ROOT / "docs"
    html_dir = docs_dir / "_build" / "html"

    if watch:
        # Use sphinx-autobuild for watching/auto-rebuild
        print(f"Watching for changes and serving docs at http://localhost:{port}")
        c.run(f"{sys.executable} -m sphinx_autobuild {docs_dir} {html_dir} --port {port}")
    else:
        if not html_dir.exists():
            print("Documentation not built. Building first...")
            docs(c)
        print(f"Serving docs at http://localhost:{port}")
        c.run(f"cd {html_dir} && {sys.executable} -m http.server {port}")


@task
def update_gui(c, ref=None):
    """Build 3dmol-js-gui from the vendor submodule and copy assets into cnotebook.

    :param ref: Git ref (tag, branch, commit) to checkout. If omitted, pulls latest master.
    """
    gui_dir = ROOT / "vendor" / "3dmol-js-gui"
    dist_assets = gui_dir / "dist" / "assets"
    static_dir = ROOT / "cnotebook" / "c3d" / "static"

    # Check npm is available
    result = c.run("command -v npm", warn=True, hide=True)
    if not result.ok:
        raise SystemExit("npm not found on PATH. Install Node.js to build 3dmol-js-gui.")

    # Validate ref if provided
    if ref and not re.match(r'^[a-zA-Z0-9._/^~-]+$', ref):
        raise SystemExit(f"Invalid git ref: {ref}")

    # Initialize submodule if needed
    if not (gui_dir / "package.json").exists():
        print("Submodule not initialized. Running git submodule update --init...")
        c.run("git submodule update --init vendor/3dmol-js-gui")

    # Update to desired ref
    if ref:
        c.run(f"cd {gui_dir} && git fetch origin && git checkout {ref}")
    else:
        c.run(f"cd {gui_dir} && git fetch origin master && git checkout origin/master")

    # Clean stale build artifacts
    if dist_assets.parent.exists():
        shutil.rmtree(dist_assets.parent)
        print("Cleaned stale dist/ directory.")

    # Install dependencies and build
    c.run(f"cd {gui_dir} && npm install")
    c.run(f"cd {gui_dir} && npm run build")

    # Find and copy built assets
    js_files = list(dist_assets.glob("*.js"))
    css_files = list(dist_assets.glob("*.css"))

    if len(js_files) != 1:
        raise SystemExit(f"Expected 1 JS file in dist/assets/, found {len(js_files)}: {js_files}")
    if len(css_files) != 1:
        raise SystemExit(f"Expected 1 CSS file in dist/assets/, found {len(css_files)}: {css_files}")

    shutil.copy2(js_files[0], static_dir / "3dmol-gui.js")
    shutil.copy2(css_files[0], static_dir / "3dmol-gui.css")

    # Report version
    with open(gui_dir / "package.json") as f:
        version = json.load(f)["version"]
    print(f"3dmol-js-gui v{version} assets copied to {static_dir}")
