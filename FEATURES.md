# Spectrum Feature Catalog

18 potential features for Spectrum, organized by category. Each feature includes a description, motivation, prior art from competing tools, design notes for Spectrum's architecture, and a complexity estimate.

Spectrum's current commands: `create`, `add`, `status`, `switch`, `next`, `prev`, `top`, `bottom`, `submit`, `sync`, `drop`, `adopt`, `log`, `pr`, `title`, `land`, `rename`, `fold`, `move`, `squash`, `wip`, `continue`, `abort`, `completion`.

---

## Navigation & Visualization

### 1. `log` / `tree` — DAG/tree view of the stack ✅

**What it does.** Prints a visual representation of the stack in the terminal, showing branches, their parent relationships, commit counts, and PR status in a tree or DAG layout. More informative than `status` — it shows the shape of the dependency graph, not just a flat list.

**Why it's useful.** `status` shows a linear list of parts with PR numbers. As stacks grow or users work on multiple stacks, a tree view makes it immediately clear which branches depend on which, where PRs are open, and which parts have uncommitted or unpushed changes. This is especially valuable after `sync` or `drop` operations that change the graph shape.

**How it works in other tools.**
- **Graphite** (`gt log`): Shows a richly formatted tree with branch names, PR numbers, commit counts, and color-coded status (needs restack, behind trunk, etc.). Supports `--short` and `--long` modes.
- **git-branchless** (`git smartlog`): Full DAG view with commit hashes, branch pointers, and merge-base annotations. Shows the "interesting" subset of the commit graph.
- **git-town** (`git town status`): Shows a branch hierarchy with sync status indicators.

**Spectrum design notes.** Build entirely from existing primitives: `stack.get_stack()` for entries, `git.diff_shortstat()` for change counts, `git.log_subjects()` for commit counts, and `entry.pr_number` for PR status. The rendering is pure string formatting — no external dependencies needed. For multi-stack views, scan all branches via `git.all_local_branches()` and group by `stack_id`. Output format could be a simple indented tree with Unicode box-drawing characters (`│`, `├──`, `└──`).

**Complexity:** Low

---

### 2. `top` / `bottom` — Jump to first or last part of the stack ✅

**What it does.** `spectrum top` checks out the last (highest-index) branch in the current stack. `spectrum bottom` checks out the first (index 0) branch. Quick navigation without needing to know the letter.

**Why it's useful.** After reviewing a stack or running `sync`, you often want to jump to either end. Currently you need `spectrum status` to see which letter is first/last, then `spectrum switch <letter>`. These commands save that round-trip and are especially useful in long stacks.

**How it works in other tools.**
- **Graphite** (`gt top`, `gt bottom`): Direct equivalents — jump to tip or base of the current stack.
- **git-town**: No direct equivalent; uses `git town switch` with interactive selection.
- **spr**: Not applicable (single-branch model).

**Spectrum design notes.** Trivial to implement. `current_stack()` returns entries sorted by index. `top` checks out `entries[-1].branch`, `bottom` checks out `entries[0].branch`. Two nearly identical Click commands, each under 15 lines. Could also be added as aliases of `switch` (e.g., `spectrum switch top`).

**Complexity:** Low

---

### 2.5. Dependent stacks — Build a stack on top of another stack's branch ✅

**What it does.** `spectrum create <branch> --on <other-branch>` starts a new stack from an arbitrary branch instead of `origin/master`. When the dependency branch's PR merges, `spectrum sync` detects it and retargets the dependent stack's PRs to master automatically.

**Why it's useful.** Related tickets often form a dependency chain — stack 2 builds on stack 1's last branch. Without this, you'd manually manage cross-stack base branches and retarget PRs when dependencies land.

