from unittest.mock import patch

from click.testing import CliRunner

from spectrum.cli import main
from spectrum.stack import StackEntry


class TestWipCommand:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_wip_on(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            wip=False,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["wip", "on"])

        assert result.exit_code == 0
        assert "marked as WIP" in result.output
        mock_git.set_branch_config.assert_called_once_with(
            "user/msg-3391-foo/a", "spectrum-wip", "true"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_wip_off(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            wip=True,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["wip", "off"])

        assert result.exit_code == 0
        assert "no longer WIP" in result.output
        mock_git.unset_branch_config.assert_called_once_with(
            "user/msg-3391-foo/a", "spectrum-wip"
        )

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_wip_toggle_on(self, mock_stack, mock_git):
        """When no argument, toggle from off to on."""
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            wip=False,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["wip"])

        assert result.exit_code == 0
        assert "marked as WIP" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_wip_toggle_off(self, mock_stack, mock_git):
        """When no argument, toggle from on to off."""
        entry = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            wip=True,
        )
        mock_stack.current_entry.return_value = entry

        runner = CliRunner()
        result = runner.invoke(main, ["wip"])

        assert result.exit_code == 0
        assert "no longer WIP" in result.output

    @patch("spectrum.cli.stack", autospec=True)
    def test_wip_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["wip"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


class TestSubmitSkipsWip:
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_submit_skips_wip_entries(self, mock_stack, mock_github, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
            pr_number=100,
            wip=False,
        )
        entry_b = StackEntry(
            branch="user/msg-3391-foo/b",
            index=1,
            stack_id="msg-3391",
            merge_base="user/msg-3391-foo/a",
            pr_number=None,
            wip=True,
        )
        mock_stack.current_stack.return_value = [entry_a, entry_b]
        mock_stack.extract_letter.return_value = None
        mock_github.get_repo_url.return_value = "https://github.com/org/repo"
        mock_github.read_pr_template.return_value = ""
        mock_github.pr_view.return_value = {
            "body": "", "title": "t", "isDraft": False,
        }
        mock_git.get_branch_config.return_value = ""

        runner = CliRunner()
        result = runner.invoke(main, ["submit"])

        assert result.exit_code == 0
        assert "Skipping [b] (WIP)" in result.output
        # Only entry_a's branch should be pushed
        mock_git.push_force_with_lease.assert_called_once_with(
            ["user/msg-3391-foo/a"]
        )
        # PR should not be created for WIP entry
        mock_github.pr_create.assert_not_called()


class TestReadEntryWip:
    @patch("spectrum.stack.git", autospec=True)
    def test_reads_wip_true(self, mock_git):
        from spectrum.stack import read_entry

        mock_git.get_branch_config.side_effect = lambda branch, key: {
            ("x/a", "spectrum-stack"): "msg-1",
            ("x/a", "spectrum-index"): "0",
            ("x/a", "gh-merge-base"): "master",
            ("x/a", "spectrum-pr"): None,
            ("x/a", "spectrum-wip"): "true",
        }.get((branch, key))

        entry = read_entry("x/a")
        assert entry is not None
        assert entry.wip is True

    @patch("spectrum.stack.git", autospec=True)
    def test_reads_wip_false_when_absent(self, mock_git):
        from spectrum.stack import read_entry

        mock_git.get_branch_config.side_effect = lambda branch, key: {
            ("x/a", "spectrum-stack"): "msg-1",
            ("x/a", "spectrum-index"): "0",
            ("x/a", "gh-merge-base"): "master",
            ("x/a", "spectrum-pr"): None,
            ("x/a", "spectrum-wip"): None,
        }.get((branch, key))

        entry = read_entry("x/a")
        assert entry is not None
        assert entry.wip is False
