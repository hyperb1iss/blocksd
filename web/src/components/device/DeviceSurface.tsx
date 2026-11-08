import { useEffect, useState } from 'react';
import { useBlocksd } from '../../hooks/useBlocksd';
import type { Device, TouchData } from '../../lib/types';

export function DeviceSurface({ device, compact = false }: { device: Device; compact?: boolean }) {
  const { subscribe, connected } = useBlocksd();
  const [touches, setTouches] = useState<TouchData[]>([]);
  const keyboard = (device.key_count ?? 0) > 0 || device.block_type === 'seaboard';
  const grid = device.grid_width > 0;
  useEffect(() => {
    setTouches([]);
    if (!connected || compact) return;
    return subscribe(msg => {
      if (msg.type !== 'touch' || msg.uid !== device.uid) return;
      setTouches(previous => {
        const next = previous.filter(touch => touch.index !== msg.index);
        return msg.action === 'end' ? next : [...next, msg];
      });
    });
  }, [connected, compact, device.uid, subscribe]);
  return (
    <div
      className={`device-surface ${compact ? 'compact' : ''} ${keyboard ? 'keyboard-surface' : ''}`}
    >
      <div className="hardware-frame" aria-hidden="true">
        <div className="hardware-mark">
          <i />
          <i />
          <i />
        </div>
        {keyboard ? (
          <div className={`keyboard ${device.block_type === 'seaboard' ? 'seaboard' : ''}`}>
            {Array.from({ length: 14 }, (_, index) => (
              <span
                className="white-key"
                key={index}
                style={{ '--key-index': index } as React.CSSProperties}
              >
                {![2, 6].includes(index % 7) && <b />}
              </span>
            ))}
          </div>
        ) : grid ? (
          <div className="pad-matrix">
            {Array.from({ length: 225 }, (_, index) => (
              <i
                key={index}
                className={index % 15 === 7 || Math.floor(index / 15) === 7 ? 'axis-dot' : ''}
              />
            ))}
            {touches.map(touch => (
              <span
                className="touch-point"
                key={touch.index}
                style={{
                  left: `${touch.x * 100}%`,
                  top: `${touch.y * 100}%`,
                  width: `${14 + touch.z * 35}px`,
                  height: `${14 + touch.z * 35}px`,
                }}
              />
            ))}
          </div>
        ) : (
          <div className="control-block">
            <span />
            <span />
            <span />
          </div>
        )}
        <span className="hardware-wordmark">ROLI</span>
      </div>
      {!compact && (
        <div className="surface-caption">
          <span className={`signal-dot ${touches.length ? 'active' : ''}`} />
          {grid
            ? touches.length
              ? `${touches.length} active touch${touches.length === 1 ? '' : 'es'}`
              : 'touch your Lightpad to see input'
            : keyboard
              ? 'device illustration'
              : 'connected control surface'}
          <span className="surface-caption-end">
            {grid ? `${device.grid_width} × ${device.grid_height}` : 'MIDI controller'}
          </span>
        </div>
      )}
    </div>
  );
}
