from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError, RebaseConflictError
from spectrum.opstate import OperationState
from spectrum.stack import StackEntry


class TestContinueCommand:
    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_continue_no_operation(self, mock_git, mock_opstate):
        mock_opstate.load.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code != 0
        assert "No operation in progress" in result.output

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_continue_happy_path(self, mock_stack, mock_git, mock_opstate):
        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
            resolve_onto_master=False,
        )
        mock_opstate.load.return_value = op

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code == 0
        assert "Rebase continued" in result.output
        assert "Done" in result.output
        mock_git.rebase_continue.assert_called_once()
        mock_opstate.clear.assert_called_once()

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_continue_still_has_conflicts(self, mock_git, mock_opstate):
        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        mock_opstate.load.return_value = op
        mock_git.rebase_continue.side_effect = RebaseConflictError("x/b", "x/a")

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code != 0
        assert "still has conflicts" in result.output

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_continue_with_remaining_entries(self, mock_stack, mock_git, mock_opstate):
        """When there are entries after the conflicting one, continue rebases them."""
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
        # Allow StackEntry to be created from the real class
        mock_stack.StackEntry.side_effect = StackEntry

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code == 0
        # Verify rebase was called for the remaining entry [c]
        mock_git.rebase_onto.assert_called()

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_continue_returns_to_original_branch(self, mock_stack, mock_git, mock_opstate):
        op = OperationState(
            command="spectrum restack",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        mock_opstate.load.return_value = op

        runner = CliRunner()
        result = runner.invoke(main, ["continue"])

        assert result.exit_code == 0
        mock_git.checkout.assert_called_with("x/a")


class TestAbortCommand:
    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_abort_no_operation(self, mock_git, mock_opstate):
        mock_opstate.load.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["abort"])

        assert result.exit_code != 0
        assert "No operation in progress" in result.output

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_abort_happy_path(self, mock_git, mock_opstate):
        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        mock_opstate.load.return_value = op

        runner = CliRunner()
        result = runner.invoke(main, ["abort"])

        assert result.exit_code == 0
        assert "Operation aborted" in result.output
        mock_git.rebase_abort.assert_called_once()
        mock_opstate.clear.assert_called_once()
        mock_git.checkout.assert_called_with("x/a")

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_abort_git_error(self, mock_git, mock_opstate):
        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        mock_opstate.load.return_value = op
        mock_git.rebase_abort.side_effect = GitError("no rebase in progress")

        runner = CliRunner()
        result = runner.invoke(main, ["abort"])

        assert result.exit_code != 0
        assert "no rebase in progress" in result.output


class TestRebaseEntriesSavesState:
    """Verify that _rebase_entries saves operation state on conflict."""

    @patch("spectrum.cli.OperationState", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_conflict_saves_state(self, mock_stack, mock_git, mock_opstate):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.merge_base_fork_point.return_value = None
        mock_git.merge_base.return_value = "abc123"
        mock_git.rev_parse.return_value = "def456"
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-3391-foo/b", "user/msg-3391-foo/a"
        )
        mock_git.current_branch.return_value = "user/msg-3391-foo/a"

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert "CONFLICT" in result.output
        assert "spectrum continue" in result.output
        assert "spectrum abort" in result.output
