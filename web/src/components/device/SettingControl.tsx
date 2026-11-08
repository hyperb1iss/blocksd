import { useEffect, useId, useState } from 'react';
import type { WriteState } from '../../hooks/useDeviceSettings';
import type { ConfigMetadata, ConfigValue } from '../../lib/types';

export function SettingControl({
  value,
  metadata,
  write,
  onChange,
  disabled,
}: {
  value: ConfigValue;
  metadata?: ConfigMetadata;
  write?: WriteState;
  onChange: (item: number, value: number) => void;
  disabled: boolean;
}) {
  const id = useId();
  const [draft, setDraft] = useState(String(value.value));
  useEffect(() => {
    setDraft(String(value.value));
  }, [value.value]);
  const pending = write?.status === 'pending';
  const readonly = value.writable === false || value.min === value.max;
  const number = Number(draft);
  const valid =
    draft.trim() !== '' && Number.isInteger(number) && number >= value.min && number <= value.max;
  const label = metadata?.label ?? `setting ${value.item}`;
  return (
    <div className={`setting-row ${write?.status === 'error' ? 'setting-error' : ''}`}>
      <div className="setting-description">
        <label htmlFor={id}>{label}</label>
        {metadata?.description && <p id={`${id}-description`}>{metadata.description}</p>}
        <span className={`write-state ${write?.status ?? ''}`} aria-live="polite">
          {pending
            ? 'waiting for device readback'
            : write?.status === 'confirmed'
              ? 'confirmed by device'
              : write?.status === 'error'
                ? write.message
                : readonly
                  ? 'reported by device'
                  : `${value.min} to ${value.max}`}
        </span>
      </div>
      {readonly ? (
        <output id={id} className="readonly-value">
          {value.value}
        </output>
      ) : metadata?.kind === 'toggle' &&
        [0, 1].includes(value.value) &&
        value.min <= 0 &&
        value.max >= 1 ? (
        <button
          id={id}
          type="button"
          role="switch"
          aria-checked={value.value === 1}
          aria-label={label}
          className="toggle"
          disabled={disabled || pending}
          onClick={() => onChange(value.item, value.value === 1 ? 0 : 1)}
        >
          <span />
        </button>
      ) : metadata?.kind === 'options' && metadata.options ? (
        <select
          id={id}
          value={value.value}
          disabled={disabled || pending}
          onChange={event => onChange(value.item, Number(event.target.value))}
        >
          {!metadata.options.some(option => option.value === value.value) && (
            <option value={value.value}>device value {value.value}</option>
          )}
          {metadata.options.map(option => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      ) : (
        <form
          className="number-control"
          onSubmit={event => {
            event.preventDefault();
            if (valid) onChange(value.item, number);
          }}
        >
          <input
            id={id}
            type="number"
            min={value.min}
            max={value.max}
            step={1}
            value={draft}
            disabled={disabled || pending}
            aria-describedby={metadata?.description ? `${id}-description` : undefined}
            onChange={event => setDraft(event.target.value)}
          />
          <button
            type="submit"
            className="apply-setting"
            aria-label={`apply ${label}`}
            disabled={disabled || pending || !valid || number === value.value}
          >
            {pending ? '…' : 'set'}
          </button>
        </form>
      )}
    </div>
  );
}
