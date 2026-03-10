"""Tests for CLI config commands."""

from __future__ import annotations

from typer.testing import CliRunner

from blocksd.cli.app import app

runner = CliRunner()


class TestConfigSubcommands:
    def test_config_help(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "Read/write device settings" in result.output

    def test_get_help(self):
        result = runner.invoke(app, ["config", "get", "--help"])
        assert result.exit_code == 0

    def test_set_help(self):
        result = runner.invoke(app, ["config", "set", "--help"])
        assert result.exit_code == 0

    def test_list_shows_config_ids(self):
        result = runner.invoke(app, ["config", "list"])
        assert result.exit_code == 0
        assert "velocity_sensitivity" in result.output
        assert "midi_channel_mode" in result.output

    def test_get_missing_item(self):
        result = runner.invoke(app, ["config", "get"])
        assert result.exit_code != 0

    def test_set_missing_args(self):
        result = runner.invoke(app, ["config", "set"])
        assert result.exit_code != 0

    def test_set_missing_value(self):
        result = runner.invoke(app, ["config", "set", "10"])
        assert result.exit_code != 0
