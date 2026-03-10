from unittest.mock import patch, call

from click.testing import CliRunner

from spectrum.cli import AliasGroup, main
from spectrum.stack import StackEntry


class TestCreateBranchAt:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_branch(self, mock_run):
        from spectrum.git import create_branch_at

        create_branch_at("new-branch", "abc1234")
        mock_run.assert_called_once_with(["branch", "new-branch", "abc1234"])


class TestResetHard:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_reset_hard(self, mock_run):
        from spectrum.git import reset_hard

        reset_hard("abc1234")
        mock_run.assert_called_once_with(["reset", "--hard", "abc1234"])


class TestLogOneline:
    @patch("spectrum.git._run", autospec=True)
    def test_calls_git_log_oneline(self, mock_run):
        from spectrum.git import log_oneline

        mock_run.return_value.stdout = "abc1234 First commit\ndef5678 Second commit\n"
        result = log_oneline("base", "head")
        mock_run.assert_called_once_with(
            ["log", "--oneline", "--reverse", "base..head"]
        )
        assert result == [("abc1234", "First commit"), ("def5678", "Second commit")]

    @patch("spectrum.git._run", autospec=True)
    def test_empty_output(self, mock_run):
        from spectrum.git import log_oneline

        mock_run.return_value.stdout = ""
        result = log_oneline("base", "head")
        assert result == []


class TestInsertEntry:
    @patch("spectrum.stack.git", autospec=True)
    def test_shifts_entries_after_index(self, mock_git):
        from spectrum.stack import insert_entry

        mock_git.all_local_branches.return_value = [
            "user/msg-3391-foo/a",
            "user/msg-3391-foo/b",
            "user/msg-3391-foo/c",
        ]

        def config_side_effect(branch, key):
            configs = {
                ("user/msg-3391-foo/a", "spectrum-stack"): "msg-3391",
                ("user/msg-3391-foo/a", "spectrum-index"): "0",
                ("user/msg-3391-foo/a", "gh-merge-base"): "master",
                ("user/msg-3391-foo/a", "spectrum-pr"): None,
                ("user/msg-3391-foo/a", "spectrum-wip"): None,
                ("user/msg-3391-foo/b", "spectrum-stack"): "msg-3391",
                ("user/msg-3391-foo/b", "spectrum-index"): "1",
                ("user/msg-3391-foo/b", "gh-merge-base"): "user/msg-3391-foo/a",
                ("user/msg-3391-foo/b", "spectrum-pr"): None,
                ("user/msg-3391-foo/b", "spectrum-wip"): None,
                ("user/msg-3391-foo/c", "spectrum-stack"): "msg-3391",
                ("user/msg-3391-foo/c", "spectrum-index"): "2",
                ("user/msg-3391-foo/c", "gh-merge-base"): "user/msg-3391-foo/b",
                ("user/msg-3391-foo/c", "spectrum-pr"): None,
                ("user/msg-3391-foo/c", "spectrum-wip"): None,
            }
            return configs.get((branch, key))

        mock_git.get_branch_config.side_effect = config_side_effect

        insert_entry("msg-3391", 0)

        # Only entries with index > 0 should be shifted
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/b", "spectrum-index", "2"
        )
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/c", "spectrum-index", "3"
        )
        # Entry at index 0 should NOT be shifted
        assert call("user/msg-3391-foo/a", "spectrum-index", "1") not in mock_git.set_branch_config.call_args_list


