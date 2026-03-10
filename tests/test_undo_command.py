"""Tests for the undo module and undo CLI command."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from spectrum.cli import AliasGroup, main
from spectrum.stack import StackEntry
from spectrum.undo import UndoSnapshot, restore_snapshot, save_snapshot


# ---------------------------------------------------------------------------
# UndoSnapshot unit tests
# ---------------------------------------------------------------------------


class TestUndoSnapshot:
    def test_save_and_load_round_trip(self, tmp_path):
        """Create snapshot, save, load, verify fields match."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.git_dir.return_value = str(tmp_path)

            snapshot = UndoSnapshot(
                command="fold",
                original_branch="user/msg-123-foo/b",
                branches={
                    "user/msg-123-foo/a": {
                        "sha": "abc123",
                        "config": {"spectrum-stack": "msg-123", "spectrum-index": "0"},
                    },
                    "user/msg-123-foo/b": {
                        "sha": "def456",
                        "config": {"spectrum-stack": "msg-123", "spectrum-index": "1"},
                    },
                },
            )
            snapshot.save()

            loaded = UndoSnapshot.load()
            assert loaded is not None
            assert loaded.command == "fold"
            assert loaded.original_branch == "user/msg-123-foo/b"
            assert loaded.branches == snapshot.branches

    def test_load_returns_none_when_no_file(self, tmp_path):
        """Verify returns None when no undo file exists."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.git_dir.return_value = str(tmp_path)

            result = UndoSnapshot.load()
            assert result is None

    def test_clear_removes_file(self, tmp_path):
        """Save, clear, load returns None."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.git_dir.return_value = str(tmp_path)

            snapshot = UndoSnapshot(
                command="drop",
                original_branch="user/msg-123-foo/a",
                branches={"user/msg-123-foo/a": {"sha": "abc123", "config": {}}},
            )
            snapshot.save()
            assert UndoSnapshot.load() is not None

            UndoSnapshot.clear()
            assert UndoSnapshot.load() is None


class TestSaveSnapshot:
    def test_save_snapshot_captures_state(self, tmp_path):
        """save_snapshot captures branch SHAs and config from StackEntry fields."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.git_dir.return_value = str(tmp_path)
            mock_git.current_branch.return_value = "user/msg-123-foo/a"
            mock_git.rev_parse.side_effect = lambda ref: f"sha-{ref}"
            mock_git.get_branch_config.return_value = None  # no spectrum-title

            entries = [
                StackEntry(
                    branch="user/msg-123-foo/a",
                    index=0,
                    stack_id="msg-123",
                    merge_base="master",
                    pr_number=42,
                ),
            ]

            save_snapshot("squash", entries)

            loaded = UndoSnapshot.load()
            assert loaded is not None
            assert loaded.command == "squash"
            assert loaded.original_branch == "user/msg-123-foo/a"
            assert "user/msg-123-foo/a" in loaded.branches
            branch_data = loaded.branches["user/msg-123-foo/a"]
            assert branch_data["sha"] == "sha-user/msg-123-foo/a"
            assert branch_data["config"]["spectrum-stack"] == "msg-123"
            assert branch_data["config"]["spectrum-index"] == "0"
            assert branch_data["config"]["gh-merge-base"] == "master"
            assert branch_data["config"]["spectrum-pr"] == "42"


class TestRestoreSnapshot:
    def test_restore_snapshot_restores_branches(self):
        """restore_snapshot moves branches and restores config."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.branch_exists.return_value = True

            snapshot = UndoSnapshot(
                command="fold",
                original_branch="user/msg-123-foo/b",
                branches={
                    "user/msg-123-foo/a": {
                        "sha": "abc123",
                        "config": {"spectrum-stack": "msg-123", "spectrum-index": "0"},
                    },
                    "user/msg-123-foo/b": {
                        "sha": "def456",
                        "config": {"spectrum-stack": "msg-123", "spectrum-index": "1", "spectrum-pr": "42"},
                    },
                },
            )

            restore_snapshot(snapshot)

            mock_git.force_branch.assert_any_call("user/msg-123-foo/a", "abc123")
            mock_git.force_branch.assert_any_call("user/msg-123-foo/b", "def456")
            mock_git.set_branch_config.assert_any_call("user/msg-123-foo/a", "spectrum-stack", "msg-123")
            mock_git.set_branch_config.assert_any_call("user/msg-123-foo/b", "spectrum-pr", "42")
            mock_git.checkout.assert_called_once_with("user/msg-123-foo/b")

    def test_restore_creates_missing_branches(self):
        """restore_snapshot creates branches that don't exist."""
        with patch("spectrum.undo.git", autospec=True) as mock_git:
            mock_git.branch_exists.return_value = False

            snapshot = UndoSnapshot(
                command="drop",
                original_branch="user/msg-123-foo/a",
                branches={
                    "user/msg-123-foo/a": {
                        "sha": "abc123",
                        "config": {},
                    },
                },
            )

            restore_snapshot(snapshot)

            mock_git.create_branch_at.assert_called_once_with("user/msg-123-foo/a", "abc123")


