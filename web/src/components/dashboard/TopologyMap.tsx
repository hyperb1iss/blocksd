import { blockTypeIcons } from '../../lib/constants';
import type { Device, DeviceConnection } from '../../lib/types';
import { colors } from '../../theme/tokens';

const NODE_W = 120;
const NODE_H = 60;
const GAP = 40;

interface Props {
  devices: Device[];
  connections: DeviceConnection[];
}

export function TopologyMap({ devices, connections }: Props) {
  if (devices.length === 0) return null;

  // Simple horizontal layout — master first, then connected devices
  const positions = new Map<number, { x: number; y: number }>();
  devices.forEach((d, i) => {
    positions.set(d.uid, {
      x: 20 + i * (NODE_W + GAP),
      y: 20,
    });
  });

  const svgWidth = 20 + devices.length * (NODE_W + GAP);
  const svgHeight = NODE_H + 40;

  return (
    <svg
      viewBox={`0 0 ${svgWidth} ${svgHeight}`}
      className="w-full rounded-lg bg-surface/50 border border-surface"
      style={{ maxHeight: 140 }}
      role="img"
      aria-label="Device topology map"
    >
      {/* Connection lines */}
      {connections.map((conn, i) => {
        const p1 = positions.get(conn.device1_uid);
        const p2 = positions.get(conn.device2_uid);
        if (!p1 || !p2) return null;

        return (
          <line
            key={i}
            x1={p1.x + NODE_W / 2}
            y1={p1.y + NODE_H / 2}
            x2={p2.x + NODE_W / 2}
            y2={p2.y + NODE_H / 2}
            stroke={colors.purple}
            strokeWidth={2}
            strokeDasharray="4 4"
            opacity={0.6}
          />
        );
      })}

      {/* Device nodes */}
      {devices.map(device => {
        const pos = positions.get(device.uid);
        if (!pos) return null;
        const icon = blockTypeIcons[device.block_type] ?? '\u25A1';

        return (
          <g key={device.uid}>
            <rect
              x={pos.x}
              y={pos.y}
              width={NODE_W}
              height={NODE_H}
              rx={8}
              fill={colors.elevated}
              stroke={colors.cyan}
              strokeWidth={1}
              opacity={0.8}
            />
            <text
              x={pos.x + NODE_W / 2}
              y={pos.y + 24}
              textAnchor="middle"
              fill={colors.cyan}
              fontSize={14}
              fontFamily="var(--font-mono)"
            >
              {icon} {device.name}
            </text>
            <text
              x={pos.x + NODE_W / 2}
              y={pos.y + 44}
              textAnchor="middle"
              fill={colors.muted}
              fontSize={9}
              fontFamily="var(--font-mono)"
            >
              {device.battery_level}%{device.battery_charging ? ' \u26A1' : ''}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
