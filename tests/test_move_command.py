from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError, RebaseConflictError
from spectrum.stack import StackEntry


class TestMoveCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_happy_path(self, mock_stack, mock_git):
        """Move [c] onto [a], detaching from [b]."""
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
        mock_stack.current_entry.return_value = entry_c
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c]
        mock_stack.letter_to_index.return_value = 0

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code == 0
        assert "Moved [c] onto [a]" in result.output
        # Verify rebase was called
        mock_git.rebase_onto.assert_called_once_with(
            "user/msg-3391-foo/c",
            "user/msg-3391-foo/a",
            "user/msg-3391-foo/b",
        )
        # Verify merge_base was updated
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/c", "gh-merge-base", "user/msg-3391-foo/a"
        )
        mock_stack.reindex_stack.assert_called_once_with("msg-3391")

    @patch("spectrum.cli.stack", autospec=True)
    def test_move_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_onto_self(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_stack.letter_to_index.return_value = 0

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code != 0
        assert "Cannot move a branch onto itself" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_onto_descendant(self, mock_stack, mock_git):
        """Moving [a] onto [b] should fail since [b] descends from [a]."""
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
        mock_stack.letter_to_index.return_value = 1

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "b"])

        assert result.exit_code != 0
        assert "descendant" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_target_not_found(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_stack.letter_to_index.return_value = 25  # z

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "z"])

        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_retargets_successor(self, mock_stack, mock_git):
        """When moving [b] (has successor [c]), [c] should retarget to [a]."""
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
        # Moving [b] onto [c] — but wait, that would be onto a descendant
        # Instead: move [c] onto [a], so [c]'s successor (none) is fine
        # Better: 3-part stack a->b->c, move [b] out by making it child of master?
        # Actually, let's use a 4-part stack: a->b->c->d, move c onto a
        entry_d = StackEntry(
            branch="user/msg-3391-foo/d",
            index=3,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/c",
        )
        mock_stack.current_entry.return_value = entry_c
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c, entry_d]
        mock_stack.letter_to_index.return_value = 0  # onto [a]

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code == 0
        # [d] was successor of [c], should be retargeted to [c]'s old merge_base [b]
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/d", "gh-merge-base", "user/msg-3391-foo/b"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_rebase_conflict(self, mock_stack, mock_git):
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
        mock_stack.current_entry.return_value = entry_c
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c]
        mock_stack.letter_to_index.return_value = 0
        mock_git.rebase_onto.side_effect = RebaseConflictError(
            "user/msg-3391-foo/c", "user/msg-3391-foo/a"
        )

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code == 0  # Conflict is handled, not an error
        assert "Conflict" in result.output
        mock_stack.reindex_stack.assert_not_called()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_move_reindexes_stack(self, mock_stack, mock_git):
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
        mock_stack.letter_to_index.return_value = 0

        # entry_b has no successors, no cycle issue
        # But wait - b's merge_base is a, and we're moving b onto a again?
        # That's the current state. Let me use a different scenario.
        # Actually move is pointless if already on target. Let me use 3 parts.
        entry_c = StackEntry(
            branch="user/msg-3391-foo/c",
            index=2,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/b",
        )
        mock_stack.current_entry.return_value = entry_c
        mock_stack.get_stack.return_value = [entry_a, entry_b, entry_c]

        runner = CliRunner()
        result = runner.invoke(main, ["move", "--onto", "a"])

        assert result.exit_code == 0
        mock_stack.reindex_stack.assert_called_once_with("msg-3391")