**Spectrum design notes.** The `--on` flag sets both the git start point and `merge_base` in the stack entry. A new `_is_cross_stack_base_merged()` helper checks whether a merge base belongs to another stack whose PR has been merged (via `stack.read_entry` then `github.pr_view`, with fallback to `github.pr_view_by_branch`). The retargeting logic in `sync` reuses the shared `_retarget_to_master()` helper. No auto-cascade restack across stacks — the user runs `restack` manually on each dependent stack.

**Complexity:** Medium

---

## Stack Manipulation

### 3. `restack` — Rebase children after local edits mid-stack ✅

**What it does.** After amending or adding commits to a branch in the middle of the stack, `restack` rebases all descendant branches so they incorporate the changes. Unlike `sync` (which fetches from remote and handles merges), `restack` is purely local — it fixes up the stack after local edits.

**Why it's useful.** The most common pain point with stacked PRs: you edit part [b] based on code review feedback, and now [c] and [d] are based on the old [b]. Without `restack`, you manually rebase each subsequent branch. This is error-prone and tedious.

**How it works in other tools.**
- **Graphite** (`gt restack`): Automatically detects which branches need rebasing by comparing merge-bases, then rebases them in topological order. Handles conflicts by pausing and prompting.
- **git-branchless** (`git restack`): Uses its event log to detect branches that need rebasing. Fully automatic.
- **git-town** (`git town sync`): Combines fetch + restack into one operation.

**Spectrum design notes.** Similar to the rebase loop in `sync`, but without the fetch/merge-detection steps. For each entry from the current position onward: compute the expected merge-base, compare with actual `git merge-base`, and rebase if they differ. Use `git.rebase_onto(entry.branch, entry.merge_base, old_base)` where `old_base` is the pre-edit fork point. Handle `RebaseConflictError` by printing conflict instructions and stopping. Could share the rebase loop with `sync` via a helper function.

**Complexity:** Medium

---

### 4. `reorder` — Swap position of branches within a stack

**What it does.** Changes the order of branches in the stack. For example, swapping [b] and [c] so that [c]'s changes come before [b]'s. After reordering, rebases the affected branches so the commit history reflects the new order.

**Why it's useful.** During development, you sometimes realize that a later part should land first (e.g., a refactor that the earlier part depends on). Reordering avoids the manual dance of cherry-picking, rebasing, and updating config.

**How it works in other tools.**
- **Graphite** (`gt reorder`): Interactive reorder with arrow keys. Rebases automatically after reordering.
- **git-branchless** (`git restack` after manual `git branch -f` moves): No dedicated reorder command, but the restack engine handles arbitrary reparenting.
- **spr**: Not applicable (single-branch model with individual commits as PRs).

**Spectrum design notes.** Accept two letters to swap: `spectrum reorder b c`. Steps: (1) swap `spectrum-index` values in git config, (2) update `gh-merge-base` pointers — the successor of the swapped entries needs its merge-base updated, (3) rebase affected branches. Reuse the rebase logic from `restack`. Need to handle the case where the two entries aren't adjacent — this requires rebasing the entire range. Consider also supporting `spectrum reorder b --before d` syntax for moving a single entry.

**Complexity:** High

---

### 5. `split` — Split a branch into two parts

**What it does.** Takes the current branch and splits it into two consecutive stack parts. The user selects which commits (or hunks) go into each part. The original branch keeps the first set of changes; a new branch is created for the second set.

**Why it's useful.** PRs that grow too large during development need to be broken up for reviewability. Manually splitting requires creating a new branch, cherry-picking commits, and updating the stack — `split` automates this.

**How it works in other tools.**
- **Graphite** (`gt split`): Interactive commit selection. Supports splitting by commit boundaries or by file.
- **ghstack**: No split support.
- **git-branchless** (`git split`): Supports splitting at commit boundaries within a branch.

**Spectrum design notes.** Two modes: (1) **commit-boundary split** — user specifies a commit SHA or offset, all commits before it stay, all after go to the new branch. Implemented via `git rebase --onto` to transplant the later commits. (2) **interactive split** — launch `git rebase -i` with editor instructions, but this conflicts with Spectrum's non-interactive subprocess model. Recommend starting with commit-boundary split only. After splitting: create a new `StackEntry`, bump indices for all subsequent entries via `reindex_stack`, update merge-bases, and rebase descendants.

