# blocksd — ROLI Blocks Linux Daemon

## Project Overview

Linux daemon that implements the ROLI Blocks protocol to keep devices alive, control LEDs, and manage topology. ROLI devices require an active host-side handshake over MIDI SysEx to enter "API mode" — without it, they show a "searching" animation and eventually power off.

**Stack:** Python 3.13, asyncio, python-rtmidi, Typer, Rich, Pydantic
**Package Manager:** uv
**Linter:** ruff
**Type Checker:** ty

## Architecture

```
daemon.py                 asyncio main loop, signal handling
  └─ TopologyManager      polls MIDI ports every 1.5s
       └─ DeviceGroup     per-USB lifecycle (serial → topology → API mode → ping)
            └─ MidiConnection   python-rtmidi wrapper (send/receive SysEx)
                 └─ protocol/*   pure protocol logic (packing, builder, decoder)
```

## ROLI Blocks Protocol Reference

### SysEx Framing

All BLOCKS protocol messages are MIDI SysEx:
```
F0 00 21 10 77 [deviceIndex] [7-bit packed payload] [checksum] F7
│  │           │  │                                  │
│  │           │  └ lower 6 bits = topology index    └ payload checksum & 0x7F
│  │           │    bit 6: 0=host→device, 1=device→host
│  │           └ BLOCKS product byte
│  └ ROLI manufacturer ID
└ SysEx start
```

### Checksum Calculation
```python
def calculate_checksum(data: bytes) -> int:
    checksum = len(data) & 0xFF
    for byte in data:
        checksum = (checksum + (checksum * 2 + byte)) & 0xFF
    return checksum & 0x7F
```

### 7-Bit Packing

Payload bits are packed LSB-first across 7-bit bytes (bit 7 always 0 for MIDI safety). When a value spans byte boundaries, low bits fill the current byte remainder, high bits continue in the next byte's low bits.

### Serial Number Request (separate SysEx format)
- **Request:** `F0 00 21 10 78 3F F7`
- **Response header:** `F0 00 21 10 78`
- Response contains MAC prefix `48:B6:20:` followed by 16-char serial
- Serial prefixes identify device type:
  - `LPB`/`LPM` = Lightpad Block
  - `SBB` = Seaboard Block
  - `LKB` = LUMI Keys Block
  - `LIC` = Live Block
  - `LOC` = Loop Block
  - `DCB` = Developer Control Block
  - `TCB` = Touch Block

### USB Device IDs (Vendor `0x2AF4`)

| PID      | Device              |
|----------|---------------------|
| `0x0100` | Seaboard (original) |
| `0x0200` | Seaboard RISE 25    |
| `0x0210` | Seaboard RISE 49    |
| `0x0700` | Seaboard Block      |
| `0x0900` | Lightpad Block      |
| `0x0E00` | LUMI Keys / Piano M |
| `0x0F00` | ROLI Piano (49-key) |
| `0x1000` | ROLI Airwave Pedal  |

### Protocol Constants

```
ROLI_SYSEX_HEADER     = F0 00 21 10 77
SERIAL_DUMP_REQUEST   = F0 00 21 10 78 3F F7
SERIAL_RESPONSE_HDR   = F0 00 21 10 78
RESET_MASTER          = F0 00 21 10 49 F7
PROTOCOL_VERSION      = 1
TOPOLOGY_INDEX_BROADCAST = 63
API_MODE_PING_TIMEOUT_MS = 5000
```

### Message Types — Device → Host

| ID     | Name                    | Payload                                          |
|--------|-------------------------|--------------------------------------------------|
| `0x01` | deviceTopology          | 7b deviceCount, 8b connectionCount, then blocks  |
| `0x02` | packetACK               | 10b packetCounter                                |
| `0x03` | firmwareUpdateACK       | 7b code, 32b detail                              |
| `0x04` | deviceTopologyExtend    | continuation of topology                         |
| `0x05` | deviceTopologyEnd       | signals end of multi-packet topology             |
| `0x06` | deviceVersion           | index + version string                           |
| `0x07` | deviceName              | index + name string                              |
| `0x10` | touchStart              | 7b devIdx, 5b touchIdx, 12b x, 12b y, 8b z      |
| `0x11` | touchMove               | same as touchStart                               |
| `0x12` | touchEnd                | same as touchStart                               |
| `0x13` | touchStartWithVelocity  | + 8b vx, 8b vy, 8b vz                           |
| `0x14` | touchMoveWithVelocity   | + velocity                                       |
| `0x15` | touchEndWithVelocity    | + velocity                                       |
| `0x18` | configMessage           | config command + data                            |
| `0x20` | controlButtonDown       | 7b devIdx, 12b buttonID                          |
| `0x21` | controlButtonUp         | 7b devIdx, 12b buttonID                          |
| `0x28` | programEventMessage     | 3 × 32b integers                                 |
| `0x30` | logMessage              | string data                                      |

