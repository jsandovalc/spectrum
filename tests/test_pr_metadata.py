from spectrum.pr_metadata import (
    SENTINEL_END,
    SENTINEL_START,
    build_stack_table,
    insert_metadata,
    remove_metadata,
)


class TestBuildStackTable:
    def test_single_entry(self):
        entries = [
            {
                "index": 0,
                "letter": "a",
                "pr_number": 100,
                "title": "First change",
                "is_draft": True,
                "stack_id": "msg-1",
            }
        ]
        result = build_stack_table(entries, current_index=0, repo_url="https://github.com/org/repo")
        assert SENTINEL_START in result
        assert SENTINEL_END in result
        assert "Part 1 of 1" in result
        assert "**#100**" in result
        assert "First change" in result

    def test_two_entries_current_is_first(self):
        entries = [
            {
                "index": 0,
                "letter": "a",
                "pr_number": 100,
                "title": "First",
                "is_draft": False,
                "stack_id": "msg-1",
            },
            {
                "index": 1,
                "letter": "b",
                "pr_number": 101,
                "title": "Second",
                "is_draft": True,
                "stack_id": "msg-1",
            },
        ]
        result = build_stack_table(entries, current_index=0, repo_url="https://github.com/org/repo")
        assert "Part 1 of 2" in result
        assert "**#100**" in result
        assert "[#101](https://github.com/org/repo/pull/101)" in result

    def test_entry_without_pr(self):
        entries = [
            {
                "index": 0,
                "letter": "a",
                "pr_number": None,
                "title": "No PR",
                "is_draft": True,
                "stack_id": "msg-1",
            }
        ]
        result = build_stack_table(entries, current_index=0, repo_url="https://github.com/org/repo")
        assert "—" in result


class TestInsertMetadata:
    def test_append_to_body_without_metadata(self):
        body = "## Changes\n- Something\n"
        metadata = f"{SENTINEL_START}\nstack info\n{SENTINEL_END}"
        result = insert_metadata(body, metadata)
        assert body.strip() in result
        assert metadata in result

    def test_replace_existing_metadata(self):
        body = (
            "## Changes\n- Something\n\n"
            f"{SENTINEL_START}\nold stack info\n{SENTINEL_END}\n"
        )
        new_metadata = f"{SENTINEL_START}\nnew stack info\n{SENTINEL_END}"
        result = insert_metadata(body, new_metadata)
        assert "old stack info" not in result
        assert "new stack info" in result
        assert "## Changes" in result

    def test_preserves_user_content(self):
        body = (
            "## Changes\n- Important change\n\n"
            "## Testing\n- Tested manually\n\n"
            f"{SENTINEL_START}\nold\n{SENTINEL_END}\n"
        )
        new_metadata = f"{SENTINEL_START}\nupdated\n{SENTINEL_END}"
        result = insert_metadata(body, new_metadata)
        assert "Important change" in result
        assert "Tested manually" in result
        assert "updated" in result


class TestRemoveMetadata:
    def test_removes_metadata(self):
        body = (
            "## Changes\n- Something\n\n"
            f"{SENTINEL_START}\nstack info\n{SENTINEL_END}\n"
        )
        result = remove_metadata(body)
        assert SENTINEL_START not in result
        assert "stack info" not in result
        assert "## Changes" in result

    def test_no_metadata_returns_unchanged(self):
        body = "## Changes\n- Something\n"
        result = remove_metadata(body)
        assert "## Changes" in result
