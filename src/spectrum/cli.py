"""Click command group and all commands."""

from __future__ import annotations

from collections.abc import Callable

import click

from spectrum import git, github, pr_metadata, stack, ui
from spectrum.git import GitError, RebaseConflictError
from spectrum.github import GhError
from spectrum.opstate import OperationState


class AliasGroup(click.Group):
    """Click group that supports short command aliases."""

    ALIASES: dict[str, str] = {
        "lg": "log",
        "o": "pr",
        "st": "status",
        "sw": "switch",
    }

    COMMAND_GROUPS: dict[str, list[str]] = {
        "Stack": ["create", "add", "drop", "adopt"],
        "Navigate": ["switch", "next", "prev", "top", "bottom"],
        "Publish": ["submit", "pr", "title", "land", "wip"],
        "Edit": ["sync", "restack", "squash", "fold", "move", "rename"],
        "Info": ["status", "log"],
        "Recovery": ["continue", "abort"],
    }

    @property
    def _aliases_by_command(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for alias, command in self.ALIASES.items():
            result.setdefault(command, []).append(alias)
        return result

    def invoke(self, ctx: click.Context) -> None:
        try:
            return super().invoke(ctx)
        except (GitError, GhError) as e:
            raise click.ClickException(str(e)) from e

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        return super().get_command(ctx, self.ALIASES.get(cmd_name, cmd_name))

    def list_commands(self, ctx: click.Context) -> list[str]:
        return super().list_commands(ctx)

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        all_commands = self.list_commands(ctx)
        cmd_map: dict[str, tuple[str, str]] = {}
        for subcommand in all_commands:
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            help_text = cmd.get_short_help_str(limit=formatter.width)
            aliases = self._aliases_by_command.get(subcommand)
            if aliases:
                display_name = f"{subcommand} ({', '.join(sorted(aliases))})"
            else:
                display_name = subcommand
            cmd_map[subcommand] = (display_name, help_text)

        for group_name, group_cmds in self.COMMAND_GROUPS.items():
            entries = []
            for cmd_name in group_cmds:
                if cmd_name in cmd_map:
                    entries.append(cmd_map[cmd_name])
            if entries:
                with formatter.section(group_name):
                    formatter.write_dl(entries)


@click.group(cls=AliasGroup)
def main() -> None:
    """Spectrum — stacked PR tool for GitHub."""


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@main.command()
@click.argument("branch_name")
@click.option("--on", "on_branch", default=None, help="Start stack from this branch instead of master")
def create(branch_name: str, on_branch: str | None) -> None:
    """Start a new stack from a branch name.

    BRANCH_NAME is the branch name, e.g.
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

    if on_branch is not None and not git.branch_exists(on_branch):
        raise click.ClickException(f"Branch {on_branch} does not exist")

    click.echo("Fetching latest master...")
    git.fetch("origin", "master")

    if on_branch is not None:
        start_point = on_branch
        merge_base = on_branch
    else:
        start_point = "origin/master"
        merge_base = "master"

    git.create_branch(first_branch, start_point)

    entry = stack.StackEntry(
        branch=first_branch,
        index=0,
        stack_id=stack_id,
        merge_base=merge_base,
    )
    stack.write_entry(entry)

    based_on = f" {ui.dim(f'(based on {on_branch})')}" if on_branch else ""
    click.echo(f"{ui.success('Created')} stack {ui.header(stack_id)} on branch:")
    click.echo(f"  {ui.letter('[a]')} {first_branch}{based_on}")


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

    git.create_branch(new_branch, last_entry.branch)

    new_entry = stack.StackEntry(
        branch=new_branch,
        index=last_entry.index + 1,
        stack_id=current.stack_id,
        merge_base=last_entry.branch,
    )
    stack.write_entry(new_entry)

    total = len(full_stack) + 1
    click.echo(f"{ui.success('Created')} branch:")
    click.echo(f"  {ui.bracket_letter(next_letter)} {new_branch} {ui.dim(f'(part {total} of {total})')}")


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
    click.echo(f"{ui.header('Stack:')} {stack_id} ({len(entries)} part{'s' if len(entries) != 1 else ''})")
    click.echo()

    repo_url = None
    if any(e.pr_number for e in entries):
        try:
            repo_url = github.get_repo_url()
        except GhError:
            pass

    for entry in entries:
        is_current = entry.branch == current_branch
        if is_current:
            marker = f"  {ui.current_label('<-- you are here')}"
        else:
            marker = ""
        click.echo(f"  {ui.bracket_letter(entry.letter)} {entry.branch}{marker}")

        pr_info_parts: list[str] = []
        if entry.pr_number:
            pr_info_parts.append(ui.pr_number(f"PR #{entry.pr_number}"))
        base_label = entry.merge_base
        sibling_letter = stack.extract_letter(entry.merge_base)
        if sibling_letter:
            base_label = f"[{sibling_letter}]"
        pr_info_parts.append(ui.dim(f"<- {base_label}"))
        click.echo(f"      {' '.join(pr_info_parts)}")

        if entry.pr_number and repo_url:
            click.echo(f"      {ui.dim(f'{repo_url}/pull/{entry.pr_number}')}")

        stat = _get_diff_stat(entry.merge_base, entry.branch)
        if stat:
            click.echo(f"      {ui.dim(stat)}")

        click.echo()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _get_diff_stat(base: str, head: str) -> str | None:
    """Return diff shortstat or None on error."""
    try:
        return git.diff_shortstat(base, head)
    except GitError:
        return None


def _show_diff_stat(entry: stack.StackEntry) -> None:
    """Show diff stat for an entry, silently ignoring errors."""
    stat = _get_diff_stat(entry.merge_base, entry.branch)
    if stat:
        click.echo(f"  {ui.dim(stat)}")


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

    git.checkout(target.branch)

    click.echo(f"Switched to {ui.bracket_letter(part)} {target.branch}")
    _show_diff_stat(target)


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

    git.checkout(target.branch)

    click.echo(f"Switched to {ui.bracket_letter(target.letter)} {target.branch}")
    _show_diff_stat(target)


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

    git.checkout(target.branch)

    click.echo(f"Switched to {ui.bracket_letter(target.letter)} {target.branch}")
    _show_diff_stat(target)


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
    git.checkout(target.branch)
    click.echo(f"Switched to {ui.bracket_letter(target.letter)} {target.branch}")
    _show_diff_stat(target)


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
    git.checkout(target.branch)
    click.echo(f"Switched to {ui.bracket_letter(target.letter)} {target.branch}")
    _show_diff_stat(target)


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

    # Filter out WIP entries for push/PR creation
    active_entries = [e for e in entries if not e.wip]
    wip_entries = [e for e in entries if e.wip]
    for wip_entry in wip_entries:
        click.echo(f"{ui.warning('Skipping')} {ui.bracket_letter(wip_entry.letter)} {ui.warning('(WIP)')}")

    # Push all active branches
    branches = [e.branch for e in active_entries]
    if branches:
        click.echo(f"Pushing {len(branches)} branch{'es' if len(branches) != 1 else ''}...")
        git.push_force_with_lease(branches)
        for b in branches:
            click.echo(f"  {b} -> origin {ui.success('(pushed)')}")

    click.echo()

    repo_url = github.get_repo_url()

    pr_template = github.read_pr_template() or ""

    # Check for branches with no commits relative to their base
    empty_branches = []
    for entry in active_entries:
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

    # Create PRs for active branches that don't have them yet
    for entry in active_entries:
        if entry.pr_number is not None:
            click.echo(f"{ui.pr_number(f'PR #{entry.pr_number}')} already exists for {ui.bracket_letter(entry.letter)}")
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
        click.echo(f"{ui.success('Created')} {ui.pr_number(f'PR #{pr_number}')}: {title}")

    # Update all PR bodies with stack metadata
    click.echo()
    _update_all_pr_bodies(entries, repo_url)

    # Print summary
    click.echo(ui.header("Stack:"))
    for entry in entries:
        base_label = entry.merge_base
        sibling_letter = stack.extract_letter(entry.merge_base)
        if sibling_letter:
            base_label = f"[{sibling_letter}]"
        title_from_config = git.get_branch_config(entry.branch, "spectrum-title") or ""
        parts = [
            f"  {ui.pr_number(f'#{entry.pr_number}')} {ui.bracket_letter(entry.letter)} {title_from_config}",
            ui.dim(f"<- {base_label}"),
        ]
        if draft:
            parts.append(ui.warning("(draft)"))
        stat = _get_diff_stat(entry.merge_base, entry.branch)
        if stat:
            parts.append(ui.dim(stat))
        click.echo("  ".join(parts))
        click.echo(f"      {ui.dim(f'{repo_url}/pull/{entry.pr_number}')}")


# ---------------------------------------------------------------------------
# pr
# ---------------------------------------------------------------------------


@main.command()
def pr() -> None:
    """Open the current branch's PR in the browser."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )
    if current.pr_number is None:
        raise click.ClickException(
            f"No PR found for [{current.letter}]. Run 'spectrum submit' first."
        )
    click.echo(f"Opening {ui.pr_number(f'PR #{current.pr_number}')} for {ui.bracket_letter(current.letter)}...")
    github.pr_view_web(current.branch)


# ---------------------------------------------------------------------------
# title
# ---------------------------------------------------------------------------


@main.command()
@click.argument("title")
def title(title: str) -> None:
    """Set the PR title for the current branch."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    git.set_branch_config(current.branch, "spectrum-title", title)
    formatted = stack.format_pr_title(current.stack_id, current.letter, title)

    if current.pr_number is not None:
        github.pr_edit_title(current.pr_number, formatted)
        click.echo(f"{ui.success('Updated')} {ui.pr_number(f'PR #{current.pr_number}')} title: {formatted}")
    else:
        click.echo(f"{ui.success('Title saved.')} Will be used on next submit.")


# ---------------------------------------------------------------------------
# land
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--method",
    type=click.Choice(["squash", "merge", "rebase"]),
    default="squash",
    help="Merge method",
)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def land(method: str, yes: bool) -> None:
    """Merge the bottom PR and update the stack."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.get_stack(current.stack_id)
    target = entries[0]  # Bottom of stack

    if target.pr_number is None:
        raise click.ClickException(
            f"No PR found for [{target.letter}]. Run 'spectrum submit' first."
        )

    if not yes:
        click.confirm(
            f"Merge PR #{target.pr_number} [{target.letter}] via {method}?",
            abort=True,
        )

    click.echo(f"Merging {ui.pr_number(f'PR #{target.pr_number}')} {ui.bracket_letter(target.letter)} via {method}...")
    github.pr_merge(target.pr_number, method=method)

    # Retarget successor
    successor = next((e for e in entries if e.merge_base == target.branch), None)
    if successor is not None:
        _retarget_to_master(successor, reason="landed")

    # Clean up
    stack.remove_entry(target.branch)
    stack.reindex_stack(target.stack_id)

    remaining = [e for e in entries if e.branch != target.branch]
    if not remaining:
        click.echo(ui.success("All parts landed! Stack is empty."))
        return

    # Fetch and rebase remaining
    click.echo("Fetching origin/master...")
    git.fetch("origin", "master")

    _rebase_entries(
        remaining,
        resolve_onto=lambda mb: "origin/master" if mb == "master" else mb,
        resume_command="spectrum sync",
        original_branch=remaining[0].branch,
    )

    # Checkout the new bottom
    try:
        git.checkout(remaining[0].branch)
    except GitError:
        pass

    click.echo(f"{ui.success('Landed')} {ui.bracket_letter(target.letter)}. {len(remaining)} part(s) remaining.")


# ---------------------------------------------------------------------------
# rebase helper
# ---------------------------------------------------------------------------


def _rebase_entries(
    entries: list[stack.StackEntry],
    *,
    resolve_onto: Callable[[str], str] | None = None,
    resume_command: str,
    original_branch: str | None = None,
) -> list[str]:
    """Rebase stack entries in order. Returns list of rebased branch names.

    Partial list if conflict stopped early (conflict message already printed).
    On conflict, saves operation state for `spectrum continue`.
    """
    rebased: list[str] = []
    pre_rebase_tip: dict[str, str] = {}
    for i, entry in enumerate(entries):
        onto = resolve_onto(entry.merge_base) if resolve_onto else entry.merge_base
        click.echo(f"Rebasing {ui.bracket_letter(entry.letter)} onto {onto}... ", nl=False)
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
            click.echo(ui.success("done"))
            rebased.append(entry.branch)
        except RebaseConflictError:
            click.echo(ui.error("CONFLICT"))
            # Save state for continue/abort
            remaining = entries[i:]
            uses_origin_master = resolve_onto is not None
            saved_branch = original_branch or entries[0].branch
            op_state = OperationState(
                command=resume_command,
                remaining_branches=[e.branch for e in remaining],
                remaining_merge_bases=[e.merge_base for e in remaining],
                remaining_stack_ids=[e.stack_id for e in remaining],
                remaining_indices=[e.index for e in remaining],
                original_branch=saved_branch,
                stack_id=entry.stack_id,
                resolve_onto_master=uses_origin_master,
            )
            op_state.save()
            click.echo(
                f"\n{ui.error('Conflict')} rebasing {ui.bracket_letter(entry.letter)} onto {onto}. "
                "Resolve conflicts, then:\n"
                "  git add <files>\n"
                "  spectrum continue\n"
                "\nOr abort with:\n"
                "  spectrum abort"
            )
            return rebased
    return rebased


def _retarget_to_master(entry: stack.StackEntry, reason: str | None = None) -> None:
    """Retarget an entry's merge base to master and update PR if it exists."""
    entry.merge_base = "master"
    git.set_branch_config(entry.branch, "gh-merge-base", "master")
    if entry.pr_number:
        try:
            github.pr_edit_base(entry.pr_number, "master")
        except GhError:
            pass
    suffix = f" {ui.dim(f'({reason})')}" if reason else ""
    click.echo(f"  {ui.bracket_letter(entry.letter)} retargeted to master{suffix}")


# ---------------------------------------------------------------------------
# sync
# ---------------------------------------------------------------------------


def _is_cross_stack_base_merged(
    merge_base: str,
    entries: list[stack.StackEntry],
) -> bool:
    """Check if merge_base is a cross-stack branch whose PR has been merged.

    Returns False for "master" or branches within the current stack.
    Falls back to pr_view_by_branch when local config is missing.
    Returns False if all lookups fail (fail-safe: don't retarget).
    """
    if merge_base == "master":
        return False

    # If the merge_base is a branch in the current stack, it's not cross-stack
    if any(e.branch == merge_base for e in entries):
        return False

    # Try looking up the PR via stack config on the merge_base branch
    base_entry = stack.read_entry(merge_base)
    if base_entry and base_entry.pr_number:
        try:
            pr_data = github.pr_view(base_entry.pr_number)
            return pr_data.get("state") == "MERGED"
        except GhError:
            pass

    # Fallback: look up PR by branch name (handles deleted local branches)
    try:
        pr_data = github.pr_view_by_branch(merge_base)
        if pr_data is not None:
            return pr_data.get("state") == "MERGED"
    except GhError:
        pass

    return False


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
    git.fetch("origin", "master")

    # Check if any earlier parts have been merged
    merged_indices: set[int] = set()
    for entry in entries:
        if entry.pr_number is None:
            continue
        try:
            pr_data = github.pr_view(entry.pr_number)
            if pr_data.get("state") == "MERGED":
                merged_indices.add(entry.index)
                click.echo(f"  {ui.bracket_letter(entry.letter)} {ui.pr_number(f'PR #{entry.pr_number}')} has been merged")
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
                _retarget_to_master(entry)

        # Clean up merged entries
        for entry in entries:
            if entry.index in merged_indices:
                stack.remove_entry(entry.branch)

        # Refresh the stack without merged entries
        entries = [e for e in entries if e.index not in merged_indices]

    if not entries:
        click.echo(ui.success("All parts merged! Stack is empty."))
        return

    # Check for cross-stack dependencies that have been merged
    for entry in entries:
        old_base = entry.merge_base
        if _is_cross_stack_base_merged(old_base, entries):
            _retarget_to_master(entry, reason=f"dependency {old_base} merged")

    # Rebase scope: from current position onward
    to_rebase = [e for e in entries if e.index >= current.index]

    branches_to_push = _rebase_entries(
        to_rebase,
        resolve_onto=lambda mb: "origin/master" if mb == "master" else mb,
        resume_command="spectrum sync",
        original_branch=original_branch,
    )
    if len(branches_to_push) < len(to_rebase):
        return

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
    git.push_force_with_lease(branches_to_push)
    click.echo(ui.success("Pushed."))

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
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def drop(part: str | None, yes: bool) -> None:
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

    if not yes:
        click.confirm(f"Drop [{target.letter}] {target.branch}?", abort=True)

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
            git.checkout(checkout_target.branch)

    click.echo(f"{ui.success('Dropped')} {ui.bracket_letter(target.letter)} {target.branch}")


# ---------------------------------------------------------------------------
# rename
# ---------------------------------------------------------------------------


@main.command()
@click.argument("new_name")
def rename(new_name: str) -> None:
    """Rename the current branch."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    old_name = current.branch
    if git.branch_exists(new_name):
        raise click.ClickException(f"Branch {new_name} already exists")

    git.rename_branch(old_name, new_name)

    # Update children's merge_base that pointed to old name
    entries = stack.get_stack(current.stack_id)
    for entry in entries:
        if entry.merge_base == old_name:
            git.set_branch_config(entry.branch, "gh-merge-base", new_name)

    # Push new name and delete old remote
    git.push_force_with_lease([new_name])

    try:
        git.delete_remote_branch(old_name)
    except GitError:
        pass  # Remote branch might not exist

    click.echo(f"{ui.success('Renamed')} {old_name} {ui.dim('->')} {new_name}")


# ---------------------------------------------------------------------------
# fold
# ---------------------------------------------------------------------------


@main.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def fold(yes: bool) -> None:
    """Merge the current branch into its parent."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.get_stack(current.stack_id)

    if current.index == 0:
        raise click.ClickException("Cannot fold the first part of the stack.")

    # Find parent entry
    parent = next((e for e in entries if e.branch == current.merge_base), None)
    if parent is None:
        raise click.ClickException(
            f"Parent branch {current.merge_base} not found in stack."
        )

    if not yes:
        click.confirm(f"Fold [{current.letter}] into [{parent.letter}]?", abort=True)

    # Checkout parent and merge
    git.checkout(parent.branch)
    git.merge_ff_only(current.branch)

    # Retarget children of current to parent
    for entry in entries:
        if entry.merge_base == current.branch:
            git.set_branch_config(entry.branch, "gh-merge-base", parent.branch)

    # Remove entry and clean up
    stack.remove_entry(current.branch)
    stack.reindex_stack(current.stack_id)

    try:
        git.delete_branch(current.branch)
    except GitError:
        pass

    click.echo(f"{ui.success('Folded')} {ui.bracket_letter(current.letter)} into {ui.bracket_letter(parent.letter)}")


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------


@main.command()
@click.option("--onto", required=True, help="Letter of the branch to move onto")
def move(onto: str) -> None:
    """Move the current branch to be a child of another branch."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.get_stack(current.stack_id)
    target_index = stack.letter_to_index(onto)
    target = next((e for e in entries if e.index == target_index), None)
    if target is None:
        available = ", ".join(e.letter for e in entries)
        raise click.ClickException(
            f"Part [{onto}] not found in stack. Available: {available}"
        )

    if target.branch == current.branch:
        raise click.ClickException("Cannot move a branch onto itself.")

    # Check if target is a descendant of current (would create a cycle)
    check = target
    while check is not None:
        if check.merge_base == current.branch:
            raise click.ClickException(
                f"Cannot move [{current.letter}] onto [{onto}] — "
                f"[{onto}] is a descendant of [{current.letter}]."
            )
        check = next((e for e in entries if e.branch == check.merge_base), None)

    # Detach current from its current position:
    # retarget current's successor to current's old merge_base
    old_merge_base = current.merge_base
    for entry in entries:
        if entry.merge_base == current.branch:
            git.set_branch_config(entry.branch, "gh-merge-base", old_merge_base)
            entry.merge_base = old_merge_base

    # Reattach current as child of target
    current.merge_base = target.branch
    git.set_branch_config(current.branch, "gh-merge-base", target.branch)

    # Rebase current onto new parent
    try:
        git.rebase_onto(current.branch, target.branch, old_merge_base)
    except RebaseConflictError:
        click.echo(
            f"\n{ui.error('Conflict')} rebasing {ui.bracket_letter(current.letter)} onto {ui.bracket_letter(onto)}. "
            "Resolve conflicts, then:\n"
            "  git add <files>\n"
            "  git rebase --continue"
        )
        return

    # Reindex
    stack.reindex_stack(current.stack_id)

    click.echo(f"{ui.success('Moved')} {ui.bracket_letter(current.letter)} onto {ui.bracket_letter(onto)} ({target.branch})")


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
    lines = [f"{ui.header('Stack:')} {stack_id} ({count} part{'s' if count != 1 else ''})", ""]

    reversed_entries = list(reversed(entries))
    for i, entry in enumerate(reversed_entries):
        is_current = entry["branch"] == current_branch
        is_last = i == len(reversed_entries) - 1
        if is_current:
            symbol = ui.current_marker("●")
            marker = f"           {ui.current_label('<-- you are here')}"
        else:
            symbol = ui.dim("○")
            marker = ""
        ltr = entry["letter"]
        lines.append(f"  {symbol} {ui.bracket_letter(ltr)} {entry['branch']}{marker}")

        connector = ui.dim("│") if not is_last else " "

        # Line 1: PR number + title
        line1_parts: list[str] = []
        if entry.get("pr_number"):
            pr_label = ui.pr_number(f"PR #{entry['pr_number']}")
            if entry.get("is_draft"):
                pr_label += f" {ui.warning('(draft)')}"
            line1_parts.append(pr_label)
        if entry.get("title"):
            line1_parts.append(entry["title"])
        if line1_parts:
            lines.append(f"  {connector}     {' · '.join(line1_parts)}")

        # Line 2: CI status + review status + diff stat
        line2_parts: list[str] = []
        if entry.get("ci_rollup"):
            line2_parts.append(ui.format_ci_status(entry["ci_rollup"]))
        if entry.get("review_decision"):
            review_text = ui.format_review_status(entry["review_decision"])
            if review_text:
                line2_parts.append(review_text)
        if entry.get("diff_stat"):
            line2_parts.append(ui.dim(entry["diff_stat"]))
        if line2_parts:
            lines.append(f"  {connector}     {' · '.join(line2_parts)}")

        if not is_last:
            lines.append(f"  {ui.dim('│')}")

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
        pr_num = entry.pr_number
        is_draft = False
        title = None
        ci_rollup: list[dict] | None = None
        review_decision: str | None = None
        if pr_num:
            try:
                pr_data = github.pr_view(
                    pr_num, extra_fields=["reviewDecision", "statusCheckRollup"]
                )
                is_draft = pr_data.get("isDraft", False)
                title = pr_data.get("title")
                ci_rollup = pr_data.get("statusCheckRollup")
                review_decision = pr_data.get("reviewDecision")
            except GhError:
                pass

        view_entries.append({
            "branch": entry.branch,
            "letter": entry.letter,
            "pr_number": pr_num,
            "is_draft": is_draft,
            "title": title,
            "ci_rollup": ci_rollup,
            "review_decision": review_decision,
            "diff_stat": _get_diff_stat(entry.merge_base, entry.branch),
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
        click.echo(f"  {ui.bracket_letter(letter)} {branch} {ui.dim(f'<- {merge_base}')}")

    click.echo(f"\n{ui.success('Adopted')} {len(branches)} branches into stack {ui.header(stack_id)}")


# ---------------------------------------------------------------------------
# restack
# ---------------------------------------------------------------------------


@main.command()
def restack() -> None:
    """Rebase all descendants of the current branch."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    entries = stack.get_stack(current.stack_id)
    original_branch = current.branch
    to_rebase = [e for e in entries if e.index > current.index]
    if not to_rebase:
        click.echo("Nothing to restack.")
        return

    _rebase_entries(to_rebase, resume_command="spectrum restack", original_branch=original_branch)

    try:
        git.checkout(original_branch)
    except GitError:
        pass


# ---------------------------------------------------------------------------
# squash
# ---------------------------------------------------------------------------


@main.command()
@click.option("--message", "-m", default=None, help="Commit message for squashed commit")
def squash(message: str | None) -> None:
    """Squash all commits in the current branch into one."""
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    subjects = git.log_subjects(current.merge_base, current.branch)
    if not subjects:
        raise click.ClickException("No commits to squash.")
    if len(subjects) == 1:
        raise click.ClickException("Only 1 commit — nothing to squash.")

    commit_message = message or subjects[0]

    git.reset_soft(current.merge_base)
    git.commit(commit_message)

    click.echo(f"{ui.success('Squashed')} {len(subjects)} commits into: {commit_message}")

    # Restack descendants
    entries = stack.get_stack(current.stack_id)
    to_rebase = [e for e in entries if e.index > current.index]
    if to_rebase:
        _rebase_entries(to_rebase, resume_command="spectrum restack", original_branch=current.branch)


# ---------------------------------------------------------------------------
# completion
# ---------------------------------------------------------------------------


@main.command(hidden=True)
@click.argument("shell", type=click.Choice(["bash", "zsh", "fish"]))
def completion(shell: str) -> None:
    """Print shell completion activation script."""
    click.echo(f'eval "$(_SPECTRUM_COMPLETE={shell}_source spectrum)"')


# ---------------------------------------------------------------------------
# wip
# ---------------------------------------------------------------------------


@main.command()
@click.argument("state", required=False, default=None, type=click.Choice(["on", "off"]))
def wip(state: str | None) -> None:
    """Toggle WIP status for the current branch.

    WIP branches are skipped during submit (no push, no PR creation).
    """
    current = stack.current_entry()
    if current is None:
        raise click.ClickException(
            "Not on a spectrum branch. Use 'spectrum create' first."
        )

    if state is None:
        # Toggle
        new_wip = not current.wip
    else:
        new_wip = state == "on"

    if new_wip:
        git.set_branch_config(current.branch, "spectrum-wip", "true")
        click.echo(f"{ui.bracket_letter(current.letter)} marked as {ui.warning('WIP')}")
    else:
        git.unset_branch_config(current.branch, "spectrum-wip")
        click.echo(f"{ui.bracket_letter(current.letter)} no longer WIP")


# ---------------------------------------------------------------------------
# continue / abort
# ---------------------------------------------------------------------------


def _rebuild_entries_from_state(op: OperationState) -> list[stack.StackEntry]:
    """Rebuild StackEntry list from saved operation state."""
    entries = []
    for i, branch in enumerate(op.remaining_branches):
        entries.append(stack.StackEntry(
            branch=branch,
            index=op.remaining_indices[i],
            stack_id=op.remaining_stack_ids[i],
            merge_base=op.remaining_merge_bases[i],
        ))
    return entries


@main.command("continue")
def continue_cmd() -> None:
    """Continue a rebase after resolving conflicts."""
    op = OperationState.load()
    if op is None:
        raise click.ClickException("No operation in progress.")

    # Continue the interrupted rebase
    try:
        git.rebase_continue()
    except RebaseConflictError:
        raise click.ClickException(
            "Rebase still has conflicts. Resolve them first:\n"
            "  git add <files>\n"
            "  spectrum continue"
        ) from None

    click.echo(ui.success("Rebase continued."))

    # Resume rebasing remaining entries (skip the first one — it was the conflicting one)
    remaining = _rebuild_entries_from_state(op)
    if len(remaining) > 1:
        to_rebase = remaining[1:]
        resolve_onto = None
        if op.resolve_onto_master:
            resolve_onto = lambda mb: "origin/master" if mb == "master" else mb
        _rebase_entries(
            to_rebase,
            resolve_onto=resolve_onto,
            resume_command=op.command,
            original_branch=op.original_branch,
        )

    # Clear state
    OperationState.clear()

    # Return to original branch
    try:
        git.checkout(op.original_branch)
    except GitError:
        pass

    click.echo(ui.success("Done."))


@main.command()
def abort() -> None:
    """Abort a rebase in progress."""
    op = OperationState.load()
    if op is None:
        raise click.ClickException("No operation in progress.")

    git.rebase_abort()

    OperationState.clear()

    try:
        git.checkout(op.original_branch)
    except GitError:
        pass

    click.echo(ui.warning("Operation aborted."))