**Complexity:** High

---

### 6. `fold` — Merge a branch into its parent ✅

**What it does.** Combines the current branch's commits into its parent branch, then removes the current branch from the stack. The inverse of `split`. Children of the folded branch are retargeted to the parent.

**Why it's useful.** Sometimes a stack part turns out to be too small to justify its own PR, or code review reveals that two parts should be one. Currently you'd need to cherry-pick commits, update config, and run `drop`.

**How it works in other tools.**
- **Graphite** (`gt fold`): Folds current branch into parent. Rebases children onto the updated parent.
- **git-town** (`git town compress`): Similar — squashes a branch's commits into its parent.
- **spr**: Not applicable.

**Spectrum design notes.** Steps: (1) identify parent via `entry.merge_base`, (2) rebase current branch's commits onto parent using `git rebase --onto parent parent current` (which is effectively a fast-forward merge of the commits), (3) move parent's branch pointer to the tip of the combined commits via `git branch -f parent HEAD`, (4) retarget any children of the current branch to the parent (update `gh-merge-base`), (5) call `stack.remove_entry()` and `reindex_stack()`. The tricky part is step 2-3 — need to ensure the parent branch pointer advances correctly. Use `git.checkout(parent_branch)` then `git merge --ff-only current_branch`.

**Complexity:** Medium

---

### 7. `move` / `reparent` — Change a branch's parent ✅

**What it does.** Changes which branch the current part is based on. For example, moving [c] from being based on [b] to being based on [a] instead. Rebases [c]'s commits onto the new parent.

**Why it's useful.** Stack structure sometimes needs adjustment as the design evolves. A branch that was created as a child of [b] might actually only depend on [a]. Reparenting produces cleaner, more reviewable PRs with smaller diffs.

**How it works in other tools.**
- **Graphite** (`gt move`): Moves a branch to a new parent. Supports `--onto` flag.
- **git-branchless** (`git move -s <branch> -d <new-parent>`): Full DAG manipulation with automatic rebasing.
- **git-town** (`git town set-parent`): Changes parent without rebasing; rebasing happens on next sync.

**Spectrum design notes.** Accept a target parent: `spectrum move --onto <letter>`. Steps: (1) resolve target parent from stack entries, (2) compute `old_base` for the rebase, (3) `git.rebase_onto(current_branch, new_parent_branch, old_base)`, (4) update `gh-merge-base` in git config, (5) if the branch has a PR, call `github.pr_edit_base()` to update the PR's base. Straightforward reuse of existing `rebase_onto` and config primitives.

**Complexity:** Medium

---

### 8. `squash` — Squash all commits within a branch into one ✅

**What it does.** Replaces all commits in the current branch (relative to its merge base) with a single commit. The commit message can be edited or auto-generated from the branch's PR title.

**Why it's useful.** Before landing or after many fixup commits during review, squashing produces a clean single-commit history per stack part. Some teams require squash-before-merge as policy.

**How it works in other tools.**
- **Graphite**: Auto-squashes on merge via GitHub's squash-merge setting.
- **spr**: Each PR is always a single commit by design.
- **git-town** (`git town compress`): Squashes all commits in a branch into one.

**Spectrum design notes.** Use `git reset --soft <merge_base>` followed by `git commit` with the squashed message. Alternatively, `git rebase -i` with all picks replaced by squash — but that's interactive. The `reset --soft` approach is simpler and subprocess-friendly. Steps: (1) get current entry's merge-base, (2) `git reset --soft <merge_base>`, (3) `git commit -m <message>`. Need to handle the case where there's only one commit (no-op). After squashing, descendants need rebasing since the commit SHAs changed — recommend running `restack` automatically.

**Complexity:** Low

---

## PR & Merge Management

