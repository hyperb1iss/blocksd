"""Transport shutdown, socket ownership, and consistent command validation."""

import asyncio
import base64
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from blocksd.api.server import ApiServer, WebServer
from blocksd.topology.manager import TopologyManager


@pytest.fixture
def socket_dir():
    """Unix socket addresses must fit even when macOS TMPDIR is long."""
    with tempfile.TemporaryDirectory(prefix="blocksd-", dir="/tmp") as directory:
        yield Path(directory)


@pytest.mark.parametrize("transport", ["unix", "tcp"])
async def test_stop_closes_idle_clients_and_detaches_events(socket_dir, transport):
    manager = TopologyManager()
    if transport == "unix":
        server = ApiServer(manager, socket_dir / "api.sock")
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(socket_dir / "api.sock"))
    else:
        server = WebServer(manager, port=0)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        await asyncio.sleep(0)
        assert len(manager.on_device_added) == 1
        async with asyncio.timeout(2):
            await server.stop()
            assert await reader.read() == b""
        assert not manager.on_device_added
        assert not server._clients
        await server.start()
        assert len(manager.on_device_added) == 1
        await server.start()
        assert len(manager.on_device_added) == 1
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_socket_path_does_not_replace_regular_file(tmp_path):
    path = tmp_path / "api.sock"
    path.write_text("keep me")
    server = ApiServer(TopologyManager(), path)
    with pytest.raises(FileExistsError, match="not a socket"):
        await server.start()
    await server.stop()
    assert path.read_text() == "keep me"


async def test_second_server_cannot_unlink_active_socket(socket_dir):
    path = socket_dir / "api.sock"
    first = ApiServer(TopologyManager(), path)
    second = ApiServer(TopologyManager(), path)
    await first.start()
    try:
        with pytest.raises(FileExistsError, match="already active"):
            await second.start()
        await second.stop()
        reader, writer = await asyncio.open_unix_connection(str(path))
        writer.write(b'{"type":"ping"}\n')
        await writer.drain()
        assert json.loads(await reader.readline())["type"] == "pong"
        writer.close()
        await writer.wait_closed()
    finally:
        await first.stop()


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize(
    "message",
    [
        [],
        None,
        {"type": "config_set", "uid": 1, "item": 2, "value": {}},
        {"type": "subscribe", "events": [None]},
        {"type": "subscribe", "events": "touch"},
    ],
)
async def test_invalid_commands_return_errors(server_class, message):
    server = server_class(TopologyManager())
    response, subscription = server._handle_json(
        json.dumps(message).encode(), asyncio.Queue(), None
    )
    assert response["type"] == "error"
    assert subscription is None
    pong, _ = server._handle_json(b'{"type":"ping"}', asyncio.Queue(), None)
    assert pong["type"] == "pong"


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize(("item", "value"), [("2", "123"), (2.9, 123.9), (2, 123)])
async def test_config_set_preserves_legacy_coercion(server_class, item, value):
    manager = Mock(spec=TopologyManager)
    manager.set_config.return_value = True
    server = server_class(manager)
    response, _ = server._handle_json(
        json.dumps(
            {"type": "config_set", "uid": 1, "item": item, "value": value, "id": 0}
        ).encode(),
        asyncio.Queue(),
        None,
    )
    assert response == {"type": "config_ack", "uid": 1, "item": item, "ok": True, "id": 0}
    manager.set_config.assert_called_once_with(1, 2, 123)


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize(("value", "expected"), [(127.9, 127), (-1.5, 0), (999.5, 255)])
async def test_fractional_brightness_can_render_frames(server_class, value, expected):
    manager = Mock(spec=TopologyManager)
    manager.set_led_data.return_value = True
    server = server_class(manager)
    response, _ = server._handle_json(
        json.dumps({"type": "brightness", "uid": 1, "value": value}).encode(), asyncio.Queue(), None
    )
    assert response == {"type": "brightness_ack", "uid": 1, "ok": True}
    pixels = base64.b64encode(bytes([255, 255, 255]) * 225).decode()
    response, _ = server._handle_json(
        json.dumps({"type": "frame", "uid": 1, "pixels": pixels}).encode(), asyncio.Queue(), None
    )
    assert response == {"type": "frame_ack", "uid": 1, "accepted": True}
    from blocksd.led.bitmap import Color, LEDGrid

    expected_grid = LEDGrid()
    expected_grid.fill(Color(expected, expected, expected))
    manager.set_led_data.assert_called_once_with(1, expected_grid.heap_data)


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize(
    ("command", "ack", "key"),
    [("frame", "frame_ack", "accepted"), ("brightness", "brightness_ack", "ok")],
)
@pytest.mark.parametrize("uid", [None, [], {}, "bad"])
async def test_invalid_uid_preserves_typed_ack(server_class, command, ack, key, uid):
    server = server_class(TopologyManager())
    response, _ = server._handle_json(
        json.dumps({"type": command, "uid": uid, "id": "invalid-uid"}).encode(),
        asyncio.Queue(),
        None,
    )
    assert response == {
        "type": ack,
        "uid": uid if uid is not None else 0,
        key: False,
        "id": "invalid-uid",
    }


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize("value", ["bad", {}, None, float("nan"), float("inf"), float("-inf")])
async def test_invalid_brightness_preserves_typed_ack(server_class, value):
    server = server_class(TopologyManager())
    response, _ = server._handle_json(
        json.dumps(
            {"type": "brightness", "uid": 1, "value": value, "id": "invalid-value"}
        ).encode(),
        asyncio.Queue(),
        None,
    )
    assert response == {"type": "brightness_ack", "uid": 1, "ok": False, "id": "invalid-value"}
    assert not server._brightness_store


