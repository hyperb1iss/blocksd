import { useId, useRef, useState } from 'react';
import type { PresetLibrary as Library } from '../../hooks/usePresets';
import type { Device } from '../../lib/types';

export function SavePreset({
  serial,
  disabled,
  library,
}: {
  serial: string;
  disabled: boolean;
  library: Library;
}) {
  const [name, setName] = useState('');
  const id = useId();
  return (
    <form
      className="save-preset"
      onSubmit={async event => {
        event.preventDefault();
        if (name.trim() && (await library.save(serial, name.trim()))) setName('');
      }}
    >
      <div>
        <label htmlFor={id}>preset name</label>
        <p>save the settings your device has reported.</p>
      </div>
      <div className="save-preset-fields">
        <input
          id={id}
          placeholder="preset name"
          value={name}
          maxLength={80}
          onChange={event => setName(event.target.value)}
          disabled={disabled || library.busy}
        />
        <button
          type="submit"
          className="button primary"
          disabled={disabled || library.busy || !name.trim()}
        >
          save preset <span aria-hidden="true">↗</span>
        </button>
      </div>
    </form>
  );
}
export function PresetLibrary({
  library,
  devices,
  connected,
  serial,
}: {
  library: Library;
  devices: Device[];
  connected: boolean;
  serial?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const presets = library.presets.filter(preset => !serial || preset.serial === serial);
  return (
    <section className="preset-library" aria-label="saved presets">
      <div className="section-heading">
        <h2>{serial ? 'presets for this device' : 'saved presets'}</h2>
        <button
          type="button"
          className="button secondary"
          disabled={!connected || library.busy}
          onClick={() => input.current?.click()}
        >
          import preset <span aria-hidden="true">↓</span>
        </button>
        <input
          ref={input}
          type="file"
          accept=".json,application/json"
          className="sr-only"
          aria-label="import preset file"
          onChange={event => {
            const file = event.target.files?.[0];
            if (file) void library.importPreset(file);
            event.target.value = '';
          }}
        />
      </div>
      {library.error && (
        <p className="message error" role="alert">
          {library.error}
        </p>
      )}
      {library.notice && (
        <p className="message success" role="status">
          {library.notice}
        </p>
      )}
      {presets.length === 0 ? (
        <div className="empty-presets">
          <span className="preset-glyph" aria-hidden="true">
            ▤
          </span>
          <h3>no saved presets</h3>
          <p>save the current device settings or import a preset file.</p>
        </div>
      ) : (
        <div className="preset-grid">
          {presets.map(preset => {
            const device = devices.find(item => item.serial === preset.serial);
            const application = library.applications[preset.id];
            const serialPending = library.presets.some(
              item =>
                item.serial === preset.serial &&
                library.applications[item.id]?.status === 'pending',
            );
            return (
              <article className="preset-card" key={preset.id}>
                <div className="preset-card-top">
                  <span className="preset-glyph" aria-hidden="true">
                    ▤
                  </span>
                  {preset.auto_restore && (
                    <span className="badge purple">restores on USB reconnect</span>
                  )}
                </div>
                <h3>{preset.name}</h3>
                <p className="preset-device">{device?.name || preset.block_type}</p>
                <p className="serial">{preset.serial}</p>
                <div className="preset-meta">
                  <span>{preset.values.length} settings</span>
                  <span className={device && connected ? 'text-cyan' : 'text-muted'}>
                    {device && connected ? 'device connected' : 'device offline'}
                  </span>
                </div>
                <div className="preset-actions">
                  <button
                    className="button primary"
                    type="button"
                    disabled={!connected || !device || library.busy || serialPending}
                    onClick={() => void library.apply(preset)}
                  >
                    apply preset <span aria-hidden="true">↗</span>
                  </button>
                  <button
                    className="button secondary"
                    type="button"
                    disabled={!connected || library.busy}
                    onClick={() => void library.exportPreset(preset)}
                  >
                    export
                  </button>
                </div>
                {application && (
                  <p className={`write-state ${application.status}`} role="status">
                    {application.message}
                  </p>
                )}
                <label className="restore-setting">
                  <span>
                    restore automatically
                    <span className="restore-caption">
                      on USB reconnect or daemon restart. brief device dropouts keep your current
                      settings.
                    </span>
                  </span>
                  <input
                    type="checkbox"
                    checked={preset.auto_restore}
                    disabled={!connected || library.busy}
                    onChange={() => void library.updateDefault(preset)}
                  />
                  <span className="toggle-visual" aria-hidden="true" />
                </label>
                <div className="preset-delete">
                  {deleting === preset.id ? (
                    <>
                      <span>delete “{preset.name}”?</span>
                      <button
                        type="button"
                        disabled={library.busy}
                        onClick={() => {
                          void library.remove(preset);
                          setDeleting(null);
                        }}
                      >
                        delete
                      </button>
                      <button type="button" onClick={() => setDeleting(null)}>
                        cancel
                      </button>
                    </>
                  ) : (
                    <button
                      type="button"
                      disabled={!connected || library.busy}
                      onClick={() => setDeleting(preset.id)}
                    >
                      delete preset
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </section>
  );
}
