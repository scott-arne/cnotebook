"""AnyWidget-based widget for MolGrid communication."""

import anywidget
import traitlets


class MolGridWidget(anywidget.AnyWidget):
    """Widget for bidirectional communication between Python and JavaScript.

    :param grid_id: Unique identifier for this grid.
    """

    # Widget identity
    grid_id = traitlets.Unicode("").tag(sync=True)

    # Selection state - JSON dict {index: smiles}
    selection = traitlets.Unicode("{}").tag(sync=True)

    # Search state
    search_query = traitlets.Unicode("").tag(sync=True)
    search_mode = traitlets.Unicode("properties").tag(sync=True)
    search_results = traitlets.Unicode("{}").tag(sync=True)

    # Filtering
    filter_mask = traitlets.List([]).tag(sync=True)

    # Loading indicator
    is_searching = traitlets.Bool(False).tag(sync=True)

    # ESM module for JavaScript side (minimal - just model sync)
    _esm = """
    export function render({ model, el }) {
        window.molgridWidget = window.molgridWidget || {};
        window.molgridWidget[model.get('grid_id')] = { model: model };

        // Listen for search results from Python
        model.on('change:search_results', () => {
            const results = JSON.parse(model.get('search_results'));
            const gridId = model.get('grid_id');
            if (window.molgridState && window.molgridState[gridId] && results.matches) {
                // Update images with highlighted versions
                Object.entries(results.matches).forEach(([idx, data]) => {
                    const cell = document.querySelector(`#${gridId} .molgrid-cell[data-index="${idx}"] .molgrid-image`);
                    if (cell && data.img) {
                        cell.innerHTML = data.img;
                    }
                });
                // Filter to show only matches
                if (window.molgridState[gridId].list) {
                    window.molgridState[gridId].list.filter(item => {
                        return results.matches.hasOwnProperty(item.values().index);
                    });
                }
            }
        });

        // Listen for filter mask changes
        model.on('change:filter_mask', () => {
            const mask = model.get('filter_mask');
            const gridId = model.get('grid_id');
            if (window.molgridState && window.molgridState[gridId] && window.molgridState[gridId].list && mask.length > 0) {
                window.molgridState[gridId].list.filter(item => {
                    const idx = parseInt(item.values().index);
                    return mask[idx] === true;
                });
            }
        });
    }
    """

    _css = ""