### 9. `land` / `merge` — Merge bottom PR(s) from CLI + auto-sync ✅

**What it does.** Merges the bottom-most (or a specified) PR in the stack via the GitHub API, then automatically runs the equivalent of `sync` to retarget remaining PRs and rebase the stack.

**Why it's useful.** Currently, merging a stacked PR requires: (1) merge via GitHub UI, (2) run `spectrum sync` to detect the merge and retarget. `land` combines these into one command, reducing context-switching and ensuring the stack is immediately updated.

**How it works in other tools.**
- **Graphite** (`gt merge`): Merges the bottom PR and auto-restacks. Supports `--squash`, `--merge`, `--rebase` strategies.
- **spr** (`spr land`): Merges the bottom commit's PR, then rebases the stack.
- **ghstack**: Lands PRs individually, updating the internal stack state.
- **Aviator**: Automates merge queues with CI validation.

**Spectrum design notes.** Use `gh pr merge <number> --squash` (or `--merge`/`--rebase` based on a flag) via a new `github.pr_merge()` function. After merging: (1) retarget the next entry's merge-base to `master`, (2) update the PR's base via `github.pr_edit_base()`, (3) remove the merged entry with `stack.remove_entry()`, (4) fetch origin/master and rebase remaining branches (reuse `sync` logic). Should require the PR's CI checks to be passing — check via `gh pr checks`.

**Complexity:** Medium

---

### 10. Open PR in browser — `spectrum pr` ✅

**What it does.** Opens the current branch's PR in the default web browser. If no PR exists yet, shows an error suggesting `spectrum submit` first.

**Why it's useful.** Quick access to PR review pages without hunting for URLs. Especially useful after `submit` when you want to add reviewers, check CI, or review the diff on GitHub.

**How it works in other tools.**
- **Graphite** (`gt pr`): Opens the PR in the browser.
- **gh CLI** (`gh pr view --web`): Opens PR for current branch in browser.
- **git-town** (`git town repo`): Opens the repo page (not PR-specific).

**Spectrum design notes.** Get the current entry via `stack.current_entry()`, read `entry.pr_number`, construct the URL from `github.get_repo_url()`, and open with `click.launch(url)` (Click has built-in browser-open support). Alternatively, delegate to `gh pr view --web` via subprocess. The `gh` approach is simpler and handles edge cases (SSH remotes, enterprise GitHub). Entire command is ~10 lines.

**Complexity:** Low

---

### 11. PR title editing — Edit PR titles from CLI ✅

**What it does.** Updates the PR title for the current branch (or a specified part) without leaving the terminal. Also updates the `spectrum-title` git config key so future `submit` calls use the new title.

**Why it's useful.** PR titles often need tweaking after creation — fixing typos, updating to match the final implementation, or conforming to team conventions. Currently requires visiting GitHub or using `gh pr edit` manually.

**How it works in other tools.**
- **Graphite** (`gt edit`): Edit PR title and description from CLI.
- **gh CLI** (`gh pr edit --title`): Direct title editing.
- **spr**: Titles are derived from commit messages; editing commits updates titles.

**Spectrum design notes.** Add `spectrum title [--part LETTER] "New title"`. Steps: (1) resolve the target entry, (2) store in `spectrum-title` git config via `git.set_branch_config()`, (3) if a PR exists, format the full title via `stack.format_pr_title()` and update via a new `github.pr_edit_title()` function (a simple `gh pr edit --title` wrapper). Could also support interactive editing by launching `$EDITOR` if no title argument is provided.

**Complexity:** Low

---

### 12. WIP/skip support — Mark branches to skip during PR creation ✅

**What it does.** Marks a branch as "work in progress" so that `submit` skips it when creating PRs. The branch still exists in the stack and can be developed on, but PRs are only created for non-WIP parts.

**Why it's useful.** When building a stack incrementally, you might have placeholder branches or work-in-progress parts that aren't ready for review. Currently `submit` creates PRs for all branches, leading to premature PRs that clutter the review queue.

