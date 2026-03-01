# Changelog

## [Unreleased]

### Added
- `spectrum top` / `spectrum bottom`: jump to the last or first part of the stack
- `spectrum log` (`lg`): graphical stack view with Unicode tree, PR status, draft labels, and diff stats
- `spectrum create`: start a new stack from a Linear branch name
- `spectrum add`: add a new part to the current stack
- `spectrum status` (`st`): show current stack state with PR URLs and diff stats
- `spectrum switch` (`sw`): switch to a part of the current stack by letter
- `spectrum next` / `spectrum prev`: navigate between adjacent stack parts
- `spectrum submit`: create or update PRs for all branches in the stack
- `spectrum sync`: fetch, detect merges, and rebase from current position
- `spectrum drop`: remove a part from the stack and relink neighbors
- `spectrum adopt`: import existing branches into a stack
