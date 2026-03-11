"""Git operations: run commands, read/write branch config, detect current branch."""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Callable


class GitError(Exception):
    pass


class RebaseConflictError(GitError):
    def __init__(self, branch: str, onto: str, files: list[str] | None = None) -> None:
        self.branch = branch
        self.onto = onto
        self.files = files or []
        super().__init__(f"Conflict rebasing {branch} onto {onto}")


def _run(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = None
    if env:
        run_env = {**os.environ, **env}
    try:
        return subprocess.run(
            ["git", *args],
            check=check,
            capture_output=capture,
            text=True,
            env=run_env,
        )
    except subprocess.CalledProcessError as e:
        raise GitError(f"git {' '.join(args)} failed: {e.stderr.strip()}") from e


def _rebase_in_progress() -> bool:
    """Check if a rebase is in progress by looking for rebase state directories."""
    result = _run(["rev-parse", "--git-dir"], check=False)
    if result.returncode != 0:
        return False
    git_dir_path = result.stdout.strip()
    return os.path.isdir(os.path.join(git_dir_path, "rebase-merge")) or os.path.isdir(
        os.path.join(git_dir_path, "rebase-apply")
    )


def current_branch() -> str:
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"])
    branch = result.stdout.strip()
    if branch == "HEAD":
        if _rebase_in_progress():
            raise GitError(
                "Not on a branch (detached HEAD). "
                "A rebase is in progress — resolve conflicts then run: sp continue\n"
                "Or abort with: sp abort"
            )
        raise GitError(
            "Not on a branch (detached HEAD). "
            "Check out a spectrum branch with: sp switch"
        )
    return branch


def branch_exists(branch: str) -> bool:
    result = _run(["rev-parse", "--verify", f"refs/heads/{branch}"], check=False)
    return result.returncode == 0


def remote_branch_exists(branch: str, remote: str = "origin") -> bool:
    result = _run(["ls-remote", "--heads", remote, branch])
    return bool(result.stdout.strip())


def fetch(remote: str = "origin", ref: str = "master") -> None:
    _run(["fetch", remote, ref])


def create_branch(name: str, start_point: str) -> None:
    _run(["checkout", "-b", name, start_point])


def checkout(branch: str) -> None:
    _run(["checkout", branch])


def push_force_with_lease(
    branches: list[str],
    remote: str = "origin",
    on_retry: Callable[[str], None] | None = None,
) -> None:
    for branch in branches:
        try:
            _run(["push", "--force-with-lease", remote, branch])
        except GitError as e:
            if "rejected" in str(e) or "stale info" in str(e):
                if on_retry:
                    on_retry(branch)
                _run(["fetch", remote, branch])
                _run(["push", "--force-with-lease", remote, branch])
            else:
                raise


def conflict_files() -> list[str]:
    """Return filenames with UU or AA status (unmerged paths)."""
    status = _run(["status", "--porcelain"], check=False)
    files = []
    for line in (status.stdout or "").splitlines():
        if line[:2] in ("UU", "AA"):
            files.append(line[3:])
    return files


def rebase_onto(branch: str, onto: str, old_base: str) -> None:
    """Rebase branch onto a new base, transplanting commits from old_base.

    Equivalent to: git rebase --onto <onto> <old_base> <branch>
    """
    result = _run(
        ["rebase", "--onto", onto, old_base, branch],
        check=False,
    )
    if result.returncode != 0:
        # Check if it's a conflict
        files = conflict_files()
        if files:
            raise RebaseConflictError(branch, onto, files)
        raise GitError(f"Rebase failed: {result.stderr.strip()}")


def rebase_simple(onto: str) -> None:
    """Rebase current branch onto another branch."""
    result = _run(["rebase", onto], check=False)
    if result.returncode != 0:
        branch = current_branch()
        _run(["rebase", "--abort"], check=False)
        raise RebaseConflictError(branch, onto)


# --- Branch config operations ---


def get_branch_config(branch: str, key: str) -> str | None:
    result = _run(["config", "--get", f"branch.{branch}.{key}"], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def set_branch_config(branch: str, key: str, value: str) -> None:
    _run(["config", f"branch.{branch}.{key}", value])


def unset_branch_config(branch: str, key: str) -> None:
    _run(["config", "--unset", f"branch.{branch}.{key}"], check=False)


def all_local_branches() -> list[str]:
    result = _run(["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
    return [line for line in result.stdout.strip().splitlines() if line]


def merge_base(ref1: str, ref2: str) -> str:
    result = _run(["merge-base", ref1, ref2])
    return result.stdout.strip()


def merge_base_fork_point(upstream: str, branch: str) -> str | None:
    """Find fork point using reflog. Returns None if unavailable."""
    result = _run(["merge-base", "--fork-point", upstream, branch], check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def rev_parse(ref: str) -> str:
    result = _run(["rev-parse", ref])
    return result.stdout.strip()


def diffstat(ref1: str, ref2: str) -> str:
    """Return short diffstat between two refs."""
    result = _run(["diff", "--stat", "--shortstat", ref1, ref2])
    return result.stdout.strip()


def diff_shortstat(ref1: str, ref2: str) -> str:
    """Return compact diffstat like '+45 -12, 3 files'."""
    result = _run(["diff", "--shortstat", ref1, ref2])
    raw = result.stdout.strip()
    if not raw:
        return "no changes"
    # Parse: " 3 files changed, 45 insertions(+), 12 deletions(-)"
    files_m = re.search(r"(\d+) files? changed", raw)
    ins_m = re.search(r"(\d+) insertions?\(\+\)", raw)
    del_m = re.search(r"(\d+) deletions?\(-\)", raw)
    parts = []
    if ins_m:
        parts.append(f"+{ins_m.group(1)}")
    if del_m:
        parts.append(f"-{del_m.group(1)}")
    if files_m:
        n = files_m.group(1)
        parts.append(f"{n} file{'s' if int(n) != 1 else ''}")
    return ", ".join(parts) if parts else raw


def repo_root() -> str:
    """Return the absolute path of the repository root."""
    result = _run(["rev-parse", "--show-toplevel"])
    return result.stdout.strip()


def log_subjects(base: str, head: str) -> list[str]:
    """Return commit subjects between base and head (oldest first)."""
    result = _run(["log", "--format=%s", "--reverse", f"{base}..{head}"])
    return [line for line in result.stdout.strip().splitlines() if line]


def delete_branch(branch: str, *, force: bool = False) -> None:
    flag = "-D" if force else "-d"
    _run(["branch", flag, branch])


def reset_soft(ref: str) -> None:
    """Reset current branch to ref, keeping changes staged."""
    _run(["reset", "--soft", ref])


def commit(message: str) -> None:
    """Create a commit with the given message."""
    _run(["commit", "-m", message])


def rename_branch(old: str, new: str) -> None:
    """Rename a branch. Git auto-migrates branch.<name>.* config."""
    _run(["branch", "-m", old, new])


def delete_remote_branch(branch: str, remote: str = "origin") -> None:
    """Delete a branch on the remote."""
    _run(["push", remote, "--delete", branch])


def merge_ff_only(branch: str) -> None:
    """Fast-forward merge a branch into the current branch."""
    _run(["merge", "--ff-only", branch])


def git_dir() -> str:
    """Return the path to the .git directory."""
    result = _run(["rev-parse", "--git-dir"])
    return result.stdout.strip()


def rebase_continue() -> None:
    """Continue an in-progress rebase. No-op if no rebase is in progress."""
    if not _rebase_in_progress():
        return
    result = _run(
        ["rebase", "--continue"],
        check=False,
        env={"GIT_EDITOR": "true"},
    )
    if result.returncode != 0:
        raise RebaseConflictError("unknown", "unknown", conflict_files())


def rebase_abort() -> None:
    """Abort an in-progress rebase."""
    _run(["rebase", "--abort"])


def diff_cached_files() -> list[str]:
    """Return list of staged file paths."""
    result = _run(["diff", "--cached", "--name-only"])
    return [f for f in result.stdout.strip().splitlines() if f]


def log_files(base: str, head: str, file: str) -> list[str]:
    """Return commit SHAs that modified a file between base and head."""
    result = _run(["log", "--format=%H", f"{base}..{head}", "--", file])
    return [line for line in result.stdout.strip().splitlines() if line]


def checkout_file(ref: str, file: str) -> None:
    """Restore a file from a ref into the working tree and index."""
    _run(["checkout", ref, "--", file])


def add_files(files: list[str]) -> None:
    """Stage files."""
    _run(["add", "--"] + files)


def reset_files(files: list[str]) -> None:
    """Unstage files (reset HEAD)."""
    _run(["reset", "HEAD", "--"] + files)


def force_branch(name: str, sha: str) -> None:
    """Move an existing branch to point at a different SHA."""
    _run(["branch", "-f", name, sha])


def create_branch_at(name: str, start_point: str) -> None:
    """Create a branch at a specific point without checking it out."""
    _run(["branch", name, start_point])


def reset_hard(ref: str) -> None:
    """Reset current branch to ref, discarding all changes."""
    _run(["reset", "--hard", ref])


def log_oneline(base: str, head: str) -> list[tuple[str, str]]:
    """Return list of (sha, subject) between base and head, oldest first."""
    result = _run(["log", "--oneline", "--reverse", f"{base}..{head}"])
    commits = []
    for line in result.stdout.strip().splitlines():
        if line:
            sha, _, subject = line.partition(" ")
            commits.append((sha, subject))
    return commits
