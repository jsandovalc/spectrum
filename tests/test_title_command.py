from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.github import GhError
from spectrum.stack import StackEntry


class TestPrEditTitle:
    @patch("subprocess.run", autospec=True)
    def test_calls_gh_api_patch(self, mock_run):
        from spectrum.github import pr_edit_title

        pr_edit_title(100, "New Title")
        mock_run.assert_called_once_with(
            ["gh", "api", "repos/{owner}/{repo}/pulls/100",
             "--method", "PATCH", "--input", "-"],
            input='{"title": "New Title"}',
            check=True, capture_output=True, text=True,
        )


class TestTitleCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_updates_pr(self, mock_stack, mock_github, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: My new title"
        mock_stack.get_stack.return_value = [entry]
        mock_github.get_repo_url.return_value = "https://github.com/org/repo"
        mock_github.pr_view.return_value = {
            "body": "", "title": "t", "isDraft": False,
        }

        runner = CliRunner()
        result = runner.invoke(main, ["title", "My new title"])

        assert result.exit_code == 0
        assert "Updated PR #100" in result.output
        assert "MSG-3391 [a]: My new title" in result.output
        mock_git.set_branch_config.assert_called_once_with(
            "user/msg-3391-foo/a", "spectrum-title", "My new title"
        )
        mock_github.pr_edit_title.assert_called_once_with(
            100, "MSG-3391 [a]: My new title"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_saves_without_pr(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=None,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: My title"

        runner = CliRunner()
        result = runner.invoke(main, ["title", "My title"])

        assert result.exit_code == 0
        assert "Title saved" in result.output
        assert "next submit" in result.output
        mock_git.set_branch_config.assert_called_once_with(
            "user/msg-3391-foo/a", "spectrum-title", "My title"
        )

    @patch("spectrum.cli.stack", autospec=True)
    def test_title_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["title", "My title"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_gh_error(self, mock_stack, mock_github, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: title"
        mock_github.pr_edit_title.side_effect = GhError("edit failed")

        runner = CliRunner()
        result = runner.invoke(main, ["title", "title"])

        assert result.exit_code != 0
        assert "edit failed" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_formats_correctly(self, mock_stack, mock_github, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=101,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [b]: Fix bug"
        mock_stack.get_stack.return_value = [entry]
        mock_github.get_repo_url.return_value = "https://github.com/org/repo"
        mock_github.pr_view.return_value = {
            "body": "", "title": "t", "isDraft": False,
        }

        runner = CliRunner()
        result = runner.invoke(main, ["title", "Fix bug"])

        assert result.exit_code == 0
        mock_stack.format_pr_title.assert_called_once_with("msg-3391", "b", "Fix bug")

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_updates_stack_tables_in_sibling_prs(self, mock_stack, mock_github, mock_git):
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
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: New title"
        mock_stack.get_stack.return_value = [entry_a, entry_b]
        mock_github.get_repo_url.return_value = "https://github.com/org/repo"
        mock_github.pr_view.return_value = {
            "body": "existing body", "title": "t", "isDraft": False,
        }

        runner = CliRunner()
        result = runner.invoke(main, ["title", "New title"])

        assert result.exit_code == 0
        mock_stack.get_stack.assert_called_once_with("msg-3391")
        mock_github.get_repo_url.assert_called_once()
        # pr_edit_body called for both PRs in the stack
        assert mock_github.pr_edit_body.call_count == 2

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_no_table_update_without_pr(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=None,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: My title"

        runner = CliRunner()
        result = runner.invoke(main, ["title", "My title"])

        assert result.exit_code == 0
        assert "Title saved" in result.output
        mock_stack.get_stack.assert_not_called()

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_title_table_update_failure_does_not_fail_command(self, mock_stack, mock_github, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry
        mock_stack.format_pr_title.return_value = "MSG-3391 [a]: title"
        mock_github.get_repo_url.side_effect = GhError("network error")

        runner = CliRunner()
        result = runner.invoke(main, ["title", "title"])

        assert result.exit_code == 0
        assert "Updated PR #100" in result.output
