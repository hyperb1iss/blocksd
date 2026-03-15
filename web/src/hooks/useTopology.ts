import { useEffect, useState } from 'react';
import type { Device, DeviceConnection } from '../lib/types';
import { useBlocksd } from './useBlocksd';

interface TopologyState {
  devices: Device[];
  connections: DeviceConnection[];
}

/** Tracks topology (devices + connections) with live updates. */
export function useTopology(): TopologyState {
  const { send, subscribe, connected } = useBlocksd();
  const [topo, setTopo] = useState<TopologyState>({ devices: [], connections: [] });

  useEffect(() => {
    if (connected) {
      send({ type: 'topology' });
    }
  }, [connected, send]);

  useEffect(() => {
    return subscribe(msg => {
      if (msg.type === 'topology_response' || msg.type === 'topology_changed') {
        setTopo({ devices: msg.devices, connections: msg.connections });
      }
    });
  }, [subscribe]);

  return topo;
}
