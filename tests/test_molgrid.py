"""Tests for MolGrid interactive molecule grid."""

import pytest
from openeye import oechem, oedepict
from cnotebook.context import CNotebookContext
from cnotebook.grid import BEST_FIT_ORIENTATION


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def simple_mol():
    """Create a simple test molecule (ethanol)."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    return mol


@pytest.fixture
def mol_with_sd_data():
    """Create a molecule with SD data."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")
    oechem.OESetSDData(mol, "MW", "46.07")
    oechem.OESetSDData(mol, "Formula", "C2H6O")
    return mol


@pytest.fixture
def sample_molecules():
    """Create a set of test molecules."""
    smiles_list = [
        ("CCO", "Ethanol"),
        ("CC(=O)O", "Acetic Acid"),
        ("c1ccccc1", "Benzene"),
        ("CC(=O)Nc1ccc(O)cc1", "Acetaminophen"),
        ("CC(C)Cc1ccc(C(C)C(=O)O)cc1", "Ibuprofen"),
    ]
    mols = []
    for smiles, name in smiles_list:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mol.SetTitle(name)
        oechem.OESetSDData(mol, "SMILES", smiles)
        mols.append(mol)
    return mols


@pytest.fixture
def invalid_mol():
    """Create an invalid/empty molecule."""
    return oechem.OEGraphMol()


def test_cnotebook_molgrid_function():
    """The top-level factory should build a configured MolGrid."""
    from cnotebook import MolGrid, molgrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = molgrid(
        [mol],
        title=False,
        width=160,
        height=120,
        n_items_per_page=5,
        select=False,
        information=False,
        name="factory-test",
    )

    assert isinstance(grid, MolGrid)
    assert grid._molecules == [mol]
    assert grid.title is None
    assert grid.width == 160
    assert grid.height == 120
    assert grid.n_items_per_page == 5
    assert grid.selection_enabled is False
    assert grid.information_enabled is False
    assert grid.name == "factory-test"


def test_cnotebook_molgrid_factory_uses_class_render_defaults(simple_mol):
    """The top-level factory should match MolGrid render defaults."""
    from cnotebook import molgrid

    grid = molgrid([simple_mol])
    single_ctx = CNotebookContext()

    assert grid.structure_scale == pytest.approx(single_ctx.structure_scale)
    assert grid.atom_label_font_scale == pytest.approx(single_ctx.atom_label_font_scale)
    assert grid.bond_width_scaling is True


# ============================================================================
# Initialization Tests
# ============================================================================

def test_molgrid_stores_molecules(simple_mol):
    """Test that MolGrid stores molecule data."""
    from cnotebook import MolGrid

    mol2 = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol2, "CC")
    mol2.SetTitle("Ethane")

    grid = MolGrid([simple_mol, mol2])

    assert len(grid._molecules) == 2
    assert grid._molecules[0].GetTitle() == "Ethanol"
    assert grid._molecules[1].GetTitle() == "Ethane"


def test_molgrid_default_parameters(simple_mol):
    """Test MolGrid default parameter values."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])

    assert grid.title is True
    assert grid.tooltip_fields == []
    assert grid.n_items_per_page == 24
    assert grid.width == 260
    assert grid.height == 240
    assert grid.image_format == "svg"
    assert grid.selection_enabled is True
    assert grid.atom_label_font_scale == pytest.approx(1.15)
    assert grid.atom_label_font_scale == pytest.approx(CNotebookContext().atom_label_font_scale)
    assert grid.structure_scale == pytest.approx(CNotebookContext().structure_scale)
    assert grid.bond_width_scaling is True
    assert grid.render_title is False
    assert grid.depict_orientation == BEST_FIT_ORIENTATION


def test_molgrid_does_not_enlarge_small_molecules_past_grid_scale(simple_mol):
    """Small molecules should keep the grid's baseline depiction scale."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    prepared = grid._prepare_molecule_for_rendering(simple_mol)
    display = grid._create_render_context().create_molecule_display(prepared)

    assert display.GetScale() == pytest.approx(grid._baseline_scale)


def test_molgrid_compact_molecule_matches_single_molecule_scale_and_bonds():
    """Compact molecules should match the single-molecule depiction style."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CC(C)(C)c1nn(C)c(C(=O)O)c1O")

    grid = MolGrid([mol])
    single_ctx = CNotebookContext()
    single = oechem.OEGraphMol(mol)
    oedepict.OEPrepareDepiction(single, True)
    single_display = single_ctx.create_molecule_display(single)

    prepared = grid._prepare_molecule_for_rendering(mol)
    display = grid._create_molecule_display(prepared)

    single_bond_widths = [
        bond_display.GetBgnPen().GetLineWidth()
        for bond_display in single_display.GetBondDisplays()
    ]
    grid_bond_widths = [
        bond_display.GetBgnPen().GetLineWidth()
        for bond_display in display.GetBondDisplays()
    ]

    assert display.GetScale() == pytest.approx(single_display.GetScale())
    assert max(grid_bond_widths) == pytest.approx(max(single_bond_widths))


def test_molgrid_best_fit_orients_elongated_molecules_to_fill_card():
    """Best-fit (the default) should widen elongated molecules to fill the card.

    An elongated molecule rendered in its natural single-molecule orientation
    becomes a narrow vertical strip in a near-square card. Best-fit instead
    picks the orientation that lets it render at a larger scale.
    """
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(
        mol,
        "O=C(Nc1ccc(F)c(Cl)c1)N1CCN(CC1)c1ccc(OCc2ccccc2)cc1",
    )

    grid = MolGrid([mol])
    assert grid.depict_orientation == BEST_FIT_ORIENTATION

    best_fit = grid._prepare_molecule_for_rendering(mol)
    natural = grid._prepare_in_orientation(mol, oedepict.OEDepictOrientation_Default)

    best_coords = [best_fit.GetCoords(atom) for atom in best_fit.GetAtoms()]
    best_xs = [coord[0] for coord in best_coords]
    best_ys = [coord[1] for coord in best_coords]

    # Best-fit lays the molecule out wider than tall and renders at a larger
    # scale than the natural single-molecule orientation would in this card.
    assert max(best_xs) - min(best_xs) > max(best_ys) - min(best_ys)
    assert grid._fitting_scale(best_fit) >= grid._fitting_scale(natural)


def test_molgrid_explicit_orientation_matches_single_molecule():
    """An explicit Default orientation should match single-molecule layout."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(
        mol,
        "O=C(Nc1ccc(F)c(Cl)c1)N1CCN(CC1)c1ccc(OCc2ccccc2)cc1",
    )

    grid = MolGrid([mol], depict_orientation=oedepict.OEDepictOrientation_Default)
    prepared = grid._prepare_molecule_for_rendering(mol)
    single = oechem.OEGraphMol(mol)
    oedepict.OEPrepareDepiction(single, True)

    coords = [prepared.GetCoords(atom) for atom in prepared.GetAtoms()]
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    single_coords = [single.GetCoords(atom) for atom in single.GetAtoms()]
    single_xs = [coord[0] for coord in single_coords]
    single_ys = [coord[1] for coord in single_coords]

    assert max(xs) - min(xs) == pytest.approx(max(single_xs) - min(single_xs))
    assert max(ys) - min(ys) == pytest.approx(max(single_ys) - min(single_ys))


def test_molgrid_can_prepare_wide_depictions_when_requested():
    """Elongated drug-like molecules can still be rendered horizontally."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(
        mol,
        "O=C(Nc1ccc(F)c(Cl)c1)N1CCN(CC1)c1ccc(OCc2ccccc2)cc1",
    )

    grid = MolGrid([mol], depict_orientation=oedepict.OEDepictOrientation_Horizontal)
    prepared = grid._prepare_molecule_for_rendering(mol)

    coords = [prepared.GetCoords(atom) for atom in prepared.GetAtoms()]
    xs = [coord[0] for coord in coords]
    ys = [coord[1] for coord in coords]
    assert max(xs) - min(xs) > max(ys) - min(ys)


def test_molgrid_scales_bond_widths_for_larger_molecules_by_default():
    """Larger scaled-down molecules should not keep the unscaled bond pen."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(
        mol,
        "O=C(Nc1ccc(F)c(Cl)c1)N1CCN(CC1)c1ccc(OCc2ccccc2)cc1",
    )

    grid = MolGrid([mol])
    prepared = grid._prepare_molecule_for_rendering(mol)
    display = grid._create_molecule_display(prepared)

    assert display.GetWidth() <= grid.width
    assert display.GetHeight() <= grid.height
    assert display.GetScale() < oedepict.OEScale_Default

    bond_widths = [
        bond_display.GetBgnPen().GetLineWidth()
        for bond_display in display.GetBondDisplays()
    ]

    assert max(bond_widths) < oedepict.OE2DMolDisplayOptions().GetDefaultBondPen().GetLineWidth()


