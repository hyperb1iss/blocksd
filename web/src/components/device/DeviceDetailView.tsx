import { useState } from 'react';
import { blockTypeIcons, blockTypeLabels } from '../../lib/constants';
import type { ConfigValue, Device } from '../../lib/types';
import { ConfigPanel } from './ConfigPanel';

interface Props {
  device: Device;
  configValues: Map<number, ConfigValue>;
  onConfigChange: (item: number, value: number) => void;
}

type Tab = 'config' | 'led' | 'touch';

export function DeviceDetailView({ device, configValues, onConfigChange }: Props) {
  const [tab, setTab] = useState<Tab>('config');
  const icon = blockTypeIcons[device.block_type] ?? '\u25A1';
  const label = blockTypeLabels[device.block_type] ?? device.block_type;
  const hasGrid = device.grid_width > 0;

  const tabs: { id: Tab; label: string; show: boolean }[] = [
    { id: 'config', label: 'Config', show: true },
    { id: 'led', label: 'LED', show: hasGrid },
    { id: 'touch', label: 'Touch', show: hasGrid },
  ];

  return (
    <div className="p-6 max-w-3xl">
      {/* Device header */}
      <div className="flex items-center gap-4 mb-6">
        <span className="text-cyan text-3xl">{icon}</span>
        <div>
          <h1 className="text-xl font-bold">{device.name}</h1>
          <p className="text-sm text-muted">{label}</p>
        </div>
        <div className="ml-auto text-right text-xs text-muted">
          <div>{device.serial}</div>
          <div>FW {device.firmware_version ?? '\u2014'}</div>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-surface mb-6">
        {tabs
          .filter(t => t.show)
          .map(t => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                tab === t.id
                  ? 'border-cyan text-cyan'
                  : 'border-transparent text-muted hover:text-text'
              }`}
            >
              {t.label}
            </button>
          ))}
      </div>

      {/* Tab content */}
      {tab === 'config' && <ConfigPanel values={configValues} onValueChange={onConfigChange} />}
      {tab === 'led' && (
        <div className="text-muted text-sm">
          LED editor coming soon. Use <code className="text-cyan">blocksd led</code> CLI for now.
        </div>
      )}
      {tab === 'touch' && (
        <div className="text-muted text-sm">Touch visualization coming soon.</div>
      )}
    </div>
  );
}
