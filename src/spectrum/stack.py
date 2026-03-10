"""Stack state: read/write git config, reconstruct stack, compute next letter."""

from __future__ import annotations

import re
from dataclasses import dataclass

from spectrum import git


@dataclass
class StackEntry:
    branch: str
    index: int
    stack_id: str
    merge_base: str
    pr_number: int | None = None
    wip: bool = False

    @property
    def letter(self) -> str:
        return index_to_letter(self.index)


def index_to_letter(index: int) -> str:
    """Convert 0-based index to letter: 0->a, 1->b, ..., 25->z."""
    if index < 0 or index > 25:
        raise ValueError(f"Stack index {index} out of range (max 26 parts)")
    return chr(ord("a") + index)


def letter_to_index(letter: str) -> int:
    if len(letter) != 1 or not letter.isalpha():
        raise ValueError(f"Invalid stack letter: {letter}")
    return ord(letter.lower()) - ord("a")


def extract_stack_id(branch_name: str) -> str | None:
    """Extract the ticket ID from a branch name.

    e.g. 'user/msg-3391-description/a' -> 'msg-3391'
    e.g. 'user/stay-1234-foo-bar/b' -> 'stay-1234'
    """
    match = re.search(r"/([a-zA-Z]+-\d+)", branch_name)
    if match:
        return match.group(1).lower()
    return None


def extract_base_branch(branch_name: str) -> str | None:
    """Extract the base branch name (without the letter suffix).

    e.g. 'user/msg-3391-description/a' -> 'user/msg-3391-description'
    """
    if "/" not in branch_name:
        return None
    parts = branch_name.rsplit("/", 1)
    if len(parts) == 2 and len(parts[1]) == 1 and parts[1].isalpha():
        return parts[0]
    return None


def extract_letter(branch_name: str) -> str | None:
    """Extract the letter suffix from a branch name.

    e.g. 'user/msg-3391-description/a' -> 'a'
    """
    if "/" not in branch_name:
        return None
    suffix = branch_name.rsplit("/", 1)[1]
    if len(suffix) == 1 and suffix.isalpha():
        return suffix
    return None


def read_entry(branch: str) -> StackEntry | None:
    """Read stack config for a branch. Returns None if not a spectrum branch."""
    stack_id = git.get_branch_config(branch, "spectrum-stack")
    if stack_id is None:
        return None
    index_str = git.get_branch_config(branch, "spectrum-index")
    if index_str is None:
        return None
    merge_base = git.get_branch_config(branch, "gh-merge-base") or "master"
    pr_str = git.get_branch_config(branch, "spectrum-pr")
    wip_str = git.get_branch_config(branch, "spectrum-wip")
    return StackEntry(
        branch=branch,
        index=int(index_str),
        stack_id=stack_id,
        merge_base=merge_base,
        pr_number=int(pr_str) if pr_str else None,
        wip=wip_str == "true",
    )


def write_entry(entry: StackEntry) -> None:
    """Write stack config for a branch."""
    git.set_branch_config(entry.branch, "spectrum-stack", entry.stack_id)
    git.set_branch_config(entry.branch, "spectrum-index", str(entry.index))
    git.set_branch_config(entry.branch, "gh-merge-base", entry.merge_base)
    if entry.pr_number is not None:
        git.set_branch_config(entry.branch, "spectrum-pr", str(entry.pr_number))
    if entry.wip:
        git.set_branch_config(entry.branch, "spectrum-wip", "true")
    else:
        git.unset_branch_config(entry.branch, "spectrum-wip")


def remove_entry(branch: str) -> None:
    """Remove all spectrum config for a branch."""
    git.unset_branch_config(branch, "spectrum-stack")
    git.unset_branch_config(branch, "spectrum-index")
    git.unset_branch_config(branch, "spectrum-pr")
    git.unset_branch_config(branch, "spectrum-wip")


def get_stack(stack_id: str) -> list[StackEntry]:
    """Reconstruct full stack by finding all branches with matching stack_id."""
    entries: list[StackEntry] = []
    for branch in git.all_local_branches():
        entry = read_entry(branch)
        if entry and entry.stack_id == stack_id:
            entries.append(entry)
    entries.sort(key=lambda e: e.index)
    return entries


def current_entry() -> StackEntry | None:
    """Get the stack entry for the current branch."""
    branch = git.current_branch()
    return read_entry(branch)


def current_stack() -> list[StackEntry]:
    """Get the full stack for the current branch."""
    entry = current_entry()
    if entry is None:
        return []
    return get_stack(entry.stack_id)


def next_letter(stack: list[StackEntry]) -> str:
    """Compute the next letter for a stack."""
    if not stack:
        return "a"
    max_index = max(e.index for e in stack)
    return index_to_letter(max_index + 1)


def reindex_stack(stack_id: str) -> None:
    """Re-index all entries in a stack so indices are contiguous from 0."""
    entries = get_stack(stack_id)
    for new_index, entry in enumerate(entries):
        if entry.index != new_index:
            entry.index = new_index
            git.set_branch_config(entry.branch, "spectrum-index", str(new_index))


def swap_entries(stack_id: str, index_i: int, index_j: int) -> list[StackEntry]:
    """Swap two entries by index. Updates indices and merge_bases. Returns full stack."""
    if index_i == index_j:
        raise ValueError("Indices must be different")
    entries = get_stack(stack_id)
    # Normalize so i < j
    if index_i > index_j:
        index_i, index_j = index_j, index_i

    entry_i = next((e for e in entries if e.index == index_i), None)
    entry_j = next((e for e in entries if e.index == index_j), None)
    if entry_i is None or entry_j is None:
        raise ValueError("Index not found in stack")

    # Capture root base before swapping
    root_base = entries[0].merge_base

    # Swap indices
    entry_i.index, entry_j.index = entry_j.index, entry_i.index

    # Re-sort by index
    entries.sort(key=lambda e: e.index)

    # Rebuild merge_bases for affected range
    changed = {entry_i.branch, entry_j.branch}
    for idx in range(index_i, min(index_j + 2, len(entries))):
        if idx == 0:
            entries[idx].merge_base = root_base
        else:
            entries[idx].merge_base = entries[idx - 1].branch
        changed.add(entries[idx].branch)

    # Persist only modified entries
    for entry in entries:
        if entry.branch in changed:
            write_entry(entry)

    return entries


def format_pr_title(stack_id: str, letter: str, message: str | None = None) -> str:
    """Format a PR title from the stack ID and letter.

    e.g. 'MSG-3391 [a]: Preserve aggregator response kind'
    """
    ticket = stack_id.upper()
    title = f"{ticket} [{letter}]"
    if message:
        title += f": {message}"
    return title
