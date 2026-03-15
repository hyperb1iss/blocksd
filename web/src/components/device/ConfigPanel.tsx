import { configGroups, configLabels } from '../../lib/constants';
import type { ConfigValue } from '../../lib/types';
import { ConfigSlider } from './ConfigSlider';

interface Props {
  values: Map<number, ConfigValue>;
  onValueChange: (item: number, value: number) => void;
}

export function ConfigPanel({ values, onValueChange }: Props) {
  if (values.size === 0) {
    return <p className="text-muted text-sm p-4">No configuration available for this device.</p>;
  }

  return (
    <div className="space-y-6">
      {configGroups.map(group => {
        const items = group.items.filter(id => values.has(id));
        if (items.length === 0) return null;

        return (
          <div key={group.label}>
            <h3 className="text-xs font-semibold text-purple uppercase tracking-wider mb-3">
              {group.label}
            </h3>
            <div className="space-y-3">
              {items.map(id => {
                const cv = values.get(id)!;
                return (
                  <ConfigSlider
                    key={id}
                    label={configLabels[id] ?? `Config ${id}`}
                    value={cv.value}
                    min={cv.min}
                    max={cv.max}
                    onChange={v => onValueChange(id, v)}
                  />
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
}
