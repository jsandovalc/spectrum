from unittest.mock import patch

from spectrum import ui


class TestLetterStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_letter_calls_style_cyan_bold(self, mock_style):
        ui.letter("[a]")
        mock_style.assert_called_once_with("[a]", fg="cyan", bold=True)


class TestBracketLetterStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_bracket_letter_wraps_in_brackets(self, mock_style):
        ui.bracket_letter("a")
        mock_style.assert_called_once_with("[a]", fg="cyan", bold=True)


class TestPrNumberStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_pr_number_calls_style_cyan(self, mock_style):
        ui.pr_number("#123")
        mock_style.assert_called_once_with("#123", fg="cyan")


class TestSuccessStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_success_calls_style_green(self, mock_style):
        ui.success("done")
        mock_style.assert_called_once_with("done", fg="green")


class TestErrorStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_error_calls_style_red_bold(self, mock_style):
        ui.error("CONFLICT")
        mock_style.assert_called_once_with("CONFLICT", fg="red", bold=True)


class TestWarningStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_warning_calls_style_yellow(self, mock_style):
        ui.warning("WIP")
        mock_style.assert_called_once_with("WIP", fg="yellow")


class TestDimStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_dim_calls_style_dim(self, mock_style):
        ui.dim("url")
        mock_style.assert_called_once_with("url", dim=True)


class TestHeaderStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_header_calls_style_bold(self, mock_style):
        ui.header("Stack:")
        mock_style.assert_called_once_with("Stack:", bold=True)


class TestCurrentMarkerStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_current_marker_calls_style_green_bold(self, mock_style):
        ui.current_marker("●")
        mock_style.assert_called_once_with("●", fg="green", bold=True)


class TestCurrentLabelStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_current_label_calls_style_green(self, mock_style):
        ui.current_label("text")
        mock_style.assert_called_once_with("text", fg="green")


class TestCiPassStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_ci_pass_calls_style_green(self, mock_style):
        ui.ci_pass("✓ CI passing")
        mock_style.assert_called_once_with("✓ CI passing", fg="green")


class TestCiFailStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_ci_fail_calls_style_red(self, mock_style):
        ui.ci_fail("✗ CI failing")
        mock_style.assert_called_once_with("✗ CI failing", fg="red")


class TestCiPendingStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_ci_pending_calls_style_yellow(self, mock_style):
        ui.ci_pending("○ CI running")
        mock_style.assert_called_once_with("○ CI running", fg="yellow")


class TestReviewApprovedStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_review_approved_calls_style_green(self, mock_style):
        ui.review_approved("✓ Approved")
        mock_style.assert_called_once_with("✓ Approved", fg="green")


class TestReviewChangesStyle:
    @patch("spectrum.ui.click.style", autospec=True)
    def test_review_changes_calls_style_red(self, mock_style):
        ui.review_changes("✗ Changes requested")
        mock_style.assert_called_once_with("✗ Changes requested", fg="red")


class TestFormatCiStatus:
    def test_empty_rollup_returns_pending(self):
        result = ui.format_ci_status([])
        assert "CI pending" in result

    def test_all_success_returns_passing(self):
        rollup = [{"conclusion": "SUCCESS"}, {"conclusion": "SUCCESS"}]
        result = ui.format_ci_status(rollup)
        assert "CI passing" in result

    def test_any_failure_returns_failing(self):
        rollup = [{"conclusion": "SUCCESS"}, {"conclusion": "FAILURE"}]
        result = ui.format_ci_status(rollup)
        assert "CI failing" in result

    def test_in_progress_returns_running(self):
        rollup = [{"conclusion": "SUCCESS"}, {"conclusion": ""}]
        result = ui.format_ci_status(rollup)
        assert "CI running" in result


class TestFormatReviewStatus:
    def test_approved(self):
        result = ui.format_review_status("APPROVED")
        assert "Approved" in result

    def test_changes_requested(self):
        result = ui.format_review_status("CHANGES_REQUESTED")
        assert "Changes requested" in result

    def test_review_required(self):
        result = ui.format_review_status("REVIEW_REQUIRED")
        assert "Review required" in result

    def test_empty_string(self):
        result = ui.format_review_status("")
        assert result == ""
