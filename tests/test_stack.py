from unittest.mock import patch

import pytest

from spectrum.stack import (
    CONFIG_KEYS,
    StackEntry,
    extract_base_branch,
    extract_letter,
    extract_stack_id,
    format_pr_title,
    get_stack,
    index_to_letter,
    letter_to_index,
    next_letter,
    read_entry,
    reindex_stack,
    remove_entry,
    swap_entries,
    write_entry,
)


class TestIndexToLetter:
    def test_zero_returns_a(self):
        assert index_to_letter(0) == "a"

    def test_twenty_five_returns_z(self):
        assert index_to_letter(25) == "z"

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            index_to_letter(-1)

    def test_twenty_six_raises(self):
        with pytest.raises(ValueError, match="out of range"):
            index_to_letter(26)


class TestLetterToIndex:
    def test_a_returns_zero(self):
        assert letter_to_index("a") == 0

    def test_z_returns_twenty_five(self):
        assert letter_to_index("z") == 25

    def test_uppercase(self):
        assert letter_to_index("B") == 1

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid"):
            letter_to_index("ab")


class TestExtractStackId:
    def test_standard_branch(self):
        assert extract_stack_id("user/msg-3391-description/a") == "msg-3391"

    def test_no_letter_suffix(self):
        assert extract_stack_id("user/stay-1234-some-feature") == "stay-1234"

    def test_no_ticket(self):
        assert extract_stack_id("feature/no-ticket-here") is None

    def test_uppercase_ticket(self):
        assert extract_stack_id("user/MSG-100-foo") == "msg-100"


class TestExtractBaseBranch:
    def test_with_letter(self):
        assert extract_base_branch("user/msg-3391-desc/a") == "user/msg-3391-desc"

    def test_with_multi_char_suffix(self):
        assert extract_base_branch("user/msg-3391-desc/ab") is None

    def test_no_slash(self):
        assert extract_base_branch("master") is None


class TestExtractLetter:
    def test_with_letter(self):
        assert extract_letter("user/msg-3391-desc/a") == "a"

    def test_with_b(self):
        assert extract_letter("user/msg-3391-desc/b") == "b"

    def test_no_letter(self):
        assert extract_letter("user/msg-3391-desc") is None

    def test_multi_char(self):
        assert extract_letter("user/msg-3391-desc/ab") is None


class TestNextLetter:
    def test_empty_stack(self):
        assert next_letter([]) == "a"

    def test_one_entry(self):
        entries = [StackEntry(branch="x/a", index=0, stack_id="t-1", merge_base="master")]
        assert next_letter(entries) == "b"

    def test_two_entries(self):
        entries = [
            StackEntry(branch="x/a", index=0, stack_id="t-1", merge_base="master"),
            StackEntry(branch="x/b", index=1, stack_id="t-1", merge_base="x/a"),
        ]
        assert next_letter(entries) == "c"


class TestFormatPrTitle:
    def test_with_message(self):
        assert format_pr_title("msg-3391", "a", "Preserve response kind") == (
            "MSG-3391 [a]: Preserve response kind"
        )

    def test_without_message(self):
        assert format_pr_title("stay-100", "b") == "STAY-100 [b]"

    def test_none_message(self):
        assert format_pr_title("msg-1", "a", None) == "MSG-1 [a]"


class TestReadEntry:
    @patch("spectrum.stack.git")
    def test_returns_entry(self, mock_git):
        mock_git.get_branch_config.side_effect = lambda branch, key: {
            ("x/a", "spectrum-stack"): "msg-1",
            ("x/a", "spectrum-index"): "0",
            ("x/a", "gh-merge-base"): "master",
            ("x/a", "spectrum-pr"): "100",
        }.get((branch, key))

        entry = read_entry("x/a")
        assert entry is not None
        assert entry.stack_id == "msg-1"
        assert entry.index == 0
        assert entry.merge_base == "master"
        assert entry.pr_number == 100

    @patch("spectrum.stack.git")
    def test_returns_none_when_no_stack(self, mock_git):
        mock_git.get_branch_config.return_value = None
        assert read_entry("x/a") is None


class TestWriteEntry:
    @patch("spectrum.stack.git")
    def test_writes_all_config(self, mock_git):
        entry = StackEntry(
            branch="x/a", index=0, stack_id="msg-1", merge_base="master", pr_number=42
        )
        write_entry(entry)

        mock_git.set_branch_config.assert_any_call("x/a", "spectrum-stack", "msg-1")
        mock_git.set_branch_config.assert_any_call("x/a", "spectrum-index", "0")
        mock_git.set_branch_config.assert_any_call("x/a", "gh-merge-base", "master")
        mock_git.set_branch_config.assert_any_call("x/a", "spectrum-pr", "42")


class TestRemoveEntry:
    @patch("spectrum.stack.git", autospec=True)
    def test_unsets_all_config_keys(self, mock_git):
        remove_entry("x/a")

        unset_keys = [call.args[1] for call in mock_git.unset_branch_config.call_args_list]
        assert sorted(unset_keys) == sorted(CONFIG_KEYS)


