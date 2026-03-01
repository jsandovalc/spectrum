"""Click command group and all commands."""

from __future__ import annotations

import click

from spectrum import git, github, pr_metadata, stack
from spectrum.git import GitError, RebaseConflictError
from spectrum.github import GhError


class AliasGroup(click.Group):
    """Click group that supports short command aliases."""

    ALIASES: dict[str, str] = {
        "lg": "log",
        "st": "status",
        "sw": "switch",
    }

    @property
    def _aliases_by_command(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for alias, command in self.ALIASES.items():
            result.setdefault(command, []).append(alias)
        return result

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return super().get_command(ctx, self.ALIASES.get(cmd_name, cmd_name))

    def list_commands(self, ctx: click.Context) -> list[str]:
        return super().list_commands(ctx)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            help_text = cmd.get_short_help_str(limit=formatter.width)
            aliases = self._aliases_by_command.get(subcommand)
            if aliases:
                display_name = f"{subcommand} ({', '.join(sorted(aliases))})"
            else:
                display_name = subcommand
            commands.append((display_name, help_text))
        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(commands)


@click.group(cls=AliasGroup)
def main() -> None:
    """Spectrum — stacked PR tool for GitHub."""


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@main.command()
@click.argument("branch_name")
def create(branch_name: str) -> None:
    """Start a new stack from a Linear branch name.

    BRANCH_NAME is the branch name copied from Linear, e.g.
    jonathansandoval/msg-3391-preserve-aggregator-response-kind
    """
    stack_id = stack.extract_stack_id(branch_name)
    if stack_id is None:
        raise click.ClickException(
            f"Could not extract ticket ID from branch name: {branch_name}\n"
            "Expected format: user/TICKET-123-description"
        )

    first_branch = f"{branch_name}/a"
    if git.branch_exists(first_branch):
        raise click.ClickException(f"Branch {first_branch} already exists")

    click.echo("Fetching latest master...")
    try:
        git.fetch("origin", "master")
    except GitError as e:
        raise click.ClickException(str(e)) from e

    try:
        git.create_branch(first_branch, "origin/master")
    except GitError as e:
        raise click.ClickException(str(e)) from e

    entry = stack.StackEntry(
        branch=first_branch,
        index=0,
        stack_id=stack_id,
        merge_base="master",
    )
    stack.write_entry(entry)

    click.echo(f"Created stack {stack_id} on branch:")
    click.echo(f"  [a] {first_branch}")


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


@main.command()
def add() -> None:
    """Add a new part to the current stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    full_stack = stack.get_stack(current.stack_id)
    next_letter = stack.next_letter(full_stack)
    base_branch = stack.extract_base_branch(current.branch)
    if base_branch is None:
        raise click.ClickException(
            f"Could not determine base branch name from: {current.branch}"
        )

    new_branch = f"{base_branch}/{next_letter}"
    if git.branch_exists(new_branch):
        raise click.ClickException(f"Branch {new_branch} already exists")

    last_entry = max(full_stack, key=lambda e: e.index)

    try:
        git.create_branch(new_branch, last_entry.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e

    new_entry = stack.StackEntry(
        branch=new_branch,
        index=last_entry.index + 1,
        stack_id=current.stack_id,
        merge_base=last_entry.branch,
    )
    stack.write_entry(new_entry)

    total = len(full_stack) + 1
    click.echo("Created branch:")
    click.echo(f"  [{next_letter}] {new_branch} (part {total} of {total})")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@main.command()
def status() -> None:
    """Show current stack state."""
    entries = stack.current_stack()
    if not entries:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    current_branch = git.current_branch()
    stack_id = entries[0].stack_id
    click.echo(f"Stack: {stack_id} ({len(entries)} part{'s' if len(entries) != 1 else ''})")
    click.echo()

    repo_url = None
    if any(e.pr_number for e in entries):
        try:
            repo_url = github.get_repo_url()
        except GhError:
            pass

    for entry in entries:
        marker = "  <-- you are here" if entry.branch == current_branch else ""
        click.echo(f"  [{entry.letter}] {entry.branch}{marker}")

        pr_info_parts: list[str] = []
        if entry.pr_number:
            pr_info_parts.append(f"PR #{entry.pr_number}")
        base_label = entry.merge_base
        sibling_letter = stack.extract_letter(entry.merge_base)
        if sibling_letter:
            base_label = f"[{sibling_letter}]"
        pr_info_parts.append(f"<- {base_label}")
        click.echo(f"      {' '.join(pr_info_parts)}")

        if entry.pr_number and repo_url:
            click.echo(f"      {repo_url}/pull/{entry.pr_number}")

        try:
            stat = git.diff_shortstat(entry.merge_base, entry.branch)
            click.echo(f"      {stat}")
        except GitError:
            pass

        click.echo()


# ---------------------------------------------------------------------------
# switch
# ---------------------------------------------------------------------------


@main.command()
@click.argument("part")
def switch(part: str) -> None:
    """Switch to a part of the current stack.

    PART is the letter (a, b, c, ...) of the stack part to switch to.
    """
    entries = stack.current_stack()
    if not entries:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    target_index = stack.letter_to_index(part)
    target = next((e for e in entries if e.index == target_index), None)
    if target is None:
        available = ", ".join(e.letter for e in entries)
        raise click.ClickException(
            f"Part [{part}] not found in stack. Available: {available}"
        )

    try:
        git.checkout(target.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Switched to [{part}] {target.branch}")


# ---------------------------------------------------------------------------
# next / prev
# ---------------------------------------------------------------------------


@main.command("next")
def next_cmd() -> None:
    """Move to the next part in the stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.current_stack()
    target = next((e for e in entries if e.index == current.index + 1), None)
    if target is None:
        raise click.ClickException("Already on the last part.")

    try:
        git.checkout(target.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Switched to [{target.letter}] {target.branch}")


@main.command()
def prev() -> None:
    """Move to the previous part in the stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.current_stack()
    target = next((e for e in entries if e.index == current.index - 1), None)
    if target is None:
        raise click.ClickException("Already on the first part.")

    try:
        git.checkout(target.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e

    click.echo(f"Switched to [{target.letter}] {target.branch}")


# ---------------------------------------------------------------------------
# top / bottom
# ---------------------------------------------------------------------------


@main.command()
def top() -> None:
    """Jump to the last part of the stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.current_stack()
    target = entries[-1]
    if target.index == current.index:
        raise click.ClickException("Already on the last part.")
    try:
        git.checkout(target.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"Switched to [{target.letter}] {target.branch}")


@main.command()
def bottom() -> None:
    """Jump to the first part of the stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.current_stack()
    target = entries[0]
    if target.index == current.index:
        raise click.ClickException("Already on the first part.")
    try:
        git.checkout(target.branch)
    except GitError as e:
        raise click.ClickException(str(e)) from e
    click.echo(f"Switched to [{target.letter}] {target.branch}")


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


def _get_title(entry: stack.StackEntry) -> str:
    """Get the PR title for a stack entry."""
    title_from_config = git.get_branch_config(entry.branch, "spectrum-title")
    message = title_from_config
    if not message:
        subjects = git.log_subjects(entry.merge_base, entry.branch)
        if subjects:
            message = subjects[0]
    return stack.format_pr_title(entry.stack_id, entry.letter, message)


def _build_stack_table_entries(
    entries: list[stack.StackEntry],
) -> list[dict]:
    """Convert StackEntry list to dicts for pr_metadata."""
    result = []
    for entry in entries:
        title_from_config = git.get_branch_config(entry.branch, "spectrum-title")
        pr_info = None
        if entry.pr_number:
            try:
                pr_info = github.pr_view(entry.pr_number)
            except GhError:
                pass

        result.append({
            "index": entry.index,
            "letter": entry.letter,
            "pr_number": entry.pr_number,
            "title": title_from_config or (pr_info.get("title", "") if pr_info else ""),
            "is_draft": pr_info.get("isDraft", True) if pr_info else True,
            "stack_id": entry.stack_id,
        })
    return result


def _update_all_pr_bodies(entries: list[stack.StackEntry], repo_url: str) -> None:
    """Update the spectrum metadata section in all PR bodies."""
    table_entries = _build_stack_table_entries(entries)
    for entry in entries:
        if entry.pr_number is None:
            continue
        try:
            pr_data = github.pr_view(entry.pr_number)
        except GhError:
            continue
        current_body = pr_data.get("body", "")
        metadata = pr_metadata.build_stack_table(
            table_entries,
            current_index=entry.index,
            repo_url=repo_url,
        )
        new_body = pr_metadata.insert_metadata(current_body, metadata)
        if new_body != current_body:
            github.pr_edit_body(entry.pr_number, new_body)


@main.command()
@click.option("--draft", is_flag=True, help="Create PRs as drafts")
@click.option("--reviewer", "-r", default=None, help="Add reviewer to new PRs")
def submit(draft: bool, reviewer: str | None) -> None:
    """Create or update PRs for all branches in the stack."""
    entries = stack.current_stack()
    if not entries:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    # Push all branches
    branches = [e.branch for e in entries]
    click.echo(f"Pushing {len(branches)} branch{'es' if len(branches) != 1 else ''}...")
    try:
        git.push_force_with_lease(branches)
    except GitError as e:
        raise click.ClickException(str(e)) from e
    for b in branches:
        click.echo(f"  {b} -> origin (pushed)")

    click.echo()

    try:
        repo_url = github.get_repo_url()
    except GhError as e:
        raise click.ClickException(str(e)) from e

    pr_template = github.read_pr_template() or ""

    # Check for branches with no commits relative to their base
    empty_branches = []
    for entry in entries:
        if entry.pr_number is not None:
            continue
        commits = git.log_subjects(entry.merge_base, entry.branch)
        if not commits:
            empty_branches.append(entry)

    if empty_branches:
        labels = ", ".join(f"[{e.letter}]" for e in empty_branches)
        raise click.ClickException(
            f"No commits found for {labels} relative to "
            f"{'its' if len(empty_branches) == 1 else 'their'} base branch. "
            f"Did you forget to commit your changes?"
        )

    # Create PRs for branches that don't have them yet
    for entry in entries:
        if entry.pr_number is not None:
            click.echo(f"PR #{entry.pr_number} already exists for [{entry.letter}]")
            continue

        title = _get_title(entry)
        body = pr_template

        try:
            pr_number = github.pr_create(
                title=title,
                body=body,
                base=entry.merge_base,
                head=entry.branch,
                draft=draft,
                reviewer=reviewer,
            )
        except GhError as e:
            raise click.ClickException(f"Failed to create PR for [{entry.letter}]: {e}") from e

        entry.pr_number = pr_number
        git.set_branch_config(entry.branch, "spectrum-pr", str(pr_number))
        click.echo(f"Created PR #{pr_number}: {title}")

    # Update all PR bodies with stack metadata
    click.echo()
    _update_all_pr_bodies(entries, repo_url)

    # Print summary
    click.echo("Stack:")
    for entry in entries:
        base_label = entry.merge_base
        sibling_letter = stack.extract_letter(entry.merge_base)
        if sibling_letter:
            base_label = f"[{sibling_letter}]"
        status_label = "(draft)" if draft else ""
        title_from_config = git.get_branch_config(entry.branch, "spectrum-title") or ""
        click.echo(
            f"  #{entry.pr_number} [{entry.letter}] {title_from_config}  "
            f"<- {base_label}  {status_label}"
        )
        click.echo(f"      {repo_url}/pull/{entry.pr_number}")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


@main.command()
@click.option("--no-push", is_flag=True, help="Skip pushing after rebase")
def sync(no_push: bool) -> None:
    """Fetch, detect merges, and rebase from current position."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.get_stack(current.stack_id)
    original_branch = git.current_branch()

    click.echo("Fetching origin/master...")
    try:
        git.fetch("origin", "master")
    except GitError as e:
        raise click.ClickException(str(e)) from e

    # Check if any earlier parts have been merged
    merged_indices: set[int] = set()
    for entry in entries:
        if entry.pr_number is None:
            continue
        try:
            pr_data = github.pr_view(entry.pr_number)
            if pr_data.get("state") == "MERGED":
                merged_indices.add(entry.index)
                click.echo(f"  [{entry.letter}] PR #{entry.pr_number} has been merged")
        except GhError:
            pass

    # Handle merged entries: retarget the next entry to master
    if merged_indices:
        for entry in entries:
            if entry.index in merged_indices:
                continue
            # If this entry's parent was merged, retarget to master
            parent_entry = next(
                (e for e in entries if e.branch == entry.merge_base), None
            )
            if parent_entry and parent_entry.index in merged_indices:
                entry.merge_base = "master"
                git.set_branch_config(entry.branch, "gh-merge-base", "master")
                if entry.pr_number:
                    try:
                        github.pr_edit_base(entry.pr_number, "master")
                    except GhError:
                        pass
                click.echo(f"  [{entry.letter}] retargeted to master")

        # Clean up merged entries
        for entry in entries:
            if entry.index in merged_indices:
                stack.remove_entry(entry.branch)

        # Refresh the stack without merged entries
        entries = [e for e in entries if e.index not in merged_indices]

    if not entries:
        click.echo("All parts merged! Stack is empty.")
        return

    # Rebase scope: from current position onward
    to_rebase = [e for e in entries if e.index >= current.index]

    branches_to_push: list[str] = []
    pre_rebase_tip: dict[str, str] = {}
    for entry in to_rebase:
        onto = "origin/master" if entry.merge_base == "master" else entry.merge_base
        click.echo(f"Rebasing [{entry.letter}] onto {onto}... ", nl=False)
        try:
            if entry.merge_base in pre_rebase_tip:
                old_base = pre_rebase_tip[entry.merge_base]
            else:
                old_base = (
                    git.merge_base_fork_point(onto, entry.branch)
                    or git.merge_base(entry.branch, onto)
                )
            pre_rebase_tip[entry.branch] = git.rev_parse(entry.branch)
            git.rebase_onto(entry.branch, onto, old_base)
            click.echo("done")
            branches_to_push.append(entry.branch)
        except RebaseConflictError:
            click.echo("CONFLICT")
            click.echo(
                f"\nConflict rebasing [{entry.letter}] onto {onto}. "
                "Resolve conflicts, then:\n"
                "  git add <files>\n"
                "  git rebase --continue\n"
                "  spectrum sync"
            )
            return
        except GitError as e:
            raise click.ClickException(str(e)) from e

    # Return to original branch
    try:
        git.checkout(original_branch)
    except GitError:
        git.checkout(entries[0].branch)

    if not branches_to_push:
        click.echo("Nothing to push.")
        return

    if no_push:
        click.echo("Rebase complete. Skipping push.")
        return

    click.echo()
    try:
        git.push_force_with_lease(branches_to_push)
    except GitError as e:
        raise click.ClickException(str(e)) from e
    click.echo("Pushed.")

    # Update PR metadata
    try:
        repo_url = github.get_repo_url()
        _update_all_pr_bodies(entries, repo_url)
    except GhError:
        pass


# ---------------------------------------------------------------------------
# drop
# ---------------------------------------------------------------------------


@main.command()
@click.argument("part", required=False, default=None)
def drop(part: str | None) -> None:
    """Remove a part from the stack.

    PART is the letter to drop. Defaults to current branch.
    """
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.current_stack()

    # Resolve target entry
    if part is not None:
        target_index = stack.letter_to_index(part)
        target = next((e for e in entries if e.index == target_index), None)
        if target is None:
            available = ", ".join(e.letter for e in entries)
            raise click.ClickException(
                f"Part [{part}] not found in stack. Available: {available}"
            )
    else:
        target = current

    # Find the entry after the dropped one and retarget it
    successor = next((e for e in entries if e.merge_base == target.branch), None)
    if successor is not None:
        successor.merge_base = target.merge_base
        git.set_branch_config(successor.branch, "gh-merge-base", target.merge_base)

    # Remove the entry
    stack.remove_entry(target.branch)

    # Re-index remaining entries
    stack.reindex_stack(target.stack_id)

    # Determine where to checkout
    remaining = [e for e in entries if e.branch != target.branch]
    if remaining:
        # Prefer previous part, fall back to next
        prev_entry = next((e for e in remaining if e.index < target.index), None)
        next_entry = next((e for e in remaining if e.index > target.index), None)
        checkout_target = prev_entry or next_entry
        if checkout_target and target.branch == current.branch:
            try:
                git.checkout(checkout_target.branch)
            except GitError as e:
                raise click.ClickException(str(e)) from e

    click.echo(f"Dropped [{target.letter}] {target.branch}")


# ---------------------------------------------------------------------------
# log
# ---------------------------------------------------------------------------


def _format_log(
    entries: list[dict],
    *,
    stack_id: str,
    current_branch: str,
) -> str:
    """Format a graphical stack view. Pure function — no I/O."""
    count = len(entries)
    lines = [f"Stack: {stack_id} ({count} part{'s' if count != 1 else ''})", ""]

    reversed_entries = list(reversed(entries))
    for i, entry in enumerate(reversed_entries):
        is_current = entry["branch"] == current_branch
        is_last = i == len(reversed_entries) - 1
        symbol = "●" if is_current else "○"
        marker = "           <-- you are here" if is_current else ""
        lines.append(f"  {symbol} [{entry['letter']}] {entry['branch']}{marker}")

        detail_parts: list[str] = []
        if entry.get("pr_number"):
            pr_label = f"PR #{entry['pr_number']}"
            if entry.get("is_draft"):
                pr_label += " (draft)"
            detail_parts.append(pr_label)

        if entry.get("diff_stat"):
            detail_parts.append(entry["diff_stat"])

        connector = "│" if not is_last else " "
        if detail_parts:
            lines.append(f"  {connector}     {'  '.join(detail_parts)}")

        if not is_last:
            lines.append("  │")

    return "\n".join(lines)


@main.command()
def log() -> None:
    """Show graphical stack view."""
    entries = stack.current_stack()
    if not entries:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    current_branch = git.current_branch()

    view_entries = []
    for entry in entries:
        pr_number = entry.pr_number
        is_draft = False
        if pr_number:
            try:
                is_draft = github.pr_view(pr_number).get("isDraft", False)
            except GhError:
                pass

        diff_stat = None
        try:
            diff_stat = git.diff_shortstat(entry.merge_base, entry.branch)
        except GitError:
            pass

        view_entries.append({
            "branch": entry.branch,
            "letter": entry.letter,
            "pr_number": pr_number,
            "is_draft": is_draft,
            "diff_stat": diff_stat,
        })

    click.echo(_format_log(
        view_entries,
        stack_id=entries[0].stack_id,
        current_branch=current_branch,
    ))


# ---------------------------------------------------------------------------
# adopt
# ---------------------------------------------------------------------------


@main.command()
@click.argument("branches", nargs=-1, required=True)
def adopt(branches: tuple[str, ...]) -> None:
    """Import existing branches into a stack.

    BRANCHES are existing branch names to adopt, in order.
    The first branch will be [a], second [b], etc.
    """
    if not branches:
        raise click.ClickException("Provide at least one branch name.")

    # Validate all branches exist
    for branch in branches:
        if not git.branch_exists(branch):
            raise click.ClickException(f"Branch {branch} does not exist")

    # Try to extract stack_id from the first branch
    stack_id = stack.extract_stack_id(branches[0])
    if stack_id is None:
        raise click.ClickException(
            f"Could not extract ticket ID from: {branches[0]}\n"
            "Expected format: user/TICKET-123-description"
        )

    # Check none are already in a stack
    for branch in branches:
        existing = stack.read_entry(branch)
        if existing is not None:
            raise click.ClickException(
                f"Branch {branch} is already in stack {existing.stack_id}"
            )

    for i, branch in enumerate(branches):
        if i == 0:
            merge_base = "master"
        else:
            merge_base = branches[i - 1]

        entry = stack.StackEntry(
            branch=branch,
            index=i,
            stack_id=stack_id,
            merge_base=merge_base,
        )
        stack.write_entry(entry)

        letter = stack.index_to_letter(i)
        click.echo(f"  [{letter}] {branch} <- {merge_base}")

    click.echo(f"\nAdopted {len(branches)} branches into stack {stack_id}")
