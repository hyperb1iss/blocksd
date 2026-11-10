export interface Device {
  uid: number;
  serial: string;
  block_type: string;
  name: string;
  battery_level: number;
  battery_charging: boolean;
  grid_width: number;
  grid_height: number;
  key_count?: number;
  firmware_version: string | null;
}
export interface DeviceConnection {
  device1_uid: number;
  device2_uid: number;
  port1: number;
  port2: number;
}
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
export interface ConfigValue {
  item: number;
  value: number;
  min: number;
  max: number;
  writable?: boolean;
}
export interface ConfigMetadata {
  item: number;
  key: string;
  label: string;
  group: string;
  kind: 'integer' | 'toggle' | 'options';
  description?: string;
  options?: { value: number; label: string }[];
}
export interface Preset {
  id: string;
  name: string;
  serial: string;
  block_type: string;
  values: { item: number; value: number }[];
  auto_restore: boolean;
}

export interface DeviceProgram {
  owner: 'device' | 'lighting' | 'custom';
  name: string | null;
  state: 'idle' | 'compiling' | 'uploading' | 'waiting' | 'ready' | 'uploaded' | 'unresponsive';
  message: string;
  code_size: number;
  heap_size: number;
}
