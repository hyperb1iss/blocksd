import { useEffect, useState } from 'react';
import type { Device } from '../lib/types';
import { useBlocksd } from './useBlocksd';

/** Tracks all connected devices via discover + live events. */
export function useDevices(): Device[] {
  const { send, subscribe, connected } = useBlocksd();
  const [devices, setDevices] = useState<Device[]>([]);

  // Request device list on (re)connect
  useEffect(() => {
    if (connected) {
      send({ type: 'discover' });
    }
  }, [connected, send]);

  // Listen for device events
  useEffect(() => {
    return subscribe(msg => {
      switch (msg.type) {
        case 'discover_response':
          setDevices(msg.devices);
          break;
        case 'device_added':
          setDevices(prev => {
            if (prev.some(d => d.uid === msg.device.uid)) return prev;
            return [...prev, msg.device];
          });
          break;
        case 'device_removed':
          setDevices(prev => prev.filter(d => d.uid !== msg.uid));
          break;
      }
    });
  }, [subscribe]);

  return devices;
}
