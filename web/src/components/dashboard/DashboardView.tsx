import type { Device, DeviceConnection } from '../../lib/types';
import { DeviceCard } from './DeviceCard';
import { TopologyMap } from './TopologyMap';

interface Props {
  devices: Device[];
  connections: DeviceConnection[];
}

export function DashboardView({ devices, connections }: Props) {
  if (devices.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center">
          <p className="text-4xl mb-4">{'\uD83C\uDFB9'}</p>
          <h2 className="text-lg font-semibold text-muted mb-2">No Blocks Connected</h2>
          <p className="text-sm text-subtle max-w-xs">
            Connect a ROLI Block via USB. The daemon will detect it automatically.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Topology map (shown when multiple connected blocks) */}
      {connections.length > 0 && (
        <section>
          <h2 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">
            Topology
          </h2>
          <TopologyMap devices={devices} connections={connections} />
        </section>
      )}

      {/* Device cards */}
      <section>
        <h2 className="text-sm font-semibold text-muted uppercase tracking-wider mb-3">Devices</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {devices.map(device => (
            <DeviceCard key={device.uid} device={device} />
          ))}
        </div>
      </section>
    </div>
  );
}
