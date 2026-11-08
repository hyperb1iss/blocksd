"""CLI workflows over a real Unix socket, without opening MIDI devices."""

from __future__ import annotations

import base64
import contextlib
import json
import socket
import tempfile
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from blocksd.cli.app import app
from blocksd.cli.client import ClientError, DaemonClient

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

runner = CliRunner()
DEVICE = {
    "uid": 9_007_199_254_740_993,
    "serial": "LKB001",
    "block_type": "lumi_keys",
    "name": "LUMI Keys",
    "battery_level": 80,
    "battery_charging": True,
    "firmware_version": "1.3.9",
    "grid_width": 0,
    "grid_height": 0,
    "key_count": 24,
}


@pytest.fixture
def socket_path():
    # macOS TMPDIR plus pytest names can exceed sockaddr_un.sun_path.
    with tempfile.TemporaryDirectory(prefix="blocksd-cli-", dir="/tmp") as directory:
        yield Path(directory) / "daemon.sock"


@contextlib.contextmanager
def serve(path: Path, handler: Callable[[dict], list[dict]]) -> Iterator[Path]:
    errors: list[BaseException] = []
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(path))
        server.listen()
        server.settimeout(3)

        def run() -> None:
            try:
                conn, _ = server.accept()
                with conn, conn.makefile("rb") as reader:
                    conn.settimeout(3)
                    for line in reader:
                        request = json.loads(line)
                        for response in handler(request):
                            conn.sendall(json.dumps(response).encode() + b"\n")
            except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
                errors.append(exc)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        try:
            yield path
        finally:
            thread.join(4)
            assert not thread.is_alive()
            assert not errors


def response(request: dict, **fields: object) -> dict:
    return {"id": request["id"], **fields}


@pytest.mark.parametrize(("value", "arguments"), [(1, ["1"]), (-1, ["--", "-1"])])
def test_config_set_waits_for_readback_arriving_before_ack(socket_path, value, arguments):
    requests = []

    def handle(request):
        requests.append(request)
        match request["type"]:
            case "discover":
                return [response(request, type="discover_response", devices=[DEVICE])]
            case "subscribe":
                return [response(request, type="subscribed", events=["config"])]
            case "config_set":
                assert request["uid"] == DEVICE["uid"]
                assert request["item"] == 40
                return [
                    {"type": "config_changed", "uid": DEVICE["uid"], "item": 40, "value": value},
                    response(request, type="config_ack", ok=True, status="pending"),
                ]
        raise AssertionError(request)

    with serve(socket_path, handle) as path:
        result = runner.invoke(app, ["--socket", str(path), "config", "set", "40", *arguments])
    assert result.exit_code == 0, result.exception
    assert f"Confirmed: LKB001 config[40] = {value}" in result.output
    assert [r["type"] for r in requests] == ["discover", "subscribe", "config_set"]


def test_config_set_does_not_claim_success_after_disconnect(socket_path):
    def handle(request):
        match request["type"]:
            case "discover":
                return [response(request, devices=[DEVICE])]
            case "subscribe":
                return [response(request, type="subscribed")]
            case "config_set":
                return [
                    response(request, type="config_ack", ok=True),
                    {"type": "device_removed", "uid": DEVICE["uid"]},
                ]
        raise AssertionError(request)

    with serve(socket_path, handle) as path:
        result = runner.invoke(app, ["--socket", str(path), "config", "set", "40", "1"])
    assert result.exit_code == 1
    assert "disconnected before confirming" in result.output
    assert "Confirmed:" not in result.output


def test_config_requires_selection_when_multiple_devices_connected(socket_path):
    with serve(
        socket_path,
        lambda request: [response(request, devices=[DEVICE, {**DEVICE, "serial": "LKB002"}])],
    ) as path:
        result = runner.invoke(app, ["--socket", str(path), "config", "set", "40", "1"])
    assert result.exit_code == 1
    assert "--device SERIAL" in result.output


def test_ui_opens_reported_url_without_starting_a_daemon(socket_path):
    with (
        serve(
            socket_path,
            lambda request: [response(request, type="pong", web_url="http://localhost:9022")],
        ) as path,
        patch("blocksd.daemon.start") as start,
        patch("webbrowser.open") as browser,
    ):
        result = runner.invoke(app, ["--socket", str(path), "ui"])
    assert result.exit_code == 0, result.exception
    start.assert_not_called()
    browser.assert_called_once_with("http://localhost:9022")


def test_status_uses_daemon_topology(socket_path):
    with serve(
        socket_path,
        lambda request: [response(request, devices=[DEVICE], connections=[])],
    ) as path:
        result = runner.invoke(app, ["--socket", str(path), "status", "--probe"])
    assert result.exit_code == 0, result.exception
    assert "LKB001" in result.output
    assert "DNA connections: 0" in result.output


def test_led_keys_send_only_key_surface_and_exit(socket_path):
    frames = []

    def handle(request):
        if request["type"] == "discover":
            return [
                response(
                    request,
                    devices=[
                        DEVICE,
                        {
                            **DEVICE,
                            "serial": "LPM001",
                            "uid": 5,
                            "key_count": 0,
                            "grid_width": 15,
                            "grid_height": 15,
                        },
                    ],
                )
            ]
        frames.append(request)
        return [response(request, type="key_frame_ack", accepted=True)]

    with serve(socket_path, handle) as path:
        result = runner.invoke(app, ["--socket", str(path), "led", "keys", "ff0000"])
    assert result.exit_code == 0, result.exception
    assert len(frames) == 1
    assert frames[0]["type"] == "key_frame"
    assert frames[0]["uid"] == DEVICE["uid"]
    assert base64.b64decode(frames[0]["pixels"]) == bytes([248, 0, 0]) * 24
    assert "Frame accepted" in result.output


def test_missing_daemon_is_actionable(socket_path):
    result = runner.invoke(app, ["--socket", str(socket_path), "status"])
    assert result.exit_code == 1
    assert "blocksd run" in result.output


def test_client_timeout_is_not_confirmation(socket_path):
    with (
        serve(socket_path, lambda _: []) as path,
        DaemonClient(path, timeout=0.02) as client,
        pytest.raises(ClientError, match="Timed out"),
    ):
        client.request("ping")
