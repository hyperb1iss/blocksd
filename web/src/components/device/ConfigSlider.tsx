import { useId } from 'react';

interface Props {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (value: number) => void;
}

export function ConfigSlider({ label, value, min, max, onChange }: Props) {
  const id = useId();
  const range = max - min || 1;
  const pct = ((value - min) / range) * 100;

  return (
    <div className="flex items-center gap-3">
      <label htmlFor={id} className="text-xs text-muted w-32 shrink-0 text-right">
        {label}
      </label>
      <div className="flex-1 relative">
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          value={value}
          onChange={e => onChange(Number(e.target.value))}
          className="w-full h-1.5 bg-surface rounded-full appearance-none cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5
            [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:rounded-full
            [&::-webkit-slider-thumb]:bg-cyan [&::-webkit-slider-thumb]:shadow-[0_0_6px_rgba(128,255,234,0.4)]
            [&::-webkit-slider-thumb]:transition-shadow [&::-webkit-slider-thumb]:hover:shadow-[0_0_10px_rgba(128,255,234,0.6)]"
          style={{
            background: `linear-gradient(to right, #80ffea ${pct}%, #1a162a ${pct}%)`,
          }}
        />
      </div>
      <span className="text-xs text-cyan tabular-nums w-8 text-right">{value}</span>
    </div>
  );
}
