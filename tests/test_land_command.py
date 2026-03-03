from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.git import GitError
from spectrum.github import GhError
from spectrum.stack import StackEntry


class TestPrMerge:
    @patch("spectrum.github._run_gh", autospec=True)
    def test_calls_gh_pr_merge(self, mock_run_gh):
        from spectrum.github import pr_merge

        pr_merge(100, method="squash")
        mock_run_gh.assert_called_once_with(
            ["pr", "merge", "100", "--squash", "--delete-branch"]
        )

    @patch("spectrum.github._run_gh", autospec=True)
    def test_calls_gh_pr_merge_with_merge_method(self, mock_run_gh):
        from spectrum.github import pr_merge

        pr_merge(100, method="merge")
        mock_run_gh.assert_called_once_with(
            ["pr", "merge", "100", "--merge", "--delete-branch"]
        )


class TestLandCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_happy_path(self, mock_stack, mock_github, mock_git):
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
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_stack.extract_letter.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["land", "-y"])

        assert result.exit_code == 0
        assert "Merging" in result.output
        assert "PR #100" in result.output
        mock_github.pr_merge.assert_called_once_with(100, method="squash")
        mock_stack.remove_entry.assert_called_once_with("user/msg-3391-foo/a")
        mock_stack.reindex_stack.assert_called_once_with("msg-3391")

    @patch("spectrum.cli.stack", autospec=True)
    def test_land_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["land"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_no_pr_number(self, mock_stack, mock_github, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=None,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]

        runner = CliRunner()
        result = runner.invoke(main, ["land"])

        assert result.exit_code != 0
        assert "No PR found" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_single_entry_stack(self, mock_stack, mock_github, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]

        runner = CliRunner()
        result = runner.invoke(main, ["land", "-y"])

        assert result.exit_code == 0
        assert "All parts landed" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_with_merge_method(self, mock_stack, mock_github, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]

        runner = CliRunner()
        result = runner.invoke(main, ["land", "-y", "--method", "merge"])

        assert result.exit_code == 0
        mock_github.pr_merge.assert_called_once_with(100, method="merge")

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_gh_error(self, mock_stack, mock_github, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_github.pr_merge.side_effect = GhError("merge failed")

        runner = CliRunner()
        result = runner.invoke(main, ["land", "-y"])

        assert result.exit_code != 0
        assert "merge failed" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_land_retargets_successor_to_master(self, mock_stack, mock_github, mock_git):
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
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_stack.extract_letter.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["land", "-y"])

        assert result.exit_code == 0
        # Verify successor was retargeted to master
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/b", "gh-merge-base", "master"
        )
