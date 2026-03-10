from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import AliasGroup, main
from spectrum.stack import StackEntry


ENTRY_A = StackEntry(
    branch="user/msg-3391-foo/a",
    index=0,
    stack_id="msg-3391",
    merge_base="master",
    pr_number=100,
)
ENTRY_B = StackEntry(
    branch="user/msg-3391-foo/b",
    index=1,
    stack_id="msg-3391",
    merge_base="user/msg-3391-foo/a",
    pr_number=101,
)
ENTRY_C = StackEntry(
    branch="user/msg-3391-foo/c",
    index=2,
    stack_id="msg-3391",
    merge_base="user/msg-3391-foo/b",
    pr_number=102,
)


class TestAbsorbCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_happy_path_two_files_two_branches(self, mock_stack, mock_git):
        """Two staged files, one owned by [a], one by [b]. Verify full flow."""
        mock_stack.current_entry.return_value = ENTRY_C
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B, ENTRY_C]
        mock_git.current_branch.return_value = "user/msg-3391-foo/c"
        mock_git.diff_cached_files.return_value = ["foo.py", "bar.py"]

        # foo.py was modified in [a], bar.py in [b]
        def log_files_side_effect(base, head, file):
            if head == "user/msg-3391-foo/a" and file == "foo.py":
                return ["abc123"]
            if head == "user/msg-3391-foo/b" and file == "bar.py":
                return ["def456"]
            return []

        mock_git.log_files.side_effect = log_files_side_effect

        runner = CliRunner()
        result = runner.invoke(main, ["absorb", "-y"])

        assert result.exit_code == 0, result.output

        # Should checkout [a], apply foo.py, commit
        assert mock_git.checkout.call_args_list[0] == (("user/msg-3391-foo/a",),)
        mock_git.checkout_file.assert_any_call("user/msg-3391-foo/c", "foo.py")
        mock_git.add_files.assert_any_call(["foo.py"])
        mock_git.commit.assert_any_call("absorb: foo.py")

        # Should checkout [b], apply bar.py, commit
        assert mock_git.checkout.call_args_list[1] == (("user/msg-3391-foo/b",),)
        mock_git.checkout_file.assert_any_call("user/msg-3391-foo/c", "bar.py")
        mock_git.add_files.assert_any_call(["bar.py"])
        mock_git.commit.assert_any_call("absorb: bar.py")

        # Should return to original branch
        assert mock_git.checkout.call_args_list[2] == (("user/msg-3391-foo/c",),)

        # Should unstage absorbed files
        mock_git.reset_files.assert_called_once_with(["foo.py", "bar.py"])

        assert "Absorbed" in result.output
        assert "sp restack" in result.output

    @patch("spectrum.cli.stack", autospec=True)
    def test_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["absorb"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_no_staged_files(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = ENTRY_B
        mock_git.diff_cached_files.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["absorb"])

        assert result.exit_code != 0
        assert "No staged files" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_file_not_owned_by_any_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = ENTRY_B
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B]
        mock_git.current_branch.return_value = "user/msg-3391-foo/b"
        mock_git.diff_cached_files.return_value = ["new_file.py"]
        mock_git.log_files.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["absorb", "-y"])

        assert result.exit_code == 0
        assert "Skipped (no branch owns): new_file.py" in result.output
        assert "No files to distribute" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_file_owned_by_current_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = ENTRY_B
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B]
        mock_git.current_branch.return_value = "user/msg-3391-foo/b"
        mock_git.diff_cached_files.return_value = ["main.py"]

        # main.py is owned by [b] which is the current branch
        def log_files_side_effect(base, head, file):
            if head == "user/msg-3391-foo/b" and file == "main.py":
                return ["abc123"]
            return []

        mock_git.log_files.side_effect = log_files_side_effect

        runner = CliRunner()
        result = runner.invoke(main, ["absorb", "-y"])

        assert result.exit_code == 0
        assert "Skipped (current branch): main.py" in result.output
        assert "No files to distribute" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_all_files_skipped(self, mock_stack, mock_git):
        """When all files are either current branch or unowned, no distribution happens."""
        mock_stack.current_entry.return_value = ENTRY_B
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B]
        mock_git.current_branch.return_value = "user/msg-3391-foo/b"
        mock_git.diff_cached_files.return_value = ["owned.py", "unowned.py"]

        def log_files_side_effect(base, head, file):
            if head == "user/msg-3391-foo/b" and file == "owned.py":
                return ["abc123"]
            return []

        mock_git.log_files.side_effect = log_files_side_effect

        runner = CliRunner()
        result = runner.invoke(main, ["absorb", "-y"])

        assert result.exit_code == 0
        assert "No files to distribute" in result.output
        # Should NOT have called checkout for any branch distribution
        mock_git.checkout.assert_not_called()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_confirmation_declined(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = ENTRY_B
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B]
        mock_git.current_branch.return_value = "user/msg-3391-foo/b"
        mock_git.diff_cached_files.return_value = ["foo.py"]

        def log_files_side_effect(base, head, file):
            if head == "user/msg-3391-foo/a" and file == "foo.py":
                return ["abc123"]
            return []

        mock_git.log_files.side_effect = log_files_side_effect

        runner = CliRunner()
        result = runner.invoke(main, ["absorb"], input="n\n")

        assert result.exit_code != 0
        # No checkout should have happened (aborted before distribution)
        mock_git.checkout.assert_not_called()
        mock_git.commit.assert_not_called()

    def test_absorb_in_edit_command_group(self):
        assert "absorb" in AliasGroup.COMMAND_GROUPS["Edit"]

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_file_owned_by_highest_branch_when_multiple(self, mock_stack, mock_git):
        """When a file is modified by multiple branches, attribute to the highest index."""
        mock_stack.current_entry.return_value = ENTRY_C
        mock_stack.get_stack.return_value = [ENTRY_A, ENTRY_B, ENTRY_C]
        mock_git.current_branch.return_value = "user/msg-3391-foo/c"
        mock_git.diff_cached_files.return_value = ["shared.py"]

        # shared.py modified in both [a] and [b]
        def log_files_side_effect(base, head, file):
            if head == "user/msg-3391-foo/a" and file == "shared.py":
                return ["abc123"]
            if head == "user/msg-3391-foo/b" and file == "shared.py":
                return ["def456"]
            return []

        mock_git.log_files.side_effect = log_files_side_effect

        runner = CliRunner()
        result = runner.invoke(main, ["absorb", "-y"])

        assert result.exit_code == 0
        # Should be distributed to [b] (highest), not [a]
        assert "[b]" in result.output
        mock_git.checkout.assert_any_call("user/msg-3391-foo/b")
        mock_git.checkout_file.assert_any_call("user/msg-3391-foo/c", "shared.py")
