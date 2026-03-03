import json
import os
from unittest.mock import patch

from spectrum.opstate import OperationState


class TestOperationState:
    @patch("spectrum.opstate.git", autospec=True)
    def test_save_and_load(self, mock_git, tmp_path):
        mock_git.git_dir.return_value = str(tmp_path)

        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b", "x/c"],
            remaining_merge_bases=["x/a", "x/b"],
            remaining_stack_ids=["msg-1", "msg-1"],
            remaining_indices=[1, 2],
            original_branch="x/a",
            stack_id="msg-1",
            resolve_onto_master=True,
        )
        op.save()

        loaded = OperationState.load()
        assert loaded is not None
        assert loaded.command == "spectrum sync"
        assert loaded.remaining_branches == ["x/b", "x/c"]
        assert loaded.remaining_merge_bases == ["x/a", "x/b"]
        assert loaded.original_branch == "x/a"
        assert loaded.stack_id == "msg-1"
        assert loaded.resolve_onto_master is True

    @patch("spectrum.opstate.git", autospec=True)
    def test_load_returns_none_when_no_state(self, mock_git, tmp_path):
        mock_git.git_dir.return_value = str(tmp_path)

        result = OperationState.load()
        assert result is None

    @patch("spectrum.opstate.git", autospec=True)
    def test_clear_removes_state_file(self, mock_git, tmp_path):
        mock_git.git_dir.return_value = str(tmp_path)

        op = OperationState(
            command="spectrum sync",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        op.save()

        state_path = os.path.join(str(tmp_path), "spectrum-state.json")
        assert os.path.exists(state_path)

        OperationState.clear()
        assert not os.path.exists(state_path)

    @patch("spectrum.opstate.git", autospec=True)
    def test_clear_when_no_state_is_noop(self, mock_git, tmp_path):
        mock_git.git_dir.return_value = str(tmp_path)

        # Should not raise
        OperationState.clear()

    @patch("spectrum.opstate.git", autospec=True)
    def test_state_is_valid_json(self, mock_git, tmp_path):
        mock_git.git_dir.return_value = str(tmp_path)

        op = OperationState(
            command="spectrum restack",
            remaining_branches=["x/b"],
            remaining_merge_bases=["x/a"],
            remaining_stack_ids=["msg-1"],
            remaining_indices=[1],
            original_branch="x/a",
            stack_id="msg-1",
        )
        op.save()

        state_path = os.path.join(str(tmp_path), "spectrum-state.json")
        with open(state_path) as f:
            data = json.load(f)

        assert data["command"] == "spectrum restack"
        assert data["remaining_branches"] == ["x/b"]
