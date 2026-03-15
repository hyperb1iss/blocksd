import { useEffect, useState } from 'react';
import type { Device } from '../lib/types';
import { useBlocksd } from './useBlocksd';

const POLL_INTERVAL = 5000;

/** Tracks all connected devices via discover + live events. */
export function useDevices(): Device[] {
  const { send, subscribe, connected } = useBlocksd();
  const [devices, setDevices] = useState<Device[]>([]);

  // Poll for devices — daemon may still be discovering on first connect
  useEffect(() => {
    if (!connected) return;

    send({ type: 'discover' });
    const interval = setInterval(() => send({ type: 'discover' }), POLL_INTERVAL);
    return () => clearInterval(interval);
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