### Message Types — Host → Device

| ID     | Name                  | Payload                              |
|--------|-----------------------|--------------------------------------|
| `0x01` | deviceCommandMessage  | 9b command (see Device Commands)     |
| `0x02` | sharedDataChange      | 16b packetIndex + data change cmds   |
| `0x03` | programEventMessage   | 3 × 32b integers                     |
| `0x04` | firmwareUpdatePacket  | 7b size + 7-bit encoded data         |
| `0x10` | configMessage         | 4b configCmd + item + value          |
| `0x11` | factoryReset          | (no payload)                         |
| `0x12` | blockReset            | (no payload)                         |
| `0x20` | setName               | 7b length + 7-bit chars              |

### Device Commands (inside deviceCommandMessage)

| ID     | Name                   |
|--------|------------------------|
| `0x00` | beginAPIMode           |
| `0x01` | requestTopologyMessage |
| `0x02` | endAPIMode             |
| `0x03` | ping                   |
| `0x04` | debugMode              |
| `0x05` | saveProgramAsDefault   |

### Config Commands

| ID     | Name               |
|--------|--------------------|
| `0x00` | setConfig          |
| `0x01` | requestConfig      |
| `0x02` | requestFactorySync |
| `0x03` | requestUserSync    |
| `0x04` | updateConfig       |
| `0x05` | updateUserConfig   |
| `0x06` | setConfigState     |
| `0x07` | factorySyncEnd     |
| `0x08` | clusterConfigSync  |
| `0x09` | factorySyncReset   |

### Data Change Commands (for sharedDataChange / program upload)

| ID  | Name                    | Extra bits                  |
|-----|-------------------------|-----------------------------|
| `0` | endOfPacket             | —                           |
| `1` | endOfChanges            | —                           |
| `2` | skipBytesFew            | 4b count                    |
| `3` | skipBytesMany           | 8b count                    |
| `4` | setSequenceOfBytes      | (8b value + 1b continues)×N |
| `5` | setFewBytesWithValue    | 4b count + 8b value         |
| `6` | setFewBytesWithLastValue| 4b count                    |
| `7` | setManyBytesWithValue   | 8b count + 8b value         |

### Topology Packet Format

Device info block (per device in topology):
- 16 × 7-bit chars: serial number
- 5 bits: battery level
- 1 bit: battery charging

Connection info block:
- 7 bits: device1 topology index
- 5 bits: device1 port (clockwise from top-left)
- 7 bits: device2 topology index
- 5 bits: device2 port

Max 6 devices and 24 connections per topology packet. Use extend/end for larger topologies.

### Connection Lifecycle (from roli_ConnectedDeviceGroup.cpp)

```
1. Scan MIDI ports for names containing "BLOCK" or "Block"
2. Open matched in/out pair
3. Send serial dump: F0 00 21 10 78 3F F7 (retry every 300ms)
4. Parse serial from response (find "48:B6:20:", skip MAC, read 16 chars)
5. Send requestTopologyMessage (cmd 0x01) to device index 0
6. Parse topology response → build device list
7. For each device not yet in API mode:
   a. Send endAPIMode (cmd 0x02) — reset stale state
   b. Send beginAPIMode (cmd 0x00) — enter rich protocol
8. Ping loop:
   - Master block: ping every ~400ms
   - DNA-connected blocks: ping every ~1666ms
   - Device timeout: 5000ms without ping → falls back to MPE mode
9. On ACK received: update ping timer for that device
10. On topology change: re-request topology
11. On disconnect: destroy group, emit device-removed
```

### Bit Sizes Reference

