# Contributing to CNotebook

Thank you for your interest in contributing to CNotebook! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Style](#code-style)
- [Submitting Changes](#submitting-changes)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Enhancements](#suggesting-enhancements)

## Code of Conduct

This project adheres to a Code of Conduct that all contributors are expected to follow. Please read [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) before contributing.

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/your-username/cnotebook.git
   cd cnotebook
   ```
3. **Add the upstream repository**:
   ```bash
   git remote add upstream https://github.com/[original-owner]/cnotebook.git
   ```

## Development Setup

### Prerequisites

- Python 3.10 or higher
- OpenEye Toolkits (requires license)
- Git

### Installing Dependencies

1. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install the package in development mode**:
   ```bash
   pip install -e .
   ```

3. **Install development dependencies**:
   ```bash
   pip install -e ".[dev,test]"
   ```

### OpenEye Toolkits Setup

CNotebook requires the OpenEye Toolkits. You'll need:
- A valid OpenEye license
- `openeye-toolkits` and `oepandas` packages installed

If you don't have access to OpenEye Toolkits, please note this in your PR and maintainers can test on your behalf.

## Making Changes

### Branching Strategy

1. **Create a feature branch** from `master`:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Branch naming conventions**:
   - `feature/` - New features
   - `fix/` - Bug fixes
   - `docs/` - Documentation updates
   - `test/` - Test improvements
   - `refactor/` - Code refactoring

### Commit Messages

Write clear, descriptive commit messages:

```
Short summary (50 chars or less)

More detailed explanation if needed. Wrap at 72 characters.
Explain the problem this commit solves and why you chose
this solution.

Fixes #123
```

**Guidelines:**
- Use present tense ("Add feature" not "Added feature")
- Start with a capital letter
- No period at the end of the summary line
- Reference issues and PRs when relevant

## Testing

### Running Tests

Run the full test suite:
```bash
pytest tests/
```

Run with coverage:
```bash
pytest --cov=cnotebook --cov-report=term-missing tests/
```

Run specific test file:
```bash
pytest tests/test_context.py
```

Run tests matching a pattern:
```bash
pytest -k "test_display"
```

### Writing Tests

- **Location**: Place tests in the `tests/` directory
- **Naming**: Test files should start with `test_`
- **Structure**: Use descriptive class and function names

**Example**:
```python
class TestNewFeature:
    def test_basic_functionality(self):
        # Arrange
        mol = create_test_molecule()

        # Act
        result = new_feature(mol)

        # Assert
        assert result is not None
```

### Test Requirements

- All new features must include tests
- Bug fixes should include regression tests
- Aim for high test coverage (75%+ for new code)
- Tests should be independent and repeatable

## Code Style

### Python Style Guide

We follow [PEP 8](https://pep8.org/) with some modifications:

- **Line length**: 100 characters (not 79)
- **Indentation**: 4 spaces (no tabs)
- **Imports**: Organized by standard library, third-party, local
- **Docstrings**: Use for all public functions, classes, and modules

### Type Hints

Use type hints for function signatures:
```python
def render_molecule(mol: oechem.OEMolBase, width: int = 250) -> str:
    """
    Render a molecule as HTML.

    Args:
        mol: OpenEye molecule object
        width: Image width in pixels

    Returns:
        HTML string containing the rendered molecule
    """
    pass
```

### Documentation

- **Docstrings**: Required for public APIs
- **Comments**: Use sparingly, prefer self-documenting code
- **README updates**: Include if adding features or changing behavior

## Submitting Changes

### Before Submitting

**Checklist**:
- [ ] Code follows the style guidelines
- [ ] Tests pass locally
- [ ] New tests added for new functionality
- [ ] Documentation updated if needed
- [ ] Commit messages are clear and descriptive
- [ ] No merge conflicts with master

### Pull Request Process

1. **Push your changes** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```

2. **Create a Pull Request** on GitHub:
   - Use a clear, descriptive title
   - Reference related issues
   - Describe what changed and why
   - Include screenshots for UI changes
   - List any breaking changes

3. **PR Template**:
   ```markdown
   ## Description
   Brief description of the changes

   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update

   ## Testing
   Describe the tests you ran

   ## Checklist
   - [ ] Tests pass
   - [ ] Code follows style guidelines
   - [ ] Documentation updated
   ```

4. **Code Review**:
   - Address reviewer feedback promptly
   - Update your PR based on comments
   - Request re-review when ready

### After Your PR is Merged

1. **Delete your feature branch**:
   ```bash
   git branch -d feature/your-feature-name
   git push origin --delete feature/your-feature-name
   ```

2. **Update your local master**:
   ```bash
   git checkout master
   git pull upstream master
   ```

## Reporting Bugs

### Before Reporting

1. **Check existing issues** - Your bug may already be reported
2. **Try the latest version** - It might already be fixed
3. **Verify it's reproducible** - Ensure it happens consistently

### Bug Report Template

```markdown
**Description**
Clear description of the bug

**To Reproduce**
Steps to reproduce:
1. Import cnotebook
2. Create molecule with...
3. See error

**Expected Behavior**
What you expected to happen

**Actual Behavior**
What actually happened

**Environment**
- CNotebook version:
- Python version:
- Operating System:
- OpenEye Toolkits version:

**Additional Context**
Any other relevant information
```

## Suggesting Enhancements

### Enhancement Proposal Template

```markdown
**Feature Description**
Clear description of the proposed feature

**Motivation**
Why is this feature needed? What problem does it solve?

**Proposed Solution**
How would you implement this?

**Alternatives Considered**
What other approaches did you consider?

**Additional Context**
Mockups, examples, or references
```

## Development Tips

### Useful Commands

```bash
# Run tests with verbose output
pytest -v tests/

# Run only failed tests
pytest --lf

# Generate coverage HTML report
pytest --cov=cnotebook --cov-report=html tests/

# Build distribution packages
python -m build

# Install in editable mode
pip install -e .
```

### IDE Setup

**VS Code** recommended extensions:
- Python
- Pylance
- Python Test Explorer

**PyCharm** configuration:
- Enable pytest as default test runner
- Configure project interpreter with OpenEye environment

## Questions?

If you have questions about contributing:
- Open a GitHub Discussion
- Email: scott.arne.johnson@gmail.com
- Check existing issues and PRs for examples

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to CNotebook! 🧬✨
