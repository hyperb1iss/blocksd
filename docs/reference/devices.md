# Supported Devices

ROLI shipped a surprisingly diverse family of Blocks devices: pressure-sensitive pads, keyboard strips, control surfaces, loop controllers, and more. blocksd supports all known Blocks devices through the topology and keepalive protocol. LED bitmap streaming is currently limited to the Lightpad family, which is the only device type with an addressable RGB grid.

## Device Matrix

| Device                  | USB PID  | Serial Prefix | LED Grid | Status      |
| ----------------------- | -------- | ------------- | -------- | ----------- |
| Lightpad Block          | `0x0900` | `LPB`         | 15x15    | ✅ Tested   |
| Lightpad Block M        | `0x0900` | `LPM`         | 15x15    | ✅ Tested   |
| LUMI Keys Block         | `0x0E00` | `LKB`         | —        | ✅ Tested   |
| Seaboard Block          | `0x0700` | `SBB`         | —        | 🔲 Untested |
| Live Block              | —        | `LIC`         | —        | 🔲 Untested |
| Loop Block              | —        | `LOC`         | —        | 🔲 Untested |
| Developer Control Block | —        | `DCB`         | —        | 🔲 Untested |
| Touch Block             | —        | `TCB`         | —        | 🔲 Untested |
| Seaboard RISE 25        | `0x0200` | —             | —        | 🔲 Untested |
| Seaboard RISE 49        | `0x0210` | —             | —        | 🔲 Untested |
| ROLI Piano (49-key)     | `0x0F00` | —             | —        | 🔲 Untested |
| ROLI Airwave Pedal      | `0x1000` | —             | —        | 🔲 Untested |

## What "Tested" Means

**Tested** devices have been physically connected and verified through the full lifecycle: serial request, topology discovery, API mode activation, keepalive, and (where applicable) LED control and touch events.

**Untested** devices are supported at the protocol level. blocksd will discover them, read their serial numbers, include them in topology, and maintain API mode keepalive. But the specific device behavior hasn't been validated with real hardware.

## LED Capabilities

Only Lightpad Block and Lightpad Block M expose a 15x15 RGB LED grid through the bitmap frame protocol. These are the only devices that:

- Advertise `grid_width = 15` and `grid_height = 15` in discovery
- Accept binary LED frame writes
- Respond to `blocksd led` CLI commands

Other devices (LUMI Keys, Seaboard, Control Blocks) are discoverable and kept alive, but they advertise `grid_width = 0` / `grid_height = 0` and reject frame writes.

## Touch Capabilities

Touch events are supported on devices with pressure-sensitive surfaces:

- **Lightpad Block / M**: 15x15 continuous touch surface with X, Y, Z (pressure) and velocity
- **Seaboard Block**: continuous pitch surface with MPE expression
- **LUMI Keys**: key-level pressure sensitivity

Touch events are normalized to floating-point values (0.0 to 1.0) regardless of the device's native resolution.

## Button Capabilities

Control-style devices emit button press/release events:

- **Live Block**: transport controls
- **Loop Block**: loop controls
- **Developer Control Block**: programmable buttons

Buttons are identified by a 12-bit button ID.

## DNA Mesh Networking

All Blocks devices support DNA magnetic connectors for mesh networking. When blocks are physically connected:

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

The BitmapLEDProgram (LED repaint routine) is 94 bytes, leaving the rest of the heap available for pixel data.

## USB Identification

All ROLI devices share vendor ID `0x2AF4`. blocksd identifies devices by:

1. Scanning MIDI port names for "BLOCK" or "Block"
2. Validating the USB vendor ID via sysfs (fallback check)
3. Requesting the serial number to determine the exact device type

The MIDI port name check is primary because it works across all Linux MIDI subsystems. The sysfs check provides additional confidence when the port name is ambiguous.
