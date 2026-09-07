# Supported Devices

ROLI shipped a surprisingly diverse family of Blocks devices: pressure-sensitive pads, keyboard strips, control surfaces, loop controllers, and more. blocksd identifies known Blocks serial prefixes and manages discovered devices through the topology and keepalive protocol. Compatibility must be checked per device and firmware. Lightpad devices expose a bitmap grid; LUMI Keys uses a separate per-key lighting surface.

## Device Matrix

| Device                  | USB PID  | Serial Prefix | LED Grid | Status      |
| ----------------------- | -------- | ------------- | -------- | ----------- |
| Lightpad Block          | `0x0900` | `LPB`         | 15x15    | ✅ Tested   |
| Lightpad Block M        | `0x0900` | `LPM`         | 15x15    | ✅ Tested   |
| LUMI Keys Block         | `0x0E00` | `LKB`         | :        | ✅ Tested   |
| Seaboard Block          | `0x0700` | `SBB`         | :        | 🔲 Untested |
| Live Block              | :        | `LIC`         | :        | 🔲 Untested |
| Loop Block              | :        | `LOC`         | :        | 🔲 Untested |
| Developer Control Block | :        | `DCB`         | :        | 🔲 Untested |
| Touch Block             | :        | `TCB`         | :        | 🔲 Untested |
| Seaboard RISE 25        | `0x0200` | :             | :        | 🔲 Untested |
| Seaboard RISE 49        | `0x0210` | :             | :        | 🔲 Untested |
| ROLI Piano (49-key)     | `0x0F00` | :             | :        | 🔲 Untested |
| ROLI Airwave Pedal      | `0x1000` | :             | :        | 🔲 Untested |

## What "Tested" Means

**Tested** records prior project hardware reports, not a release-by-release certification. Visible RGB patterns were confirmed on Lightpad Block M firmware 1.1.0 and LUMI Keys firmware 1.3.9 on September 7, 2026. The original Lightpad has no new rendering validation from that session. Live MIDI/MPE preservation during LUMI lighting, sustained frame timing, and physical color calibration remain unverified.

**Untested** means no hardware validation is recorded here. A USB PID or serial prefix in the source does not guarantee discovery or support. Non-Blocks products in the table are identification references only; the MIDI scanner requires a matching Blocks port name.

## LED Capabilities

The first frame loads the appropriate LittleFoot renderer. Pixel delivery waits for complete upload acknowledgement and a matching renderer challenge reply. Accepted API frames confirm daemon acceptance, not visible output (see [LittleFoot status](../architecture/littlefoot)).

| Device                | Discovery capability                                   | Frame API                     | CLI                                                       |
| --------------------- | ------------------------------------------------------ | ----------------------------- | --------------------------------------------------------- |
| Lightpad / Lightpad M | `grid_width = 15`, `grid_height = 15`, `key_count = 0` | Binary bitmap or JSON `frame` | `led solid`, `rainbow`, `gradient`, `checkerboard`, `off` |
| LUMI Keys             | `grid_width = 0`, `grid_height = 0`, `key_count = 24`  | JSON `key_frame`              | `led keys`                                                |

Key lighting requires LUMI firmware 1.3.0 or newer. Other recognized Blocks can participate in discovery and keepalive, but do not expose a supported lighting surface.

## Touch and Button Events

The decoder handles Blocks touch and button messages when a device emits them. Touch coordinates and pressure are normalized; velocity is signed. The API exposes touch position, pressure, velocity, and contact index, plus button press/release actions. The protocol button ID is not currently included in the API event. Ordinary MIDI notes and MPE events are not translated into touch events by this API.

## DNA Mesh Networking

Blocks devices with DNA magnetic connectors can form a mesh. When blocks are physically connected:

- The USB-connected block becomes the master (topology index 0)
- DNA-connected blocks get indices 1+
- All protocol messages to non-master blocks are routed through the master
- Touch events from DNA blocks arrive through the master's USB connection

blocksd tracks the full mesh topology and maintains keepalive for all devices in the chain.

## Device Memory

Devices have limited memory for LittleFoot programs:

| Device Type          | Program + Heap | Stack     |
| -------------------- | -------------- | --------- |
| Pad Block (Lightpad) | 7200 bytes     | 800 bytes |
| Control Block        | 3000 bytes     | 800 bytes |

The Lightpad renderer occupies 145 bytes plus a 450-byte pixel heap. The LUMI renderer occupies 130 bytes plus a 48-byte pixel heap.

## USB Identification

ROLI's vendor ID is `0x2AF4`. The daemon scans MIDI port names for the words "BLOCK" or "Block", pairs matching inputs and outputs, and uses serial prefixes to identify device types. The current detector does not inspect USB IDs or sysfs.
