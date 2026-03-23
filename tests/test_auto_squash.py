from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import _squash_branch, main
from spectrum.stack import StackEntry


@patch("spectrum.cli.git", autospec=True)
class TestSquashBranch:
    def test_skips_when_single_commit(self, mock_git):
        entry = StackEntry(
            branch="user/msg-1/a",
            index=0,
            stack_id="msg-1",
            merge_base="master",
        )
        mock_git.log_subjects.return_value = ["only commit"]

        _squash_branch(entry, "abc123")

        mock_git.reset_soft.assert_not_called()
        mock_git.commit.assert_not_called()

    def test_squashes_multi_commit_branch(self, mock_git):
        entry = StackEntry(
            branch="user/msg-1/a",
            index=0,
            stack_id="msg-1",
            merge_base="master",
        )
        mock_git.log_subjects.return_value = ["first commit", "second", "third"]
        mock_git.get_branch_config.return_value = None

        _squash_branch(entry, "fork-point-sha")

        mock_git.checkout.assert_called_once_with("user/msg-1/a")
        mock_git.reset_soft.assert_called_once_with("fork-point-sha")
        mock_git.commit.assert_called_once_with("first commit")

    def test_retargeted_branch_squashes_using_old_base_not_master(self, mock_git):
        """When a branch is retargeted to master after parent merged,
        squash must use old_base (fork-point SHA), not 'master'."""
        entry = StackEntry(
            branch="user/msg-1/a",
            index=0,
            stack_id="msg-1",
            merge_base="master",  # retargeted to master
        )
        mock_git.log_subjects.return_value = ["feat: add field", "feat: add migration"]
        mock_git.get_branch_config.return_value = "Add field"

        _squash_branch(entry, "old-parent-tip-sha")

        # Must use the fork-point SHA, not "master"
        mock_git.log_subjects.assert_called_once_with("old-parent-tip-sha", "user/msg-1/a")
        mock_git.reset_soft.assert_called_once_with("old-parent-tip-sha")
        mock_git.commit.assert_called_once_with("Add field")


@patch("spectrum.cli.git", autospec=True)
@patch("spectrum.cli.stack", autospec=True)
class TestAutoSquashInRebaseEntries:
    def test_restack_squashes_before_rebase(self, mock_stack, mock_git):
        """Restack auto-squashes a multi-commit descendant before rebasing it."""
        entry_a = StackEntry(
            branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master",
        )
        entry_b = StackEntry(
            branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base.return_value = "abc123"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.rev_parse.side_effect = lambda ref: f"tip-{ref.split('/')[-1]}"
        # /b has 3 commits — should be squashed
        mock_git.log_subjects.return_value = ["first", "second", "third"]
        mock_git.get_branch_config.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["restack"])

        assert result.exit_code == 0
        # Verify squash happened: reset_soft called with computed old_base
        # (merge_base fork point of /b against /a = "abc123")
        mock_git.reset_soft.assert_called_once_with("abc123")
        mock_git.commit.assert_called_once_with("first")

    def test_sync_first_branch_squashes_using_fork_point_not_master(self, mock_stack, mock_git):
        """First branch in stack (merge_base=master) must squash using
        the fork-point SHA, not the symbolic ref 'master'."""
        entry_a = StackEntry(
            branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base_fork_point.return_value = "fork-point-sha-abc"
        mock_git.rev_parse.return_value = "tip-a"
        mock_git.log_subjects.return_value = ["first", "second", "third"]
        mock_git.get_branch_config.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--no-push"])

        assert result.exit_code == 0
        # Must use fork-point SHA, not "master" or "origin/master"
        mock_git.reset_soft.assert_called_once_with("fork-point-sha-abc")