**How it works in other tools.**
- **Graphite**: Supports `--draft` per branch. No explicit skip — uses GitHub draft PRs instead.
- **spr**: Commits can be marked with `wip:` prefix to skip PR creation.
- **git-town**: No explicit WIP support.

**Spectrum design notes.** Add a `spectrum-wip` git config key per branch. Set via `spectrum wip [on|off]`. In `submit`, skip entries where `git.get_branch_config(branch, "spectrum-wip")` is truthy. Show WIP status in `status` output with a `[WIP]` marker. The `submit` command already iterates entries and checks `entry.pr_number` — adding a WIP check is a one-line conditional. Could also support `--include-wip` flag on `submit` to override.

**Complexity:** Low

---

## Safety & Recovery

### 13. `undo` — Undo last spectrum command

**What it does.** Reverts the effects of the most recent spectrum command. Restores branch positions, git config state, and checked-out branch to their pre-command state.

**Why it's useful.** Stacked-PR operations are inherently risky — a bad rebase, accidental drop, or wrong reorder can leave the stack in a broken state. `undo` provides a safety net that encourages experimentation.

**How it works in other tools.**
- **Graphite** (`gt undo`): Full undo of the last operation. Maintains a log of operations.
- **git-branchless** (`git undo`): Uses an event log and reference log to undo arbitrary operations. Very sophisticated.
- **git-town** (`git town undo`): Undoes the last git-town command using a recorded operation log.

**Spectrum design notes.** This is the most architecturally significant feature. Requires an **operation log** — before each command, snapshot: (1) all branch HEAs via `git rev-parse`, (2) all spectrum git config keys, (3) current branch. Store as JSON in `.git/spectrum-undo.json` (single-level undo) or `.git/spectrum-undo/` directory (multi-level). On `undo`: (1) restore branch tips via `git branch -f <branch> <sha>`, (2) restore config keys, (3) checkout original branch. Does NOT undo remote operations (pushed branches, created PRs) — those require separate reversal. Start with single-level undo and expand later.

**Complexity:** High

---

### 14. `continue` / `abort` — Resume or cancel after rebase conflicts ✅

**What it does.** After a `sync` or `restack` stops due to a rebase conflict, `spectrum continue` resumes the operation from where it left off (after the user resolves conflicts). `spectrum abort` cancels the in-progress operation and restores the previous state.

**Why it's useful.** Currently, after a conflict during `sync`, the user must manually `git rebase --continue` then re-run `spectrum sync` — but `sync` re-fetches and re-checks merges, which is wasteful and can produce different results. `continue` picks up exactly where the operation paused. `abort` provides a clean escape hatch.

**How it works in other tools.**
- **Graphite** (`gt continue`, `gt abort`): Resume or cancel after conflicts. Graphite tracks the interrupted operation state.
- **git-branchless** (`git restack --continue`): Continues restacking after conflict resolution.
- **git-town** (`git town continue`, `git town abort`): Full resume/cancel support with operation state tracking.

**Spectrum design notes.** Requires **operation state persistence**. When `sync` or `restack` hits a conflict, save state to `.git/spectrum-state.json`: the command name, the list of entries remaining to rebase, the current entry index, and pre-rebase SHAs. `continue`: (1) read state file, (2) run `git rebase --continue`, (3) resume the rebase loop from the saved position. `abort`: (1) run `git rebase --abort`, (2) optionally restore branch tips from saved SHAs, (3) delete state file. The conflict-handling path in `sync` already prints manual instructions — replace those with a state save and a "run `spectrum continue`" message.

**Complexity:** Medium

---

## Advanced

### 15. `absorb` — Auto-distribute staged hunks to correct branch in stack

**What it does.** Takes currently staged changes and automatically distributes each hunk to the correct branch in the stack based on which branch last modified those lines. Like `git absorb` but stack-aware.

