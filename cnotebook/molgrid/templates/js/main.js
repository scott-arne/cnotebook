(function() {
    var gridId = '{{ grid_id }}';
    var itemsPerPage = {{ n_items_per_page }};
    var searchFields = {{ search_fields | tojson }};
    var container = document.getElementById(gridId);

    // Initialize List.js
    var options = {
        valueNames: ['title', 'index', 'smiles'].concat(searchFields),
        page: itemsPerPage,
        pagination: {
            innerWindow: 1,
            outerWindow: 1,
            left: 1,
            right: 1,
            paginationClass: 'pagination'
        }
    };

    var molgridList = new List(gridId, options);

    // State management
    var molgridState = {
        gridId: gridId,
        list: molgridList,
        selectedIndices: new Set(),
        searchMode: 'properties',  // 'properties' or 'smarts'

        getSelectedIndices: function() {
            return Array.from(this.selectedIndices);
        },

        setSelectedIndices: function(indices) {
            this.selectedIndices = new Set(indices);
            updateCheckboxes();
        },

        clearSelection: function() {
            this.selectedIndices.clear();
            updateCheckboxes();
        }
    };

    // Update showing info
    function updateShowingInfo() {
        var visibleItems = molgridList.visibleItems.length;
        var totalItems = molgridList.matchingItems.length;
        var currentPage = molgridList.i;
        var perPage = molgridList.page;

        var start = totalItems > 0 ? currentPage : 0;
        var end = Math.min(currentPage + perPage - 1, totalItems);

        var showingStart = container.querySelector('.showing-start');
        var showingEnd = container.querySelector('.showing-end');
        var showingTotal = container.querySelector('.showing-total');

        if (showingStart) showingStart.textContent = start;
        if (showingEnd) showingEnd.textContent = end;
        if (showingTotal) showingTotal.textContent = totalItems;
    }

    // Update checkboxes based on state
    function updateCheckboxes() {
        var checkboxes = container.querySelectorAll('.molgrid-checkbox');
        checkboxes.forEach(function(checkbox) {
            var index = parseInt(checkbox.getAttribute('data-index'), 10);
            checkbox.checked = molgridState.selectedIndices.has(index);
            var cell = checkbox.closest('.molgrid-cell');
            if (cell) {
                cell.classList.toggle('selected', checkbox.checked);
            }
        });
    }

    // Sort dropdown handler
    var sortSelect = container.querySelector('.sort-select');
    if (sortSelect) {
        sortSelect.addEventListener('change', function() {
            var sortField = this.value;
            if (sortField) {
                molgridList.sort(sortField, { order: 'asc' });
            }
        });
    }

    // Search mode toggle
    var searchModeToggle = container.querySelector('.search-mode-toggle');
    if (searchModeToggle) {
        searchModeToggle.addEventListener('change', function() {
            molgridState.searchMode = this.checked ? 'smarts' : 'properties';
            // Re-trigger search with current query
            var searchInput = container.querySelector('.molgrid-search-input');
            if (searchInput && searchInput.value) {
                performSearch(searchInput.value);
            }
        });
    }

    // Debounce function
    function debounce(func, wait) {
        var timeout;
        return function() {
            var context = this;
            var args = arguments;
            clearTimeout(timeout);
            timeout = setTimeout(function() {
                func.apply(context, args);
            }, wait);
        };
    }

    // Perform search
    function performSearch(query) {
        if (molgridState.searchMode === 'smarts') {
            // SMARTS search - filter by smiles field
            // For full SMARTS matching, backend processing would be needed
            // This is a placeholder for client-side substring matching on SMILES
            molgridList.search(query, ['smiles']);
        } else {
            // Properties search - search all configured fields
            var fieldsToSearch = ['title'].concat(searchFields);
            molgridList.search(query, fieldsToSearch);
        }
        updateShowingInfo();
    }

    // Debounced search handler
    var searchInput = container.querySelector('.molgrid-search-input');
    if (searchInput) {
        var debouncedSearch = debounce(function(e) {
            performSearch(e.target.value);
        }, 300);

        searchInput.addEventListener('input', debouncedSearch);
    }

    // Selection checkbox handling
    container.addEventListener('change', function(e) {
        if (e.target.classList.contains('molgrid-checkbox')) {
            var index = parseInt(e.target.getAttribute('data-index'), 10);
            if (e.target.checked) {
                molgridState.selectedIndices.add(index);
            } else {
                molgridState.selectedIndices.delete(index);
            }
            var cell = e.target.closest('.molgrid-cell');
            if (cell) {
                cell.classList.toggle('selected', e.target.checked);
            }
        }
    });

    // Listen for list updates
    molgridList.on('updated', function() {
        updateShowingInfo();
        updateCheckboxes();
    });

    // Initial update
    updateShowingInfo();

    // Expose state for widget communication
    window.molgridState = window.molgridState || {};
    window.molgridState[gridId] = molgridState;
})();
