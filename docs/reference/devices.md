# Supported Devices

ROLI shipped a surprisingly diverse family of Blocks devices: pressure-sensitive pads, keyboard strips, control surfaces, loop controllers, and more. blocksd identifies known Blocks serial prefixes and manages discovered devices through the topology and keepalive protocol. Compatibility must be checked per device and firmware. LED bitmap streaming is currently limited to the Lightpad family, which is the only device type with an addressable RGB grid.

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

**Tested** records prior project hardware reports, not a release-by-release certification. A passing software test suite does not establish physical device compatibility or visible LED rendering.

**Untested** means no hardware validation is recorded here. A USB PID or serial prefix in the source does not guarantee discovery or support. Non-Blocks products in the table are identification references only; the MIDI scanner requires a matching Blocks port name.

## LED Capabilities

The daemon currently skips LittleFoot program upload. An accepted frame is a heap write, not proof of visible rendering (see [LittleFoot status](../architecture/littlefoot)).

Only Lightpad Block and Lightpad Block M expose a 15x15 RGB LED grid through the bitmap frame protocol. These are the only devices that:

- Advertise `grid_width = 15` and `grid_height = 15` in discovery
- Accept binary LED frame writes
- Respond to `blocksd led` CLI commands

Other recognized Blocks devices can participate in discovery and keepalive, but they advertise `grid_width = 0` / `grid_height = 0` and reject frame writes.

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

The BitmapLEDProgram (LED repaint routine) is 100 bytes, leaving the rest of the heap available for pixel data.

## USB Identification

ROLI's vendor ID is `0x2AF4`. The daemon scans MIDI port names for the words "BLOCK" or "Block", pairs matching inputs and outputs, and uses serial prefixes to identify device types. The current detector does not inspect USB IDs or sysfs.
