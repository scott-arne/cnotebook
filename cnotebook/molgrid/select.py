"""Selection state management for MolGrid instances."""

import ast
from typing import Dict, List, Optional


class SelectionRegister:
    """Singleton registry for tracking grid selections.

    Maintains selection state for multiple grid instances.
    """

    SELECTIONS: Dict[str, Dict[int, str]] = {}
    _current_grid: Optional[str] = None

    @classmethod
    def _init_grid(cls, grid_id: str):
        """Initialize selection tracking for a grid.

        :param grid_id: Unique grid identifier.
        """
        if grid_id not in cls.SELECTIONS:
            cls.SELECTIONS[grid_id] = {}
        cls._current_grid = grid_id

    @classmethod
    def selection_updated(cls, grid_id: str, change: dict):
        """Handle selection change from widget.

        :param grid_id: Grid identifier.
        :param change: Traitlet change dict with 'new' key.
        """
        cls._init_grid(grid_id)
        try:
            selection = ast.literal_eval(change["new"])
            cls.SELECTIONS[grid_id] = {int(k): v for k, v in selection.items()}
        except (ValueError, SyntaxError):
            pass

    @classmethod
    def get_selection(cls, grid_id: Optional[str] = None) -> Dict[int, str]:
        """Get selection for a grid.

        :param grid_id: Grid identifier (uses current if None).
        :returns: Dict mapping index to SMILES.
        """
        gid = grid_id or cls._current_grid
        if gid is None:
            return {}
        return cls.SELECTIONS.get(gid, {})

    @classmethod
    def list_grids(cls) -> List[str]:
        """List all registered grid IDs.

        :returns: List of grid identifiers.
        """
        return list(cls.SELECTIONS.keys())


register = SelectionRegister()