**Why it's useful.** After code review, you often have fixes that apply to different parts of the stack. Manually switching branches, applying patches, and committing is tedious. `absorb` does this automatically — stage your fixes, run `spectrum absorb`, and each hunk lands on the right branch.

**How it works in other tools.**
- **Graphite**: No built-in absorb.
- **git-branchless** (`git absorb`): Uses `git blame` to determine which commit should absorb each hunk, then creates fixup commits and auto-squashes.
- **git absorb** (standalone tool): Same approach — blame-based hunk distribution.

**Spectrum design notes.** This is the most technically complex feature. Algorithm: (1) get staged diff hunks via `git diff --cached`, (2) for each hunk, run `git blame` on the affected lines to find the originating commit, (3) map commits to stack branches, (4) for each branch, apply its hunks as fixup commits, (5) run `restack` to propagate changes. The blame-to-branch mapping uses `git log --format=%H <merge_base>..<branch>` to determine which commits belong to which entry. Consider depending on the `git-absorb` binary as an optional dependency rather than reimplementing the hunk-distribution algorithm.

**Complexity:** High

---

### 16. `rename` — Rename current part's branch ✅

**What it does.** Renames the current branch (both locally and on the remote) while preserving all stack state — config keys, merge-base pointers in child entries, and PR associations.

**Why it's useful.** Branch names are sometimes wrong (typos, wrong ticket ID) or need updating to match changed scope. Git's `git branch -m` doesn't update spectrum config keys or child references.

**How it works in other tools.**
- **Graphite** (`gt rename`): Renames the branch and updates all internal state.
- **git-town** (`git town rename`): Renames branch, updates parent/child relationships, pushes the new name.
- **spr**: Not applicable (branches are auto-generated).

**Spectrum design notes.** Steps: (1) `git branch -m <old> <new>` to rename locally, (2) rewrite all spectrum git config keys — git config keys include the branch name (e.g., `branch.<name>.spectrum-stack`), so renaming the branch automatically moves the config section, (3) update any child entries whose `merge_base` points to the old name via `git.set_branch_config(child, "gh-merge-base", new_name)`, (4) push the new branch and delete the old remote branch: `git push origin <new>:refs/heads/<new> :<old>`, (5) if a PR exists, the head ref is already updated by the remote rename. Verify that `git branch -m` preserves the `branch.<name>.*` config section (it does in modern git).

**Complexity:** Medium

---

## DX & Ergonomics

### 17. Shell completions — Tab completion for commands and arguments ✅

**What it does.** Provides tab-completion for spectrum commands, subcommands, and arguments (like part letters in `switch`, branch names in `adopt`) in bash, zsh, and fish shells.

**Why it's useful.** Reduces typos and speeds up CLI usage. Especially valuable for `switch` (completing part letters), `drop` (completing part letters), and `adopt` (completing branch names). Professional CLI tools are expected to have shell completions.

**How it works in other tools.**
- **Graphite**: Ships zsh/bash/fish completions.
- **gh CLI**: Uses Cobra's built-in completion generation.
- **git-town**: Auto-generates completions via Cobra.

**Spectrum design notes.** Click has **built-in shell completion support** since Click 8.0. Enable by setting the `_SPECTRUM_COMPLETE` environment variable. Click auto-generates completions for commands and options. For dynamic completions (part letters, branch names), use Click's `shell_complete` parameter on arguments: e.g., `@click.argument("part", shell_complete=complete_part_letters)` where the callback returns current stack letters. Add an `install-completions` command that prints the shell-specific activation script. This is almost entirely Click framework functionality.

**Complexity:** Low

---

### 18. Offline mode — Queue operations when no network available

**What it does.** Detects when network is unavailable and queues remote operations (push, PR create/edit, fetch) for later execution. Local operations (rebase, switch, add) continue working. A `spectrum flush` command replays queued operations when connectivity returns.

**Why it's useful.** Developers on planes, trains, or unreliable connections can continue working with their stack. The most disruptive failure mode today is `submit` failing mid-way through — some PRs created, some not, metadata partially updated.

