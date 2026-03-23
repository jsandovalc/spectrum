from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError
from spectrum.stack import StackEntry


class TestResetSoft:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_reset_soft(self, mock_run):
        from spectrum.git import reset_soft

        reset_soft("abc123")
        mock_run.assert_called_once_with(["reset", "--soft", "abc123"])


class TestCommit:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_commit(self, mock_run):
        from spectrum.git import commit

        commit("my message")
        mock_run.assert_called_once_with(["commit", "-m", "my message"])


class TestSquashCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_happy_path(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.merge_base_fork_point.return_value = "fork-sha"
        mock_git.log_subjects.return_value = ["first commit", "second", "third"]
        mock_stack.get_stack.return_value = [entry]

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code == 0
        assert "Squashed 3 commits into: first commit" in result.output
        mock_git.reset_soft.assert_called_once_with("fork-sha")
        mock_git.commit.assert_called_once_with("first commit")

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_with_custom_message(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.log_subjects.return_value = ["first", "second", "third"]
        mock_stack.get_stack.return_value = [entry]

        runner = CliRunner()
        result = runner.invoke(main, ["squash", "-m", "custom msg"])

        assert result.exit_code == 0
        assert "custom msg" in result.output
        mock_git.commit.assert_called_once_with("custom msg")

    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_no_commits(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.log_subjects.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code != 0
        assert "No commits to squash" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_single_commit(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.log_subjects.return_value = ["only one"]

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code != 0
        assert "Only 1 commit" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_restacks_descendants(self, mock_stack, mock_git):
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
        mock_git.log_subjects.return_value = ["first", "second"]
        mock_stack.get_stack.return_value = [entry_a, entry_b]

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code == 0
        # Verify rebase was attempted on descendant
        mock_git.rebase_onto.assert_called()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_squash_git_error(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry
        mock_git.log_subjects.return_value = ["first", "second"]
        mock_git.reset_soft.side_effect = GitError("reset failed")

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code != 0
        assert "reset failed" in result.output
