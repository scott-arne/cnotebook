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
