"""Tests for LED CLI commands."""

from __future__ import annotations

import asyncio
import signal
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from blocksd.cli.app import app
from blocksd.cli.led import _parse_color, _run_with_pattern
from blocksd.device.models import BlockType, DeviceInfo
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
    def test_help_explains_standalone_lifetime(self):
        result = runner.invoke(app, ["led", "keys", "--help"])
        assert result.exit_code == 0
        assert "Stop the daemon" in result.output
        assert "Ctrl+C" in result.output

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

    @pytest.mark.parametrize("key_lighting", [True, False])
    def test_runner_keeps_key_and_bitmap_devices_separate(self, key_lighting):
        manager = Mock()
        manager.on_device_added = []
        manager.on_device_removed = []
        with (
            patch("blocksd.topology.manager.TopologyManager", return_value=manager),
            patch("blocksd.logging.setup_logging"),
            patch("blocksd.cli.led.asyncio.run", side_effect=lambda coroutine: coroutine.close()),
        ):
            _run_with_pattern(lambda grid: grid.fill(Color(255, 0, 0)), key_lighting=key_lighting)
        for uid, block_type in enumerate(BlockType):
            manager.on_device_added[0](
                DeviceInfo(
                    uid=uid,
                    topology_index=uid,
                    serial="DEVICE",
                    block_type=block_type,
                    version="1.3.9",
                )
            )
        if key_lighting:
            manager.set_key_led_data.assert_called_once()
            assert manager.set_key_led_data.call_args.args[1] == bytes.fromhex("1f00") * 24
            manager.set_led_data.assert_not_called()
        else:
            assert manager.set_led_data.call_count == 2
            assert manager.set_led_data.call_args.args[1] == bytes.fromhex("1f00") * 225
            manager.set_key_led_data.assert_not_called()

    @pytest.mark.parametrize("disconnect_before_version", [False, True])
    def test_command_waits_for_firmware_and_cancels_on_disconnect(
        self, monkeypatch, disconnect_before_version
    ):
        manager = Mock()
        manager.on_device_added = []
        manager.on_device_removed = []
        stopped = False
        device = DeviceInfo(
            uid=7, topology_index=1, serial="LKB000", block_type=BlockType.LUMI_KEYS
        )
        signals = {}

        async def manager_run():
            nonlocal stopped
            try:
                manager.on_device_added[0](device)
                await asyncio.sleep(0.06)
                manager.set_key_led_data.assert_not_called()
                if disconnect_before_version:
                    manager.on_device_removed[0](device)
                device.version = "1.3.9"
                await asyncio.sleep(0.12)
                if disconnect_before_version:
                    manager.set_key_led_data.assert_not_called()
                else:
                    manager.set_key_led_data.assert_called_once_with(7, bytes.fromhex("1f00") * 24)
                signals[signal.SIGINT]()
                await asyncio.Future()
            finally:
                stopped = True

        manager.run = manager_run

        def run_command(coroutine):
            with asyncio.Runner() as async_runner:
                loop = async_runner.get_loop()
                monkeypatch.setattr(
                    loop, "add_signal_handler", lambda sig, cb: signals.update({sig: cb})
                )

                async def bounded():
                    async with asyncio.timeout(1):
                        await coroutine

                async_runner.run(bounded())

        with (
            patch("blocksd.topology.manager.TopologyManager", return_value=manager),
            patch("blocksd.logging.setup_logging"),
            patch("blocksd.cli.led.asyncio.run", side_effect=run_command),
        ):
            result = runner.invoke(app, ["led", "keys", "ff0000"])
        assert result.exit_code == 0, result.exception
        assert stopped
