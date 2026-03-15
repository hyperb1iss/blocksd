import { useEffect, useState } from 'react';
import { useBlocksd } from '../../hooks/useBlocksd';

export function StatusBar() {
  const { connected, send, subscribe } = useBlocksd();
  const [uptime, setUptime] = useState<number | null>(null);

  // Ping every 10s for uptime
  useEffect(() => {
    if (!connected) {
      setUptime(null);
      return;
    }

    const ping = () => send({ type: 'ping' });
    ping();
    const interval = setInterval(ping, 10_000);
    return () => clearInterval(interval);
  }, [connected, send]);

  useEffect(() => {
    return subscribe(msg => {
      if (msg.type === 'pong') {
        setUptime(msg.uptime_seconds);
      }
    });
  }, [subscribe]);

  const formatUptime = (s: number) => {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    if (h > 0) return `${h}h ${m}m`;
    return `${m}m ${s % 60}s`;
  };

  return (
    <div className="p-3 border-t border-surface text-xs text-muted">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-green' : 'bg-red'}`}
        />
        <span>{connected ? 'Connected' : 'Disconnected'}</span>
      </div>
      {uptime != null && <div className="mt-1">Uptime: {formatUptime(uptime)}</div>}
    </div>
  );
}
