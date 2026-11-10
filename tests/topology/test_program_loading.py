"""Temporary programs own the heap until an explicit replacement or reset."""

import asyncio
import base64
import struct
from unittest.mock import patch

import pytest

from blocksd.api.commands import ApiCommands
from blocksd.api.programs import load_program
from blocksd.littlefoot.assembler import BytecodeAssembler, compute_program_checksum
from blocksd.littlefoot.upload import ProgramUpload, validate_program
from blocksd.protocol.builder import (
    build_begin_api_mode,
    build_config_request_factory_sync,
    build_end_api_mode,
)
from blocksd.topology.detector import MidiPortPair
from blocksd.topology.device_group import DeviceGroup
from blocksd.topology.manager import TopologyManager, _GroupEntry
from tests.led.test_program import finish_upload
from tests.topology.test_device_group import MockMidiConnection, _build_topology_packet


def program_bytes(heap_size=4):
    asm = BytecodeAssembler(heap_size=heap_size)
    asm.begin_function("repaint/v")
    asm.ret_void()
    return asm.build()


@pytest.fixture
def connected():
    conn = MockMidiConnection()
    group = DeviceGroup(conn)
    group._process_message(_build_topology_packet(["LPM123456789ABCD"]))
    uid = group.topology.devices[0].uid
    group._update_api_ping(uid)
    manager = TopologyManager()
    manager._groups["test"] = _GroupEntry(group, MidiPortPair(0, 0, "test"))
    return manager, group, conn, uid


def test_custom_program_owns_heap_and_ack_does_not_claim_execution(connected):
    _, group, _, uid = connected
    group.load_program(uid, program_bytes(), "sequence.littlefoot")
    before = group.get_heap(uid).target
    assert not group.set_led_data(uid, bytes(450))
    assert group.get_heap(uid).target == before
    assert group.program_status(uid).state == "uploading"
    finish_upload(group.get_heap(uid))
    status = group.program_status(uid)
    assert status.state == "uploaded"
    assert "execution is not verified" in status.message


def test_invalid_binary_leaves_active_program_untouched(connected):
    _, group, conn, uid = connected
    group.load_program(uid, program_bytes(), "first")
    before = group.get_heap(uid).target
    count = len(conn.sent)
    with pytest.raises(ValueError, match="header"):
        group.load_program(uid, b"bad", "second")
    assert group.get_heap(uid).target == before
    assert len(conn.sent) == count
    assert group.program_status(uid).name == "first"


def test_reset_discards_queued_upload_and_uses_sdk_sequence(connected):
    _, group, conn, uid = connected
    group.load_program(uid, program_bytes(), "sequence")
    conn.sent.clear()
    group.reset_program(uid)
    assert conn.sent[:2] == [build_end_api_mode(0), build_begin_api_mode(0)]
    assert group.get_heap(uid).in_flight_count == 0
    assert not any(group.get_heap(uid).target)
    assert group.program_status(uid).owner == "device"
    assert group.set_led_data(uid, bytes(450))


def test_restore_send_failure_preserves_program_ownership(connected):
    _, group, conn, uid = connected
    group.load_program(uid, program_bytes(), "sequence")
    conn.close()
    with pytest.raises(OSError, match="saved program"):
        group.reset_program(uid)
    assert group.program_status(uid).owner == "custom"


@pytest.mark.parametrize("mutation", ["checksum", "size", "address", "capacity", "globals"])
def test_binary_validation_rejects_invalid_program(mutation):
    code = bytearray(program_bytes())
    if mutation == "checksum":
        code[0] ^= 1
    elif mutation == "size":
        code[2] += 1
    else:
        if mutation == "address":
            struct.pack_into("<H", code, 12, 0)
        elif mutation == "capacity":
            struct.pack_into("<H", code, 8, 7200)
        else:
            struct.pack_into("<H", code, 6, 65535)
        struct.pack_into("<H", code, 0, compute_program_checksum(code))
    with pytest.raises(ValueError):
        validate_program(bytes(code), 7200)


async def test_source_compilation_keeps_loop_live_and_rejects_replacement_session(connected):
    manager, group, _, uid = connected
    started = asyncio.Event()
    release = asyncio.Event()

    async def compile_in_worker(*args, **kwargs):
        started.set()
        await release.wait()
        return program_bytes()

    with patch("blocksd.api.programs.asyncio.to_thread", side_effect=compile_in_worker):
        task = asyncio.create_task(
            load_program(manager, uid, {"name": "seq", "source": "void repaint() {}"})
        )
        await started.wait()
        assert group.program_status(uid).state == "compiling"
        assert not group.set_led_data(uid, bytes(450))
        with pytest.raises(ValueError, match="already being compiled"):
            await load_program(manager, uid, {"name": "other", "source": ""})
        group._remove_device(uid)
        release.set()
        with pytest.raises(ValueError, match="disconnected"):
            await task


async def test_compile_failure_retains_previous_program(connected):
    manager, group, _, uid = connected
    group.load_program(uid, program_bytes(), "first")
    before = group.get_heap(uid).target
    with (
        patch(
            "blocksd.littlefoot.compiler.compile_source", side_effect=ValueError("line 3: syntax")
        ),
        pytest.raises(ValueError, match="line 3"),
    ):
        await load_program(manager, uid, {"name": "broken", "source": "broken"})
    assert group.program_status(uid).name == "first"
    assert group.get_heap(uid).target == before


async def test_api_binary_upload_preserves_serial_and_request_correlation(connected):
    manager, group, _, uid = connected
    api = ApiCommands(manager)
    import json

    message = {
        "type": "program_load",
        "serial": group.topology.devices[0].serial,
        "name": "seq",
        "code": base64.b64encode(program_bytes()).decode(),
        "id": "load1",
    }
    response, _ = await api._handle_json_async(json.dumps(message).encode(), asyncio.Queue(), None)
    assert response is not None
    assert response["type"] == "program_status"
    assert response["id"] == "load1"
    assert response["uid"] == uid
    assert response["program"]["state"] == "uploading"


def test_custom_upload_recovers_after_heap_state_loss(connected):
    _, group, _, uid = connected
    heap = group.get_heap(uid)
    upload = ProgramUpload(heap, program_bytes(), "seq")
    finish_upload(heap)
    heap.reset()
    upload.advance()
    assert heap.target.startswith(program_bytes())
    assert upload.status().state == "uploading"


def test_custom_upload_refreshes_settings_once_after_each_completed_transfer(connected):
    _, group, conn, uid = connected
    group.load_program(uid, program_bytes(), "seq")
    conn.sent.clear()
    group._flush_heaps(1)
    request = build_config_request_factory_sync(0)
    assert request not in conn.sent
    finish_upload(group.get_heap(uid))
    group._flush_heaps(2)
    group._flush_heaps(3)
    assert conn.sent.count(request) == 1
    group.get_heap(uid).reset_device_state()
    group._flush_heaps(4)
    finish_upload(group.get_heap(uid))
    group._flush_heaps(5)
    assert conn.sent.count(request) == 2
