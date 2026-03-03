from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError
from spectrum.stack import StackEntry


class TestRenameBranch:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_branch_m(self, mock_run):
        from spectrum.git import rename_branch

        rename_branch("old-name", "new-name")
        mock_run.assert_called_once_with(["branch", "-m", "old-name", "new-name"])


class TestDeleteRemoteBranch:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_push_delete(self, mock_run):
        from spectrum.git import delete_remote_branch

        delete_remote_branch("my-branch")
        mock_run.assert_called_once_with(["push", "origin", "--delete", "my-branch"])


class TestRenameCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_happy_path(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.branch_exists.return_value = False
        mock_stack.get_stack.return_value = [entry]

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "user/msg-3391-bar/a"])

        assert result.exit_code == 0
        assert "Renamed user/msg-3391-foo/a -> user/msg-3391-bar/a" in result.output
        mock_git.rename_branch.assert_called_once_with(
            "user/msg-3391-foo/a", "user/msg-3391-bar/a"
        )
        mock_git.push_force_with_lease.assert_called_once_with(
            ["user/msg-3391-bar/a"]
        )
        mock_git.delete_remote_branch.assert_called_once_with("user/msg-3391-foo/a")

    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "new-name"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_branch_already_exists(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.branch_exists.return_value = True

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "existing-branch"])

        assert result.exit_code != 0
        assert "already exists" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_updates_children_merge_base(self, mock_stack, mock_git):
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
        mock_git.branch_exists.return_value = False
        mock_stack.get_stack.return_value = [entry_a, entry_b]

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "user/msg-3391-bar/a"])

        assert result.exit_code == 0
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/b", "gh-merge-base", "user/msg-3391-bar/a"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_git_error(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.branch_exists.return_value = False
        mock_git.rename_branch.side_effect = GitError("rename failed")

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "new-name"])

        assert result.exit_code != 0
        assert "rename failed" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rename_remote_delete_fails_silently(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.branch_exists.return_value = False
        mock_stack.get_stack.return_value = [entry]
        mock_git.delete_remote_branch.side_effect = GitError("no remote")

        runner = CliRunner()
        result = runner.invoke(main, ["rename", "new-name"])

        assert result.exit_code == 0
        assert "Renamed" in result.output
