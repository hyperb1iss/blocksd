# Lightpad Block M Firmware v1.1.0 — LittleFoot VM Notes

Hardware testing session 2026-03-15. Devices: Lightpad Block M (fw 1.1.0), LUMI Keys Block (fw 1.3.9).

## What Works

- **Keep-alive**: serial request, topology, beginAPIMode, ping, packetACK — all work correctly
- **Config sync**: factory sync, config request/set — all work
- **SharedDataChange**: data change packets are received, ACK'd, and applied to device heap
- **Program upload + execution**: LittleFoot programs uploaded via SharedDataChange DO execute
- **fillPixel / makeARGB**: native functions work correctly at any (x,y) coordinate
- **DNA bridge**: LUMI Keys forwards messages to Lightpad via DNA — requires beginAPIMode on LUMI Keys first
- **Verified working program**: 225 unrolled fillPixel(makeARGB(255,0,255,0), x, y) calls → solid green fill ✓

## Opcode Compatibility

The firmware's LittleFoot VM opcode table **differs** from the ROLI JUCE SDK source (`~/Downloads/roli-extracted/roli_blocks_basics/littlefoot/roli_LittleFootRunner.h`).

### Known Working Opcodes

| Byte | SDK Name    | Operand | Verified                   |
| ---- | ----------- | ------- | -------------------------- |
| 0x00 | halt        | —       | ✓                          |
| 0x01 | jump        | int16   | ✓ (loop back-jumps work)   |
| 0x03 | jumpIfFalse | int16   | ✓ (loop conditionals work) |
| 0x05 | retVoid     | int8    | ✓                          |
| 0x07 | callNative  | int16   | ✓ (makeARGB, fillPixel)    |
| 0x08 | drop        | —       | ✓                          |
| 0x0B | push0       | —       | ✓                          |
| 0x0C | push1       | —       | ✓                          |
| 0x0D | push8       | int8    | ✓                          |
| 0x0E | push16      | int16   | ✓                          |
| 0x10 | dup         | —       | ✓                          |

### Known Broken Opcodes

| Byte | SDK Name     | Result                                                       |
| ---- | ------------ | ------------------------------------------------------------ |
| 0x11 | dupOffset_01 | **ILLEGAL INSTRUCTION** — device logs error, program aborted |
| 0x40 | getHeapBits  | **ILLEGAL INSTRUCTION** — the BitmapLEDProgram uses this     |

### Uncertain / Behaves Differently

| Byte | SDK Name        | Observation                                                                                                                                        |
| ---- | --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0x12 | dupOffset_02    | Works but produces wrong results — may be dupOffset(int8) consuming next byte as operand, OR dupOffset_02 but stack layout differs from simulation |
| 0x18 | dupOffset(int8) | Produced blank screen — may not be dupOffset on this firmware                                                                                      |
| 0x1C | dupFromGlobal   | No illegal instruction but globals always returned 0                                                                                               |
| 0x1D | dropToGlobal    | Same — silently fails                                                                                                                              |
| 0x20 | add_int32       | Loop increment works in corner test context                                                                                                        |
| 0x24 | sub_int32       | Loop comparison works                                                                                                                              |
| 0x36 | test_lt_int32   | Loop comparison works                                                                                                                              |

### Untested but Likely Working (0x00-0x10 range)

0x02 (jumpIfTrue), 0x04 (call), 0x06 (retValue), 0x09 (dropMultiple), 0x0A (pushMultiple0), 0x0F (push32)

### Untested and Risky (0x11+ range)

Everything from 0x11 onward might have a shifted opcode table. The safe opcodes above 0x10 that we verified (0x20 add, 0x24 sub, 0x36 test_lt) might work by coincidence or because the shift preserves their positions.

## Key Bugs Fixed

### 1. RemoteHeap `_expected_state()` — Full Heap Sync

**Bug**: Unknown device bytes (uint16 0x100) were mapped to 0x00 in `_expected_state()`. When the target was also 0x00 (all bytes beyond the program), the diff engine skipped them. The device heap retained stale data from previous programs/firmware.

