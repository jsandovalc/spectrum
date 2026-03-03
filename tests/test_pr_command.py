from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.github import GhError
from spectrum.stack import StackEntry


class TestPrViewWeb:
    @patch("spectrum.github._run_gh", autospec=True)
    def test_calls_gh_pr_view_web(self, mock_run_gh):
        from spectrum.github import pr_view_web

        pr_view_web("user/msg-3391-foo/a")
        mock_run_gh.assert_called_once_with(
            ["pr", "view", "user/msg-3391-foo/a", "--web"]
        )


class TestPrCommand:
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_pr_opens_browser(self, mock_stack, mock_github):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["pr"])

        assert result.exit_code == 0
        assert "Opening PR #100 for [a]" in result.output
        mock_github.pr_view_web.assert_called_once_with("user/msg-3391-foo/a")

    @patch("spectrum.cli.stack", autospec=True)
    def test_pr_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["pr"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.stack", autospec=True)
    def test_pr_no_pr_number(self, mock_stack):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=None,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["pr"])

        assert result.exit_code != 0
        assert "No PR found" in result.output
        assert "spectrum submit" in result.output

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_pr_gh_error(self, mock_stack, mock_github):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry
        mock_github.pr_view_web.side_effect = GhError("browser failed")

        runner = CliRunner()
        result = runner.invoke(main, ["pr"])

        assert result.exit_code != 0
        assert "browser failed" in result.output

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_pr_alias_o(self, mock_stack, mock_github):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["o"])

        assert result.exit_code == 0
        assert "Opening PR #100" in result.output
        mock_github.pr_view_web.assert_called_once()