def test_molgrid_tightens_margin_to_enlarge_large_molecules():
    """Large molecules should render larger than at OpenEye's default margin."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(
        mol,
        "O=C1CCC(N2C(=O)c3cccc(NC(=O)CCCCCCN4CCN(c5ccc(Nc6ncc(Cl)c"
        "(Nc7ccccc7)n6)cc5)CC4)c3C2=O)C(=O)N1",
    )

    grid = MolGrid([mol])
    prepared = grid._prepare_molecule_for_rendering(mol)
    display = grid._create_molecule_display(prepared)

    # Reference: same molecule at OpenEye's default 5% depiction margin.
    default_opts = oedepict.OE2DMolDisplayOptions()
    default_opts.SetWidth(grid.width)
    default_opts.SetHeight(grid.height)
    default_opts.SetScale(grid._baseline_scale)
    default_opts.SetTitleLocation(oedepict.OETitleLocation_Hidden)
    default_scale = oedepict.OE2DMolDisplay(prepared, default_opts).GetScale()

    # The molecule must shrink below the baseline scale to fit, and the
    # tightened grid margin lets it render larger than the default would.
    assert display.GetScale() < grid._baseline_scale
    assert display.GetScale() > default_scale


def test_molgrid_margin_does_not_enlarge_small_molecules(simple_mol):
    """Small molecules stay at the baseline scale regardless of margin."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    prepared = grid._prepare_molecule_for_rendering(simple_mol)
    display = grid._create_molecule_display(prepared)

    assert display.GetScale() == pytest.approx(grid._baseline_scale)


def test_molgrid_set_render_options(simple_mol):
    """MolGrid render options should update the grid rendering context."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])

    result = grid.set_render_options(
        width=320,
        height=240,
        min_width=180,
        min_height=160,
        max_width=360,
        max_height=280,
        structure_scale=1.5,
        auto_scale=True,
        atom_label_font_scale=1.25,
        title_font_scale=0.9,
        image_format="png",
        bond_width_scaling=True,
        title=True,
        max_heavy_atoms=None,
    )

    assert result is None
    assert grid.width == 320
    assert grid.height == 240
    assert grid.min_width == 180
    assert grid.min_height == 160
    assert grid.max_width == 360
    assert grid.max_height == 280
    assert grid.structure_scale == 1.5
    assert grid.auto_scale is True
    assert grid.atom_label_font_scale == 1.25
    assert grid.title_font_scale == 0.9
    assert grid.image_format == "png"
    assert grid.bond_width_scaling is True
    assert grid.render_title is True
    assert grid.max_heavy_atoms is None


def test_molgrid_set_render_options_updates_rendered_output(simple_mol):
    """MolGrid should use updated render options for later HTML output."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])

    grid.set_render_options(width=320, height=240, image_format="png")

    html = grid.to_html()

    assert '"image_width":320' in html
    assert '"image_height":240' in html
    assert "data:image/png" in html


def test_molgrid_custom_parameters(simple_mol):
    """Test MolGrid with custom parameters."""
    from cnotebook import MolGrid

    grid = MolGrid(
        [simple_mol],
        title="Name",
        tooltip_fields=["MW", "Formula"],
        n_items_per_page=12,
        width=250,
        height=180,
        image_format="png",
        select=False,
        atom_label_font_scale=2.0,
        name="custom-grid"
    )

    assert grid.title == "Name"
    assert grid.tooltip_fields == ["MW", "Formula"]
    assert grid.n_items_per_page == 12
    assert grid.width == 250
    assert grid.height == 180
    assert grid.image_format == "png"
    assert grid.selection_enabled is False
    assert grid.atom_label_font_scale == 2.0
    assert grid.name == "custom-grid"


def test_molgrid_auto_generates_name(simple_mol):
    """Test that MolGrid auto-generates unique names."""
    from cnotebook import MolGrid

    grid1 = MolGrid([simple_mol])
    grid2 = MolGrid([simple_mol])

    assert grid1.name is not None
    assert grid2.name is not None
    assert grid1.name != grid2.name
    assert grid1.name.startswith("molgrid-")
    assert grid2.name.startswith("molgrid-")


def test_molgrid_construction_creates_no_widget(simple_mol):
    """Construction must not build a front end; the widget is created on demand."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])

    assert grid._widget is None
    assert grid.closed is False
    assert grid.name.startswith("molgrid-")


def test_molgrid_empty_molecules():
    """Test MolGrid with empty molecule list."""
    from cnotebook import MolGrid

    grid = MolGrid([])

    assert len(grid._molecules) == 0
    html = grid.to_html()
    assert "molgrid" in html.lower()


def test_molgrid_with_invalid_molecules(simple_mol, invalid_mol):
    """Test MolGrid handles invalid molecules gracefully."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol, invalid_mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()
    assert len(grid._molecules) == 2


def test_molgrid_search_fields_parameter(simple_mol):
    """Test that explicit search_fields parameter is used."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], search_fields=["MW", "Formula"])

    assert grid.search_fields == ["MW", "Formula"]


# ============================================================================
# Data Preparation Tests
# ============================================================================

def test_molgrid_prepare_data_basic(mol_with_sd_data):
    """Test _prepare_data extracts basic data correctly."""
    from cnotebook import MolGrid

    grid = MolGrid([mol_with_sd_data], title="Title", tooltip_fields=["MW"])
    data = grid._prepare_data()

    assert len(data) == 1
    assert data[0]["index"] == 0
    assert data[0]["title"] == "Ethanol"
    assert data[0]["tooltip"]["MW"] == "46.07"
    assert "img" in data[0]
    assert "smiles" in data[0]


def test_molgrid_prepare_data_smiles(simple_mol):
    """Test that SMILES is correctly extracted."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    data = grid._prepare_data()

    assert data[0]["smiles"] == "CCO"


def test_molgrid_prepare_data_no_title(simple_mol):
    """Test _prepare_data with title=None."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], title=None)
    data = grid._prepare_data()

    assert data[0]["title"] is None


def test_molgrid_prepare_data_missing_sd_data(simple_mol):
    """Test _prepare_data when SD data field doesn't exist."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], tooltip_fields=["NonExistentField"])
    data = grid._prepare_data()

    assert data[0]["tooltip"]["NonExistentField"] is None


def test_molgrid_prepare_data_search_fields(mol_with_sd_data):
    """Test _prepare_data extracts search fields."""
    from cnotebook import MolGrid

    grid = MolGrid([mol_with_sd_data], search_fields=["MW", "Formula"])
    data = grid._prepare_data()

    assert data[0]["search_fields"]["MW"] == "46.07"
    assert data[0]["search_fields"]["Formula"] == "C2H6O"


def test_molgrid_prepare_data_invalid_mol(invalid_mol):
    """Test _prepare_data handles invalid molecules."""
    from cnotebook import MolGrid

    grid = MolGrid([invalid_mol])
    data = grid._prepare_data()

    assert len(data) == 1
    assert data[0]["smiles"] == ""
    assert "img" in data[0]


# ============================================================================
# Export Data Tests
# ============================================================================

def test_molgrid_prepare_export_data_basic(simple_mol):
    """Test _prepare_export_data basic functionality."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    export_data = grid._prepare_export_data()

    assert len(export_data) == 1
    assert export_data[0]["index"] == 0
    assert export_data[0]["smiles"] == "CCO"


def test_molgrid_prepare_export_data_multiple_mols(sample_molecules):
    """Test _prepare_export_data with multiple molecules."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    export_data = grid._prepare_export_data()

    assert len(export_data) == 5
    assert export_data[0]["smiles"] == "CCO"
    assert export_data[2]["smiles"] == "c1ccccc1"


def test_molgrid_prepare_export_data_invalid_mol(invalid_mol):
    """Test _prepare_export_data with invalid molecule."""
    from cnotebook import MolGrid

    grid = MolGrid([invalid_mol])
    export_data = grid._prepare_export_data()

    assert export_data[0]["smiles"] == ""


# ============================================================================
# HTML Generation Tests
# ============================================================================