class TestGetStack:
    @patch("spectrum.stack.git")
    @patch("spectrum.stack.read_entry")
    def test_returns_sorted_entries(self, mock_read, mock_git):
        mock_git.all_local_branches.return_value = ["x/a", "x/b", "other"]
        entry_a = StackEntry(branch="x/a", index=0, stack_id="msg-1", merge_base="master")
        entry_b = StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="x/a")

        def side_effect(branch):
            return {"x/a": entry_a, "x/b": entry_b}.get(branch)

        mock_read.side_effect = side_effect

        result = get_stack("msg-1")
        assert len(result) == 2
        assert result[0].branch == "x/a"
        assert result[1].branch == "x/b"


class TestReindexStack:
    @patch("spectrum.stack.get_stack")
    @patch("spectrum.stack.git", autospec=True)
    def test_reindexes_after_gap(self, mock_git, mock_get_stack):
        """After removing index 0, entries at 1,2 should become 0,1."""
        entries = [
            StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="x/c", index=2, stack_id="msg-1", merge_base="x/b"),
        ]
        mock_get_stack.return_value = entries

        reindex_stack("msg-1")

        assert entries[0].index == 0
        assert entries[1].index == 1
        mock_git.set_branch_config.assert_any_call("x/b", "spectrum-index", "0")
        mock_git.set_branch_config.assert_any_call("x/c", "spectrum-index", "1")

    @patch("spectrum.stack.get_stack")
    @patch("spectrum.stack.git", autospec=True)
    def test_noop_when_already_contiguous(self, mock_git, mock_get_stack):
        entries = [
            StackEntry(branch="x/a", index=0, stack_id="msg-1", merge_base="master"),
            StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="x/a"),
        ]
        mock_get_stack.return_value = entries

        reindex_stack("msg-1")

        mock_git.set_branch_config.assert_not_called()


class TestSwapEntries:
    @patch("spectrum.stack.write_entry", autospec=True)
    @patch("spectrum.stack.get_stack", autospec=True)
    def test_adjacent_swap(self, mock_get_stack, mock_write_entry):
        """Swap indices 0 and 1 in a 3-entry stack: updates indices and merge_bases."""
        entry_a = StackEntry(branch="x/a", index=0, stack_id="msg-1", merge_base="master")
        entry_b = StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="x/a")
        entry_c = StackEntry(branch="x/c", index=2, stack_id="msg-1", merge_base="x/b")
        mock_get_stack.return_value = [entry_a, entry_b, entry_c]

        # Act
        result = swap_entries("msg-1", 0, 1)

        # After swap: b(0) -> a(1) -> c(2)
        assert result[0].branch == "x/b"
        assert result[0].index == 0
        assert result[0].merge_base == "master"
        assert result[1].branch == "x/a"
        assert result[1].index == 1
        assert result[1].merge_base == "x/b"
        assert result[2].branch == "x/c"
        assert result[2].index == 2
        assert result[2].merge_base == "x/a"

    @patch("spectrum.stack.write_entry", autospec=True)
    @patch("spectrum.stack.get_stack", autospec=True)
    def test_non_adjacent_swap(self, mock_get_stack, mock_write_entry):
        """Swap indices 0 and 2 in a 4-entry stack."""
        entry_a = StackEntry(branch="x/a", index=0, stack_id="msg-1", merge_base="master")
        entry_b = StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="x/a")
        entry_c = StackEntry(branch="x/c", index=2, stack_id="msg-1", merge_base="x/b")
        entry_d = StackEntry(branch="x/d", index=3, stack_id="msg-1", merge_base="x/c")
        mock_get_stack.return_value = [entry_a, entry_b, entry_c, entry_d]

        # Act
        result = swap_entries("msg-1", 0, 2)

        # After swap: c(0) -> b(1) -> a(2) -> d(3)
        assert result[0].branch == "x/c"
        assert result[0].index == 0
        assert result[0].merge_base == "master"
        assert result[1].branch == "x/b"
        assert result[1].index == 1
        assert result[1].merge_base == "x/c"
        assert result[2].branch == "x/a"
        assert result[2].index == 2
        assert result[2].merge_base == "x/b"
        assert result[3].branch == "x/d"
        assert result[3].index == 3
        assert result[3].merge_base == "x/a"

    def test_same_index_raises(self):
        """Swapping an index with itself raises ValueError."""
        with pytest.raises(ValueError, match="must be different"):
            swap_entries("msg-1", 1, 1)

    @patch("spectrum.stack.write_entry", autospec=True)
    @patch("spectrum.stack.get_stack", autospec=True)
    def test_index_not_found_raises(self, mock_get_stack, mock_write_entry):
        """Swapping with an index not in the stack raises ValueError."""
        entry_a = StackEntry(branch="x/a", index=0, stack_id="msg-1", merge_base="master")
        entry_b = StackEntry(branch="x/b", index=1, stack_id="msg-1", merge_base="x/a")
        mock_get_stack.return_value = [entry_a, entry_b]

        with pytest.raises(ValueError, match="not found"):
            swap_entries("msg-1", 0, 5)
