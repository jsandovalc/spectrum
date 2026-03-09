from unittest.mock import patch, call, MagicMock

import pytest

from spectrum.git import GitError, push_force_with_lease


class TestPushForceWithLeaseRetry:
    @patch("spectrum.git._run")
    def test_successful_push_no_retry(self, mock_run):
        push_force_with_lease(["branch-a"])
        mock_run.assert_called_once_with(
            ["push", "--force-with-lease", "origin", "branch-a"]
        )

    @patch("spectrum.git._run")
    def test_retries_on_stale_info(self, mock_run):
        mock_run.side_effect = [
            GitError("git push failed: stale info"),
            None,  # fetch
            None,  # retry push
        ]
        push_force_with_lease(["branch-a"])
        assert mock_run.call_args_list == [
            call(["push", "--force-with-lease", "origin", "branch-a"]),
            call(["fetch", "origin", "branch-a"]),
            call(["push", "--force-with-lease", "origin", "branch-a"]),
        ]

    @patch("spectrum.git._run")
    def test_retries_on_rejected(self, mock_run):
        mock_run.side_effect = [
            GitError("git push failed: rejected"),
            None,  # fetch
            None,  # retry push
        ]
        push_force_with_lease(["branch-a"])
        assert mock_run.call_args_list == [
            call(["push", "--force-with-lease", "origin", "branch-a"]),
            call(["fetch", "origin", "branch-a"]),
            call(["push", "--force-with-lease", "origin", "branch-a"]),
        ]

    @patch("spectrum.git._run")
    def test_on_retry_callback_invoked(self, mock_run):
        mock_run.side_effect = [
            GitError("git push failed: stale info"),
            None,
            None,
        ]
        callback = MagicMock()
        push_force_with_lease(["branch-a"], on_retry=callback)
        callback.assert_called_once_with("branch-a")

    @patch("spectrum.git._run")
    def test_non_rejection_error_raises_immediately(self, mock_run):
        mock_run.side_effect = GitError("git push failed: permission denied")
        with pytest.raises(GitError, match="permission denied"):
            push_force_with_lease(["branch-a"])
        # Only one call — no fetch or retry
        mock_run.assert_called_once()

    @patch("spectrum.git._run")
    def test_second_push_failure_raises(self, mock_run):
        mock_run.side_effect = [
            GitError("git push failed: stale info"),
            None,  # fetch succeeds
            GitError("git push failed: still rejected"),
        ]
        with pytest.raises(GitError, match="still rejected"):
            push_force_with_lease(["branch-a"])

    @patch("spectrum.git._run")
    def test_retries_per_branch(self, mock_run):
        """Each branch is retried independently."""
        mock_run.side_effect = [
            None,  # branch-a succeeds
            GitError("git push failed: rejected"),  # branch-b fails
            None,  # fetch branch-b
            None,  # retry branch-b
        ]
        push_force_with_lease(["branch-a", "branch-b"])
        assert mock_run.call_args_list == [
            call(["push", "--force-with-lease", "origin", "branch-a"]),
            call(["push", "--force-with-lease", "origin", "branch-b"]),
            call(["fetch", "origin", "branch-b"]),
            call(["push", "--force-with-lease", "origin", "branch-b"]),
        ]