def test_molgrid_generates_html(simple_mol):
    """Test that MolGrid generates valid HTML output."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "<!DOCTYPE html>" in html
    assert "<html" in html.lower()
    assert "</html>" in html.lower()


def test_molgrid_html_contains_grid_elements(simple_mol):
    """Test the document mounts the front end and carries none of the old markup."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert '<div id="molgrid-root"></div>' in html
    assert "__CNOTEBOOK_MOLGRID_STATIC__" in html
    # The cards are built by the embedded module; no server-rendered list remains.
    assert "molgrid-container" not in html
    assert "List(" not in html


def test_molgrid_html_contains_title(simple_mol):
    """Test HTML contains molecule title."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "Ethanol" in html


def test_molgrid_html_contains_svg(simple_mol):
    """Test SVG images are embedded, escaped for the script context they travel in."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], image_format="svg")
    html = grid.to_html()

    assert "\\u003csvg" in html.lower()
    assert "<svg" not in html.lower()


def test_molgrid_html_contains_search_elements(simple_mol):
    """Test HTML contains search-related elements."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid-search" in html
    assert "Properties" in html
    assert "SMARTS" in html


def test_molgrid_html_contains_actions_menu(simple_mol):
    """Test the document ships the front end that draws the actions menu."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    # The menu is built by the embedded module; Python only supplies what it exports.
    assert "Select all" in html
    assert "Invert selection" in html
    assert "Save CSV" in html
    assert '"export_columns":' in html


def test_molgrid_html_contains_checkbox_when_enabled(simple_mol):
    """Test the document tells the front end that selection is enabled."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], select=True)
    html = grid.to_html()

    assert '"select":true' in html


def test_molgrid_html_no_checkbox_when_disabled(simple_mol):
    """Test HTML does not contain checkbox when select=False."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], select=False)
    html = grid.to_html()

    assert 'class="molgrid-checkbox"' not in html


def test_molgrid_html_pagination_info(sample_molecules):
    """Test the document carries the page size and every molecule to page through."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, n_items_per_page=3)
    html = grid.to_html()

    assert '"page_size":3' in html
    assert f'"i":{len(sample_molecules) - 1}' in html


def test_molgrid_html_export_data_embedded(simple_mol):
    """Test the document carries what the front end exports: columns and SMILES."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert '"export_columns":' in html
    assert '"smiles":"CCO"' in html


def test_molgrid_html_contains_listjs(simple_mol):
    """Test HTML contains List.js library."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    # List.js should be included
    assert "List" in html


# ============================================================================
# SMARTS Search Tests
# ============================================================================

def test_molgrid_search_smarts_match(sample_molecules):
    """Test _search_smarts finds matching molecules."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    matches = grid._search_smarts("[OH]")

    # Ethanol, Acetaminophen have OH
    assert len(matches) >= 2
    assert 0 in matches  # Ethanol


def test_molgrid_search_smarts_aromatic(sample_molecules):
    """Test _search_smarts for aromatic ring."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    matches = grid._search_smarts("c1ccccc1")

    # Benzene, Acetaminophen, Ibuprofen have aromatic rings
    assert len(matches) >= 3
    assert 2 in matches  # Benzene


def test_molgrid_search_smarts_no_match(simple_mol):
    """Test _search_smarts with pattern that doesn't match."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    matches = grid._search_smarts("[Br]")  # No bromine

    assert matches == []


def test_molgrid_search_smarts_invalid_pattern(simple_mol):
    """Test _search_smarts handles invalid SMARTS gracefully."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    matches = grid._search_smarts("invalid[[[smarts")

    assert matches == []


def test_molgrid_search_smarts_empty_pattern(sample_molecules):
    """Test _search_smarts with empty pattern."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    matches = grid._search_smarts("")

    assert matches == []


def test_molgrid_search_smarts_empty_query_reports_error(sample_molecules):
    """Test search_smarts reports an empty query as an invalid pattern."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    matches, error = grid.search_smarts("")

    assert matches == []
    assert "Invalid SMARTS" in error


def test_molgrid_search_smarts_with_pattern(sample_molecules):
    """Test search_smarts returns matching indices and no error for a valid query."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules)
    matches, error = grid.search_smarts("[OH]")

    assert len(matches) >= 2
    assert error is None


# ============================================================================
# Selection Tests
# ============================================================================

def test_molgrid_selection_indices_sorted(sample_molecules):
    """Test selection indices are reported in ascending order."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, name="selection-test")

    # The front end reports selected indices in click order.
    grid.selection = [2, 0]

    indices = grid.get_selection_indices()
    assert indices == [0, 2]


def test_molgrid_get_selection_molecules(sample_molecules):
    """Test get_selection returns actual molecules."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, name="selection-mol-test")
    grid.selection = [0]

    selected = grid.get_selection()
    assert len(selected) == 1
    assert selected[0].GetTitle() == "Ethanol"


def test_molgrid_get_selection_indices_empty(sample_molecules):
    """Test get_selection_indices with no selection."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, name="empty-selection-test")

    indices = grid.get_selection_indices()
    assert indices == []


def test_molgrid_get_selection_empty(sample_molecules):
    """Test get_selection with no selection."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, name="empty-selection-mols-test")

    selected = grid.get_selection()
    assert selected == []


def test_molgrid_selection_survives_render_option_change(sample_molecules):
    """Test changing render options drops cached images but keeps the selection."""
    from cnotebook import MolGrid

    grid = MolGrid(sample_molecules, name="change-handler-test")
    grid.selection = [1, 3]
    grid.render_item(0)

    grid.set_render_options(width=300)

    assert grid.get_selection_indices() == [1, 3]
    assert grid._images == {}


def test_molgrid_selection_isolated_between_grids(sample_molecules):
    """Test that selections are isolated between grid instances."""
    from cnotebook import MolGrid

    grid1 = MolGrid(sample_molecules, name="grid1-isolated")
    grid2 = MolGrid(sample_molecules, name="grid2-isolated")

    grid1.selection = [0]
    grid2.selection = [1, 2]

    assert grid1.get_selection_indices() == [0]
    assert grid2.get_selection_indices() == [1, 2]


# ============================================================================
# Display Tests
# ============================================================================

def test_molgrid_display_returns_html(simple_mol):
    """display() should return the document in an iframe when no front end can draw."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], name="display-test")
    result = grid.display()

    markup = result._repr_html_()
    assert 'class="molgrid-iframe"' in markup
    assert "srcdoc=" in markup
    assert "Ethanol" in markup


# ============================================================================
# Field Value Extraction Tests
# ============================================================================

def test_molgrid_get_field_value_title(simple_mol):
    """Test _get_field_value extracts Title field."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    value = grid._get_field_value(0, simple_mol, "Title")

    assert value == "Ethanol"


def test_molgrid_get_field_value_sd_data(mol_with_sd_data):
    """Test _get_field_value extracts SD data."""
    from cnotebook import MolGrid

    grid = MolGrid([mol_with_sd_data])
    value = grid._get_field_value(0, mol_with_sd_data, "MW")

    assert value == "46.07"


def test_molgrid_get_field_value_missing(simple_mol):
    """Test _get_field_value returns None for missing field."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    value = grid._get_field_value(0, simple_mol, "NonExistent")

    assert value is None


def test_molgrid_get_field_value_empty_title():
    """Test _get_field_value with molecule without title."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    # No title set

    grid = MolGrid([mol])
    value = grid._get_field_value(0, mol, "Title")

    assert value is None


# ============================================================================
# Rendering Settings Tests
# ============================================================================

def test_molgrid_svg_format(simple_mol):
    """Test MolGrid with SVG image format."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], image_format="svg")
    data = grid._prepare_data()

    assert "<svg" in data[0]["img"].lower() or "data:image/svg" in data[0]["img"]


def test_molgrid_png_format(simple_mol):
    """Test MolGrid with PNG image format."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], image_format="png")
    data = grid._prepare_data()

    assert "data:image/png" in data[0]["img"]


def test_molgrid_custom_dimensions(simple_mol):
    """Test MolGrid with custom width/height."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], width=300, height=250)
    html = grid.to_html()

    assert "300px" in html
    assert "250px" in html


def test_molgrid_atom_label_font_scale(simple_mol):
    """Test MolGrid with custom atom label font scale."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], atom_label_font_scale=2.5)

    assert grid.atom_label_font_scale == 2.5


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================

