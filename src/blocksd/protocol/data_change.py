"""SharedDataChange encoder — diff-based heap writes over MIDI SysEx.

Ported from roli_HostPacketBuilder.h data change methods and
roli_LittleFootRemoteHeap.h diff algorithm.

The ROLI Blocks protocol updates device heap memory via SharedDataChange
messages. These encode byte-level diffs between the current device state
and the desired target state using a compact command set:

  - Skip unchanged regions (few/many variants)
  - Set sequences of distinct byte values
  - Set runs of repeated values (with last-value optimization)

The diff engine coalesces small skips between set regions to avoid
command overhead when sending the unchanged bytes is cheaper.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from blocksd.protocol.constants import BitSize, DataChangeCommand

if TYPE_CHECKING:
    from blocksd.protocol.packing import Packed7BitWriter

# Max values derived from bit widths
_FEW_MAX = (1 << BitSize.BYTE_COUNT_FEW) - 1  # 15
_MANY_MAX = (1 << BitSize.BYTE_COUNT_MANY) - 1  # 255

# Merge set+skip+set into one set region if total bytes < this threshold
_COALESCE_THRESHOLD = 32

# Run-length encoding kicks in at this many identical consecutive bytes
_MIN_RUN_LENGTH = 3


# ── Low-Level Encoder ─────────────────────────────────────────────────────────


class DataChangeEncoder:
    """Writes DataChange commands to a Packed7BitWriter.

    Low-level encoder that emits skip, set-sequence, and set-repeated
    commands following the ROLI SharedDataChange protocol. Tracks the
    last written value for the setFewBytesWithLastValue optimization.
    """

    def __init__(self, writer: Packed7BitWriter) -> None:
        self._writer = writer
        self._last_value: int | None = None

    @property
    def last_value(self) -> int | None:
        """Last byte value written in this packet, if any."""
        return self._last_value

    def skip_bytes(self, count: int) -> None:
        """Emit skip commands for unchanged heap bytes.

        Automatically splits large skips into multiple skipBytesMany (max 255)
        and a final skipBytesFew (max 15) if needed.
        """
        while count > 0:
            if count > _FEW_MAX:
                chunk = min(count, _MANY_MAX)
                self._cmd(DataChangeCommand.SKIP_BYTES_MANY)
                self._writer.write_bits(chunk, BitSize.BYTE_COUNT_MANY)
                count -= chunk
            else:
                self._cmd(DataChangeCommand.SKIP_BYTES_FEW)
                self._writer.write_bits(count, BitSize.BYTE_COUNT_FEW)
                count = 0

    def set_sequence(self, values: bytes | bytearray) -> None:
        """Emit a sequence of distinct byte values.

        Each byte is followed by a 1-bit continuation flag.
        """
        if not values:
            return
        self._cmd(DataChangeCommand.SET_SEQUENCE_OF_BYTES)
        for i, value in enumerate(values):
            self._writer.write_bits(value, BitSize.BYTE_VALUE)
            continues = 1 if i < len(values) - 1 else 0
            self._writer.write_bits(continues, BitSize.BYTE_SEQUENCE_CONTINUES)
            self._last_value = value

    def set_repeated(self, value: int, count: int) -> None:
        """Emit repeated byte value commands.

        Uses the most compact encoding:
        - count > 15: setManyBytesWithValue (8-bit count + 8-bit value)
        - value == last: setFewBytesWithLastValue (4-bit count, no value)
        - otherwise: setFewBytesWithValue (4-bit count + 8-bit value)
        """
        while count > 0:
            if count > _FEW_MAX:
                chunk = min(count, _MANY_MAX)
                self._cmd(DataChangeCommand.SET_MANY_BYTES_WITH_VALUE)
                self._writer.write_bits(chunk, BitSize.BYTE_COUNT_MANY)
                self._writer.write_bits(value, BitSize.BYTE_VALUE)
                count -= chunk
            elif self._last_value is not None and value == self._last_value:
                self._cmd(DataChangeCommand.SET_FEW_BYTES_WITH_LAST_VALUE)
                self._writer.write_bits(count, BitSize.BYTE_COUNT_FEW)
                count = 0
            else:
                self._cmd(DataChangeCommand.SET_FEW_BYTES_WITH_VALUE)
                self._writer.write_bits(count, BitSize.BYTE_COUNT_FEW)
                self._writer.write_bits(value, BitSize.BYTE_VALUE)
                count = 0
        self._last_value = value

    def end(self, *, is_last: bool = True) -> None:
        """Write end-of-packet or end-of-changes marker."""
        cmd = DataChangeCommand.END_OF_CHANGES if is_last else DataChangeCommand.END_OF_PACKET
        self._cmd(cmd)

    def _cmd(self, cmd: DataChangeCommand) -> None:
        self._writer.write_bits(cmd, BitSize.DATA_CHANGE_COMMAND)


# ── Heap Diff ─────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class DiffRegion:
    """A contiguous region of unchanged (skip) or changed (set) bytes."""

    is_skip: bool
    offset: int
    count: int


def compute_diff(
    current: bytes | bytearray,
    target: bytes | bytearray,
) -> list[DiffRegion]:
    """Compute optimized diff regions between two heap states.

    Returns a list of skip/set regions with small skips coalesced
    into adjacent set regions for encoding efficiency. Returns an
    empty list if the heaps are identical.
    """
    if len(current) != len(target):
        raise ValueError(f"Heap sizes differ: {len(current)} vs {len(target)}")

    size = len(target)
    regions: list[DiffRegion] = []
    i = 0

    while i < size:
        start = i
        if current[i] == target[i]:
            while i < size and current[i] == target[i]:
                i += 1
            regions.append(DiffRegion(is_skip=True, offset=start, count=i - start))
        else:
            while i < size and current[i] != target[i]:
                i += 1
            regions.append(DiffRegion(is_skip=False, offset=start, count=i - start))

    _coalesce_sequences(regions)

    # Trim trailing skip — never need to skip past the last change
    if regions and regions[-1].is_skip:
        regions.pop()

    return regions


def _coalesce_sequences(regions: list[DiffRegion]) -> None:
    """Merge small skips between set regions when cheaper to send bytes than skip.

    Pattern: [SET, SKIP(small), SET] -> [SET(merged)] when total < 32 bytes.
    Processes right-to-left so index adjustments stay valid.
    """
    i = len(regions) - 1
    while i > 1:
        right = regions[i]
        skip = regions[i - 1]
        left = regions[i - 2]
        if not right.is_skip and skip.is_skip and not left.is_skip:
            total = left.count + skip.count + right.count
            if total < _COALESCE_THRESHOLD:
                left.count = total
                del regions[i - 1 : i + 1]
                i -= 2
                continue
        i -= 1


# ── Region Encoding ───────────────────────────────────────────────────────────


def encode_regions(
    encoder: DataChangeEncoder,
    regions: list[DiffRegion],
    target: bytes | bytearray,
) -> None:
    """Encode diff regions as DataChange commands with run-length optimization."""
    for region in regions:
        if region.is_skip:
            encoder.skip_bytes(region.count)
        else:
            _encode_set_region(encoder, target, region.offset, region.count)


def encode_regions_limited(
    encoder: DataChangeEncoder,
    regions: list[DiffRegion],
    target: bytes | bytearray,
    result_state: bytearray,
) -> bool:
    """Encode as many diff regions as fit in the current packet budget.

    Updates `result_state` with only the bytes that were successfully encoded.
    Returns True when all regions fit, False when the packet filled before the
    entire diff could be serialized.
    """
    for region in regions:
        if region.is_skip:
            encoder.skip_bytes(region.count)
            continue

        encoded = _encode_set_region_limited(
            encoder,
            target,
            result_state,
            region.offset,
            region.count,
        )
        if encoded < region.count:
            return False

    return True


def _encode_set_region(
    encoder: DataChangeEncoder,
    target: bytes | bytearray,
    offset: int,
    count: int,
) -> None:
    """Encode a set region with run-length optimization.

    Matches the C++ createChangeMessage algorithm:
    - Runs of 3+ identical bytes -> set_repeated
    - Remaining <= 3 bytes -> set_repeated (avoids sequence overhead)
    - Varied byte sequences -> set_sequence (stops before runs of 3+)
    """
    data = target[offset : offset + count]
    i = 0

    while i < len(data):
        # Count run of identical bytes from current position
        run_len = 1
        while i + run_len < len(data) and data[i + run_len] == data[i]:
            run_len += 1

        remaining = len(data) - i
        if run_len >= _MIN_RUN_LENGTH or remaining <= _MIN_RUN_LENGTH:
            encoder.set_repeated(data[i], run_len)
            i += run_len
        else:
            # Varied sequence — accumulate until we hit a run of 3+
            seq_start = i
            j = i + 1
            while j < len(data):
                if j + 2 < len(data) and data[j] == data[j + 1] == data[j + 2]:
                    break
                j += 1
            encoder.set_sequence(data[seq_start:j])
            i = j


_END_BITS = BitSize.DATA_CHANGE_COMMAND
_SET_SEQUENCE_BASE_BITS = BitSize.DATA_CHANGE_COMMAND
_SET_SEQUENCE_BYTE_BITS = BitSize.BYTE_VALUE + BitSize.BYTE_SEQUENCE_CONTINUES
_SET_FEW_BITS = BitSize.DATA_CHANGE_COMMAND + BitSize.BYTE_COUNT_FEW + BitSize.BYTE_VALUE
_SET_FEW_LAST_BITS = BitSize.DATA_CHANGE_COMMAND + BitSize.BYTE_COUNT_FEW
_SET_MANY_BITS = BitSize.DATA_CHANGE_COMMAND + BitSize.BYTE_COUNT_MANY + BitSize.BYTE_VALUE


def _encode_set_region_limited(
    encoder: DataChangeEncoder,
    target: bytes | bytearray,
    result_state: bytearray,
    offset: int,
    count: int,
) -> int:
    """Encode a set region prefix that fits in the packet budget.

    Returns the number of heap bytes successfully encoded.
    """
    data = target[offset : offset + count]
    i = 0

    while i < len(data):
        run_len = 1
        while i + run_len < len(data) and data[i + run_len] == data[i]:
            run_len += 1

        remaining = len(data) - i
        if run_len >= _MIN_RUN_LENGTH or remaining <= _MIN_RUN_LENGTH:
            chunk_len = _max_repeated_chunk(encoder, data[i], run_len)
            if chunk_len == 0:
                break

            encoder.set_repeated(data[i], chunk_len)
            result_state[offset + i : offset + i + chunk_len] = data[i : i + chunk_len]
            i += chunk_len
            continue

        seq_start = i
        j = i + 1
        while j < len(data):
            if j + 2 < len(data) and data[j] == data[j + 1] == data[j + 2]:
                break
            j += 1

        chunk_len = _max_sequence_chunk(encoder, j - seq_start)
        if chunk_len == 0:
            break

        encoder.set_sequence(data[seq_start : seq_start + chunk_len])
        result_state[offset + seq_start : offset + seq_start + chunk_len] = (
            data[seq_start : seq_start + chunk_len]
        )
        i += chunk_len

    return i


def _max_repeated_chunk(
    encoder: DataChangeEncoder,
    value: int,
    count: int,
) -> int:
    writer = encoder._writer

    if count > _FEW_MAX and writer.has_capacity(_SET_MANY_BITS + _END_BITS):
        return min(count, _MANY_MAX)

    if value == encoder.last_value and writer.has_capacity(_SET_FEW_LAST_BITS + _END_BITS):
        return min(count, _FEW_MAX)

    if writer.has_capacity(_SET_FEW_BITS + _END_BITS):
        return min(count, _FEW_MAX)

    return 0


def _max_sequence_chunk(encoder: DataChangeEncoder, count: int) -> int:
    writer = encoder._writer
    low = 0
    high = count

    while low < high:
        mid = (low + high + 1) // 2
        bits = _SET_SEQUENCE_BASE_BITS + (mid * _SET_SEQUENCE_BYTE_BITS) + _END_BITS
        if writer.has_capacity(bits):
            low = mid
        else:
            high = mid - 1

    return low


# ── Convenience Builder ───────────────────────────────────────────────────────


def build_data_change_packet(
    device_index: int,
    packet_index: int,
    current: bytes | bytearray,
    target: bytes | bytearray,
    *,
    is_last: bool = True,
    max_packet_bytes: int = 256,
) -> bytes | None:
    """Build a SharedDataChange SysEx packet from heap diff.

    Computes the diff, encodes it with run-length optimization, and wraps
    it in a properly framed SysEx message with checksum.

    Returns None if the heaps are identical (no changes needed).
    """
    from blocksd.protocol.builder import HostPacketBuilder

    regions = compute_diff(current, target)
    if not regions:
        return None

    builder = HostPacketBuilder(max_bytes=max_packet_bytes)
    builder.write_sysex_header(device_index)
    builder.begin_data_changes(packet_index)

    encoder = DataChangeEncoder(builder.writer)
    encode_regions(encoder, regions, target)
    encoder.end(is_last=is_last)

    return builder.build()
