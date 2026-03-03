from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError
from spectrum.stack import StackEntry


class TestMergeFfOnly:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_merge_ff_only(self, mock_run):
        from spectrum.git import merge_ff_only

        merge_ff_only("feature-branch")
        mock_run.assert_called_once_with(["merge", "--ff-only", "feature-branch"])


class TestFoldCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_happy_path(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=101,
        )
        mock_stack.current_entry.return_value = entry_b
        mock_stack.get_stack.return_value = [entry_a, entry_b]

        runner = CliRunner()
        result = runner.invoke(main, ["fold", "-y"])

        assert result.exit_code == 0
        assert "Folded [b] into [a]" in result.output
        mock_git.checkout.assert_called_with("user/msg-3391-foo/a")
        mock_git.merge_ff_only.assert_called_once_with("user/msg-3391-foo/b")
        mock_stack.remove_entry.assert_called_once_with("user/msg-3391-foo/b")
        mock_stack.reindex_stack.assert_called_once_with("msg-3391")
        mock_git.delete_branch.assert_called_once_with("user/msg-3391-foo/b")

    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["fold"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_first_part(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]

        runner = CliRunner()
        result = runner.invoke(main, ["fold"])

        assert result.exit_code != 0
        assert "Cannot fold the first part" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_retargets_children(self, mock_stack, mock_git):
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
        entry_c = StackEntry(
            branch="user/msg-3391-foo/c",
            index=2,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b",
        )
        mock_stack.current_entry.return_value = entry_b
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c]

        runner = CliRunner()
        result = runner.invoke(main, ["fold", "-y"])

        assert result.exit_code == 0
        # entry_c should be retargeted to entry_a
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/c", "gh-merge-base", "user/msg-3391-foo/a"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_no_children(self, mock_stack, mock_git):
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
        mock_stack.current_entry.return_value = entry_b
        mock_stack.get_stack.return_value = [entry_a, entry_b]

        runner = CliRunner()
        result = runner.invoke(main, ["fold", "-y"])

        assert result.exit_code == 0
        assert "Folded [b] into [a]" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_fold_git_error_on_merge(self, mock_stack, mock_git):
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
        mock_stack.current_entry.return_value = entry_b
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_git.merge_ff_only.side_effect = GitError("not fast-forward")

        runner = CliRunner()
        result = runner.invoke(main, ["fold", "-y"])

        assert result.exit_code != 0
        assert "not fast-forward" in result.output
