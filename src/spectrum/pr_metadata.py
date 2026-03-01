"""PR body manipulation: sentinel-based metadata insert/update."""

from __future__ import annotations

import re

SENTINEL_START = "<!-- SPECTRUM:START -->"
SENTINEL_END = "<!-- SPECTRUM:END -->"


def build_stack_table(
    entries: list[dict],
    *,
    current_index: int,
    repo_url: str,
) -> str:
    """Build the spectrum metadata block for a PR body.

    entries: list of dicts with keys: index, letter, pr_number, title, is_draft
    current_index: the index of the PR this table is being inserted into
    repo_url: e.g. https://github.com/org/repo
    """
    total = len(entries)
    stack_id = entries[0].get("stack_id", "") if entries else ""

    lines = [
        SENTINEL_START,
        "---",
        f"> **Part {current_index + 1} of {total}** · `{stack_id.upper()}`",
        ">",
        "> | | PR | Title | Status |",
        "> |---|---|---|---|",
    ]

    for entry in entries:
        idx = entry["index"]
        pr_num = entry.get("pr_number")
        title = entry.get("title", "")
        is_draft = entry.get("is_draft", False)
        status = "Draft" if is_draft else "Open"

        num_display = f"#{pr_num}" if pr_num else "—"
        is_current = idx == current_index

        if is_current:
            # Bold the current row
            pr_link = f"**{num_display}**"
            row = f"> | **{idx + 1}** | {pr_link} | {title} | **{status}** |"
        else:
            if pr_num:
                pr_link = f"[{num_display}]({repo_url}/pull/{pr_num})"
            else:
                pr_link = num_display
            row = f"> | {idx + 1} | {pr_link} | {title} | {status} |"

        lines.append(row)

    lines.append(SENTINEL_END)
    return "\n".join(lines)


def insert_metadata(body: str, metadata: str) -> str:
    """Insert or replace spectrum metadata in a PR body."""
    pattern = re.compile(
        re.escape(SENTINEL_START) + r".*?" + re.escape(SENTINEL_END),
        re.DOTALL,
    )
    if pattern.search(body):
        return pattern.sub(metadata, body)
    # Append to end
    return body.rstrip() + "\n\n" + metadata + "\n"


def remove_metadata(body: str) -> str:
    """Remove spectrum metadata from a PR body."""
    pattern = re.compile(
        r"\n*" + re.escape(SENTINEL_START) + r".*?" + re.escape(SENTINEL_END) + r"\n*",
        re.DOTALL,
    )
    return pattern.sub("", body).rstrip() + "\n"
