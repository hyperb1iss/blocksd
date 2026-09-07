# LittleFoot VM

ROLI Blocks run LittleFoot, a bytecode virtual machine in the firmware. The host uploads a renderer and sends pixel data to its heap. The renderer calls `fillPixel()` during device-side repaint callbacks.

## Renderer Startup

The daemon loads a renderer when it accepts the first frame for a supported device. Discovery and keepalive alone leave the device's existing program in place.

Startup follows this sequence:

1. Upload the renderer with an empty pixel heap. Initialisation disables the status overlay; LUMI also retains its default musical handler.
2. Wait for acknowledgement of the complete code transfer.
3. Send a fresh execution challenge to the renderer's `handleMessage()` callback.
4. Accept only the matching reply, then publish the latest queued pixel frame. Subsequent frames update the pixel heap directly.

The challenge and reply each contain three integers: `(0x424C4544, renderer_kind, nonce)`. Renderer kind `1` identifies the Lightpad bitmap program; kind `2` identifies the LUMI key program. The nonce is a positive signed 32-bit value refreshed whenever confirmed heap state is lost. LUMI initialisation calls `setUseDefaultKeyHandler(true, false)` (retain musical key handling, replace lighting).

An unanswered challenge is retried without reuploading the program. The message callback can answer even if identical program bytes survive a reconnect without another initialisation callback. When confirmed heap state is lost, the daemon clears readiness, rotates the nonce, and restarts the code-only transfer while retaining the latest requested pixels. Replies from the previous transfer cannot release those pixels.

An accepted API frame confirms daemon acceptance. The frame can remain queued during renderer startup. Neither API acceptance nor a device packet ACK establishes visible rendering.

## Programs and Pixel Layout

| Surface               | Program size | Pixel heap        | Device coordinates          |
| --------------------- | ------------ | ----------------- | --------------------------- |
| Lightpad / Lightpad M | 145 bytes    | 450 bytes, RGB565 | 15×15 grid                  |
| LUMI Keys             | 130 bytes    | 48 bytes, RGB565  | 24 keys at `(key_index, 0)` |

Both programs expose `initialise()`, `repaint()`, and `handleMessage()`. Pixel data begins immediately after the program binary. Each little-endian 16-bit pixel stores red in bits 0 to 4, green in bits 5 to 10, and blue in bits 11 to 15. Repaint expands these channels to 8-bit values with shifts of 3, 2, and 3 bits respectively.

LUMI does not expose the SDK's bitmap LEDGrid capability. Its key lighting uses `fillPixel(colour, key_index, 0)`, following the vendor's LittleFoot example. The separate key-frame API preserves that distinction.

## Program Binary Format

```text
Offset 0-1:  uint16 LE  checksum
Offset 2-3:  uint16 LE  program size, including header
Offset 4-5:  uint16 LE  number of functions
Offset 6-7:  uint16 LE  number of globals
Offset 8-9:  uint16 LE  heap size
Offset 10+:  function table (int16 function ID + uint16 code address)
Remaining:   bytecode
```

The checksum algorithm is `n = programSize; for each byte from index 2: n = (3*n + byte) & 0xFFFF`. Function addresses and jump targets are relative to the complete program binary, including the header and function table.

Native function IDs use the SDK's multiply-by-31 signature hash. The return-type character after `/` is excluded; the signature length is added before retaining the low 16 bits. Native calls push arguments right to left. Callback IDs use the same hashing convention.

| Signature        | Function ID |
| ---------------- | ----------- |
| `makeARGB/iiiii` | `0x3F83`    |
| `fillPixel/viii` | `0xC20B`    |
| `repaint/v`      | `0x6F8D`    |

## What Hardware Testing Established

On September 7, 2026, visible red and repeating RGB patterns were confirmed on a USB-connected LUMI Keys running firmware 1.3.9 and a DNA-connected Lightpad Block M running firmware 1.1.0. An instrumented bitmap program also completed all 225 pixel iterations on hardware. Both devices answered fresh execution challenges after simulated host heap-state loss while their unchanged programs remained on-device. The subsequent pixel transfers were acknowledged. Physical cable and power-cycle recovery still need separate checks.

The unchanged upstream C++ LittleFoot runner executes both renderer binaries. Native callback checks verify challenge replies, rejection of unrelated messages, status-overlay settings, LUMI handler arguments, and each pixel's coordinates and logical RGB565 color across repeated repaint calls.

These checks do not establish calibrated physical colors, sustained frame rate, latency, or compatibility with every firmware version. The LUMI renderer requests preservation of musical handling, but a live MIDI/MPE exercise during lighting remains pending. Key rendering requires firmware 1.3.0 or newer (the documented minimum for separate musical and lighting handler switches).

## Causes of the Earlier Rendering Failure

### Incorrect Jump Addresses

The assembler previously encoded jumps relative to the bytecode section. The VM interpreted them relative to the complete program binary. The original bitmap program reproduced an illegal-instruction error in the upstream C++ runner after drawing one pixel. Relocating jump targets by the header and function-table size allowed all 225 pixels to render correctly.

Earlier reports attributed those errors to incompatible `dupOffset` and `getHeapBits` opcodes. Those reports did not isolate firmware incompatibility; the host's incorrect jump addresses were sufficient to reproduce the failure. The current renderer uses the SDK opcode map.

### Pixel Data Lost During Startup

Hardware probes read zeroes from pixel data uploaded alongside program code. A later pixel-only white frame produced the expected byte values. The startup handshake now delays the first pixel upload until the complete code transfer is acknowledged and the renderer answers the current execution challenge.

### Status Overlay

A minimal green test rendered visibly over the existing background. Disabling the device's status overlay allowed the uploaded renderer to control the full surface. Both renderer initialisers disable that overlay.

### Heap Synchronisation and DNA Forwarding

Unknown heap bytes must differ from every target value, including zero. The diff engine maps unknown bytes to `target[i] ^ 0xFF` so the first transfer replaces stale memory.

The USB-connected bridge must remain in API mode to forward messages to DNA-connected devices. The daemon activates and keeps alive every device in the topology.
