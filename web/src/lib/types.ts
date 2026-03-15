/** Device info from the daemon API. */
export interface Device {
  uid: number;
  serial: string;
  block_type: string;
  name: string;
  battery_level: number;
  battery_charging: boolean;
  grid_width: number;
  grid_height: number;
  firmware_version: string | null;
}

/** DNA connector link between two blocks. */
export interface DeviceConnection {
  device1_uid: number;
  device2_uid: number;
  port1: number;
  port2: number;
}

/** Touch event from a pressure-sensitive surface. */
export interface TouchData {
  uid: number;
  action: 'start' | 'move' | 'end';
  index: number;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
}

/** A single config value with its range. */
export interface ConfigValue {
  item: number;
  value: number;
  min: number;
  max: number;
}