def test_molgrid_large_molecule_list():
    """Test MolGrid with many molecules."""
    from cnotebook import MolGrid

    mols = []
    for i in range(100):
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, "C" * (i % 10 + 1))
        mol.SetTitle(f"Molecule_{i}")
        mols.append(mol)

    grid = MolGrid(mols, n_items_per_page=10)
    html = grid.to_html()

    assert "molgrid" in html.lower()
    assert len(grid._molecules) == 100


def test_molgrid_single_molecule(simple_mol):
    """Test MolGrid with single molecule."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_molgrid_molecules_with_special_characters():
    """Test MolGrid handles molecules with special characters in title."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle('Ethanol <script>alert("XSS")</script>')

    grid = MolGrid([mol])
    html = grid.to_html()

    # The title travels inside a script element, so the angle brackets have to leave
    # escape_script_json as </> rather than as markup the parser would act on.
    assert "\\u003cscript\\u003e" in html
    assert "<script>alert" not in html


def test_molgrid_unicode_title():
    """Test MolGrid handles unicode in title."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Éthanol café α-酒精")

    grid = MolGrid([mol])
    html = grid.to_html()

    assert "molgrid" in html.lower()


def test_molgrid_very_long_smiles():
    """Test MolGrid handles very long SMILES."""
    from cnotebook import MolGrid

    # Create a long molecule
    mol = oechem.OEGraphMol()
    long_smiles = "C" * 50
    oechem.OESmilesToMol(mol, long_smiles)

    grid = MolGrid([mol])
    data = grid._prepare_data()

    assert len(data[0]["smiles"]) > 0


def test_molgrid_with_none_in_list(simple_mol):
    """Test MolGrid behavior with None values in molecule list."""
    from cnotebook import MolGrid

    # This tests defensive coding - though ideally users shouldn't pass None
    mols = [simple_mol]

    grid = MolGrid(mols)
    assert len(grid._molecules) == 1


def test_molgrid_smarts_exception_handling():
    """Test SMARTS search handles exceptions gracefully."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])

    # Test with a pattern that could cause issues - extremely malformed patterns
    # The SMARTS parser should handle this gracefully
    matches = grid._search_smarts("[invalid")
    assert isinstance(matches, list)


def test_molgrid_get_marimo_selection_outside_marimo(simple_mol):
    """Test get_marimo_selection raises error outside marimo."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])

    with pytest.raises(RuntimeError, match="marimo"):
        grid.get_marimo_selection()


def test_molgrid_is_marimo_check():
    """Test _is_marimo returns False when not in marimo."""
    from cnotebook.grid.grid import _is_marimo

    # When not in marimo, should return False
    result = _is_marimo()
    assert result is False


# ============================================================================
# Information Button Tests
# ============================================================================

def test_molgrid_information_enabled_by_default(simple_mol):
    """Test that information button is enabled by default."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    assert grid.information_enabled is True


def test_molgrid_information_can_be_disabled(simple_mol):
    """Test that information button can be disabled."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], information=False)
    assert grid.information_enabled is False


def test_molgrid_html_contains_info_button_when_enabled(simple_mol):
    """Test HTML contains info button when information=True."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], information=True)
    html = grid.to_html()

    assert '"information":true' in html


def test_molgrid_html_no_info_button_when_disabled(simple_mol):
    """Test HTML does not contain info button when information=False."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], information=False)
    html = grid.to_html()

    assert '"information":false' in html


def test_molgrid_info_tooltip_contains_index(simple_mol):
    """Test every item carries the index the tooltip shows."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], information=True)
    html = grid.to_html()

    assert '"i":0' in html


def test_molgrid_info_tooltip_contains_title_when_set():
    """Test info tooltip contains title when molecule has one."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    mol.SetTitle("Ethanol")

    grid = MolGrid([mol], information=True)
    html = grid.to_html()

    # Should have Title in tooltip
    assert "Title:" in html
    assert "Ethanol" in html


def test_molgrid_info_tooltip_no_title_when_empty():
    """Test info tooltip does not show title row when molecule has no title."""
    from cnotebook import MolGrid

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")
    # Don't set a title

    grid = MolGrid([mol], information=True)
    data = grid._prepare_data()

    # mol_title should be empty string (not None since mol is valid)
    assert data[0]["mol_title"] == ""


def test_molgrid_prepare_data_includes_mol_title(simple_mol):
    """Test _prepare_data includes mol_title field."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    data = grid._prepare_data()

    assert "mol_title" in data[0]
    assert data[0]["mol_title"] == "Ethanol"


def test_molgrid_info_css_present(simple_mol):
    """Test that info button CSS is included in HTML."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert ".cn-molgrid-infobtn" in html
    assert ".cn-molgrid-tooltip" in html


def test_molgrid_info_tooltip_pinned_css(simple_mol):
    """Test that pinned tooltip CSS is included."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol])
    html = grid.to_html()

    assert ".cn-molgrid-pinned" in html


def test_molgrid_data_parameter_string(simple_mol):
    """Test data parameter accepts a single string."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], data="MW")

    assert grid.information_fields == ["MW"]


def test_molgrid_data_parameter_list(simple_mol):
    """Test data parameter accepts a list of strings."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], data=["MW", "Formula"])

    assert grid.information_fields == ["MW", "Formula"]


def test_molgrid_data_parameter_none_without_dataframe(simple_mol):
    """Test data=None with no DataFrame results in empty info fields."""
    from cnotebook import MolGrid

    grid = MolGrid([simple_mol], data=None)

    assert grid.information_fields == []


def test_molgrid_prepare_data_includes_info_fields(mol_with_sd_data):
    """Test _prepare_data includes info_fields."""
    from cnotebook import MolGrid

    grid = MolGrid([mol_with_sd_data], data=["MW"])
    data = grid._prepare_data()

    assert "info_fields" in data[0]
    assert "MW" in data[0]["info_fields"]
    assert data[0]["info_fields"]["MW"] == "46.07"


def test_molgrid_info_tooltip_displays_data_fields(mol_with_sd_data):
    """Test info tooltip displays data fields from the data parameter."""
    from cnotebook import MolGrid

    grid = MolGrid([mol_with_sd_data], data=["MW", "Formula"])
    html = grid.to_html()

    assert '"info_fields":["MW","Formula"]' in html
    assert '"MW":"46.07"' in html
    assert '"Formula":"C2H6O"' in html


# ============================================================================
# Cluster Parameter Tests
# ============================================================================

def test_molgrid_cluster_parameter_string():
    """Test cluster parameter accepts a column name string."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({"mol": [mol], "cluster_id": ["Active"]})
    grid = MolGrid([mol], dataframe=df, mol_col="mol", cluster="cluster_id")

    assert grid.cluster == "cluster_id"
    assert grid.cluster_counts is True  # Default


def test_molgrid_cluster_parameter_dict():
    """Test cluster parameter accepts a dict mapping."""
    from cnotebook import MolGrid
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    cluster_map = {0: "Active", 1: "Inactive"}
    grid = MolGrid([mol], cluster=cluster_map)

    assert grid.cluster == cluster_map


def test_molgrid_cluster_counts_parameter():
    """Test cluster_counts parameter can be set to False."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({"mol": [mol], "cluster_id": ["Active"]})
    grid = MolGrid([mol], dataframe=df, mol_col="mol", cluster="cluster_id", cluster_counts=False)

    assert grid.cluster_counts is False


def test_molgrid_cluster_string_requires_dataframe():
    """Test cluster string parameter requires a DataFrame."""
    from cnotebook import MolGrid
    from openeye import oechem
    import pytest

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    with pytest.raises(ValueError, match="requires a DataFrame"):
        MolGrid([mol], cluster="cluster_id")


def test_molgrid_cluster_string_validates_column():
    """Test cluster string parameter validates column exists."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem
    import pytest

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    df = pd.DataFrame({"mol": [mol], "other_col": ["value"]})

    with pytest.raises(ValueError, match="not found"):
        MolGrid([mol], dataframe=df, mol_col="mol", cluster="nonexistent")


def test_molgrid_cluster_invalid_type():
    """Test cluster parameter rejects invalid types."""
    from cnotebook import MolGrid
    from openeye import oechem
    import pytest

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    with pytest.raises(TypeError, match="must be a string"):
        MolGrid([mol], cluster=123)


# ============================================================================
# Cluster Data Preparation Tests
# ============================================================================

def test_molgrid_prepare_data_includes_cluster():
    """Test _prepare_data includes cluster value for each item."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC", "CCC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_id": ["Active", "Inactive", "Active"]
    })

    grid = MolGrid(mols, dataframe=df, mol_col="mol", cluster="cluster_id")
    data = grid._prepare_data()

    assert data[0]["cluster"] == "Active"
    assert data[1]["cluster"] == "Inactive"
    assert data[2]["cluster"] == "Active"


