"""Tests for auto-skip duplicate commits during rebase.

When a child branch has stale copies of parent commits (from a prior incomplete
sync/restack), cascading rebases produce false conflicts. Spectrum detects these
by matching the conflicting commit's subject against the target branch and
auto-skips duplicates.
"""

from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main, _auto_skip_duplicate_commits
from spectrum.git import RebaseConflictError
from spectrum.stack import StackEntry


class TestAutoSkipDuplicateCommits:
    """Tests for the _auto_skip_duplicate_commits helper."""

    @patch("spectrum.cli.git", autospec=True)
    def test_skips_single_duplicate(self, mock_git):
        """A conflict whose subject matches the target is auto-skipped."""
        mock_git.log_subjects_from_range.return_value = {
            "Fix type annotations",
            "make check-fix",
        }
        mock_git.rebase_head_subject.return_value = "Fix type annotations"
        # rebase_skip succeeds (rebase completes)

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        assert skipped == ["Fix type annotations"]
        mock_git.rebase_skip.assert_called_once()

    @patch("spectrum.cli.git", autospec=True)
    def test_skips_multiple_consecutive_duplicates(self, mock_git):
        """Multiple consecutive duplicate commits are all skipped."""
        mock_git.log_subjects_from_range.return_value = {
            "Fix type annotations",
            "make check-fix",
            "Add autospec=True",
        }
        # First two conflicts are duplicates, third skip succeeds
        mock_git.rebase_head_subject.side_effect = [
            "Fix type annotations",
            "make check-fix",
        ]
        mock_git.rebase_skip.side_effect = [
            RebaseConflictError("branch_c", "new_b", ["file.py"]),
            None,  # rebase completes
        ]

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        assert skipped == ["Fix type annotations", "make check-fix"]
        assert mock_git.rebase_skip.call_count == 2

    @patch("spectrum.cli.git", autospec=True)
    def test_returns_empty_for_real_conflict(self, mock_git):
        """A conflict whose subject doesn't match the target returns empty."""
        mock_git.log_subjects_from_range.return_value = {
            "Fix type annotations",
            "make check-fix",
        }
        mock_git.rebase_head_subject.return_value = "Add new booking feature"

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        assert skipped == []
        mock_git.rebase_skip.assert_not_called()

    @patch("spectrum.cli.git", autospec=True)
    def test_returns_empty_when_no_rebase_head(self, mock_git):
        """Returns empty if REBASE_HEAD subject can't be read."""
        mock_git.log_subjects_from_range.return_value = {"some subject"}
        mock_git.rebase_head_subject.return_value = None

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        assert skipped == []

    @patch("spectrum.cli.git", autospec=True)
    def test_returns_empty_when_no_target_subjects(self, mock_git):
        """Returns empty if target branch has no subjects."""
        mock_git.log_subjects_from_range.return_value = set()

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        assert skipped == []

    @patch("spectrum.cli.git", autospec=True)
    def test_skips_duplicates_then_hits_real_conflict(self, mock_git):
        """Skips duplicates until a non-duplicate conflict is hit."""
        mock_git.log_subjects_from_range.return_value = {
            "Fix type annotations",
            "make check-fix",
        }
        mock_git.rebase_head_subject.side_effect = [
            "Fix type annotations",
            "Add new booking feature",  # not a duplicate
        ]
        mock_git.rebase_skip.side_effect = [
            RebaseConflictError("branch_c", "new_b", ["file.py"]),
        ]

        skipped = _auto_skip_duplicate_commits("new_b", "old_b")

        # Only the first duplicate was skipped; second conflict is real
        assert skipped == ["Fix type annotations"]


class TestRebaseEntriesAutoSkip:
    """Integration tests: auto-skip within _rebase_entries via CLI commands."""

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_restack_auto_skips_duplicate_and_succeeds(self, mock_stack, mock_git):
        """restack auto-skips a duplicate conflict and continues."""
        entry_a = StackEntry(
            branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master",
        )
        entry_b = StackEntry(
            branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.merge_base.return_value = "abc123"
        mock_git.rev_parse.return_value = "def456"

        # [b] rebase conflicts, but it's a duplicate
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-1/b", "user/msg-1/a", ["nodes.py"]
        )
        mock_git.log_subjects_from_range.return_value = {"Fix type annotations"}
        mock_git.rebase_head_subject.return_value = "Fix type annotations"
        # rebase_skip succeeds

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert result.exit_code == 0
        assert "Skipped duplicate" in result.output
        assert "done" in result.output
        mock_git.rebase_skip.assert_called_once()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_restack_real_conflict_not_skipped(self, mock_stack, mock_git):
        """restack with a real (non-duplicate) conflict behaves as before."""
        entry_a = StackEntry(
            branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master",
        )
        entry_b = StackEntry(
            branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.merge_base.return_value = "abc123"
        mock_git.rev_parse.return_value = "def456"
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-1/b", "user/msg-1/a", ["nodes.py"]
        )
        # Not a duplicate — subject doesn't match target
        mock_git.log_subjects_from_range.return_value = {"unrelated commit"}
        mock_git.rebase_head_subject.return_value = "Add new feature"

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert "CONFLICT" in result.output
        assert "spectrum continue" in result.output
        mock_git.rebase_skip.assert_not_called()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_restack_no_conflict_unaffected(self, mock_stack, mock_git):
        """restack with no conflicts works exactly as before."""
        entry_a = StackEntry(
            branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master",
        )
        entry_b = StackEntry(
            branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base_fork_point.return_value = "fork123"
        mock_git.rev_parse.return_value = "tip456"

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert result.exit_code == 0
        assert "done" in result.output
        assert "Skipped duplicate" not in result.output
        mock_git.rebase_skip.assert_not_called()
        mock_git.log_subjects_from_range.assert_not_called()