# ---------------------------------------------------------------------------
# CLI undo command tests
# ---------------------------------------------------------------------------


class TestUndoCommand:
    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_happy_path_with_yes(self, mock_git, mock_stack, mock_undo):
        """Load snapshot returns valid snapshot. Verify restore called, clear called."""
        snapshot = UndoSnapshot(
            command="fold",
            original_branch="user/msg-123-foo/b",
            branches={
                "user/msg-123-foo/a": {"sha": "abc123", "config": {}},
                "user/msg-123-foo/b": {"sha": "def456", "config": {}},
            },
        )
        mock_undo.UndoSnapshot.load.return_value = snapshot

        runner = CliRunner()
        result = runner.invoke(main, ["undo", "--yes"])

        assert result.exit_code == 0
        mock_undo.restore_snapshot.assert_called_once_with(snapshot)
        mock_undo.UndoSnapshot.clear.assert_called_once()

    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_nothing_to_undo(self, mock_git, mock_stack, mock_undo):
        """Load returns None, shows error."""
        mock_undo.UndoSnapshot.load.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["undo", "--yes"])

        assert result.exit_code != 0
        assert "Nothing to undo" in result.output

    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_confirmation_declined(self, mock_git, mock_stack, mock_undo):
        """Aborts without restoring when user declines."""
        snapshot = UndoSnapshot(
            command="fold",
            original_branch="user/msg-123-foo/b",
            branches={"user/msg-123-foo/a": {"sha": "abc123", "config": {}}},
        )
        mock_undo.UndoSnapshot.load.return_value = snapshot

        runner = CliRunner()
        result = runner.invoke(main, ["undo"], input="n\n")

        assert result.exit_code != 0
        mock_undo.restore_snapshot.assert_not_called()

    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_shows_command_name_in_output(self, mock_git, mock_stack, mock_undo):
        """The output mentions which command is being undone."""
        snapshot = UndoSnapshot(
            command="squash",
            original_branch="user/msg-123-foo/a",
            branches={"user/msg-123-foo/a": {"sha": "abc123", "config": {}}},
        )
        mock_undo.UndoSnapshot.load.return_value = snapshot

        runner = CliRunner()
        result = runner.invoke(main, ["undo", "--yes"])

        assert result.exit_code == 0
        assert "squash" in result.output

    def test_undo_in_recovery_command_group(self):
        """undo is in the Recovery command group."""
        assert "undo" in AliasGroup.COMMAND_GROUPS["Recovery"]


# ---------------------------------------------------------------------------
# _save_undo integration tests
# ---------------------------------------------------------------------------


class TestSaveUndoIntegration:
    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_fold_saves_undo(self, mock_git, mock_stack, mock_github, mock_undo):
        """Invoke fold with -y, verify undo.save_snapshot was called with entries."""
        parent = StackEntry(branch="user/msg-123-foo/a", index=0, stack_id="msg-123", merge_base="master")
        current = StackEntry(branch="user/msg-123-foo/b", index=1, stack_id="msg-123", merge_base="user/msg-123-foo/a")
        entries = [parent, current]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-123-foo/b"

        runner = CliRunner()
        result = runner.invoke(main, ["fold", "-y"])

        assert result.exit_code == 0, result.output
        mock_undo.save_snapshot.assert_called_once_with("fold", entries)

    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_squash_saves_undo(self, mock_git, mock_stack, mock_github, mock_undo):
        """Invoke squash, verify undo.save_snapshot was called."""
        current = StackEntry(branch="user/msg-123-foo/a", index=0, stack_id="msg-123", merge_base="master")
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = [current]
        mock_stack.get_stack.return_value = [current]
        mock_git.current_branch.return_value = "user/msg-123-foo/a"
        mock_git.log_subjects.return_value = ["commit 1", "commit 2"]

        runner = CliRunner()
        result = runner.invoke(main, ["squash"])

        assert result.exit_code == 0, result.output
        mock_undo.save_snapshot.assert_called_once_with("squash", [current])

    @patch("spectrum.cli.undo_mod", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    def test_drop_saves_undo(self, mock_git, mock_stack, mock_github, mock_undo):
        """Invoke drop with -y, verify undo.save_snapshot was called with entries."""
        current = StackEntry(branch="user/msg-123-foo/a", index=0, stack_id="msg-123", merge_base="master")
        entries = [current]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-123-foo/a"

        runner = CliRunner()
        result = runner.invoke(main, ["drop", "-y"])

        assert result.exit_code == 0, result.output
        mock_undo.save_snapshot.assert_called_once_with("drop", entries)
