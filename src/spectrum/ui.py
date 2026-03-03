"""Thin styling helpers wrapping click.style(). No I/O — string in, styled string out."""

from __future__ import annotations

import click


def letter(text: str) -> str:
    """Style a letter marker like [a], [b]."""
    return click.style(text, fg="cyan", bold=True)


def bracket_letter(ltr: str) -> str:
    """Style a letter with brackets, e.g. 'a' -> styled '[a]'."""
    return letter(f"[{ltr}]")


def pr_number(text: str) -> str:
    """Style a PR number like #123."""
    return click.style(text, fg="cyan")


def success(text: str) -> str:
    """Style a success message."""
    return click.style(text, fg="green")


def error(text: str) -> str:
    """Style an error message."""
    return click.style(text, fg="red", bold=True)


def warning(text: str) -> str:
    """Style a warning message."""
    return click.style(text, fg="yellow")


def dim(text: str) -> str:
    """Style dim/secondary text."""
    return click.style(text, dim=True)


def header(text: str) -> str:
    """Style a section header."""
    return click.style(text, bold=True)


def current_marker(text: str) -> str:
    """Style the current branch marker."""
    return click.style(text, fg="green", bold=True)


def current_label(text: str) -> str:
    """Style the current branch label."""
    return click.style(text, fg="green")


def ci_pass(text: str) -> str:
    """Style a passing CI indicator."""
    return click.style(text, fg="green")


def ci_fail(text: str) -> str:
    """Style a failing CI indicator."""
    return click.style(text, fg="red")


def ci_pending(text: str) -> str:
    """Style a pending CI indicator."""
    return click.style(text, fg="yellow")


def review_approved(text: str) -> str:
    """Style an approved review indicator."""
    return click.style(text, fg="green")


def review_changes(text: str) -> str:
    """Style a changes-requested review indicator."""
    return click.style(text, fg="red")


def format_ci_status(rollup: list[dict]) -> str:
    """Aggregate check results into a single styled indicator."""
    if not rollup:
        return ci_pending("○ CI pending")
    conclusions = [c.get("conclusion", "") for c in rollup]
    if all(s == "SUCCESS" for s in conclusions):
        return ci_pass("✓ CI passing")
    if any(s == "FAILURE" for s in conclusions):
        return ci_fail("✗ CI failing")
    return ci_pending("○ CI running")


def format_review_status(decision: str) -> str:
    """Format review decision into a styled indicator."""
    if decision == "APPROVED":
        return review_approved("✓ Approved")
    if decision == "CHANGES_REQUESTED":
        return review_changes("✗ Changes requested")
    if decision == "REVIEW_REQUIRED":
        return dim("○ Review required")
    return ""
