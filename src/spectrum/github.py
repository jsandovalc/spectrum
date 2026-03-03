"""GitHub operations via `gh` CLI: PR create/edit/view."""

from __future__ import annotations

import json
import os
import subprocess


class GhError(Exception):
    pass


def _run_gh(
    args: list[str],
    *,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["gh", *args],
            check=check,
            capture_output=capture,
            text=True,
        )
    except subprocess.CalledProcessError as e:
        raise GhError(f"gh {' '.join(args)} failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        raise GhError("'gh' CLI not found. Install it: https://cli.github.com") from None


def pr_create(
    *,
    title: str,
    body: str,
    base: str,
    head: str,
    draft: bool = False,
    reviewer: str | None = None,
) -> int:
    """Create a PR and return the PR number."""
    args = [
        "pr", "create",
        "--title", title,
        "--body", body,
        "--base", base,
        "--head", head,
        "--assignee", "@me",
    ]
    if draft:
        args.append("--draft")
    if reviewer:
        args.extend(["--reviewer", reviewer])

    result = _run_gh(args)
    # gh pr create prints the PR URL, extract the number
    url = result.stdout.strip()
    try:
        return int(url.rstrip("/").split("/")[-1])
    except (ValueError, IndexError):
        raise GhError(f"Could not parse PR number from: {url}") from None


def pr_edit_body(pr_number: int, body: str) -> None:
    """Update a PR's body."""
    payload = json.dumps({"body": body})
    try:
        subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/pulls/{pr_number}",
             "--method", "PATCH", "--input", "-"],
            input=payload, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        raise GhError(f"gh api PATCH pulls/{pr_number} failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        raise GhError("'gh' CLI not found. Install it: https://cli.github.com") from None


def pr_edit_base(pr_number: int, base: str) -> None:
    """Update a PR's base branch."""
    payload = json.dumps({"base": base})
    try:
        subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/pulls/{pr_number}",
             "--method", "PATCH", "--input", "-"],
            input=payload, check=True, capture_output=True, text=True,
        )
    except subprocess.CalledProcessError as e:
        raise GhError(f"gh api PATCH pulls/{pr_number} failed: {e.stderr.strip()}") from e
    except FileNotFoundError:
        raise GhError("'gh' CLI not found. Install it: https://cli.github.com") from None


def pr_view_web(branch: str) -> None:
    """Open the PR for a branch in the default web browser."""
    _run_gh(["pr", "view", branch, "--web"])


def pr_edit_title(pr_number: int, title: str) -> None:
    """Update a PR's title."""
    _run_gh(["pr", "edit", str(pr_number), "--title", title])


def pr_merge(pr_number: int, *, method: str = "squash") -> None:
    """Merge a PR using the specified method."""
    _run_gh(["pr", "merge", str(pr_number), f"--{method}", "--delete-branch"])


def pr_view(pr_number: int, *, extra_fields: list[str] | None = None) -> dict:
    """Get PR details as a dict."""
    fields = "number,title,body,state,isDraft,baseRefName,headRefName,url"
    if extra_fields:
        fields += "," + ",".join(extra_fields)
    result = _run_gh([
        "pr", "view", str(pr_number),
        "--json", fields,
    ])
    return json.loads(result.stdout)


def pr_view_by_branch(branch: str) -> dict | None:
    """Get PR details for a branch, or None if no PR exists."""
    result = _run_gh(
        [
            "pr", "view", branch,
            "--json", "number,title,body,state,isDraft,baseRefName,headRefName,url",
        ],
        check=False,
    )
    if result.returncode != 0:
        return None
    return json.loads(result.stdout)


def get_repo_url() -> str:
    """Get the current repo's GitHub URL."""
    result = _run_gh(["repo", "view", "--json", "url", "--jq", ".url"])
    return result.stdout.strip()


def read_pr_template() -> str | None:
    """Read .github/pull_request_template.md if it exists."""
    from spectrum import git

    try:
        root = git.repo_root()
    except git.GitError:
        return None

    for name in ("pull_request_template.md", "PULL_REQUEST_TEMPLATE.md"):
        path = os.path.join(root, ".github", name)
        try:
            with open(path) as f:
                return f.read()
        except FileNotFoundError:
            continue
    return None
