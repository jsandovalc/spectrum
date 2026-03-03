# Spectrum

Stacked PR tool for GitHub, built around `git` and `gh`.

Spectrum manages branch creation, cascading rebases, and PR lifecycle for stacked diffs. PR descriptions stay intact — spectrum appends navigational metadata (stack table) using HTML comment sentinels.

## Prerequisites

- `git`
- [`gh`](https://cli.github.com) (authenticated)

## Install

```bash
uv tool install git+https://github.com/canary-technologies/spectrum
# or
pipx install git+https://github.com/canary-technologies/spectrum
```

Both `spectrum` and `sp` are installed as entry points — use whichever you prefer.

For development:

```bash
git clone https://github.com/canary-technologies/spectrum
cd spectrum
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest
```

## Workflow

### 1. Start a stack

Copy the branch name from Linear and pass it to `create`:

```
$ spectrum create jonathansandoval/msg-3391-preserve-aggregator-response-kind
Fetching latest master...
Created stack msg-3391 on branch:
  [a] jonathansandoval/msg-3391-preserve-aggregator-response-kind/a
```

### 2. Make changes, then add more parts

```
# ... commit work on [a] ...

$ sp add
Created branch:
  [b] jonathansandoval/msg-3391-preserve-aggregator-response-kind/b (part 2 of 2)
```

### 3. Submit PRs

```
$ spectrum submit --draft
Pushing 2 branches...
  .../a -> origin (pushed)
  .../b -> origin (pushed)

Created PR #38550: MSG-3391 [a]: Preserve aggregator response kind
Created PR #38551: MSG-3391 [b]: Add migration scripts

Stack:
  #38550 [a] Preserve aggregator response kind  <- master  (draft)
  #38551 [b] Add migration scripts              <- [a]     (draft)
```

Each PR gets a stack navigation table appended to its body:

```markdown
<!-- SPECTRUM:START -->
---
> **Part 1 of 2** · `MSG-3391`
>
> | | PR | Title | Status |
> |---|---|---|---|
> | **1** | **#38550** | Preserve aggregator response kind | **Draft** |
> | 2 | [#38551](https://github.com/.../pull/38551) | Add migration scripts | Draft |
<!-- SPECTRUM:END -->
```

User-written content in the PR body is never touched.

### 4. Keep in sync

```
$ sp sync
Fetching origin/master...
Rebasing [a] onto origin/master... done
Rebasing [b] onto [a]... done

Pushed.
```

If [a]'s PR has been merged (squash-and-merge), `sync` detects it, retargets [b] to master, and rebases accordingly.

Sync rebases from your current position onward — on `[a]` it rebases the whole stack, on `[b]` it rebases `[b]+` only. Use `--no-push` to skip the push step.

### 5. Navigate and fix earlier parts

```
$ sp prev          # move to previous part
$ sp next          # move to next part
$ sp switch a      # or jump directly by letter
```

After amending an earlier part, use `restack` to cascade the rebase forward locally:

```
$ sp prev
# ... fix something, commit ...
$ sp restack
Rebasing [b] onto [a]... done
```

`restack` is purely local — no fetch, no push. Use `sync` when you also want to fetch `origin/master`, detect merged PRs, and push.

### 6. Drop a part

Remove a part from the stack. The chain is automatically re-linked:

```
$ sp drop b
Dropped [b] user/msg-3391-preserve-aggregator-response-kind/b
```

## Commands

| Command | Description |
|---------|-------------|
| `sp create <branch> [--on <branch>]` | Start a new stack (optionally based on another branch) |
| `sp add` | Add a new part to the current stack |
| `sp status` (`st`) | Show the current stack with diffstats |
| `sp switch <letter>` (`sw`) | Switch to a stack part (a, b, c, ...) |
| `sp next` | Move to the next part in the stack |
| `sp prev` | Move to the previous part in the stack |
| `sp top` | Jump to the last part of the stack |
| `sp bottom` | Jump to the first part of the stack |
| `sp submit [--draft] [-r reviewer]` | Push and create/update PRs for all parts |
| `sp sync [--no-push]` | Fetch, detect merges, rebase from current position |
| `sp restack` | Rebase descendants of the current branch (local only) |
| `sp drop [letter]` | Remove a part from the stack |
| `sp adopt <branch> [...]` | Import existing branches into a stack |
| `sp pr` (`o`) | Open current branch's PR in the browser |
| `sp title <title>` | Set the PR title for the current branch |
| `sp land [--method squash\|merge\|rebase]` | Merge the bottom PR and update the stack |
| `sp squash [-m message]` | Squash all commits in the current branch into one |
| `sp fold` | Merge the current branch into its parent |
| `sp move --onto <letter>` | Move the current branch to be a child of another branch |
| `sp rename <new-name>` | Rename the current branch (local + remote) |
| `sp wip [on\|off]` | Toggle WIP status (WIP branches are skipped during submit) |
| `sp continue` | Resume a rebase after resolving conflicts |
| `sp abort` | Abort a rebase in progress |

## Common flows

### Fix an earlier part (address PR feedback)

```
sp switch a            # go to the part that needs changes
# ... edit, commit ...
sp restack             # cascade rebase to [b], [c], ...
sp submit              # push and update PRs
```

### Start of day / before resuming work

```
sp sync                # fetch master, detect merges, rebase, push
```

### First PR merged, continue with the rest

```
sp sync                # detects [a] was merged, retargets [b] to master, rebases, pushes
```

### Add a part mid-stack

```
sp switch b            # go to where you want to insert after
sp add                 # creates [c] branching off [b]
# ... commit work on [c] ...
sp submit --draft
```

### Resolve a rebase conflict

```
sp restack             # or sp sync — stops at the conflict
# ... fix conflicts ...
git add <files>
sp continue            # resume from where it stopped
```

Or abort the operation entirely:

```
sp abort               # cancel the rebase and return to your branch
```

### Dependent stacks (stack on top of another stack)

```
sp create user/msg-200-bar --on user/msg-100-foo/c
# msg-200 stack starts from the tip of msg-100's last branch
sp add
sp submit --draft   # PRs target msg-100's branch, not master
```

When the dependency stack's PR merges, `sp sync` detects it and retargets your PRs to master automatically.

### Adopt existing branches into a stack

```
sp adopt user/msg-1-foo/a user/msg-1-foo/b user/msg-1-foo/c
sp submit --draft
```

### Land the bottom PR

```
sp land                # merges bottom PR via squash, retargets stack, rebases
```

Use `--method merge` or `--method rebase` for alternative merge strategies.

### Squash commits before landing

```
sp squash              # squashes all commits into one, using first commit's subject
sp squash -m "Clean implementation"   # custom message
```

### Fold a branch into its parent

```
sp switch b
sp fold                # merges [b] into [a], removes [b] from stack
```

### Move a branch to a different parent

```
sp move --onto a       # move current branch to be a child of [a]
```

### Mark a branch as WIP

```
sp wip                 # toggle WIP on current branch
sp wip on              # or explicitly set
sp submit              # WIP branches are skipped
```

### Rename a branch

```
sp rename user/msg-3391-better-name/a   # renames local + remote
```

## Branch naming

Spectrum appends `/a`, `/b`, `/c` to the Linear branch name:

```
jonathansandoval/msg-3391-preserve-aggregator-response-kind/a
jonathansandoval/msg-3391-preserve-aggregator-response-kind/b
```

PR titles follow the convention: `MSG-3391 [a]: Preserve aggregator response kind`

## State model

Stack state lives in git branch config (local `.git/config`):

```ini
[branch "user/msg-3391-description/a"]
    gh-merge-base = master
    spectrum-stack = msg-3391
    spectrum-index = 0
    spectrum-pr = 38550
```

- `gh-merge-base` — read natively by `gh pr create` to set the PR base
- `spectrum-stack` — stack identifier (ticket ID)
- `spectrum-index` — position in stack (0-indexed)
- `spectrum-pr` — PR number (set after creation)
- `spectrum-wip` — `true` if branch is marked as WIP (skipped during submit)
- `spectrum-title` — custom PR title (used by submit and title commands)

Operation state (for `continue`/`abort`) is saved to `.git/spectrum-state.json` during rebase conflicts.

No extra files or directories. State survives rebases.

## Safety

- All pushes use `--force-with-lease`
- Rebase conflicts save state and can be resumed with `spectrum continue` or cancelled with `spectrum abort`
- PR body edits only touch the `<!-- SPECTRUM:START -->` / `<!-- SPECTRUM:END -->` region

## Tests

```bash
pytest -v
```
