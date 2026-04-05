# LittleFoot VM

ROLI Blocks devices run LittleFoot, a bytecode virtual machine baked into the firmware. Programs uploaded to the device execute locally at native speed, enabling LED rendering and touch processing without USB round-trips. This is how ROLI's own software achieves responsive LED feedback: the host writes pixel data to the device heap, and a LittleFoot program reads it and calls `fillPixel()` on each repaint cycle.

## Architecture

blocksd includes a complete LittleFoot assembler that generates valid program binaries from instruction sequences. The assembler handles label resolution, function table generation, and program checksum computation.

```mermaid
graph LR
    ASM[Assembly Instructions] --> ASSEMBLE[Assembler]
    ASSEMBLE --> BIN[Program Binary]
    BIN --> DC[Data Change Encoder]
    DC --> HEAP[Device Heap Upload]
    HEAP --> VM[LittleFoot VM on Device]
```

## Program Binary Format

```
Offset 0-1:  uint16 LE  checksum
Offset 2-3:  uint16 LE  program size (bytes, including header)
Offset 4-5:  uint16 LE  number of functions
Offset 6-7:  uint16 LE  number of globals
Offset 8-9:  uint16 LE  heap size
Offset 10+:  function table (4 bytes each: int16 func_id + uint16 code_offset)
Remaining:   bytecode
```

The checksum algorithm: `n = programSize; for each byte from index 2: n = (3*n + byte) & 0xFFFF`. The device validates this before executing.

## Native Functions

LittleFoot programs call native device functions by their hashed name (FNV1a of the signature string).

| Function         | ID                | Verified |
| ---------------- | ----------------- | -------- |
| `makeARGB/iiiii` | `0x3F83` (16259)  | ✅       |
| `fillPixel/viii` | `0xC20B` (-15861) | ✅       |
| `repaint/v`      | `0x6F8D` (28557)  | ✅       |

These functions are called via the `callNative` opcode with the function's 16-bit hash as the operand.

## BitmapLEDProgram

The primary use case for LittleFoot in blocksd is the BitmapLEDProgram: a 94-byte repaint routine that reads RGB565 pixel data from the heap and calls `fillPixel()` for each of the 225 pixels on the Lightpad's 15x15 grid.

This is the same approach used by the ROLI SDK. The host writes pixel data to the device heap via SharedDataChange, and the LittleFoot program renders it on each repaint cycle.

## Firmware Compatibility

::: warning
The LittleFoot program upload is currently disabled due to opcode incompatibilities with Lightpad Block M firmware v1.1.0.
:::

### Known Working Opcodes

| Byte   | Name        | Verified                 |
| ------ | ----------- | ------------------------ |
| `0x00` | halt        | ✅                       |
| `0x01` | jump        | ✅ (loop back-jumps)     |
| `0x03` | jumpIfFalse | ✅ (loop conditionals)   |
| `0x05` | retVoid     | ✅                       |
| `0x07` | callNative  | ✅ (makeARGB, fillPixel) |
| `0x08` | drop        | ✅                       |
| `0x0B` | push0       | ✅                       |
| `0x0C` | push1       | ✅                       |
| `0x0D` | push8       | ✅                       |
| `0x0E` | push16      | ✅                       |
| `0x10` | dup         | ✅                       |

### Known Broken Opcodes

| Byte   | Name         | Result                                                  |
| ------ | ------------ | ------------------------------------------------------- |
| `0x11` | dupOffset_01 | **Illegal instruction**, program aborted                |
| `0x40` | getHeapBits  | **Illegal instruction**, BitmapLEDProgram requires this |

The firmware's opcode table differs from the ROLI JUCE SDK source. Opcodes `0x11` and `0x40` are critical for the standard BitmapLEDProgram but crash the VM on firmware v1.1.0.

### Workaround

blocksd currently bypasses LittleFoot entirely for LED control. Instead of uploading a repaint program and writing pixel data to the heap, the daemon uses unrolled `fillPixel` calls (225 per frame) via SharedDataChange. This is less efficient but works reliably on all tested firmware versions.

## Key Bugs Discovered

### RemoteHeap Full Heap Sync

Unknown device bytes (uint16 `0x100`) were mapped to `0x00` in the expected state computation. When the target was also `0x00`, the diff engine skipped those bytes, leaving stale data in the device heap. Fix: map unknown bytes to `target[i] ^ 0xFF`, guaranteeing they always diff.

### DNA Bridge Requires API Mode on All Devices

Messages addressed to a DNA-connected Lightpad weren't delivered unless the USB-connected LUMI Keys was also in API mode. The daemon already handles this by activating API mode on all devices in the topology.

### Initial TOS Value

The VM initializes `tos = 0` before calling `repaint()`. The first push operation flushes this value onto the stack, creating an extra entry that shifts all `dup_offset` references. Worked around with unrolled code.

## Future Work

The right long-term fix is to probe the actual opcode table on each firmware version by uploading small test programs and checking for illegal instruction errors. Once the real opcode map is known, BitmapLEDProgram can be rewritten to use the correct opcodes.

Key unknowns to resolve:

- Is `getHeapByte` (`0x3E`) available on v1.1.0?
- What is the actual opcode for `dupOffset(int8)`?
- Do loops work with the correct opcodes?
- What is the max ops per repaint call?
