"""Stable CoreMIDI endpoint identity alongside RtMidi's indexed port access."""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from functools import cache

_OBJECT_NOT_FOUND = -10842


@dataclass(frozen=True)
class CoreMidiEndpoint:
    uid: int
    entity: int


@cache
def _framework() -> tuple[ctypes.CDLL, ctypes.c_void_p]:
    if sys.platform != "darwin":
        raise RuntimeError("CoreMIDI endpoint discovery requires macOS")
    library = ctypes.CDLL("/System/Library/Frameworks/CoreMIDI.framework/CoreMIDI")
    for name in ("MIDIGetNumberOfSources", "MIDIGetNumberOfDestinations"):
        function = getattr(library, name)
        function.argtypes = []
        function.restype = ctypes.c_ulong
    for name in ("MIDIGetSource", "MIDIGetDestination"):
        function = getattr(library, name)
        function.argtypes = [ctypes.c_ulong]
        function.restype = ctypes.c_uint32
    library.MIDIObjectGetIntegerProperty.argtypes = [
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int32),
    ]
    library.MIDIObjectGetIntegerProperty.restype = ctypes.c_int32
    library.MIDIEndpointGetEntity.argtypes = [ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    library.MIDIEndpointGetEntity.restype = ctypes.c_int32
    unique_id = ctypes.c_void_p.in_dll(library, "kMIDIPropertyUniqueID")
    return library, unique_id


def _read_endpoint(
    library: ctypes.CDLL, unique_id: ctypes.c_void_p, endpoint: int
) -> CoreMidiEndpoint:
    if endpoint == 0:
        raise RuntimeError("CoreMIDI endpoint disappeared during discovery")
    uid = ctypes.c_int32()
    status = library.MIDIObjectGetIntegerProperty(endpoint, unique_id, ctypes.byref(uid))
    if status != 0:
        raise RuntimeError(f"CoreMIDI unique ID lookup failed for {endpoint}: OSStatus {status}")
    entity = ctypes.c_uint32()
    status = library.MIDIEndpointGetEntity(endpoint, ctypes.byref(entity))
    # Virtual endpoints have a UID but no owning entity.
    if status == _OBJECT_NOT_FOUND:
        return CoreMidiEndpoint(uid.value, 0)
    if status != 0:
        raise RuntimeError(f"CoreMIDI entity lookup failed for {endpoint}: OSStatus {status}")
    return CoreMidiEndpoint(uid.value, entity.value)


def endpoint_snapshot() -> tuple[list[CoreMidiEndpoint], list[CoreMidiEndpoint]]:
    """Read sources and destinations in RtMidi order after its client initializes."""
    library, unique_id = _framework()
    sources = [
        _read_endpoint(library, unique_id, library.MIDIGetSource(index))
        for index in range(library.MIDIGetNumberOfSources())
    ]
    destinations = [
        _read_endpoint(library, unique_id, library.MIDIGetDestination(index))
        for index in range(library.MIDIGetNumberOfDestinations())
    ]
    return sources, destinations


def endpoint_ids(input_port: int, output_port: int) -> tuple[int, int]:
    """Resolve current identities for an indexed pair before opening its ports."""
    if input_port < 0 or output_port < 0:
        raise ValueError("CoreMIDI port indices must be nonnegative")
    library, unique_id = _framework()
    source = _read_endpoint(library, unique_id, library.MIDIGetSource(input_port))
    destination = _read_endpoint(library, unique_id, library.MIDIGetDestination(output_port))
    return source.uid, destination.uid