def test_molgrid_prepare_data_cluster_with_dict():
    """Test _prepare_data uses dict mapping for cluster labels."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_num": [0, 1]
    })

    cluster_map = {0: "Active", 1: "Inactive"}
    grid = MolGrid(mols, dataframe=df, mol_col="mol", cluster=cluster_map)
    data = grid._prepare_data()

    # A mapping is {molecule index: label}, so each item carries its label.
    assert data[0]["cluster"] == "Active"
    assert data[1]["cluster"] == "Inactive"


def test_molgrid_prepare_data_cluster_none_value():
    """Test _prepare_data handles None/NaN cluster values."""
    import pandas as pd
    import numpy as np
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_id": ["Active", np.nan]
    })

    grid = MolGrid(mols, dataframe=df, mol_col="mol", cluster="cluster_id")
    data = grid._prepare_data()

    assert data[0]["cluster"] == "Active"
    assert data[1]["cluster"] == "Uncategorized"


def test_molgrid_no_cluster_field_when_disabled():
    """Test _prepare_data does not include cluster when cluster=None."""
    from cnotebook import MolGrid
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])
    data = grid._prepare_data()

    assert "cluster" not in data[0]


# ============================================================================
# Cluster HTML Output Tests
# ============================================================================

def test_molgrid_html_contains_cluster_data():
    """Test HTML contains cluster metadata when cluster is enabled."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC", "CCC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_id": ["Active", "Inactive", "Active"]
    })

    grid = MolGrid(mols, dataframe=df, mol_col="mol", cluster="cluster_id")
    html = grid.to_html()

    assert '"cluster_labels":["Active","Inactive"]' in html
    assert '"cluster":"Active"' in html
    assert '"cluster":"Inactive"' in html


def test_molgrid_html_cluster_counts():
    """Test HTML contains cluster counts when cluster_counts=True."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC", "CCC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_id": ["Active", "Inactive", "Active"]
    })

    grid = MolGrid(mols, dataframe=df, mol_col="mol", cluster="cluster_id", cluster_counts=True)
    html = grid.to_html()

    # The front end counts the members of each label itself; the document only has to
    # say that the counts are wanted, and carry a label on every item.
    assert '"cluster_counts":true' in html
    assert '"cluster_labels":["Active","Inactive"]' in html


def test_molgrid_html_no_cluster_data_when_disabled():
    """Test HTML does not contain cluster data when cluster=None."""
    from cnotebook import MolGrid
    from openeye import oechem

    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, "CCO")

    grid = MolGrid([mol])
    html = grid.to_html()

    # No labels means no cluster control at all, and nothing to filter items by.
    assert '"cluster_labels":null' in html
    assert '"cluster":null' in html


# ============================================================================
# Cluster Integration Tests
# ============================================================================

def test_molgrid_cluster_full_workflow():
    """Integration test for cluster filtering workflow."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    # Create test molecules with clusters
    mols = []
    smiles_list = ["CCO", "CC", "CCC", "CCCC", "c1ccccc1"]
    for smiles in smiles_list:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster": ["Active", "Inactive", "Active", "Inactive", "Active"],
        "property": ["A", "B", "C", "D", "E"]
    })

    # Create grid with cluster filtering
    grid = MolGrid(
        mols,
        dataframe=df,
        mol_col="mol",
        cluster="cluster",
        cluster_counts=True,
        search_fields=["property"]
    )

    # Verify parameters stored
    assert grid.cluster == "cluster"
    assert grid.cluster_counts is True

    # Verify HTML generation
    html = grid.to_html()

    assert '"cluster_labels":["Active","Inactive"]' in html
    assert '"cluster_counts":true' in html

    # Every molecule carries its own label, so the front end can both fill the
    # control and count the members of each label from the items alone.
    labels = [item["cluster"] for item in grid.items()]
    assert labels == ["Active", "Inactive", "Active", "Inactive", "Active"]

    # The searchable field travels with each item too.
    assert '"search_fields":["property"]' in html
    assert '"property":"A"' in html


def test_molgrid_cluster_dict_mapping():
    """Test cluster with dict value mapping."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC", "CCC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_num": [0, 1, 0]
    })

    cluster_map = {0: "Active", 1: "Inactive"}
    grid = MolGrid(
        mols,
        dataframe=df,
        mol_col="mol",
        cluster=cluster_map
    )

    assert grid.cluster == cluster_map
    html = grid.to_html()
    assert "molgrid-cluster" in html


def test_molgrid_cluster_without_counts():
    """Test cluster with counts disabled."""
    import pandas as pd
    from cnotebook import MolGrid
    from openeye import oechem

    mols = []
    for smiles in ["CCO", "CC"]:
        mol = oechem.OEGraphMol()
        oechem.OESmilesToMol(mol, smiles)
        mols.append(mol)

    df = pd.DataFrame({
        "mol": mols,
        "cluster_id": ["Active", "Inactive"]
    })

    grid = MolGrid(
        mols,
        dataframe=df,
        mol_col="mol",
        cluster="cluster_id",
        cluster_counts=False
    )

    html = grid.to_html()

    assert '"cluster_labels":["Active","Inactive"]' in html
    assert '"cluster_counts":false' in html


# ============================================================================
# Data Model, Render Cache and Cluster Forms
# ============================================================================

def _mol(smiles="CCO", title=None):
    """Build a molecule for the data model tests."""
    mol = oechem.OEGraphMol()
    oechem.OESmilesToMol(mol, smiles)
    if title:
        mol.SetTitle(title)
    return mol


def test_constructor_has_no_display_side_effect(capsys, monkeypatch):
    """Test construction renders nothing, displays nothing and creates no widget."""
    import cnotebook.grid.grid as grid_module
    from cnotebook.grid import MolGrid

    called = []
    monkeypatch.setattr(grid_module, "display", lambda *a, **k: called.append(a), raising=False)
    grid = MolGrid([_mol()])
    assert called == [] and capsys.readouterr().out == ""
    assert grid._widget is None


def test_grid_module_imports_without_pandas():
    """Test the grid module imports and renders static HTML without pandas, anywidget or IPython."""
    import subprocess
    import sys

    code = (
        "import sys, builtins; real = builtins.__import__\n"
        "def guard(name, *a, **k):\n"
        "    if name.split('.')[0] in ('pandas', 'anywidget', 'IPython'):"
        " raise ImportError(name)\n"
        "    return real(name, *a, **k)\n"
        "builtins.__import__ = guard\n"
        "from cnotebook.grid.grid import MolGrid\n"
        "from openeye import oechem\n"
        "m = oechem.OEGraphMol(); oechem.OESmilesToMol(m, 'CCO')\n"
        "print(len(MolGrid([m]).to_html()) > 0)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("True")


def test_none_molecule_renders_placeholder():
    """Test None and empty molecules produce empty SMILES and a placeholder image."""
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), None, oechem.OEGraphMol()])
    items = grid.items()
    assert [it["smiles"] for it in items] == ["CCO", "", ""]
    html = grid.render_item(1)
    assert "Empty Molecule" in html or "<img" in html or "<svg" in html
    assert grid.render_item(2)


def test_invalid_smarts_reports_error():
    """Test search_smarts returns matches plus an error message for invalid patterns."""
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol("c1ccccc1"), _mol()])
    assert grid.search_smarts("c1ccccc1") == ([0], None)
    matches, error = grid.search_smarts("c1cc(")
    assert matches == [] and "SMARTS" in error


def test_search_smarts_does_not_mutate_source_molecules():
    """Test SMARTS searching perceives a copy and leaves the caller's molecule alone."""
    from cnotebook.grid import MolGrid

    benzene = _mol("c1ccccc1")
    # OEPrepareSearch re-perceives aromaticity, so a molecule whose flags were
    # deliberately cleared shows the mutation plainly.
    oechem.OEClearAromaticFlags(benzene)
    atoms_before = [atom.IsAromatic() for atom in benzene.GetAtoms()]
    bonds_before = [bond.IsAromatic() for bond in benzene.GetBonds()]
    bytes_before = oechem.OEWriteMolToBytes("oeb", benzene)
    assert not any(atoms_before) and not any(bonds_before)

    grid = MolGrid([benzene, _mol("CCO")])
    assert grid.search_smarts("c1ccccc1") == ([0], None)

    assert [atom.IsAromatic() for atom in benzene.GetAtoms()] == atoms_before
    assert [bond.IsAromatic() for bond in benzene.GetBonds()] == bonds_before
    assert oechem.OEWriteMolToBytes("oeb", benzene) == bytes_before


