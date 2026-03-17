"""Tests for auto-continue rebase when rerere resolves conflicts.

When git rerere is enabled, it can automatically resolve conflicts that it has
seen before. Spectrum should detect this and auto-continue the rebase instead
of stopping and asking the user to run `sp continue`.
"""

from unittest.mock import mock_open, patch

from click.testing import CliRunner

from spectrum.cli import main, _auto_continue_rerere_resolved
from spectrum.git import RebaseConflictError
from spectrum.opstate import OperationState
from spectrum.stack import StackEntry


class TestAutoContinueRerereResolved:
    """Tests for the _auto_continue_rerere_resolved helper."""

    @patch("builtins.open", mock_open(read_data="clean file content"))
    @patch("spectrum.cli.git", autospec=True)
    def test_auto_continues_when_no_unmerged_files(self, mock_git):
        """When no unmerged files remain, rerere resolved everything."""
        mock_git.unmerged_files.return_value = []
        mock_git.repo_root.return_value = "/repo"

        result = _auto_continue_rerere_resolved()

        assert result is True
        mock_git.rebase_continue.assert_called_once()

    @patch("builtins.open", mock_open(read_data="clean file content"))
    @patch("spectrum.cli.git", autospec=True)
    def test_auto_continues_when_rerere_resolved_without_autoupdate(self, mock_git):
        """When files are unmerged but have no conflict markers, stage and continue."""
        mock_git.unmerged_files.return_value = ["src/foo.py"]
        mock_git.repo_root.return_value = "/repo"

        result = _auto_continue_rerere_resolved()

        assert result is True
        mock_git.add_files.assert_called_once_with(["src/foo.py"])
        mock_git.rebase_continue.assert_called_once()

    @patch("spectrum.cli.git", autospec=True)
    def test_returns_false_when_conflict_markers_remain(self, mock_git):
        """When files still have conflict markers, return False."""
        mock_git.unmerged_files.return_value = ["src/foo.py"]
        mock_git.repo_root.return_value = "/repo"

        content = "before\n<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> abc123\nafter"
        with patch("builtins.open", mock_open(read_data=content)):
            result = _auto_continue_rerere_resolved()

        assert result is False
        mock_git.add_files.assert_not_called()
        mock_git.rebase_continue.assert_not_called()

    @patch("builtins.open", mock_open(read_data="clean content"))
    @patch("spectrum.cli.git", autospec=True)
    def test_loops_when_next_commit_also_resolved_by_rerere(self, mock_git):
        """When rebase_continue hits another conflict that rerere resolves, loop."""
        mock_git.repo_root.return_value = "/repo"
        # First call: unmerged files (rerere resolved), second call after continue: none
        mock_git.unmerged_files.side_effect = [["src/foo.py"], []]
        # First continue raises (next commit conflicts), second succeeds
        mock_git.rebase_continue.side_effect = [
            RebaseConflictError("branch", "onto", []),
            None,
        ]

        result = _auto_continue_rerere_resolved()

        assert result is True
        assert mock_git.rebase_continue.call_count == 2
        mock_git.add_files.assert_called_once_with(["src/foo.py"])

    @patch("spectrum.cli.git", autospec=True)
    def test_returns_false_when_loop_hits_real_conflict(self, mock_git):
        """When looping, stop if a genuinely unresolved conflict is hit."""
        mock_git.repo_root.return_value = "/repo"
        content_clean = "clean content"
        content_conflict = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>>\n"
        # First: resolved by rerere, second: real conflict
        mock_git.unmerged_files.side_effect = [["a.py"], ["b.py"]]
        mock_git.rebase_continue.side_effect = [
            RebaseConflictError("branch", "onto", ["b.py"]),
        ]

        def open_side_effect(path, *args, **kwargs):
            if "a.py" in str(path):
                return mock_open(read_data=content_clean)()
            return mock_open(read_data=content_conflict)()

        with patch("builtins.open", side_effect=open_side_effect):
            result = _auto_continue_rerere_resolved()

        assert result is False
        mock_git.add_files.assert_called_once_with(["a.py"])


class TestRebaseEntriesRerereAutoContinue:
    """Integration tests: rerere auto-continue within _rebase_entries via CLI."""

    @patch("builtins.open", mock_open(read_data="clean content"))
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_restack_auto_continues_with_rerere(self, mock_stack, mock_git):
        """restack auto-continues when rerere resolves a conflict."""
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
        mock_git.repo_root.return_value = "/repo"

        # [b] rebase conflicts, but rerere resolves it (no unmerged files)
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-1/b", "user/msg-1/a", ["nodes.py"]
        )
        # Not a duplicate (auto-skip won't handle it)
        mock_git.log_subjects_from_range.return_value = set()
        # rerere resolved — no unmerged files
        mock_git.unmerged_files.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert result.exit_code == 0
        assert "rerere" in result.output
        assert "done" in result.output
        mock_git.rebase_continue.assert_called_once()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_restack_conflict_not_resolved_by_rerere(self, mock_stack, mock_git):
        """restack with a real conflict falls through to conflict-stop."""
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
        mock_git.repo_root.return_value = "/repo"

        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-1/b", "user/msg-1/a", ["nodes.py"]
        )
        mock_git.log_subjects_from_range.return_value = set()
        # Still has unmerged files with conflict markers
        mock_git.unmerged_files.return_value = ["nodes.py"]

        content = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>>\n"
        with patch("builtins.open", mock_open(read_data=content)):
            runner = CliRunner()
            result = runner.invoke(main, ["restack"])

        assert "CONFLICT" in result.output
        assert "spectrum continue" in result.output
        mock_git.rebase_continue.assert_not_called()

    @patch("builtins.open", mock_open(read_data="clean content"))
    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_continue_remaining_entries_use_rerere(self, mock_stack, mock_git, mock_opstate):
        """sp continue feeds remaining entries through _rebase_entries which uses rerere."""
        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b", "x/c"],
            remaining_merge_bases=["x/a", "x/b"],
            remaining_stack_ids=["msg-1", "msg-1"],
            remaining_indices=[1, 2],
            original_branch="x/a",
            stack_id="msg-1",
            resolve_onto_master=False,
        )
        mock_opstate.load.return_value = op
        mock_stack.StackEntry.side_effect = lambda **kw: StackEntry(**kw)
        mock_git.current_branch.return_value = "x/b"
        mock_git.rev_parse.return_value = "tip456"
        mock_git.repo_root.return_value = "/repo"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.merge_base.return_value = "abc123"

        # rebase_continue for the first branch (user resolved manually) succeeds
        # Then x/c rebase conflicts but rerere resolves it
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "x/c", "x/b", ["file.py"]
        )
        mock_git.log_subjects_from_range.return_value = set()
        mock_git.unmerged_files.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code == 0
        assert "rerere" in result.output