| Field              | Bits |
|--------------------|------|
| MessageType        | 7    |
| ProtocolVersion    | 8    |
| PacketTimestamp     | 32   |
| TimestampOffset    | 5    |
| TopologyIndex      | 7    |
| DeviceCount        | 7    |
| ConnectionCount    | 8    |
| BatteryLevel       | 5    |
| BatteryCharging    | 1    |
| ConnectorPort      | 5    |
| TouchIndex         | 5    |
| TouchPosition.x    | 12   |
| TouchPosition.y    | 12   |
| TouchPosition.z    | 8    |
| TouchVelocity.v*   | 8    |
| DeviceCommand      | 9    |
| ConfigCommand      | 4    |
| ConfigItemIndex    | 8    |
| ConfigItemValue    | 32   |
| ControlButtonID    | 12   |
| PacketCounter      | 10   |
| PacketIndex        | 16   |
| DataChangeCommand  | 3    |
| ByteCountFew       | 4    |
| ByteCountMany      | 8    |
| ByteValue          | 8    |
| ByteSequenceCont   | 1    |
| FirmwareUpdateACK  | 7    |
| FirmwareUpdateDtl  | 32   |
| FirmwareUpdateSize | 7    |

### Device Memory Sizes

| Device Type    | Program + Heap | Stack |
|----------------|---------------|-------|
| Pad Block      | 7200 bytes    | 800   |
| Control Block  | 3000 bytes    | 800   |

## Key Reference Files

Protocol source (cloned to `~/Downloads/roli-extracted/roli_blocks_basics/`):
- `protocol/roli_BitPackingUtilities.h` — 7-bit packing algorithm (CRITICAL to port correctly)
- `protocol/roli_BlocksProtocolDefinitions.h` — all enums, constants, bit sizes
- `protocol/roli_HostPacketBuilder.h` — host→device packet construction
- `protocol/roli_HostPacketDecoder.h` — device→host packet parsing
- `protocol/roli_BlockModels.h` — device type definitions and capabilities
- `topology/internal/roli_ConnectedDeviceGroup.cpp` — full device lifecycle state machine
- `topology/internal/roli_BlockSerialReader.cpp` — serial number request/parse
- `topology/internal/roli_MIDIDeviceDetector.cpp` — MIDI port scanning/matching
- `topology/internal/roli_Detector.cpp` — top-level detection loop
- `topology/internal/roli_MidiDeviceConnection.cpp` — MIDI I/O wrapper

Extracted ROLI Connect installer (`~/Downloads/roli-extracted/`):
- `rpkg-driver/` — Windows driver package (reference only)
- `midi-driver/DriverINF` — USB VID/PID mapping
- `app-asar-unpacked/` — Electron app source (minified JS)
- `app/resources/app/resources/extra/firmware/default/*.littlefoot` — device firmware

## Implementation Phases

### Phase 1: Protocol Core (no hardware needed)
`protocol/constants.py` → `protocol/checksum.py` → `protocol/packing.py` → `protocol/builder.py` → `protocol/decoder.py` → `protocol/serial.py` + full test suite

### Phase 2: Device Models
`device/models.py` → `device/registry.py` → `device/config_ids.py`

### Phase 3: Connection Layer
`device/connection.py` → `topology/detector.py` → `topology/device_group.py` → `topology/manager.py`

### Phase 4: Daemon + Config
`daemon.py` → `config/schema.py` + `config/loader.py` → `logging.py`

### Phase 5: CLI
`cli/app.py` → `cli/status.py` → `cli/config_cmd.py` → `cli/led_cmd.py`

### Phase 6: LED Control + Program Upload
`led/bitmap.py` → `led/patterns.py` → `protocol/data_change.py`

### Phase 7: Polish
systemd service → udev rules → `cli/service.py` → sd_notify integration

## Critical Implementation Notes

- **7-bit packing is the #1 risk** — must be tested exhaustively with round-trips and golden vectors from the C++ implementation
- **Ping timing is critical** — 5000ms timeout means we need reliable <400ms ping intervals. Use dedicated asyncio tasks, not shared timers
- **rtmidi callbacks arrive on a separate thread** — marshal to asyncio via `loop.call_soon_threadsafe()` or `asyncio.Queue`
- **ALSA handles multi-client MIDI natively** — we don't block DAW access
- **Device detection**: match MIDI port names containing "BLOCK" or "Block", validate with USB VID `0x2AF4` via sysfs as fallback
- **Incoming packet processing**: strip SysEx header (5 bytes), first byte after header is device index, remaining bytes are payload + checksum (last byte). Validate checksum on payload bytes, then create `Packed7BitReader` from payload (excluding checksum)
