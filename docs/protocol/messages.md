# Message Types

The Blocks protocol defines two sets of messages: device-to-host (responses, events, topology) and host-to-device (commands, configuration, data writes). This is the complete catalog, covering everything from keepalive pings to pressure-sensitive touch events to heap memory diffs for LED updates.

Every message payload starts with a 7-bit message type followed by an 8-bit protocol version. The remaining bits depend on the message type and are decoded according to the bit sizes in the [framing reference](./sysex-framing#seven-bit-packing).

## Device → Host Messages

These messages originate from the device and are received by blocksd.

| ID     | Name                   | Payload                                                           |
| ------ | ---------------------- | ----------------------------------------------------------------- |
| `0x01` | deviceTopology         | 7b deviceCount, 8b connectionCount, then device/connection blocks |
| `0x02` | packetACK              | 10b packetCounter                                                 |
| `0x03` | firmwareUpdateACK      | 7b code, 32b detail                                               |
| `0x04` | deviceTopologyExtend   | continuation of topology (multi-packet)                           |
| `0x05` | deviceTopologyEnd      | signals end of multi-packet topology                              |
| `0x06` | deviceVersion          | index + version string                                            |
| `0x07` | deviceName             | index + name string                                               |
| `0x10` | touchStart             | 7b devIdx, 5b touchIdx, 12b x, 12b y, 8b z                        |
| `0x11` | touchMove              | same as touchStart                                                |
| `0x12` | touchEnd               | same as touchStart                                                |
| `0x13` | touchStartWithVelocity | + 8b vx, 8b vy, 8b vz                                             |
| `0x14` | touchMoveWithVelocity  | + velocity                                                        |
| `0x15` | touchEndWithVelocity   | + velocity                                                        |
| `0x18` | configMessage          | config command + data                                             |
| `0x20` | controlButtonDown      | 7b devIdx, 12b buttonID                                           |
| `0x21` | controlButtonUp        | 7b devIdx, 12b buttonID                                           |
| `0x28` | programEventMessage    | 3 x 32b integers                                                  |
| `0x30` | logMessage             | string data                                                       |

### deviceTopology (0x01)

The primary topology response. Contains a count of devices and connections, followed by device info blocks and connection info blocks. See [Topology](./topology) for the full format.

### packetACK (0x02)

Acknowledges receipt of a host-to-device packet. Contains a 10-bit packet counter that matches the counter from the original message. blocksd uses ACKs to track keepalive status and data change delivery.

### Touch Events (0x10-0x15)

Touch events report finger position and pressure on the device surface. The `x` and `y` fields are 12-bit fixed-point values representing position on the touch surface. The `z` field is an 8-bit pressure value. Velocity variants add 8-bit velocity components for each axis.

blocksd normalizes these to floating-point values in the 0.0-1.0 range before exposing them through the external API.

### configMessage (0x18)

Device configuration responses. The payload starts with a 4-bit config command followed by an 8-bit item index and 32-bit value. Used for both config sync (factory and user) and individual config reads.

### controlButton Events (0x20-0x21)

Button press and release events. The 12-bit button ID identifies which physical button was pressed. Used by Control Blocks, Live Blocks, and similar devices with discrete buttons.

### logMessage (0x30)

Free-form log output from the device. Useful for debugging LittleFoot programs or diagnosing firmware issues. The payload is a variable-length string.

## Host → Device Messages

These messages are sent by blocksd to the device.

| ID     | Name                 | Payload                                |
| ------ | -------------------- | -------------------------------------- |
| `0x01` | deviceCommandMessage | 9b command (see Device Commands below) |
| `0x02` | sharedDataChange     | 16b packetIndex + data change commands |
| `0x03` | programEventMessage  | 3 x 32b integers                       |
| `0x04` | firmwareUpdatePacket | 7b size + 7-bit encoded data           |
| `0x10` | configMessage        | 4b configCmd + item + value            |
| `0x11` | factoryReset         | (no payload)                           |
| `0x12` | blockReset           | (no payload)                           |
| `0x20` | setName              | 7b length + 7-bit chars                |

### Device Commands (inside deviceCommandMessage)

The 9-bit command field in `deviceCommandMessage` selects the operation:

| ID     | Name                   | Description                                                            |
| ------ | ---------------------- | ---------------------------------------------------------------------- |
| `0x00` | beginAPIMode           | Enter rich protocol mode. Required before touch events or LED control. |
| `0x01` | requestTopologyMessage | Request the current topology report.                                   |
| `0x02` | endAPIMode             | Exit rich protocol mode. Device returns to basic MIDI.                 |
| `0x03` | ping                   | Keepalive ping. Must arrive within 5000ms or device exits API mode.    |
| `0x04` | debugMode              | Enable debug logging on device.                                        |
| `0x05` | saveProgramAsDefault   | Save the current LittleFoot program as the device's default.           |

### sharedDataChange (0x02)

The mechanism for writing data to the device's heap memory. Used for LED bitmap updates and LittleFoot program uploads. The payload starts with a 16-bit packet index (for ACK tracking), followed by a sequence of data change commands.

See [Data Change Commands](#data-change-commands) below.

### Config Commands

The 4-bit config command field selects the configuration operation:

| ID     | Name               | Description                       |
| ------ | ------------------ | --------------------------------- |
| `0x00` | setConfig          | Write a config value              |
| `0x01` | requestConfig      | Read a config value               |
| `0x02` | requestFactorySync | Request all factory config values |
| `0x03` | requestUserSync    | Request all user config values    |
| `0x04` | updateConfig       | Update config (factory)           |
| `0x05` | updateUserConfig   | Update config (user)              |
| `0x06` | setConfigState     | Set config state                  |
| `0x07` | factorySyncEnd     | End of factory sync               |
| `0x08` | clusterConfigSync  | Cluster config sync               |
| `0x09` | factorySyncReset   | Factory sync reset                |

## Data Change Commands

Data change commands encode diff-based heap writes using a compact RLE scheme. They are packed within `sharedDataChange` messages.

Each command starts with a 3-bit command ID:

| ID  | Name                     | Extra Bits                   | Description                             |
| --- | ------------------------ | ---------------------------- | --------------------------------------- |
| `0` | endOfPacket              | —                            | End of this packet's changes            |
| `1` | endOfChanges             | —                            | All changes complete                    |
| `2` | skipBytesFew             | 4b count                     | Skip 1-15 heap bytes                    |
| `3` | skipBytesMany            | 8b count                     | Skip 1-255 heap bytes                   |
| `4` | setSequenceOfBytes       | (8b value + 1b continue) x N | Write a sequence of distinct bytes      |
| `5` | setFewBytesWithValue     | 4b count + 8b value          | Write 1-15 copies of a value            |
| `6` | setFewBytesWithLastValue | 4b count                     | Write 1-15 copies of the previous value |
| `7` | setManyBytesWithValue    | 8b count + 8b value          | Write 1-255 copies of a value           |

The data change encoder walks the heap diff and selects the most compact command for each run. Skips over unchanged regions, uses RLE for repeated bytes, and falls back to byte sequences for unique data.
