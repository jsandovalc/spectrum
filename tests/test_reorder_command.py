from unittest.mock import mock_open, patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import RebaseConflictError
from spectrum.github import GhError
from spectrum.stack import StackEntry


class TestReorderCommand:
    @patch("spectrum.cli.stack", autospec=True)
    def test_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "b"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.stack", autospec=True)
    def test_same_letter_error(self, mock_stack):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "a"])

        assert result.exit_code != 0
        assert "must be different" in result.output.lower()

    @patch("spectrum.cli.stack", autospec=True)
    def test_letter_not_in_stack(self, mock_stack):
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
        mock_stack.letter_to_index.side_effect = lambda l: ord(l) - ord("a")

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "z"])

        assert result.exit_code != 0
        assert "not found" in result.output.lower()
        assert "a, b" in result.output

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_happy_path_adjacent_swap(self, mock_stack, mock_git, mock_github):
        """Swap [a] and [b] in a 3-entry stack with -y flag."""
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=10,
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=11,
        )
        entry_c = StackEntry(
            branch="user/msg-3391-foo/c",
            index=2,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b",
            pr_number=12,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c]
        mock_stack.letter_to_index.side_effect = lambda l: ord(l) - ord("a")

        # swap_entries returns the reordered stack: b(0), a(1), c(2)
        swapped_b = StackEntry(
            branch="user/msg-3391-foo/b", index=0, stack_id="msg-3391",
            merge_base="master", pr_number=11,
        )
        swapped_a = StackEntry(
            branch="user/msg-3391-foo/a", index=1, stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b", pr_number=10,
        )
        swapped_c = StackEntry(
            branch="user/msg-3391-foo/c", index=2, stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a", pr_number=12,
        )
        mock_stack.swap_entries.return_value = [swapped_b, swapped_a, swapped_c]

        mock_git.rev_parse.side_effect = lambda ref: f"sha-{ref}"
        mock_git.current_branch.return_value = "user/msg-3391-foo/a"

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "b", "-y"])

        assert result.exit_code == 0, result.output
        # swap_entries called with correct args
        mock_stack.swap_entries.assert_called_once_with("msg-3391", 0, 1)
        # PR bases updated for affected entries
        mock_github.pr_edit_base.assert_any_call(11, "master")
        mock_github.pr_edit_base.assert_any_call(10, "user/msg-3391-foo/b")
        mock_github.pr_edit_base.assert_any_call(12, "user/msg-3391-foo/a")
        # Success message with submit reminder
        assert "submit" in result.output.lower()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_confirmation_aborts(self, mock_stack, mock_git):
        """Declining confirmation aborts without swapping."""
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
        mock_stack.letter_to_index.side_effect = lambda l: ord(l) - ord("a")

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "b"], input="n\n")

        assert result.exit_code != 0
        mock_stack.swap_entries.assert_not_called()

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_gherror_on_pr_update_ignored(self, mock_stack, mock_git, mock_github):
        """GhError when updating PR base is silently ignored."""
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=10,
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=11,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_stack.letter_to_index.side_effect = lambda l: ord(l) - ord("a")

        mock_github.pr_edit_base.side_effect = GhError("API error")

        swapped_b = StackEntry(
            branch="user/msg-3391-foo/b", index=0, stack_id="msg-3391",
            merge_base="master", pr_number=11,
        )
        swapped_a = StackEntry(
            branch="user/msg-3391-foo/a", index=1, stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b", pr_number=10,
        )
        mock_stack.swap_entries.return_value = [swapped_b, swapped_a]
        mock_git.rev_parse.side_effect = lambda ref: f"sha-{ref}"
        mock_git.current_branch.return_value = "user/msg-3391-foo/a"

        runner = CliRunner()
        result = runner.invoke(main, ["reorder", "a", "b", "-y"])

        assert result.exit_code == 0, result.output
        assert "submit" in result.output.lower()

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_rebase_conflict_saves_opstate(self, mock_stack, mock_git, mock_github):
        """Rebase conflict prints conflict message (opstate handled by _rebase_entries)."""
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=10,
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=11,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_stack.letter_to_index.side_effect = lambda l: ord(l) - ord("a")

        swapped_b = StackEntry(
            branch="user/msg-3391-foo/b", index=0, stack_id="msg-3391",
            merge_base="master", pr_number=11,
        )
        swapped_a = StackEntry(
            branch="user/msg-3391-foo/a", index=1, stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b", pr_number=10,
        )
        mock_stack.swap_entries.return_value = [swapped_b, swapped_a]
        mock_git.rev_parse.side_effect = lambda ref: f"sha-{ref}"
        mock_git.current_branch.return_value = "user/msg-3391-foo/a"

        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-3391-foo/b", "master"
        )
        mock_git.unmerged_files.return_value = ["file.py"]
        mock_git.repo_root.return_value = "/repo"

        content = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>>\n"
        with patch("builtins.open", mock_open(read_data=content)):
            runner = CliRunner()
            result = runner.invoke(main, ["reorder", "a", "b", "-y"])

        assert result.exit_code == 0
        assert "conflict" in result.output.lower()
        assert "spectrum continue" in result.output
        assert "Reordered" not in result.output

    def test_reorder_in_edit_command_group(self):
        """reorder appears in the Edit command group."""
        from spectrum.cli import AliasGroup
        assert "reorder" in AliasGroup.COMMAND_GROUPS["Edit"]