class TestSplitCommand:
    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_happy_path_with_at(self, mock_stack, mock_git, mock_github):
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
        mock_stack.extract_base_branch.return_value = "user/msg-3391-foo"
        mock_stack.next_letter.return_value = "c"
        mock_stack.StackEntry = StackEntry
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
            ("ghi9012", "Third commit"),
        ]
        mock_git.rev_parse.return_value = "def5678full"

        runner = CliRunner()
        result = runner.invoke(main, ["split", "--at", "2"])

        assert result.exit_code == 0, result.output
        assert "Split" in result.output
        mock_git.create_branch_at.assert_called_once_with("user/msg-3391-foo/c", "HEAD")
        mock_git.reset_hard.assert_called_once_with("def5678full")
        mock_stack.insert_entry.assert_called_once_with("msg-3391", 0)
        mock_stack.write_entry.assert_called_once()
        written = mock_stack.write_entry.call_args[0][0]
        assert written.branch == "user/msg-3391-foo/c"
        assert written.index == 1
        assert written.merge_base == "user/msg-3391-foo/a"
        assert written.stack_id == "msg-3391"
        # Successor (entry_b) should be retargeted to new branch
        mock_git.set_branch_config.assert_any_call(
            "user/msg-3391-foo/b", "gh-merge-base", "user/msg-3391-foo/c"
        )

    @patch("spectrum.cli.stack", autospec=True)
    def test_not_on_spectrum_branch(self, mock_stack):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["split"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_only_one_commit(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_git.log_oneline.return_value = [("abc1234", "Only commit")]

        runner = CliRunner()
        result = runner.invoke(main, ["split"])

        assert result.exit_code != 0
        assert "Nothing to split" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_at_out_of_range_too_high(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["split", "--at", "2"])

        assert result.exit_code != 0
        assert "--at must be between 1 and 1" in result.output

    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_at_out_of_range_zero(self, mock_stack, mock_git):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["split", "--at", "0"])

        assert result.exit_code != 0
        assert "--at must be between 1 and 1" in result.output

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_interactive_prompt(self, mock_stack, mock_git, mock_github):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_stack.extract_base_branch.return_value = "user/msg-3391-foo"
        mock_stack.next_letter.return_value = "b"
        mock_stack.StackEntry = StackEntry
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
            ("ghi9012", "Third commit"),
        ]
        mock_git.rev_parse.return_value = "def5678full"

        runner = CliRunner()
        result = runner.invoke(main, ["split"], input="2\n")

        assert result.exit_code == 0, result.output
        assert "Split" in result.output
        assert "First commit" in result.output
        assert "Second commit" in result.output
        assert "Third commit" in result.output
        mock_git.create_branch_at.assert_called_once_with("user/msg-3391-foo/b", "HEAD")
        mock_git.reset_hard.assert_called_once_with("def5678full")

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_no_successor(self, mock_stack, mock_git, mock_github):
        entry_a = StackEntry(
            branch="user/msg-3391-foo/a",
            index=0,
            stack_id="msg-3391",
            merge_base="master",
        )
        mock_stack.current_entry.return_value = entry_a
        mock_stack.get_stack.return_value = [entry_a]
        mock_stack.extract_base_branch.return_value = "user/msg-3391-foo"
        mock_stack.next_letter.return_value = "b"
        mock_stack.StackEntry = StackEntry
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
        ]
        mock_git.rev_parse.return_value = "abc1234full"

        runner = CliRunner()
        result = runner.invoke(main, ["split", "--at", "1"])

        assert result.exit_code == 0, result.output
        assert "Split" in result.output
        # No successor, so set_branch_config should not be called for retargeting
        for c in mock_git.set_branch_config.call_args_list:
            assert c[0][1] != "gh-merge-base"

    @patch("spectrum.cli.github", autospec=True)
    @patch("spectrum.cli.git", autospec=True)
    @patch("spectrum.cli.stack", autospec=True)
    def test_successor_with_pr(self, mock_stack, mock_git, mock_github):
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
        mock_stack.extract_base_branch.return_value = "user/msg-3391-foo"
        mock_stack.next_letter.return_value = "c"
        mock_stack.StackEntry = StackEntry
        mock_git.log_oneline.return_value = [
            ("abc1234", "First commit"),
            ("def5678", "Second commit"),
            ("ghi9012", "Third commit"),
        ]
        mock_git.rev_parse.return_value = "abc1234full"

        runner = CliRunner()
        result = runner.invoke(main, ["split", "--at", "1"])

        assert result.exit_code == 0, result.output
        mock_github.pr_edit_base.assert_called_once_with(101, "user/msg-3391-foo/c")

    def test_split_in_edit_command_group(self):
        assert "split" in AliasGroup.COMMAND_GROUPS["Edit"]
