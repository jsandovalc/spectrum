"""Undo snapshot: save/restore branch state for destructive commands."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass

from spectrum import git


CONFIG_KEYS = ["spectrum-stack", "spectrum-index", "gh-merge-base", "spectrum-pr", "spectrum-wip", "spectrum-title"]


@dataclass
class UndoSnapshot:
    command: str
    original_branch: str
    branches: dict[str, dict]  # branch_name -> {"sha": ..., "config": {...}}

    def save(self) -> None:
        """Save snapshot to .git/spectrum-undo.json."""
        path = _undo_path()
        with open(path, "w") as f:
            json.dump(asdict(self), f)

    @staticmethod
    def load() -> UndoSnapshot | None:
        path = _undo_path()
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = json.load(f)
        return UndoSnapshot(**data)

    @staticmethod
    def clear() -> None:
        path = _undo_path()
        if os.path.exists(path):
            os.remove(path)


def _undo_path() -> str:
    return os.path.join(git.git_dir(), "spectrum-undo.json")


def save_snapshot(command: str, stack_entries: list) -> None:
    """Capture current state of all branches in the stack."""
    original_branch = git.current_branch()
    branches: dict[str, dict] = {}
    for entry in stack_entries:
        config: dict[str, str] = {
            "spectrum-stack": entry.stack_id,
            "spectrum-index": str(entry.index),
            "gh-merge-base": entry.merge_base,
        }
        if entry.pr_number is not None:
            config["spectrum-pr"] = str(entry.pr_number)
        if entry.wip:
            config["spectrum-wip"] = "true"
        title = git.get_branch_config(entry.branch, "spectrum-title")
        if title is not None:
            config["spectrum-title"] = title
        branches[entry.branch] = {
            "sha": git.rev_parse(entry.branch),
            "config": config,
        }
    snapshot = UndoSnapshot(
        command=command,
        original_branch=original_branch,
        branches=branches,
    )
    snapshot.save()


def restore_snapshot(snapshot: UndoSnapshot) -> None:
    """Restore all branches to saved state."""
    for branch_name, state in snapshot.branches.items():
        sha = state["sha"]
        config = state["config"]
        if git.branch_exists(branch_name):
            git.force_branch(branch_name, sha)
        else:
            git.create_branch_at(branch_name, sha)
        for key in CONFIG_KEYS:
            if key in config:
                git.set_branch_config(branch_name, key, config[key])
            else:
                git.unset_branch_config(branch_name, key)
    git.checkout(snapshot.original_branch)
