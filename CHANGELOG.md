# Changelog

## [Unreleased]

## [0.1.1] - 2026-03-05

### Fixed
- `pr_edit_title` now uses `gh api` REST calls instead of `gh pr edit --title`, which was failing due to GitHub's Projects Classic deprecation

### Added
- Colored terminal output: all CLI output uses color-coded styling (cyan for letters/PR numbers, green for success, red for errors, yellow for warnings, dim for secondary info). Centralized in `ui.py`.
- Grouped command help: `--help` organizes commands into 6 groups (Stack, Navigate, Publish, Edit, Info, Recovery) instead of a flat list
- Confirmation prompts on destructive commands: `drop`, `fold`, and `land` now prompt before executing. Use `--yes`/`-y` to skip.
- Richer `log` output: shows PR title, CI status (passing/failing/running), and review status (approved/changes requested) alongside the stack graph
- Diff stats in navigation: `switch`, `next`, `prev`, `top`, `bottom` show diff stats after switching branches
- Diff stats in `submit` summary: each entry in the post-submit summary includes diff stats
- `spectrum pr` (`o`): open current branch's PR in the browser via `gh pr view --web`
- `spectrum title <title>`: set PR title from the CLI; updates GitHub immediately if a PR exists
- `spectrum land [--method]`: merge the bottom PR (squash/merge/rebase), retarget the stack, and rebase remaining entries
- `spectrum squash [-m message]`: squash all commits in the current branch into one; auto-restacks descendants
- `spectrum fold`: merge the current branch into its parent and remove it from the stack
- `spectrum move --onto <letter>`: reparent the current branch under a different stack entry
- `spectrum rename <new-name>`: rename the current branch locally and on the remote, updating child references
- `spectrum wip [on|off]`: toggle WIP status; WIP branches are skipped during `submit`
- `spectrum continue`: resume a rebase after resolving conflicts (replaces manual `git rebase --continue` + re-run)
- `spectrum abort`: cancel an in-progress rebase and return to the original branch
- `spectrum completion bash|zsh|fish`: print shell completion activation script
- Operation state persistence (`opstate.py`): on rebase conflicts, state is saved to `.git/spectrum-state.json` for `continue`/`abort`
- `wip` field on `StackEntry`, stored in `spectrum-wip` git config key

### Changed
- `_rebase_entries` now accepts `original_branch` parameter instead of calling `git.current_branch()` during conflict (which fails in detached HEAD state)
- `write_entry` now persists the `wip` field to git config
- `remove_entry` now cleans up `spectrum-wip` config key
- `submit` skips WIP entries (no push, no PR creation)
- Conflict messages now instruct users to run `spectrum continue` / `spectrum abort` instead of manual git commands

### Previous
- `spectrum create --on <branch>`: start a stack from another branch instead of master, enabling dependent stacks
- `spectrum sync` cross-stack retargeting: when a dependency stack's PR merges, sync detects it and retargets PRs to master
- `spectrum restack`: rebase all descendants of the current branch (local only — no fetch, no push)
- Extracted shared retarget-to-master logic into `_retarget_to_master` helper
- Extracted shared rebase loop into `_rebase_entries` helper

### Previous
- `spectrum top` / `spectrum bottom`: jump to the last or first part of the stack
- `spectrum log` (`lg`): graphical stack view with Unicode tree, PR status, draft labels, and diff stats
- `spectrum create`: start a new stack from a branch name
- `spectrum add`: add a new part to the current stack
- `spectrum status` (`st`): show current stack state with PR URLs and diff stats
- `spectrum switch` (`sw`): switch to a part of the current stack by letter
- `spectrum next` / `spectrum prev`: navigate between adjacent stack parts
- `spectrum submit`: create or update PRs for all branches in the stack
- `spectrum sync`: fetch, detect merges, and rebase from current position
- `spectrum drop`: remove a part from the stack and relink neighbors
- `spectrum adopt`: import existing branches into a stack
