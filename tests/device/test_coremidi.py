"""Native discovery behavior with CoreMIDI calls replaced by typed callbacks."""

from __future__ import annotations

import ctypes
from unittest.mock import Mock

import pytest

from blocksd.device import coremidi


@pytest.fixture
def framework(monkeypatch: pytest.MonkeyPatch) -> Mock:
    library = Mock()
    sources = [101, 202]
    destinations = [303, 404]
    library.MIDIGetNumberOfSources.return_value = len(sources)
    library.MIDIGetNumberOfDestinations.return_value = len(destinations)
    library.MIDIGetSource.side_effect = sources.__getitem__
    library.MIDIGetDestination.side_effect = destinations.__getitem__

    @ctypes.CFUNCTYPE(
        ctypes.c_int32, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int32)
    )
    def get_uid(endpoint, property_id, output):
        output[0] = -endpoint
        return 0

    @ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32))
    def get_entity(endpoint, output):
        output[0] = 10 if endpoint in {101, 303} else 0
        return 0

    library.MIDIObjectGetIntegerProperty.side_effect = get_uid
    library.MIDIEndpointGetEntity.side_effect = get_entity
    monkeypatch.setattr(coremidi, "_framework", lambda: (library, ctypes.c_void_p(1)))
    return library


def test_snapshot_keeps_order_signed_ids_and_virtual_entities(framework: Mock) -> None:
    sources, destinations = coremidi.endpoint_snapshot()
    assert sources == [coremidi.CoreMidiEndpoint(-101, 10), coremidi.CoreMidiEndpoint(-202, 0)]
    assert destinations == [coremidi.CoreMidiEndpoint(-303, 10), coremidi.CoreMidiEndpoint(-404, 0)]


def test_endpoint_ids_query_current_indices(framework: Mock) -> None:
    assert coremidi.endpoint_ids(1, 0) == (-202, -303)
    framework.MIDIGetSource.assert_called_once_with(1)
    framework.MIDIGetDestination.assert_called_once_with(0)
    framework.MIDIGetNumberOfSources.assert_not_called()


def test_virtual_endpoint_without_an_owner_is_valid(framework: Mock) -> None:
    framework.MIDIEndpointGetEntity.side_effect = None
    framework.MIDIEndpointGetEntity.return_value = -10842
    sources, destinations = coremidi.endpoint_snapshot()
    assert [endpoint.entity for endpoint in sources + destinations] == [0, 0, 0, 0]
    assert coremidi.endpoint_ids(0, 0) == (-101, -303)


@pytest.mark.parametrize("indices", [(-1, 0), (0, -1)])
def test_negative_indices_are_rejected(framework: Mock, indices: tuple[int, int]) -> None:
    with pytest.raises(ValueError, match="nonnegative"):
        coremidi.endpoint_ids(*indices)
    framework.MIDIGetSource.assert_not_called()


def test_missing_endpoint_is_not_silently_accepted(framework: Mock) -> None:
    framework.MIDIGetSource.side_effect = None
    framework.MIDIGetSource.return_value = 0
    with pytest.raises(RuntimeError, match="disappeared"):
        coremidi.endpoint_snapshot()


@pytest.mark.parametrize(
    ("function", "message"),
    [("MIDIObjectGetIntegerProperty", "unique ID"), ("MIDIEndpointGetEntity", "entity")],
)
def test_native_status_errors_preserve_code(framework: Mock, function: str, message: str) -> None:
    native = getattr(framework, function)
    native.side_effect = None
    native.return_value = -10830
    with pytest.raises(RuntimeError, match=f"{message}.*OSStatus -10830"):
        coremidi.endpoint_ids(0, 0)


def test_empty_system_returns_empty_snapshot(framework: Mock) -> None:
    framework.MIDIGetNumberOfSources.return_value = 0
    framework.MIDIGetNumberOfDestinations.return_value = 0
    assert coremidi.endpoint_snapshot() == ([], [])


def test_framework_loading_is_guarded_and_lazy(monkeypatch: pytest.MonkeyPatch) -> None:
    coremidi._framework.cache_clear()
    monkeypatch.setattr(coremidi.sys, "platform", "linux")
    loader = Mock(side_effect=AssertionError("must not load framework"))
    monkeypatch.setattr(coremidi.ctypes, "CDLL", loader)
    with pytest.raises(RuntimeError, match="requires macOS"):
        coremidi.endpoint_snapshot()
    loader.assert_not_called()
