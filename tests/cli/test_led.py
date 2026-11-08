"""Tests for LED CLI commands."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from blocksd.cli.app import app
from blocksd.cli.led import _parse_color
from blocksd.led.bitmap import Color, LEDGrid

runner = CliRunner()


class TestParseColor:
    def test_hex_with_hash(self):
        assert _parse_color("#ff00ff") == Color(255, 0, 255)

    def test_hex_without_hash(self):
        assert _parse_color("00ff00") == Color(0, 255, 0)

    def test_black(self):
        assert _parse_color("#000000") == Color(0, 0, 0)

    def test_white(self):
        assert _parse_color("ffffff") == Color(255, 255, 255)

    def test_invalid_exits(self):
        result = runner.invoke(app, ["led", "solid", "notacolor"])
        assert result.exit_code != 0

    def test_short_hex_exits(self):
        result = runner.invoke(app, ["led", "solid", "fff"])
        assert result.exit_code != 0


class TestLedSubcommands:
    def test_led_help(self):
        result = runner.invoke(app, ["led", "--help"])
        assert result.exit_code == 0
        assert "Control device LEDs" in result.output

    def test_solid_help(self):
        result = runner.invoke(app, ["led", "solid", "--help"])
        assert result.exit_code == 0
        assert "solid color" in result.output.lower()

    def test_off_help(self):
        result = runner.invoke(app, ["led", "off", "--help"])
        assert result.exit_code == 0

    def test_rainbow_help(self):
        result = runner.invoke(app, ["led", "rainbow", "--help"])
        assert result.exit_code == 0
        assert "brightness" in result.output.lower()

    def test_gradient_help(self):
        result = runner.invoke(app, ["led", "gradient", "--help"])
        assert result.exit_code == 0

    def test_checkerboard_help(self):
        result = runner.invoke(app, ["led", "checkerboard", "--help"])
        assert result.exit_code == 0
        assert "size" in result.output.lower()

    def test_solid_missing_color(self):
        result = runner.invoke(app, ["led", "solid"])
        assert result.exit_code != 0

    def test_gradient_missing_args(self):
        result = runner.invoke(app, ["led", "gradient"])
        assert result.exit_code != 0

    def test_checkerboard_missing_args(self):
        result = runner.invoke(app, ["led", "checkerboard"])
        assert result.exit_code != 0


class TestLedCommandsRun:
    """Test that commands invoke _run_with_pattern correctly (mocked)."""

    @patch("blocksd.cli.led._run_with_pattern")
    def test_solid_invokes_runner(self, mock_run):
        result = runner.invoke(app, ["led", "solid", "#ff0000"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_off_invokes_runner(self, mock_run):
        result = runner.invoke(app, ["led", "off"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_rainbow_invokes_runner(self, mock_run):
        result = runner.invoke(app, ["led", "rainbow"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_gradient_invokes_runner(self, mock_run):
        result = runner.invoke(app, ["led", "gradient", "ff0000", "0000ff"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_checkerboard_invokes_runner(self, mock_run):
        result = runner.invoke(app, ["led", "checkerboard", "ff0000", "00ff00"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_rainbow_with_brightness(self, mock_run):
        result = runner.invoke(app, ["led", "rainbow", "--brightness", "0.5"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_gradient_vertical(self, mock_run):
        result = runner.invoke(app, ["led", "gradient", "ff0000", "0000ff", "--vertical"])
        assert result.exit_code == 0
        mock_run.assert_called_once()

    @patch("blocksd.cli.led._run_with_pattern")
    def test_checkerboard_with_size(self, mock_run):
        result = runner.invoke(app, ["led", "checkerboard", "ff0000", "00ff00", "--size", "3"])
        assert result.exit_code == 0
        mock_run.assert_called_once()


class TestKeyLighting:
    def test_help_explains_daemon_connection(self):
        result = runner.invoke(app, ["led", "keys", "--help"])
        assert result.exit_code == 0
        assert "running daemon" in result.output
        assert "then exit" in result.output

    @pytest.mark.parametrize("args", [[], ["rainbow"], ["ff0000"]])
    @patch("blocksd.cli.led._run_with_pattern")
    def test_keys_routes_a_24_key_pattern(self, mock_run, args):
        result = runner.invoke(app, ["led", "keys", *args])
        assert result.exit_code == 0
        assert mock_run.call_args.kwargs["key_lighting"] is True
        grid = LEDGrid(cols=24, rows=1)
        mock_run.call_args.args[0](grid)
        assert len(grid.heap_data) == 48
        assert grid.heap_data[:2] == bytes.fromhex("1f00")
        if args == ["ff0000"]:
            assert grid.heap_data == bytes.fromhex("1f00") * 24
        else:
            assert grid.heap_data[24:26] == bytes.fromhex("e0ff")

    @patch("blocksd.cli.led._run_with_pattern")
    def test_invalid_color_does_not_start_device_manager(self, mock_run):
        result = runner.invoke(app, ["led", "keys", "bad"])
        assert result.exit_code == 1
        mock_run.assert_not_called()
