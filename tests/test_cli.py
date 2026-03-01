from unittest.mock import patch, call

from click.testing import CliRunner

from spectrum.cli import main, _get_title, _build_stack_table_entries, AliasGroup
from spectrum.git import GitError
from spectrum.github import GhError
from spectrum.stack import StackEntry


class TestAliasGroup:
    def test_st_resolves_to_status(self):
        group = AliasGroup()
        assert group.ALIASES["st"] == "status"

    def test_sw_resolves_to_switch(self):
        group = AliasGroup()
        assert group.ALIASES["sw"] == "switch"

    def test_aliases_not_in_list_commands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        # Aliases should not appear as separate commands in help
        assert "  st " not in result.output
        assert "  sw " not in result.output
        # But real commands should
        assert "status" in result.output
        assert "switch" in result.output

    def test_help_shows_aliases_inline(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "status (st)" in result.output
        assert "switch (sw)" in result.output

    @patch("spectrum.cli.git")
    @patch("spectrum.cli.stack")
    def test_st_invokes_status(self, mock_stack, mock_git):
        mock_stack.current_stack.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["st"])

        # Should fail with the "Not on a spectrum branch" error, proving status ran
        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestCreateCommand:
    def test_creates_stack(self, mock_stack, mock_git):
        mock_stack.extract_stack_id.return_value = "msg-3391"
        mock_git.branch_exists.return_value = False

        runner = CliRunner()
        result = runner.invoke(main, ["create", "user/msg-3391-description"])

        assert result.exit_code == 0
        assert "msg-3391" in result.output
        assert "[a]" in result.output
        mock_git.fetch.assert_called_once_with("origin", "master")
        mock_git.create_branch.assert_called_once_with(
            "user/msg-3391-description/a", "origin/master"
        )
        mock_stack.write_entry.assert_called_once()

    def test_rejects_missing_ticket_id(self, mock_stack, mock_git):
        mock_stack.extract_stack_id.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["create", "no-ticket"])

        assert result.exit_code != 0
        assert "Could not extract ticket ID" in result.output

    def test_rejects_existing_branch(self, mock_stack, mock_git):
        mock_stack.extract_stack_id.return_value = "msg-1"
        mock_git.branch_exists.return_value = True

        runner = CliRunner()
        result = runner.invoke(main, ["create", "user/msg-1-foo"])

        assert result.exit_code != 0
        assert "already exists" in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestAddCommand:
    def test_adds_part(self, mock_stack, mock_git):
        current = StackEntry(
            branch="user/msg-1-foo/a", index=0, stack_id="msg-1", merge_base="master"
        )
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = [current]
        mock_stack.next_letter.return_value = "b"
        mock_stack.extract_base_branch.return_value = "user/msg-1-foo"
        mock_git.branch_exists.return_value = False

        runner = CliRunner()
        result = runner.invoke(main, ["add"])

        assert result.exit_code == 0
        assert "[b]" in result.output
        mock_git.create_branch.assert_called_once_with(
            "user/msg-1-foo/b", "user/msg-1-foo/a"
        )

    def test_not_on_spectrum_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["add"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.github")
@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestStatusCommand:
    def test_shows_stack(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=100,
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/b"
        mock_stack.extract_letter.side_effect = lambda b: (
            "a" if b.endswith("/a") else None
        )
        mock_git.diff_shortstat.return_value = "+10 -2, 1 file"

        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "msg-1" in result.output
        assert "[a]" in result.output
        assert "[b]" in result.output
        assert "you are here" in result.output
        assert "PR #100" in result.output

    def test_not_on_spectrum_branch(self, mock_stack, mock_git, mock_github):
        mock_stack.current_stack.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code != 0

    def test_shows_pr_url(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=100,
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_stack.extract_letter.return_value = None
        mock_git.diff_shortstat.return_value = "+10 -2, 1 file"
        mock_github.get_repo_url.return_value = "https://github.com/org/repo"

        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "https://github.com/org/repo/pull/100" in result.output

    def test_shows_pr_number_without_url_when_get_repo_url_fails(
        self, mock_stack, mock_git, mock_github
    ):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=100,
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_stack.extract_letter.return_value = None
        mock_git.diff_shortstat.return_value = "+10 -2, 1 file"
        mock_github.get_repo_url.side_effect = GhError("gh not found")

        runner = CliRunner()
        result = runner.invoke(main, ["status"])

        assert result.exit_code == 0
        assert "PR #100" in result.output
        assert "https://" not in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestSwitchCommand:
    def test_switches_to_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        mock_stack.current_stack.return_value = entries
        mock_stack.letter_to_index.return_value = 0

        runner = CliRunner()
        result = runner.invoke(main, ["switch", "a"])

        assert result.exit_code == 0
        assert "Switched to [a]" in result.output
        mock_git.checkout.assert_called_once_with("user/msg-1/a")

    def test_invalid_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
        ]
        mock_stack.current_stack.return_value = entries
        mock_stack.letter_to_index.return_value = 5

        runner = CliRunner()
        result = runner.invoke(main, ["switch", "f"])

        assert result.exit_code != 0
        assert "not found" in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestNextCommand:
    def test_moves_to_next_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries

        runner = CliRunner()
        result = runner.invoke(main, ["next"])

        assert result.exit_code == 0
        assert "[b]" in result.output
        mock_git.checkout.assert_called_once_with("user/msg-1/b")

    def test_errors_on_last_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[1]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries

        runner = CliRunner()
        result = runner.invoke(main, ["next"])

        assert result.exit_code != 0
        assert "last part" in result.output

    def test_not_on_spectrum_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["next"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestPrevCommand:
    def test_moves_to_prev_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[1]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries

        runner = CliRunner()
        result = runner.invoke(main, ["prev"])

        assert result.exit_code == 0
        assert "[a]" in result.output
        mock_git.checkout.assert_called_once_with("user/msg-1/a")

    def test_errors_on_first_part(self, mock_stack, mock_git):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries

        runner = CliRunner()
        result = runner.invoke(main, ["prev"])

        assert result.exit_code != 0
        assert "first part" in result.output

    def test_not_on_spectrum_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["prev"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestAdoptCommand:
    def test_adopts_branches(self, mock_stack, mock_git):
        mock_git.branch_exists.return_value = True
        mock_stack.extract_stack_id.return_value = "msg-1"
        mock_stack.read_entry.return_value = None
        mock_stack.index_to_letter.side_effect = lambda i: chr(ord("a") + i)

        runner = CliRunner()
        result = runner.invoke(
            main, ["adopt", "user/msg-1-foo/a", "user/msg-1-foo/b"]
        )

        assert result.exit_code == 0
        assert "Adopted 2 branches" in result.output
        assert mock_stack.write_entry.call_count == 2

    def test_rejects_nonexistent_branch(self, mock_stack, mock_git):
        mock_git.branch_exists.return_value = False
        mock_stack.extract_stack_id.return_value = "msg-1"

        runner = CliRunner()
        result = runner.invoke(main, ["adopt", "nonexistent"])

        assert result.exit_code != 0
        assert "does not exist" in result.output


@patch("spectrum.cli.github")
@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestSyncCommand:
    def test_on_first_part_rebases_all(self, mock_stack, mock_git, mock_github):
        """On [a], sync rebases the entire stack."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base.return_value = "abc123"

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        assert "Rebasing [a]" in result.output
        assert "Rebasing [b]" in result.output
        assert mock_git.rebase_onto.call_count == 2
        mock_git.push_force_with_lease.assert_called_once()

    def test_on_second_part_rebases_from_b(self, mock_stack, mock_git, mock_github):
        """On [b], sync only rebases [b] onward."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
            StackEntry(branch="user/msg-1/c", index=2, stack_id="msg-1", merge_base="user/msg-1/b"),
        ]
        current = entries[1]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/b"
        mock_git.merge_base.return_value = "abc123"

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        assert "Rebasing [a]" not in result.output
        assert "Rebasing [b]" in result.output
        assert "Rebasing [c]" in result.output
        assert mock_git.rebase_onto.call_count == 2

    def test_no_push_flag(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base.return_value = "abc123"

        runner = CliRunner()
        result = runner.invoke(main, ["sync", "--no-push"])

        assert result.exit_code == 0
        assert "Skipping push" in result.output
        mock_git.push_force_with_lease.assert_not_called()

    def test_not_on_spectrum_branch(self, mock_stack, mock_git, mock_github):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    def test_conflict_message_says_spectrum_sync(self, mock_stack, mock_git, mock_github):
        from spectrum.git import RebaseConflictError

        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base.return_value = "abc123"
        mock_git.rebase_onto.side_effect = RebaseConflictError("user/msg-1/a", "origin/master")

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert "spectrum sync" in result.output

    def test_uses_pre_rebase_tip_for_second_branch(self, mock_stack, mock_git, mock_github):
        """When rebasing a→b, rebase_onto for b uses a's pre-rebase tip, not merge_base."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/a"
        mock_git.merge_base.return_value = "merge-base-sha"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.rev_parse.side_effect = lambda ref: {
            "user/msg-1/a": "tip-a-before-rebase",
            "user/msg-1/b": "tip-b-before-rebase",
        }[ref]

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        # [a] should use merge_base (no saved tip for "master")
        assert mock_git.rebase_onto.call_args_list[0] == call(
            "user/msg-1/a", "origin/master", "merge-base-sha"
        )
        # [b] should use a's pre-rebase tip, NOT merge_base
        assert mock_git.rebase_onto.call_args_list[1] == call(
            "user/msg-1/b", "user/msg-1/a", "tip-a-before-rebase"
        )
        # merge_base should only be called once (for [a]), not for [b]
        mock_git.merge_base.assert_called_once()

    def test_uses_fork_point_when_starting_mid_stack(self, mock_stack, mock_git, mock_github):
        """On [b] only, fork_point finds where b forked from a (handles prior rebase of a)."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[1]  # on [b]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/b"
        mock_git.merge_base_fork_point.return_value = "fork-point-sha"
        mock_git.rev_parse.return_value = "tip-b-before-rebase"

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        # Should use fork_point, not merge_base
        mock_git.merge_base_fork_point.assert_called_once_with("user/msg-1/a", "user/msg-1/b")
        mock_git.merge_base.assert_not_called()
        assert mock_git.rebase_onto.call_args_list[0] == call(
            "user/msg-1/b", "user/msg-1/a", "fork-point-sha"
        )

    def test_falls_back_to_merge_base_when_fork_point_unavailable(self, mock_stack, mock_git, mock_github):
        """When fork_point returns None (no reflog), falls back to merge_base."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[1]  # on [b]
        mock_stack.current_entry.return_value = current
        mock_stack.get_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1/b"
        mock_git.merge_base_fork_point.return_value = None
        mock_git.merge_base.return_value = "merge-base-sha"
        mock_git.rev_parse.return_value = "tip-b"

        runner = CliRunner()
        result = runner.invoke(main, ["sync"])

        assert result.exit_code == 0
        assert mock_git.rebase_onto.call_args_list[0] == call(
            "user/msg-1/b", "user/msg-1/a", "merge-base-sha"
        )


@patch("spectrum.cli.git")
@patch("spectrum.cli.stack")
class TestDropCommand:
    def test_drop_middle_relinks_chain(self, mock_stack, mock_git):
        """Dropping [b] from a-b-c should retarget [c] to [a]."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
            StackEntry(branch="user/msg-1/c", index=2, stack_id="msg-1", merge_base="user/msg-1/b"),
        ]
        current = entries[1]  # on [b]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.side_effect = lambda b: (
            {"user/msg-1/a": "a", "user/msg-1/b": "b", "user/msg-1/c": "c"}.get(b)
        )

        runner = CliRunner()
        result = runner.invoke(main, ["drop"])

        assert result.exit_code == 0
        # Should retarget [c]'s merge_base to [a]
        mock_git.set_branch_config.assert_any_call(
            "user/msg-1/c", "gh-merge-base", "user/msg-1/a"
        )
        mock_stack.remove_entry.assert_called_once_with("user/msg-1/b")
        mock_stack.reindex_stack.assert_called_once_with("msg-1")
        # Should checkout adjacent part
        mock_git.checkout.assert_called()

    def test_drop_current_switches_to_prev(self, mock_stack, mock_git):
        """Dropping current part when there's a previous part checks out previous."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[1]  # on [b]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["drop"])

        assert result.exit_code == 0
        mock_git.checkout.assert_called_with("user/msg-1/a")

    def test_drop_first_part_switches_to_next(self, mock_stack, mock_git):
        """Dropping [a] when [b] exists checks out [b]."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
        ]
        current = entries[0]  # on [a]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.return_value = None
        mock_stack.letter_to_index.return_value = 0

        runner = CliRunner()
        result = runner.invoke(main, ["drop", "a"])

        assert result.exit_code == 0
        mock_git.checkout.assert_called_with("user/msg-1/b")

    def test_drop_only_part_clears_stack(self, mock_stack, mock_git):
        """Dropping the only part in the stack."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
        ]
        current = entries[0]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["drop"])

        assert result.exit_code == 0
        mock_stack.remove_entry.assert_called_once_with("user/msg-1/a")
        assert "Dropped" in result.output

    def test_drop_by_letter_arg(self, mock_stack, mock_git):
        """Drop a specific part by letter argument."""
        entries = [
            StackEntry(branch="user/msg-1/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="user/msg-1/b", index=1, stack_id="msg-1", merge_base="user/msg-1/a"),
            StackEntry(branch="user/msg-1/c", index=2, stack_id="msg-1", merge_base="user/msg-1/b"),
        ]
        current = entries[0]  # on [a]
        mock_stack.current_entry.return_value = current
        mock_stack.current_stack.return_value = entries
        mock_stack.letter_to_index.return_value = 1
        mock_stack.extract_letter.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["drop", "b"])

        assert result.exit_code == 0
        mock_stack.remove_entry.assert_called_once_with("user/msg-1/b")

    def test_not_on_spectrum_branch(self, mock_stack, mock_git):
        mock_stack.current_entry.return_value = None

        runner = CliRunner()
        result = runner.invoke(main, ["drop"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.git", autospec=True)
@patch("spectrum.cli.stack", autospec=True)
class TestGetTitle:
    def test_uses_spectrum_title_when_set(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-1-foo/a", index=0, stack_id="msg-1", merge_base="master"
        )
        mock_git.get_branch_config.return_value = "My explicit title"
        mock_stack.format_pr_title.return_value = "MSG-1 [a]: My explicit title"

        result = _get_title(entry)

        assert result == "MSG-1 [a]: My explicit title"
        mock_stack.format_pr_title.assert_called_once_with("msg-1", "a", "My explicit title")
        mock_git.log_subjects.assert_not_called()

    def test_falls_back_to_first_commit_subject(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-1-foo/a", index=0, stack_id="msg-1", merge_base="master"
        )
        mock_git.get_branch_config.return_value = None
        mock_git.log_subjects.return_value = ["Set response kind to handoff", "Fix typo"]
        mock_stack.format_pr_title.return_value = "MSG-1 [a]: Set response kind to handoff"

        result = _get_title(entry)

        assert result == "MSG-1 [a]: Set response kind to handoff"
        mock_git.log_subjects.assert_called_once_with("master", "user/msg-1-foo/a")
        mock_stack.format_pr_title.assert_called_once_with(
            "msg-1", "a", "Set response kind to handoff"
        )

    def test_no_title_and_no_commits(self, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-1-foo/a", index=0, stack_id="msg-1", merge_base="master"
        )
        mock_git.get_branch_config.return_value = None
        mock_git.log_subjects.return_value = []
        mock_stack.format_pr_title.return_value = "MSG-1 [a]"

        result = _get_title(entry)

        assert result == "MSG-1 [a]"
        mock_stack.format_pr_title.assert_called_once_with("msg-1", "a", None)


@patch("spectrum.cli.git", autospec=True)
@patch("spectrum.cli.stack", autospec=True)
@patch("spectrum.cli.github", autospec=True)
class TestSubmitAssignee:
    def test_pr_create_passes_assignee(self, mock_github, mock_stack, mock_git):
        entry = StackEntry(
            branch="user/msg-1-foo/a",
            index=0,
            stack_id="msg-1",
            merge_base="master",
        )
        mock_stack.current_stack.return_value = [entry]
        mock_stack.format_pr_title.return_value = "MSG-1 [a]"
        mock_stack.extract_letter.return_value = None
        mock_git.get_branch_config.return_value = None
        mock_git.log_subjects.return_value = ["Initial commit"]
        mock_github.read_pr_template.return_value = None
        mock_github.get_repo_url.return_value = "https://github.com/user/repo"
        mock_github.pr_create.return_value = 42
        mock_github.pr_view.return_value = {
            "body": "", "isDraft": True, "number": 42,
        }

        runner = CliRunner()
        result = runner.invoke(main, ["submit", "--draft"])

        assert result.exit_code == 0
        mock_github.pr_create.assert_called_once()
        create_kwargs = mock_github.pr_create.call_args.kwargs
        assert create_kwargs["title"] == "MSG-1 [a]"
        assert create_kwargs["base"] == "master"
        assert create_kwargs["head"] == "user/msg-1-foo/a"
        assert create_kwargs["draft"] is True
        assert "https://github.com/user/repo/pull/42" in result.output


@patch("spectrum.cli.github", autospec=True)
@patch("spectrum.cli.git", autospec=True)
@patch("spectrum.cli.stack", autospec=True)
class TestSubmitEmptyBranchCheck:
    def test_rejects_branch_with_no_commits(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.return_value = None
        mock_github.get_repo_url.return_value = "https://github.com/user/repo"
        mock_github.read_pr_template.return_value = None
        mock_git.log_subjects.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["submit"])

        assert result.exit_code != 0
        assert "No commits found" in result.output
        assert "Did you forget to commit" in result.output
        mock_github.pr_create.assert_not_called()

    def test_only_checks_branches_without_pr(self, mock_stack, mock_git, mock_github):
        """Branches that already have a PR are skipped in the empty check."""
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=42,
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_stack.extract_letter.return_value = None
        mock_github.get_repo_url.return_value = "https://github.com/user/repo"
        mock_github.read_pr_template.return_value = None
        mock_git.log_subjects.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["submit"])

        assert result.exit_code != 0
        assert "[b]" in result.output
        assert "[a]" not in result.output


@patch("spectrum.cli.github", autospec=True)
@patch("spectrum.cli.git", autospec=True)
@patch("spectrum.cli.stack", autospec=True)
class TestLogCommand:
    def test_not_on_spectrum_branch(self, mock_stack, mock_git, mock_github):
        mock_stack.current_stack.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output

    def test_single_entry_shows_branch(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_github.pr_view.side_effect = GhError("no pr")
        mock_git.diff_shortstat.side_effect = GitError("fail")

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        assert "msg-1" in result.output
        assert "[a]" in result.output
        assert "user/msg-1-foo/a" in result.output

    def test_current_branch_marker(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/b"
        mock_github.pr_view.side_effect = GhError("no pr")
        mock_git.diff_shortstat.side_effect = GitError("fail")

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        # Current branch gets ● and "you are here"
        assert "● [b] user/msg-1-foo/b" in result.output
        assert "you are here" in result.output
        # Non-current branch gets ○
        assert "○ [a] user/msg-1-foo/a" in result.output

    def test_shows_pr_info_and_draft(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=101,
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_github.pr_view.return_value = {"isDraft": True}
        mock_git.diff_shortstat.side_effect = GitError("fail")

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        assert "PR #101" in result.output
        assert "(draft)" in result.output

    def test_shows_diff_stats(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
                pr_number=101,
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_github.pr_view.return_value = {"isDraft": False}
        mock_git.diff_shortstat.return_value = "+22 -5, 2 files"

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        assert "+22 -5, 2 files" in result.output

    def test_newest_at_top(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/a"
        mock_github.pr_view.side_effect = GhError("no pr")
        mock_git.diff_shortstat.side_effect = GitError("fail")

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        assert result.exit_code == 0
        # [b] (tip) should appear before [a] (base) in the output
        b_pos = result.output.index("[b]")
        a_pos = result.output.index("[a]")
        assert b_pos < a_pos

    def test_connecting_lines(self, mock_stack, mock_git, mock_github):
        entries = [
            StackEntry(
                branch="user/msg-1-foo/a",
                index=0,
                stack_id="msg-1",
                merge_base="master",
            ),
            StackEntry(
                branch="user/msg-1-foo/b",
                index=1,
                stack_id="msg-1",
                merge_base="user/msg-1-foo/a",
            ),
        ]
        mock_stack.current_stack.return_value = entries
        mock_git.current_branch.return_value = "user/msg-1-foo/b"
        mock_github.pr_view.side_effect = GhError("no pr")
        mock_git.diff_shortstat.side_effect = GitError("fail")

        runner = CliRunner()
        result = runner.invoke(main, ["log"])

        lines = result.output.splitlines()
        assert result.exit_code == 0
        # There should be a │ connector line between [b] and [a]
        assert any(line.strip() == "│" for line in lines)
        # The last entry ([a], at bottom) should NOT have a │ after it
        # Find the line with [a] and check nothing with │ follows
        a_line_idx = next(i for i, l in enumerate(lines) if "[a]" in l)
        remaining = lines[a_line_idx + 1:]
        assert not any("│" in line for line in remaining)

    def test_lg_alias(self, mock_stack, mock_git, mock_github):
        mock_stack.current_stack.return_value = []

        runner = CliRunner()
        result = runner.invoke(main, ["lg"])

        assert result.exit_code != 0
        assert "Not on a spectrum branch" in result.output


@patch("spectrum.cli.github", autospec=True)
@patch("spectrum.cli.git", autospec=True)
class TestBuildStackTableEntries:
    def test_falls_back_to_pr_title_when_config_empty(self, mock_git, mock_github):
        entry = StackEntry(
            branch="user/msg-1-foo/a",
            index=0,
            stack_id="msg-1",
            merge_base="master",
            pr_number=100,
        )
        mock_git.get_branch_config.return_value = None
        mock_github.pr_view.return_value = {
            "title": "MSG-1 [a]: My PR title",
            "isDraft": True,
            "number": 100,
        }

        result = _build_stack_table_entries([entry])

        assert result[0]["title"] == "MSG-1 [a]: My PR title"
