from click.testing import CliRunner

from spectrum.cli import main


class TestCompletionCommand:
    def test_completion_bash(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completion", "bash"])

        assert result.exit_code == 0
        assert '_SPECTRUM_COMPLETE=bash_source spectrum' in result.output

    def test_completion_zsh(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completion", "zsh"])

        assert result.exit_code == 0
        assert '_SPECTRUM_COMPLETE=zsh_source spectrum' in result.output

    def test_completion_fish(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completion", "fish"])

        assert result.exit_code == 0
        assert '_SPECTRUM_COMPLETE=fish_source spectrum' in result.output

    def test_completion_invalid_shell(self):
        runner = CliRunner()
        result = runner.invoke(main, ["completion", "powershell"])

        assert result.exit_code != 0

    def test_completion_hidden(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "completion" not in result.output
