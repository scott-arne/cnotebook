"""Tests for MolGrid interactive molecule grid."""


def test_molgrid_import():
    """Test that MolGrid can be imported."""
    from cnotebook.molgrid import MolGrid
    assert MolGrid is not None