**How it works in other tools.**
- **Graphite**: No offline mode (requires server connection for most operations).
- **git-town**: No offline mode, but local operations work without network.
- **spr**: No offline mode.
- **Jujutsu (jj)**: Fully offline-first; syncing is an explicit operation.

**Spectrum design notes.** Add an operation queue in `.git/spectrum-queue.json` — a list of `{operation, args}` objects. When a `github.*` or `git.push*` call raises a network error, catch it and append to the queue instead of failing. `spectrum flush`: replay the queue in order, removing each operation on success. The main challenge is idempotency — `pr_create` is not idempotent (would create duplicate PRs). Solutions: (1) check if a PR already exists for the branch before creating, (2) store "intent" rather than raw API calls (e.g., "ensure PR exists for branch X" rather than "create PR"). Start with a simpler approach: make `submit` transactional — all-or-nothing, with clear error messages about what succeeded.

**Complexity:** High

---

## Priority Roadmap

Features ordered by value to the stacked-PR workflow. Priority considers how often the need arises, how painful the workaround is, and how much effort it takes to build.

### Tier 1 — Build first (daily pain, high value/effort ratio)

| Priority | Feature | Category | Complexity | Why |
|----------|---------|----------|------------|-----|
| 1 | Open PR in browser (#10) | PR & Merge | Low | ~10 lines, used constantly |
| 2 | `log` / `tree` (#1) | Navigation | Low | Richer than `status`, makes the stack legible |
| 3 | `restack` (#3) | Stack Manipulation | Medium | Core missing piece — every mid-stack edit needs this |
| 4 | `continue` / `abort` (#14) | Safety & Recovery | Medium | Direct companion to `restack` and `sync`; without it, conflicts are manual |
| 5 | `land` / `merge` (#9) | PR & Merge | Medium | Closes the loop — merge + retarget in one command |
| 6 | `top` / `bottom` (#2) | Navigation | Low | Trivial, used dozens of times a day |

### Tier 2 — Meaningful workflow upgrades

| Priority | Feature | Category | Complexity | Why |
|----------|---------|----------|------------|-----|
| 7 | `fold` (#6) | Stack Manipulation | Medium | Common during review — "these two parts should be one" |
| 8 | `squash` (#8) | Stack Manipulation | Low | Clean history before landing, simple to build |
| 9 | PR title editing (#11) | PR & Merge | Low | Small friction, high frequency |
| 10 | `move` / `reparent` (#7) | Stack Manipulation | Medium | Stack structure evolves; painful without it |
| 11 | WIP/skip support (#12) | PR & Merge | Low | Prevents premature PRs in longer stacks |

### Tier 3 — Nice to have

| Priority | Feature | Category | Complexity | Why |
|----------|---------|----------|------------|-----|
| 12 | Shell completions (#17) | DX & Ergonomics | Low | Professional polish, Click makes it nearly free |
| 13 | `rename` (#16) | Advanced | Medium | Occasional need, not frequent |
| 14 | `reorder` (#4) | Stack Manipulation | High | Rare in practice — most stacks are built in order |
| 15 | `undo` (#13) | Safety & Recovery | High | High complexity; `git reflog` mostly covers this |

### Tier 4 — Low priority

| Priority | Feature | Category | Complexity | Why |
|----------|---------|----------|------------|-----|
| 16 | `split` (#5) | Stack Manipulation | High | Useful but rare; interactive nature is awkward |
| 17 | `absorb` (#15) | Advanced | High | Cool but niche — most review fixes hit one branch |
| 18 | Offline mode (#18) | DX & Ergonomics | High | Local ops already work; queuing adds complexity for an edge case |

### Suggested first batch

`Open PR in browser` + `log`/`tree` + `restack` + `continue`/`abort` + `top`/`bottom`. This covers the highest value-to-effort ratio and directly addresses the core workflow gaps.
