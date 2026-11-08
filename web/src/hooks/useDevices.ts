import { useEffect, useState } from 'react';
import type { Device } from '../lib/types';
import { useBlocksd } from './useBlocksd';

export function useDevices(): Device[] {
  const { send, subscribe, connected } = useBlocksd();
  const [devices, setDevices] = useState<Device[]>([]);
  useEffect(
    () =>
      subscribe(msg => {
        switch (msg.type) {
          case 'discover_response':
            setDevices(msg.devices);
            break;
          case 'topology_changed':
            send({ type: 'discover' });
            break;
          case 'device_added':
            setDevices(previous => {
              const existing = previous.findIndex(device => device.serial === msg.device.serial);
              if (existing < 0) return [...previous, msg.device];
              return previous.map((device, index) => (index === existing ? msg.device : device));
            });
            break;
          case 'device_removed':
            setDevices(previous => previous.filter(device => device.uid !== msg.uid));
            break;
        }
      }),
    [subscribe, send],
  );
  useEffect(() => {
    if (!connected) {
      setDevices([]);
      return;
    }
    send({ type: 'discover' });
    const timer = setInterval(() => send({ type: 'discover' }), 5000);
    return () => clearInterval(timer);
  }, [connected, send]);
  return devices;
}
