"""Operation state persistence for continue/abort after rebase conflicts."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from spectrum import git


@dataclass
class OperationState:
    """State of an interrupted rebase operation."""

    command: str
    remaining_branches: list[str]
    remaining_merge_bases: list[str]
    remaining_stack_ids: list[str]
    remaining_indices: list[int]
    original_branch: str
    stack_id: str
    resolve_onto_master: bool = False

    def save(self) -> None:
        """Save operation state to .git/spectrum-state.json."""
        state_path = _state_path()
        with open(state_path, "w") as f:
            json.dump(asdict(self), f)

    @staticmethod
    def load() -> OperationState | None:
        """Load operation state, or None if no saved state."""
        state_path = _state_path()
        if not os.path.exists(state_path):
            return None
        with open(state_path) as f:
            data = json.load(f)
        return OperationState(**data)

    @staticmethod
    def clear() -> None:
        """Remove saved operation state."""
        state_path = _state_path()
        if os.path.exists(state_path):
            os.remove(state_path)


def _state_path() -> str:
    """Return the path to the state file."""
    return os.path.join(git.git_dir(), "spectrum-state.json")
