import type { ConfigValue, Device, DeviceConnection, TouchData } from './types';

// ── Requests ────────────────────────────────────────────────────────────

export type Request =
  | { type: 'ping'; id?: string }
  | { type: 'discover'; id?: string }
  | { type: 'topology'; id?: string }
  | { type: 'config_get'; uid: number; id?: string }
  | { type: 'config_set'; uid: number; item: number; value: number; id?: string }
  | { type: 'frame'; uid: number; pixels: string; id?: string }
  | { type: 'brightness'; uid: number; value: number }
  | { type: 'subscribe'; events: string[] };

// ── Responses & Events ──────────────────────────────────────────────────

export interface PongResponse {
  type: 'pong';
  version: string;
  uptime_seconds: number;
  device_count: number;
  id?: string;
}

export interface DiscoverResponse {
  type: 'discover_response';
  devices: Device[];
  id?: string;
}

export interface TopologyResponse {
  type: 'topology_response';
  devices: Device[];
  connections: DeviceConnection[];
  id?: string;
}

export interface ConfigValuesResponse {
  type: 'config_values';
  uid: number;
  values: ConfigValue[];
  id?: string;
}

export interface ConfigAckResponse {
  type: 'config_ack';
  uid: number;
  item: number;
  ok: boolean;
  id?: string;
}

export interface DeviceAddedEvent {
  type: 'device_added';
  device: Device;
}

export interface DeviceRemovedEvent {
  type: 'device_removed';
  uid: number;
}

export interface TopologyChangedEvent {
  type: 'topology_changed';
  devices: Device[];
  connections: DeviceConnection[];
}

export interface ConfigChangedEvent {
  type: 'config_changed';
  uid: number;
  item: number;
  value: number;
}

export interface TouchEvent {
  type: 'touch';
  uid: number;
  action: TouchData['action'];
  index: number;
  x: number;
  y: number;
  z: number;
  vx: number;
  vy: number;
  vz: number;
}

export type ServerMessage =
  | PongResponse
  | DiscoverResponse
  | TopologyResponse
  | ConfigValuesResponse
  | ConfigAckResponse
  | DeviceAddedEvent
  | DeviceRemovedEvent
  | TopologyChangedEvent
  | ConfigChangedEvent
  | TouchEvent
  | { type: 'subscribed'; events: string[] }
  | { type: 'error'; message: string };
