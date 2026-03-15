import { Link } from 'react-router';
import { blockTypeIcons, blockTypeLabels } from '../../lib/constants';
import type { Device } from '../../lib/types';

export function DeviceCard({ device }: { device: Device }) {
  const icon = blockTypeIcons[device.block_type] ?? '\u25A1';
  const label = blockTypeLabels[device.block_type] ?? device.block_type;

  return (
    <Link
      to={`/device/${device.uid}`}
      className="group block p-5 rounded-xl bg-surface border border-surface
        hover:border-cyan/30 hover:shadow-[0_0_20px_rgba(128,255,234,0.06)]
        transition-all duration-200"
    >
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          <span className="text-cyan text-2xl">{icon}</span>
          <div>
            <h3 className="font-semibold text-sm group-hover:text-cyan transition-colors">
              {device.name}
            </h3>
            <p className="text-xs text-muted">{label}</p>
          </div>
        </div>
        <BatteryGauge level={device.battery_level} charging={device.battery_charging} />
      </div>

      {/* Details */}
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <Detail label="Serial" value={device.serial} />
        <Detail label="Firmware" value={device.firmware_version ?? '\u2014'} />
        {device.grid_width > 0 && (
          <Detail label="Grid" value={`${device.grid_width}\u00D7${device.grid_height}`} />
        )}
      </div>
    </Link>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span className="text-muted">{label}: </span>
      <span className="text-text">{value}</span>
    </div>
  );
}

function BatteryGauge({ level, charging }: { level: number; charging: boolean }) {
  const fill = charging ? 'bg-cyan' : level > 50 ? 'bg-green' : level > 20 ? 'bg-yellow' : 'bg-red';

  return (
    <div className="flex items-center gap-1.5">
      <div className="w-8 h-3 rounded-sm border border-muted/40 p-px relative">
        <div
          className={`h-full rounded-[1px] transition-all ${fill}`}
          style={{ width: `${Math.max(level, 4)}%` }}
        />
      </div>
      <span className="text-[10px] text-muted tabular-nums">
        {level}%{charging ? '\u26A1' : ''}
      </span>
    </div>
  );
}
