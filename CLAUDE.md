# CLAUDE.md — Spectrum

## What this is

Spectrum is a Python CLI tool that manages stacked PRs on GitHub. It orchestrates `git` and `gh` subprocess calls — no GitHub API tokens or library dependencies beyond Click.

## Project structure

```
spectrum/
├── pyproject.toml
├── src/spectrum/
│   ├── cli.py          # Click command group (AliasGroup), all 23 commands
│   ├── git.py          # Git subprocess wrapper (branch, config, rebase, push)
│   ├── github.py       # gh CLI wrapper (PR create/edit/view/merge)
│   ├── opstate.py      # Operation state persistence for continue/abort
│   ├── pr_metadata.py  # Sentinel-based PR body metadata management
│   ├── stack.py        # Stack state model, git config read/write, reconstruction
│   └── undo.py         # Undo snapshot save/restore for destructive commands
└── tests/
    ├── test_absorb_command.py
    ├── test_cli.py
    ├── test_completion_command.py
    ├── test_continue_abort.py
    ├── test_fold_command.py
    ├── test_land_command.py
    ├── test_move_command.py
    ├── test_opstate.py
    ├── test_pr_command.py
    ├── test_pr_metadata.py
    ├── test_rename_command.py
    ├── test_split_command.py
    ├── test_squash_command.py
    ├── test_stack.py
    ├── test_title_command.py
    ├── test_undo_command.py
    └── test_wip_command.py
```

## Key concepts

**Stack state** is stored in git branch config keys (`spectrum-stack`, `spectrum-index`, `spectrum-pr`, `gh-merge-base`, `spectrum-wip`, `spectrum-title`). Operation state for `continue`/`abort` is saved to `.git/spectrum-state.json`. Undo snapshots are saved to `.git/spectrum-undo.json`.

**Branch naming**: Base branch names get `/a`, `/b`, `/c` appended. The ticket ID (e.g. `msg-3391`) is extracted from the branch name via regex and used as the stack identifier.

**PR metadata** is injected into PR bodies between `<!-- SPECTRUM:START -->` and `<!-- SPECTRUM:END -->` HTML comment sentinels. Everything outside the sentinels is user content and never modified.

## Architecture decisions

- **All external operations go through subprocess** — `git.py` wraps git, `github.py` wraps gh. No Python git libraries.
- **`stack.py` is pure logic** (aside from calling `git.py` for config reads/writes). Stack reconstruction scans all local branches for matching `spectrum-stack` config values.
- **`cli.py` is the only module with Click decorators**. Commands catch `GitError`/`GhError` and convert to `click.ClickException`.
- **`pr_metadata.py` is fully pure** — string in, string out. No I/O.

## Running tests

```bash
cd spectrum
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest
pytest -v
```

Tests mock `git` and `github` modules. CLI tests use Click's `CliRunner`. No real git repos or network calls in the test suite.

## Error handling conventions

- **Auto-recover when possible**: Handle recoverable subprocess errors automatically with user-visible feedback. For example, `push_force_with_lease` auto-retries on "stale info" / "rejected" errors by fetching and retrying, and accepts an `on_retry` callback for user feedback.
- **Errors should be useful, following the spirit of Rust**: Error messages must tell the user *what* went wrong, *why*, and *what to do about it*. Include context (branch name, command that failed, relevant state). Prefer actionable messages like `"Rebase conflict on branch foo/a onto master. Resolve conflicts, then run: sp continue"` over generic ones like `"Rebase failed"`. When wrapping subprocess errors, preserve the underlying stderr but add Spectrum-level context.
- **Confirm destructive operations**: Any command that rewrites history, deletes branches, or makes hard-to-reverse changes must prompt the user for confirmation before proceeding. Show what will happen (e.g., branches affected, commits being rewritten) so the user can make an informed decision. Use `click.confirm()` with `abort=True`.
- **Help messages should be maximally helpful**: Command help strings (`@click.command(help=...)`) should explain what the command does, when to use it, and include usage examples. Use `click.echo()` for contextual guidance during execution (e.g., "Hint: run `sp restack` to propagate changes").

## Common tasks

### Adding a new command

1. Add the Click command in `cli.py` under the `main` group
2. Use `stack.current_stack()` or `stack.current_entry()` to get stack context
3. Wrap git/github calls in try/except, convert to `click.ClickException`

### Changing state model

Stack state keys are read/written in `stack.py` (`read_entry`, `write_entry`). The `gh-merge-base` key is special — `gh pr create` reads it natively to determine the PR base branch.

### Modifying PR metadata format

Edit `pr_metadata.build_stack_table()`. The sentinel comments must remain exactly `<!-- SPECTRUM:START -->` and `<!-- SPECTRUM:END -->` for update logic to work.

## Dependencies

Single runtime dependency: **Click >=8.0**. Tests use **pytest**.