def test_cluster_mapping_and_sequence_forms():
    """Test cluster labels from a sequence, an index mapping and a DataFrame column."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    mols = [_mol(), _mol(), _mol()]
    assert MolGrid(mols, cluster=["a", "b", "a"]).cluster_labels() == ["a", "b", "a"]
    assert MolGrid(mols, cluster={0: "x", 2: "y"}).cluster_labels() == ["x", "Uncategorized", "y"]
    df = pd.DataFrame({"c": ["p", None, "q"]})
    assert MolGrid(mols, dataframe=df, cluster="c").cluster_labels() == ["p", "Uncategorized", "q"]
    with pytest.raises(ValueError):
        MolGrid(mols, cluster=["only-two", "labels"])


def test_non_string_column_labels():
    """Test non-string DataFrame column labels become string field names."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    df = pd.DataFrame({0: [1, 2], ("t", 1): ["a", "b"]})
    grid = MolGrid([_mol(), _mol()], dataframe=df)
    assert set(grid.items()[0]["fields"]) == {"0", "('t', 1)"}
    assert grid.to_html()


def test_colliding_column_labels_rejected():
    """Test column labels that become the same field name are rejected, not silently merged."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    frame = pd.DataFrame({0: [1, 2], "0": [3, 4]})
    with pytest.raises(ValueError, match="grid field names"):
        MolGrid([_mol(), _mol()], dataframe=frame)

    # Distinct non-string labels remain acceptable.
    ok = MolGrid([_mol(), _mol()], dataframe=pd.DataFrame({0: [1, 2], 1: [3, 4]}))
    assert set(ok.items()[0]["fields"]) == {"0", "1"}

    # So does a frame mixing string and non-string labels alongside a molecule column.
    mixed = pd.DataFrame({"Name": ["a", "b"], 7: [1, 2], "mol": ["m1", "m2"]})
    grid = MolGrid([_mol(), _mol()], dataframe=mixed, mol_col="mol")
    assert grid._fields == {"Name": "Name", "7": 7}
    assert grid.items()[0]["fields"] == {"Name": "a", "7": "1"}


def test_field_names_never_resolve_to_the_molecule_column():
    """Test a data column keeps its field when the molecule column stringifies the same."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    # Both frame orders: the data column first, then the molecule column first.
    for data_label, mol_label in (("0", 0), (0, "0")):
        frame = pd.DataFrame(
            {data_label: ["data-a", "data-b"], mol_label: ["mol-a", "mol-b"]}
        )
        assert list(frame.columns) == [data_label, mol_label]
        grid = MolGrid(
            [_mol(), _mol()], dataframe=frame, mol_col=mol_label, tooltip_fields=["0"]
        )

        # Resolving "0" against a fresh {str(c): c} view of every column would
        # pick whichever label came last, which is the molecule column in the
        # first order and the data column in the second.
        assert grid._fields == {"0": data_label}
        assert grid.items()[0]["fields"] == {"0": "data-a"}
        assert grid._prepare_data()[0]["tooltip"] == {"0": "data-a"}
        assert grid._prepare_export_data()[0]["0"] == "data-a"
        assert grid._field_value(1, None, "0") == "data-b"
        assert grid.search_fields == ["0"] and grid.information_fields == ["0"]


def test_render_cache_and_revision_on_set_render_options(monkeypatch):
    """Test the render cache serves repeats, evicts by recency and is cleared by option changes."""
    import cnotebook.grid.grid as grid_module
    from cnotebook.grid import MolGrid

    renders = []
    original = MolGrid._create_molecule_display

    def spy(self, mol, ctx=None):
        renders.append(mol)
        return original(self, mol, ctx)

    monkeypatch.setattr(MolGrid, "_create_molecule_display", spy)
    # A small capacity keeps the eviction assertions readable.
    monkeypatch.setattr(grid_module, "_MAX_CACHE", 3)

    grid = MolGrid([_mol(), _mol("c1ccccc1"), _mol("CCC"), _mol("CCCC")])
    first = grid.render_indices([0, 1])
    assert set(first) == {"0", "1"} and grid.revision == 0
    assert len(renders) == 2 and list(grid._images) == [0, 1]

    # A repeat is served from the cache and refreshes that entry's recency.
    assert grid.render_indices([0]) == {"0": first["0"]}
    assert len(renders) == 2 and list(grid._images) == [1, 0]

    grid.render_item(2)
    assert list(grid._images) == [1, 0, 2]

    # Index 1 is now the least recently used, so it is evicted rather than 0.
    grid.render_item(3)
    assert list(grid._images) == [0, 2, 3] and len(renders) == 4

    grid.set_render_options(image_format="png", device_pixel_ratio=1.0)
    assert grid.revision == 1 and len(grid._images) == 0
    assert "data:image/png" in grid.render_item(0)


def test_set_render_options_applies_atomically():
    """Test a rejected render option leaves attributes, cached images and revision untouched."""
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), _mol("c1ccccc1")])
    grid.render_indices([0, 1])
    cached = dict(grid._images)
    before = {name: getattr(grid, name) for name in MolGrid._CONTEXT_ATTRS}

    with pytest.raises(ValueError):
        grid.set_render_options(image_format="png", width=-1)

    assert {name: getattr(grid, name) for name in MolGrid._CONTEXT_ATTRS} == before
    assert dict(grid._images) == cached
    assert grid.revision == 0

    grid.set_render_options(image_format="png")
    assert grid.image_format == "png" and grid.revision == 1 and not grid._images


def test_config_defaults_and_theme_validation(monkeypatch):
    """Test configured defaults apply, explicit arguments win and themes are validated."""
    from cnotebook import config as cn_config
    from cnotebook.grid import MolGrid

    monkeypatch.setattr(cn_config, "_CONFIG", None)
    cn_config.configure(molgrid={"n_items_per_page": 12, "theme": "dark"})
    try:
        grid = MolGrid([_mol()])
        assert grid.n_items_per_page == 12 and grid.theme == "dark" and grid._display_mode == "widget"
        assert MolGrid([_mol()], n_items_per_page=5).n_items_per_page == 5
    finally:
        cn_config.configure(molgrid={"n_items_per_page": 24, "theme": "auto"})
    with pytest.raises(ValueError):
        MolGrid([_mol()], theme="sepia")


def test_display_mode_snapshotted_at_construction_molgrid(monkeypatch):
    """Test the display mode is captured at construction, not at display time."""
    from cnotebook import config as cn_config
    from cnotebook.grid import MolGrid

    monkeypatch.setattr(cn_config, "_CONFIG", None)
    before = MolGrid([_mol()])
    cn_config.configure(display_mode="static")
    try:
        after = MolGrid([_mol()])
        assert before._display_mode == "widget" and after._display_mode == "static"
    finally:
        cn_config.configure(display_mode="widget")


def test_badges_sort_and_fields_in_items():
    """Test items carry badge strings, DataFrame fields and the initial sort."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    df = pd.DataFrame({"MW": [46.07, 78.11], "Name": ["ethanol", "benzene"]})
    grid = MolGrid([_mol(title="e"), _mol("c1ccccc1", title="b")], dataframe=df, badges=["MW"],
                   sort_by=("MW", True))
    items = grid.items()
    assert items[0]["badges"] == ["MW: 46.07"] and items[0]["fields"]["Name"] == "ethanol"
    assert grid.sort_by == ("MW", True)


def test_grid_is_collectable_after_close():
    """Test a closed grid is garbage collected (no global registry keeps it alive)."""
    import gc
    import weakref

    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol()])
    ref = weakref.ref(grid)
    grid.close()
    del grid
    gc.collect()
    assert ref() is None


def test_grid_does_not_mutate_source_molecules():
    """Test rendering leaves the caller's 3D molecule untouched."""
    from openeye import oeomega

    from cnotebook.grid import MolGrid

    mol = oechem.OEMol()
    oechem.OESmilesToMol(mol, "CCO")
    omega = oeomega.OEOmega()
    omega.SetMaxConfs(1)
    assert omega(mol)
    MolGrid([mol]).render_item(0)
    assert mol.GetDimension() == 3