@pytest.mark.parametrize("server_class", [ApiServer, WebServer])
@pytest.mark.parametrize("value", ["bad", {}, None, float("nan"), float("inf")])
async def test_invalid_config_retains_request_id(server_class, value):
    server = server_class(TopologyManager())
    response, _ = server._handle_json(
        json.dumps(
            {"type": "config_set", "uid": 1, "item": 2, "value": value, "id": "invalid-config"}
        ).encode(),
        asyncio.Queue(),
        None,
    )
    assert response["type"] == "error"
    assert response["id"] == "invalid-config"


@pytest.mark.parametrize("transport", ["unix", "websocket"])
async def test_transport_keeps_connection_after_compatibility_requests(
    socket_dir, monkeypatch, transport
):
    from blocksd.api.websocket import read_frame
    from tests.test_web_server import _build_masked_frame

    manager = TopologyManager()
    set_config = Mock(return_value=True)
    monkeypatch.setattr(manager, "set_config", set_config)
    if transport == "unix":
        server = ApiServer(manager, socket_dir / "compat.sock")
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(socket_dir / "compat.sock"))
    else:
        server = WebServer(manager, port=0)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"GET /ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
        )
        await writer.drain()
        assert b"101" in await reader.readuntil(b"\r\n\r\n")
    requests = [
        ({"type": "config_set", "uid": 1, "item": "2", "value": "123"}, "config_ack"),
        ({"type": "brightness", "uid": 1, "value": 127.5}, "brightness_ack"),
        ({"type": "frame", "uid": "bad"}, "frame_ack"),
        ({"type": "config_set", "uid": 1, "item": 2, "value": {}}, "error"),
        ({"type": "ping"}, "pong"),
    ]
    try:
        async with asyncio.timeout(2):
            for message, expected_type in requests:
                message["id"] = "compat"
                payload = json.dumps(message).encode()
                writer.write(
                    payload + b"\n" if transport == "unix" else _build_masked_frame(1, payload)
                )
                await writer.drain()
                if transport == "unix":
                    response = json.loads(await reader.readline())
                else:
                    frame = await read_frame(reader)
                    assert frame is not None
                    response = json.loads(frame[1])
                assert response["type"] == expected_type
                assert response["id"] == "compat"
        set_config.assert_called_once_with(1, 2, 123)
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


@pytest.mark.parametrize("transport", ["unix", "tcp"])
async def test_overflowed_subscriber_is_disconnected(socket_dir, transport):
    """A client that fell behind learns so by losing its connection."""
    from blocksd.api.websocket import WSOpcode, read_frame
    from blocksd.device.models import TouchEvent
    from tests.test_web_server import _build_masked_frame

    manager = TopologyManager()
    if transport == "unix":
        server = ApiServer(manager, socket_dir / "events.sock")
        await server.start()
        reader, writer = await asyncio.open_unix_connection(str(socket_dir / "events.sock"))
    else:
        server = WebServer(manager, port=0)
        await server.start()
        assert server._server is not None
        port = server._server.sockets[0].getsockname()[1]
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(
            b"GET /ws HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\n"
            b"Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
            b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n\r\n"
        )
        await writer.drain()
        assert b"101" in await reader.readuntil(b"\r\n\r\n")

    async def receive() -> dict | None:
        if transport == "unix":
            line = await reader.readline()
            return json.loads(line) if line else None
        frame = await read_frame(reader)
        if frame is None:
            return None
        if frame[0] == WSOpcode.CLOSE:
            assert frame[1][:2] == (1008).to_bytes(2, "big")
            return None
        return json.loads(frame[1])

    try:
        async with asyncio.timeout(2):
            payload = json.dumps({"type": "subscribe", "events": ["touch"]}).encode()
            writer.write(
                payload + b"\n" if transport == "unix" else _build_masked_frame(1, payload)
            )
            await writer.drain()
            subscribed = await receive()
            assert subscribed is not None
            assert subscribed["type"] == "subscribed"

            # Broadcast without yielding so the event writer cannot drain.
            touch = TouchEvent(uid=1, timestamp=0, touch_index=0, x=0, y=0, z=0)
            for _ in range(1025):
                server._broadcaster.broadcast_touch(touch)

            error = await receive()
            assert error is not None
            assert error["type"] == "error"
            assert "overflowed" in error["message"]
            assert await receive() is None
            assert server._broadcaster.subscriber_count == 0
    finally:
        writer.close()
        await writer.wait_closed()
        await server.stop()


async def test_overflowed_queue_cannot_subscribe_again():
    """A client that re-subscribes before its close lands stays unsubscribed."""
    server = ApiServer(TopologyManager(), Path("/unused.sock"))
    queue: asyncio.Queue = asyncio.Queue(maxsize=1)
    _, sub_id = server._handle_json(b'{"type":"subscribe","events":["button"]}', queue, None)
    assert sub_id is not None

    from blocksd.device.models import ButtonEvent

    press = ButtonEvent(uid=1, timestamp=0, button_id=0, is_down=True)
    server._broadcaster.broadcast_button(press)
    server._broadcaster.broadcast_button(press)

    response, new_sub = server._handle_json(
        b'{"type":"subscribe","events":["button"]}', queue, sub_id
    )
    assert response == {
        "type": "error",
        "message": "event queue overflowed; reconnect and subscribe again",
    }
    assert new_sub is None
    assert server._broadcaster.subscriber_count == 0
    server._broadcaster.broadcast_button(press)
