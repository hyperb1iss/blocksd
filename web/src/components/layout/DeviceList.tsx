import { Link, useParams } from 'react-router';
import { blockTypeIcons } from '../../lib/constants';
import type { Device } from '../../lib/types';

export function DeviceList({ devices }: { devices: Device[] }) {
  const { uid } = useParams();
  const selectedUid = uid ? Number(uid) : null;

  if (devices.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center p-4">
        <p className="text-muted text-xs text-center">No devices connected</p>
      </div>
    );
  }

  return (
    <nav className="flex-1 overflow-auto p-2 space-y-1">
      {devices.map(device => (
        <DeviceListItem key={device.uid} device={device} selected={device.uid === selectedUid} />
      ))}
    </nav>
  );
}

function DeviceListItem({ device, selected }: { device: Device; selected: boolean }) {
  const icon = blockTypeIcons[device.block_type] ?? '\u25A1';
  const batteryColor =
    device.battery_level > 50
      ? 'text-green'
      : device.battery_level > 20
        ? 'text-yellow'
        : 'text-red';

  return (
    <Link
      to={`/device/${device.uid}`}
      className={`block p-3 rounded-lg transition-all ${
        selected
          ? 'bg-elevated border border-cyan/40 shadow-[0_0_12px_rgba(128,255,234,0.08)]'
          : 'bg-surface/50 border border-transparent hover:bg-surface hover:border-surface'
      }`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-cyan text-sm shrink-0">{icon}</span>
          <span className="text-sm font-medium truncate">{device.name}</span>
        </div>
        <span className={`text-xs tabular-nums ${batteryColor}`}>
          {device.battery_level}%{device.battery_charging ? '\u26A1' : ''}
        </span>
      </div>
      <div className="text-[10px] text-muted mt-1 font-normal">{device.serial}</div>
    </Link>
  );
}