def test_widget_config_shape_and_branches():
    """Test widget_config reports the E1 config shape for both populated and bare grids."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    mols = [_mol("CCO", "Ethanol"), _mol("c1ccccc1", "Benzene")]
    frame = pd.DataFrame({"Name": ["Ethanol", "Benzene"], "MW": [46.07, 78.11], "Group": ["A", None]})
    grid = MolGrid(
        mols,
        dataframe=frame,
        cluster="Group",
        cluster_counts=False,
        badges=["MW"],
        sort_by=("MW", True),
        search_fields=["Name"],
        tooltip_fields=["MW"],
        theme="dark",
        select=False,
        information=False,
        title=None,
        width=300,
        height=200,
        n_items_per_page=12,
    )

    config = grid.widget_config(static=False)

    assert set(config) == {
        "page_size", "sort_by", "badges", "search_fields", "info_fields", "tooltip_fields",
        "export_columns", "cluster_labels", "cluster_counts", "theme", "static", "select",
        "information", "title", "image_width", "image_height",
    }
    assert config["page_size"] == 12
    assert config["sort_by"] == {"field": "MW", "descending": True}
    assert config["badges"] == ["MW"]
    assert config["search_fields"] == ["Name"]
    assert config["info_fields"] == ["Name", "MW", "Group"]
    # The hover surface has its own field list and is not the information list.
    assert config["tooltip_fields"] == ["MW"]
    assert config["export_columns"] == ["Name", "MW", "Group"]
    # Labels are de-duplicated and sorted; the missing value becomes Uncategorized.
    assert config["cluster_labels"] == ["A", "Uncategorized"]
    assert config["cluster_counts"] is False
    assert config["theme"] == "dark"
    assert config["static"] is False
    assert config["select"] is False
    assert config["information"] is False
    assert config["title"] is False
    assert config["image_width"] == 300
    assert config["image_height"] == 200

    bare = MolGrid([_mol()], theme="light")
    bare_config = bare.widget_config(static=True)

    assert set(bare_config) == set(config)
    assert bare_config["sort_by"] is None
    assert bare_config["cluster_labels"] is None
    assert bare_config["cluster_counts"] is True
    assert bare_config["badges"] == []
    assert bare_config["search_fields"] == []
    # No tooltip fields means the front end falls back to the information fields.
    assert bare_config["tooltip_fields"] == []
    assert bare_config["export_columns"] == []
    assert bare_config["theme"] == "light"
    assert bare_config["static"] is True
    assert bare_config["title"] is True


# ============================================================================
# Widget protocol, display modes and the static document
# ============================================================================

def test_widget_protocol_visible_images_selection_and_smarts():
    """Test the widget pre-renders two pages, serves images on demand and answers SMARTS."""
    pytest.importorskip("anywidget")
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), _mol("c1ccccc1"), _mol("CCC")], n_items_per_page=2)
    widget = grid.widget

    # The first page and the one after it are rendered before the front end asks.
    assert set(widget.images) == {"0", "1", "2"}
    assert widget.config["page_size"] == 2 and [it["i"] for it in widget.items] == [0, 1, 2]

    widget.selection = [2, 0]
    assert grid.get_selection_indices() == [0, 2]

    widget.smarts_request = {"seq": 3, "query": "c1ccccc1", "view": "view-a"}
    assert widget.smarts_result == {"seq": 3, "view": "view-a", "matches": [1], "error": None}
    widget.smarts_request = {"seq": 4, "query": "c1cc(", "view": "view-a"}
    assert widget.smarts_result["error"] and widget.smarts_result["matches"] == []

    grid.set_render_options(image_format="png", device_pixel_ratio=1.0)
    assert widget.revision == 1 and widget.images == {}
    widget.visible = [2]
    assert set(widget.images) == {"2"} and "data:image/png" in widget.images["2"]
    grid.set_render_options(image_format="svg")
    assert widget.revision == 2 and set(widget.images) == {"2"} and "<svg" in widget.images["2"]


def test_widget_answers_each_view_with_its_own_token_and_drops_malformed_requests():
    """Test every SMARTS answer echoes the asking view and malformed requests are ignored."""
    pytest.importorskip("anywidget")
    from cnotebook.grid import MolGrid

    widget = MolGrid([_mol("c1ccccc1")]).widget

    for malformed in (
        {"seq": 1, "query": "c1ccccc1"},                 # no view token
        {"seq": 1, "view": "view-a"},                    # no query
        {"seq": True, "query": "C", "view": "view-a"},   # a flag is not a sequence number
        {"seq": "1", "query": "C", "view": "view-a"},
        {"seq": 1, "query": 5, "view": "view-a"},
        {"seq": 1, "query": "C", "view": 5},
    ):
        widget.smarts_request = malformed
        assert widget.smarts_result == {}

    widget.smarts_request = {"seq": 7, "query": "c1ccccc1", "view": "view-a"}
    assert widget.smarts_result == {"seq": 7, "view": "view-a", "matches": [0], "error": None}
    # A second view of the same widget gets its own token back, never the first view's.
    widget.smarts_request = {"seq": 1, "query": "c1ccccc1", "view": "view-b"}
    assert widget.smarts_result == {"seq": 1, "view": "view-b", "matches": [0], "error": None}


def test_revision_push_clears_images_then_republishes_config_and_the_visible_window():
    """Test a render-option change drops stale images, republishes config and re-renders."""
    pytest.importorskip("anywidget")
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), _mol("CCC")], n_items_per_page=1)
    widget = grid.widget
    widget.visible = [1]
    events: list[tuple[str, object]] = []
    widget.observe(
        lambda change: events.append((change["name"], change["new"])),
        names=["images", "revision", "config"],
    )

    grid.set_render_options(width=310, image_format="png")

    # The empty dict goes first so the front end drops the images of the previous
    # revision; the window it last asked for is then rendered again on this side,
    # because the widget model suppresses a republished but unchanged ``visible``.
    assert [name for name, _ in events] == ["images", "revision", "config", "images"]
    assert events[0][1] == {}
    assert events[1][1] == 1
    assert events[2][1]["image_width"] == 310
    assert set(events[3][1]) == {"1"} and "data:image/png" in events[3][1]["1"]


def test_images_arrive_as_a_new_dict_that_keeps_the_earlier_renders():
    """Test on-demand images are merged into a new dict instead of mutated in place."""
    pytest.importorskip("anywidget")
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), _mol("CCC"), _mol("CCCC")], n_items_per_page=1)
    widget = grid.widget
    first = widget.images
    assert set(first) == {"0", "1"}

    widget.visible = [1, 2]

    # traitlets only notifies on a new container, and the previous one is left alone.
    assert set(widget.images) == {"0", "1", "2"}
    assert widget.images is not first and set(first) == {"0", "1"}


def test_a_widget_keeps_its_grid_alive():
    """Test a grid nothing else refers to still renders and searches for its widget."""
    pytest.importorskip("anywidget")
    import gc

    from cnotebook.grid import MolGrid

    # display(df.chem.molgrid()) never names the grid: the widget is all that is left,
    # and every image, search and selection is still answered on the Python side.
    widget = MolGrid([_mol(), _mol("c1ccccc1")], n_items_per_page=1).widget
    gc.collect()

    widget.visible = [1]
    assert set(widget.images) == {"0", "1"}
    widget.smarts_request = {"seq": 1, "query": "c1ccccc1", "view": "view-a"}
    assert widget.smarts_result["matches"] == [1]
    widget.selection = [1]
    assert widget.selection == [1]


def test_closing_a_grid_releases_it_and_its_widget():
    """Test close() lets a displayed grid and its widget be collected."""
    pytest.importorskip("anywidget")
    import gc
    import weakref

    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol()])
    widget_ref = weakref.ref(grid.widget)
    grid_ref = weakref.ref(grid)

    grid.close()
    del grid
    gc.collect()

    assert grid_ref() is None and widget_ref() is None


def test_initial_state_carries_only_two_pages_of_images():
    """Test widget creation renders the first two pages and indexes every molecule."""
    pytest.importorskip("anywidget")
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol() for _ in range(200)], n_items_per_page=24)
    assert len(grid.widget.images) == 48
    assert len(grid.widget.items) == 200


def test_display_modes_and_static_fallback(monkeypatch):
    """Test widget mode returns the widget and falls back to static without anywidget."""
    pytest.importorskip("anywidget")
    import sys

    from cnotebook.core.errors import CNotebookWarning
    from cnotebook.grid import MolGrid
    from cnotebook.grid.widget import MolGridWidget

    grid = MolGrid([_mol()])
    assert isinstance(grid.display(static=False), MolGridWidget)
    static = grid.display(static=True)
    assert "cn-molgrid" in static._repr_html_()
    assert "__CNOTEBOOK_MOLGRID_STATIC__" in static._repr_html_()

    other = MolGrid([_mol()])
    monkeypatch.setitem(sys.modules, "anywidget", None)
    monkeypatch.setitem(sys.modules, "cnotebook.grid.widget", None)
    with pytest.warns(CNotebookWarning, match="anywidget"):
        assert hasattr(other.display(static=False), "_repr_html_")


def test_display_static_creates_no_widget(monkeypatch):
    """Test the static path never imports anywidget and never builds a widget."""
    import sys
    import warnings

    from cnotebook.grid import MolGrid

    monkeypatch.setitem(sys.modules, "anywidget", None)
    monkeypatch.setitem(sys.modules, "cnotebook.grid.widget", None)
    grid = MolGrid([_mol()])

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        out = grid.display(static=True)

    assert hasattr(out, "_repr_html_") and grid._widget is None


def test_display_without_a_front_end_returns_the_static_output():
    """Test display() falls back to the document when no kernel front end can draw a widget."""
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol()])
    out = grid.display()

    assert hasattr(out, "_repr_html_") and grid._widget is None


def test_display_is_wrapped_for_marimo():
    """Test marimo gets mo.Html for the document and mo.ui.anywidget for the widget."""
    pytest.importorskip("anywidget")
    from unittest.mock import MagicMock, patch

    from cnotebook.grid import MolGrid

    mock_mo = MagicMock()
    grid = MolGrid([_mol()])

    with patch("cnotebook.grid.grid._is_marimo", return_value=True), \
         patch.dict("sys.modules", {"marimo": mock_mo}):
        static = grid.display(static=True)
        live = grid.display(static=False)

    mock_mo.Html.assert_called_once()
    assert static is mock_mo.Html.return_value
    mock_mo.ui.anywidget.assert_called_once_with(grid.widget)
    assert live is mock_mo.ui.anywidget.return_value


def test_static_html_escapes_script_and_attribute_payloads():
    """Test hostile titles and field values cannot break out of the embedded payload."""
    import pandas as pd

    from cnotebook.grid import MolGrid

    mol = _mol(title='</script><img src=x onerror=alert(1)>')
    oechem.OESetSDData(mol, "MW", '46" onmouseover="alert(1)')
    df = pd.DataFrame({"note": ["</script><img src=x onerror=alert(2)>"]})
    grid = MolGrid([mol], dataframe=df, tooltip_fields=["MW"], badges=["MW"])
    html_doc = grid.to_html()

    assert "</script><img" not in html_doc
    assert 'onmouseover="alert(1)"' not in html_doc
    assert "\\u003c/script\\u003e" in html_doc
    assert "\\u003cimg src=x onerror=alert(2)\\u003e" in html_doc
    # The only script elements in the document are the two it writes itself.
    assert html_doc.count("</script>") == 2


def test_static_display_never_interpolates_the_grid_name():
    """Test the grid name never reaches the static output, hostile or not."""
    from cnotebook.grid import MolGrid

    hostile = 'x" onload="alert(1)'
    html_out = MolGrid([_mol()], name=hostile).display(static=True)._repr_html_()

    assert 'onload="alert(1)"' not in html_out and hostile not in html_out


def test_to_html_warns_above_static_max_items():
    """Test the static export warns when it embeds more molecules than the threshold."""
    from cnotebook.core.errors import CNotebookWarning
    from cnotebook.grid import MolGrid

    grid = MolGrid([_mol(), _mol()], static_max_items=1)
    with pytest.warns(CNotebookWarning, match="static_max_items"):
        grid.to_html()


def test_to_html_embeds_the_front_end_module_the_stylesheet_and_every_image():
    """Test the static document is self-contained and boots the front end in static mode."""
    from cnotebook.grid import MolGrid

    html_doc = MolGrid([_mol()], theme="dark").to_html()

    assert html_doc.startswith("<!DOCTYPE html>") and html_doc.rstrip().endswith("</html>")
    assert '<div id="molgrid-root"></div>' in html_doc
    assert "window.__CNOTEBOOK_MOLGRID_STATIC__ = {" in html_doc
    assert ".cn-molgrid" in html_doc            # molgrid.css
    assert "export default" in html_doc         # molgrid.js, loaded as an ES module
    assert '"static":true' in html_doc and '"theme":"dark"' in html_doc
    # A saved document has no kernel to ask, so every image travels with it.
    assert '"images":{"0":' in html_doc


def test_selection_frame_pandas_and_polars_and_error():
    """Test selection_frame returns the selected rows of either frame kind."""
    pytest.importorskip("anywidget")
    import pandas as pd
    import polars as pl

    from cnotebook.core.errors import CNotebookError
    from cnotebook.grid import MolGrid

    df = pd.DataFrame({"x": [1, 2, 3]})
    grid = MolGrid([_mol(), _mol(), _mol()], dataframe=df)
    grid.widget.selection = [2, 0]
    assert list(grid.selection_frame()["x"]) == [1, 3]
    assert [m is grid._molecules[i] for i, m in zip([0, 2], grid.get_selection())] == [True, True]

    pgrid = MolGrid([_mol(), _mol()], dataframe=pl.DataFrame({"x": [7, 8]}))
    pgrid.widget.selection = [1]
    assert pgrid.selection_frame()["x"].to_list() == [8]

    with pytest.raises(CNotebookError):
        MolGrid([_mol()]).selection_frame()


def test_save_writes_static_document(tmp_path):
    """Test save writes the static document and returns its path."""
    from cnotebook.grid import MolGrid

    out = MolGrid([_mol()]).save(tmp_path / "grid.html")

    assert out.read_text().startswith("<!DOCTYPE html>")


def test_save_is_durable_and_checks_the_destination(tmp_path, monkeypatch):
    """Test an interrupted save keeps the previous document and leaves nothing behind."""
    import os
    import stat

    from cnotebook.core.errors import CNotebookError
    from cnotebook.grid import MolGrid

    target = tmp_path / "grid.html"
    grid = MolGrid([_mol()])
    grid.save(target)
    previous = target.read_text()

    def failing_replace(src, dst):
        raise OSError("interrupted")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(OSError, match="interrupted"):
        grid.save(target)
    monkeypatch.undo()

    assert target.read_text() == previous
    assert [p.name for p in tmp_path.iterdir()] == ["grid.html"]

    # The document is an ordinary output file, not a 0600 temporary one.
    plain = tmp_path / "plain.html"
    plain.write_text("x")
    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(plain.stat().st_mode)

    with pytest.raises(CNotebookError, match="does not exist"):
        MolGrid([_mol()]).save(tmp_path / "missing" / "grid.html")


def test_search_smarts_skips_query_molecules():
    """Test a query molecule in the grid is skipped instead of aborting the interpreter."""
    from cnotebook.grid import MolGrid

    qmol = oechem.OEQMol()
    oechem.OEParseSmarts(qmol, "c1ccccc1")
    grid = MolGrid([_mol("c1ccccc1"), qmol])

    # OESubSearch::SingleMatch is a Fatal stub for query molecules: handing it one kills
    # the process, so this test also fails by never returning.
    matches, error = grid.search_smarts("c1ccccc1")

    assert matches == [0] and error is None


def test_static_path_runs_with_anywidget_blocked():
    """Test the grid module, the item index, the document and save need no anywidget."""
    import subprocess
    import sys

    code = (
        "import pathlib, sys, tempfile\n"
        "class Block:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'anywidget' or name.startswith('anywidget.'):\n"
        "            raise ImportError('anywidget is blocked')\n"
        "        return None\n"
        "sys.meta_path.insert(0, Block())\n"
        "import cnotebook.grid\n"
        "from openeye import oechem\n"
        "m = oechem.OEGraphMol(); oechem.OESmilesToMol(m, 'CCO')\n"
        "grid = cnotebook.grid.MolGrid([m])\n"
        "assert grid.items()[0]['smiles'] == 'CCO'\n"
        "assert grid.to_html().startswith('<!DOCTYPE html>')\n"
        "with tempfile.TemporaryDirectory() as directory:\n"
        "    out = grid.save(pathlib.Path(directory) / 'grid.html')\n"
        "    assert out.read_text().startswith('<!DOCTYPE html>')\n"
        "assert 'anywidget' not in sys.modules\n"
        "print('OK')\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=False)

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip().endswith("OK")
