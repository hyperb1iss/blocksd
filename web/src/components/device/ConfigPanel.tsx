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
      {[...values.values()].map(value => (
        <ConfigSlider
          key={value.item}
          label={`setting ${value.item}`}
          value={value.value}
          min={value.min}
          max={value.max}
          onChange={next => onValueChange(value.item, next)}
        />
      ))}
    </div>
  );
}
