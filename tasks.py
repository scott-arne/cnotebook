from invoke import task


@task
def test(c):
    """Run the test suite with pytest"""
    c.run("python -m pytest tests/")


@task
def build(c):
    """Build distribution packages"""
    c.run("rm -rf dist")
    c.run("python -m build")


@task
def upload(c):
    """Upload package to PyPI (requires PyPI credentials configured)"""
    c.run("rm -rf dist")
    c.run("python -m build")
    c.run("python -m twine upload dist/*")