**Fix**: Map unknown bytes to `target[i] ^ 0xFF`, guaranteeing they always differ from the target. Add `isAllZero` guard (matching ROLI source) to prevent flushing a blank heap.

**Impact**: Without this fix, uploaded programs never executed — the device heap had corrupted data around the program.

### 2. DNA Bridge Requires API Mode on All Devices

**Bug**: When connecting through the LUMI Keys (USB) to the Lightpad (DNA), messages addressed to the Lightpad weren't delivered unless the LUMI Keys was also in API mode.

**Fix**: The daemon already sends beginAPIMode to all devices via `_start_api_on_unconnected()`. The retry logic handles the DNA latency. No code change needed — just documented behavior.

### 3. Initial TOS Value from FunctionExecutionContext

**Observation**: The VM initializes `tos = 0` before calling `repaint()`. The first push operation flushes this value onto the stack, creating an extra entry that shifts all `dup_offset` references. This is by design in the VM but wasn't accounted for in our hand-assembled bytecode.

**Status**: Worked around by using unrolled code. Needs proper handling if we implement loops.

## Architecture for Per-Pixel LED Control

The original plan: upload a BitmapLEDProgram that reads RGB565 pixel data from the heap, host writes pixels via SharedDataChange. This is how the ROLI SDK does it.

**Problem**: BitmapLEDProgram requires `getHeapBits` (0x40) which is illegal on this firmware.

### Alternative Approaches

1. **getHeapByte (0x3E)** — Read whole bytes from heap, extract RGB565 fields with bit shifts. May work if 0x3E is a valid opcode. Needs testing.

2. **Unrolled repaint with heap reads** — Instead of a loop, emit 225 hardcoded getHeapByte + fillPixel sequences. Program size: ~225 × 30 bytes = 6750 bytes (fits in 7200-byte heap, barely). But leaves almost no room for pixel data in the heap.

3. **Multiple programs per frame** — Upload a new program for each frame that has hardcoded pixel colors. Extremely inefficient (full heap sync per frame).

4. **Figure out the actual opcode table** — Systematically probe each opcode 0x11-0x42 to build the real opcode map. Then rewrite programs using the correct opcodes. This is the right long-term fix.

5. **Firmware update protocol** — Implement firmware update in blocksd to flash newer firmware that matches the SDK. The ROLI protocol supports this (firmwareUpdatePacket 0x04). But ROLI confirmed v1.1.0 is the latest for Lightpad Block M.

### Recommended Next Step

**Probe the opcode table.** Write a small test harness that uploads programs using each opcode and checks for "Illegal instruction" log messages. Build the real opcode map, then rewrite BitmapLEDProgram accordingly.

Key unknowns to resolve:

- Is `getHeapByte` (0x3E) or `getHeapInt` (0x3F) available?
- What is the actual opcode for `dupOffset(int8)`?
- Do loops work if we use the correct opcodes?
- What is the max ops per repaint call on this firmware?

## Native Function IDs (Verified Working)

| Signature      | ID              | Verified                                         |
| -------------- | --------------- | ------------------------------------------------ |
| makeARGB/iiiii | 0x3F83 (16259)  | ✓                                                |
| fillPixel/viii | 0xC20B (-15861) | ✓                                                |
| repaint/v      | 0x6F8D (28557)  | ✓ (function ID lookup works)                     |
| clearDisplay/v | unknown         | untested (was in one test but unclear if it ran) |

## Program Binary Format (Verified)

```
Offset 0-1:  uint16 LE  checksum (matches ROLI algorithm)
Offset 2-3:  uint16 LE  program size (bytes, including header)
Offset 4-5:  uint16 LE  number of functions
Offset 6-7:  uint16 LE  number of globals
Offset 8-9:  uint16 LE  heap size
Offset 10+:  function table (4 bytes each: int16 func_id + uint16 code_offset)
Remaining:   bytecode
```

Checksum algorithm: `n = programSize; for each byte from index 2: n = (3*n + byte) & 0xFFFF`

Program checksum validation confirmed working — device only executes programs with matching checksums.

## Test Files

- `diag.py` — standalone diagnostic script for raw MIDI testing (not committed)
- Corner test, green fill, and various loop programs were tested inline in `device_group.py`
