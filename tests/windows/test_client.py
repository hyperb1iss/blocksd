"""Windows commands use the real dashboard WebSocket API."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from blocksd.api.server import WebServer
from blocksd.cli import client
from blocksd.cli.app import app
from blocksd.config.schema import DaemonConfig
from blocksd.topology.manager import TopologyManager


@pytest.fixture
async def web_server():
    server = WebServer(TopologyManager(), host="127.0.0.1", port=0)
    await server.start()
    assert server._server is not None
    port = server._server.sockets[0].getsockname()[1]
    try:
        yield server, port
    finally:
        await server.stop()


async def test_windows_client_uses_configured_web_endpoint(monkeypatch, web_server):
    _, port = web_server
    monkeypatch.setattr(client, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(client, "load_config", lambda: DaemonConfig(web_port=port))
    # A machine-wide proxy must never receive local instrument commands.
    monkeypatch.setenv("WS_PROXY", "http://127.0.0.1:1")

    def exchange():
        with client.DaemonClient() as connection:
            assert connection.request("ping")["type"] == "pong"
            assert connection.request("discover")["devices"] == []
            with pytest.raises(client.ClientError, match="unknown type"):
                connection.request("nonexistent")
        result = CliRunner().invoke(app, ["status", "--probe"])
        assert result.exit_code == 0, result.exception
        assert "No ROLI Blocks devices" in result.output

    await asyncio.to_thread(exchange)


async def test_websocket_client_receives_events_before_response(web_server, monkeypatch):
    server, port = web_server
    send = server._ws_send

    def messages(writer, message):
        send(writer, {"type": "test_event", "value": 42})
        send(writer, message)

    monkeypatch.setattr(server, "_ws_send", messages)

    def exchange():
        with client.DaemonClient(websocket_url=f"ws://127.0.0.1:{port}/ws") as connection:
            connection.request("ping")
            event = connection.wait_for(lambda message: message["type"] == "test_event")
            assert event["value"] == 42

    await asyncio.to_thread(exchange)


async def test_websocket_close_is_a_cli_error(web_server):
    _, port = web_server

    def exchange():
        with client.DaemonClient(websocket_url=f"ws://127.0.0.1:{port}/ws") as connection:
            assert connection._websocket is not None
            connection._websocket.close()
            with pytest.raises(client.ClientError, match="Daemon connection failed"):
                connection.request("ping")

    await asyncio.to_thread(exchange)


async def test_websocket_wait_times_out_without_confirmation(web_server):
    _, port = web_server

    def exchange():
        with client.DaemonClient(websocket_url=f"ws://127.0.0.1:{port}/ws") as connection:
            connection.request("ping")
            connection.timeout = 0.02
            with pytest.raises(client.ClientError, match="Timed out"):
                connection.wait_for(lambda _: True)

    await asyncio.to_thread(exchange)


def test_windows_rejects_socket_option_and_disabled_web(monkeypatch):
    monkeypatch.setattr(client, "sys", SimpleNamespace(platform="win32"))
    monkeypatch.setattr(client, "load_config", lambda: DaemonConfig())
    with pytest.raises(client.ClientError, match="Unix sockets"):
        client.DaemonClient(Path("example.sock"))
    monkeypatch.setattr(client, "load_config", lambda: DaemonConfig(web_enabled=False))
    with pytest.raises(client.ClientError, match="web_enabled"):
        client.DaemonClient()
