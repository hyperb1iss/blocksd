import { useEffect, useState } from 'react';
import { Link, useLocation, useParams } from 'react-router';
import { useBlocksd } from '../hooks/useBlocksd';
import { useDeviceSettings } from '../hooks/useDeviceSettings';
import { useDevices } from '../hooks/useDevices';
import { type PresetLibrary as Library, usePresets } from '../hooks/usePresets';
import { blockTypeLabels } from '../lib/constants';
import type { PongResponse } from '../lib/protocol';
import type { Device } from '../lib/types';
import { DeviceSurface } from './device/DeviceSurface';
import { SettingControl } from './device/SettingControl';
import { PresetLibrary, SavePreset } from './presets/PresetLibrary';

export function Studio() {
  const { connected, request } = useBlocksd();
  const devices = useDevices();
  const library = usePresets();
  const location = useLocation();
  const { serial } = useParams();
  const presetsPage = location.pathname === '/presets';
  const device = serial ? devices.find(item => item.serial === serial) : devices[0];
  const [info, setInfo] = useState<PongResponse | null>(null);
  useEffect(() => {
    let active = true;
    if (connected)
      void request<PongResponse>({ type: 'ping' })
        .then(result => {
          if (active) setInfo(result);
        })
        .catch(() => {});
    else setInfo(null);
    return () => {
      active = false;
    };
  }, [connected, request]);
  return (
    <div className="studio-shell">
      <a href="#workspace" className="skip-link">
        skip to workspace
      </a>
      <aside className="sidebar">
        <Link className="brand" to="/" aria-label="blocksd home">
          <span className="brand-mark" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
          </span>
          <span>
            blocksd<span className="brand-subtitle">your hardware. your sound.</span>
          </span>
        </Link>
        <nav aria-label="main navigation">
          <Link
            to="/"
            className={!presetsPage ? 'nav-item selected' : 'nav-item'}
            aria-current={!presetsPage ? 'page' : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              ▦
            </span>
            devices<span className="nav-count">{devices.length}</span>
          </Link>
          <Link
            to="/presets"
            className={presetsPage ? 'nav-item selected' : 'nav-item'}
            aria-current={presetsPage ? 'page' : undefined}
          >
            <span className="nav-icon" aria-hidden="true">
              ▤
            </span>
            presets<span className="nav-count">{library.presets.length}</span>
          </Link>
        </nav>
        <div className="sidebar-devices">
          <div className="eyebrow">connected hardware</div>
          {devices.length ? (
            devices.map(item => (
              <Link
                key={item.serial}
                to={`/device/${encodeURIComponent(item.serial)}`}
                className={`sidebar-device ${device?.serial === item.serial && !presetsPage ? 'active' : ''}`}
              >
                <span className="signal-dot active" />
                <span>
                  {item.name || blockTypeLabels[item.block_type] || 'ROLI Block'}
                  <small>{blockTypeLabels[item.block_type] ?? item.block_type}</small>
                </span>
                <span aria-hidden="true">↗</span>
              </Link>
            ))
          ) : (
            <p className="sidebar-empty">
              {connected ? 'waiting for your Blocks' : 'connecting to blocksd'}
            </p>
          )}
        </div>
        <div className="sidebar-footer">
          <div className="connection-state" role="status">
            <span className={`signal-dot ${connected ? 'active' : ''}`} />
            {connected ? 'daemon connected' : 'reconnecting to daemon'}
          </div>
          <span className="sidebar-caption">made for your Linux studio</span>
        </div>
      </aside>
      <div className="workspace-shell">
        <header className="topbar">
          <span>
            workspace{' '}
            <span className="breadcrumb-separator" aria-hidden="true">
              /
            </span>{' '}
            <strong>{presetsPage ? 'presets' : 'devices'}</strong>
          </span>
          <span className="topbar-status">
            <i className={`signal-dot ${connected ? 'active' : ''}`} />
            {connected ? 'local connection' : 'connection interrupted'}
          </span>
        </header>
        <main id="workspace" className="workspace">
          <div className="page-heading">
            <div>
              <span className="eyebrow">ROLI Blocks on Linux</span>
              <h1>{presetsPage ? 'your presets' : 'your devices'}</h1>
              <p>
                {presetsPage
                  ? 'save, recall, and restore your device setups.'
                  : 'configure expression and recall your setup.'}
              </p>
            </div>
            <span className="page-index" aria-hidden="true">
              {presetsPage ? '02' : '01'}
              <span>/ studio</span>
            </span>
          </div>
          {!connected && (
            <div className="connection-banner" role="status">
              <span className="signal-dot" />
              <div>
                <strong>the daemon connection was interrupted.</strong>
                <p>
                  reconnecting automatically. settings stay unavailable until your devices return.
                </p>
              </div>
            </div>
          )}
          {presetsPage ? (
            <PresetLibrary library={library} devices={devices} connected={connected} />
          ) : (
            <>
              {devices.length > 0 && (
                <nav className="device-strip" aria-label="choose a device">
                  {devices.map((item, index) => (
                    <Link
                      to={`/device/${encodeURIComponent(item.serial)}`}
                      key={item.serial}
                      className={`device-tile ${device?.serial === item.serial ? 'selected' : ''}`}
                      aria-current={device?.serial === item.serial ? 'true' : undefined}
                    >
                      <div className="device-tile-top">
                        <span className="device-number">0{index + 1}</span>
                        <Battery device={item} />
                      </div>
                      <DeviceSurface device={item} compact />
                      <div className="device-tile-name">
                        {item.name || blockTypeLabels[item.block_type] || 'ROLI Block'}
                        <span aria-hidden="true">↗</span>
                      </div>
                      <p>{blockTypeLabels[item.block_type] ?? item.block_type}</p>
                    </Link>
                  ))}
                </nav>
              )}
              {device ? (
                <DeviceWorkspace
                  key={device.serial}
                  device={device}
                  library={library}
                  devices={devices}
                />
              ) : (
                <div className="empty-workspace">
                  <div className="empty-hardware" aria-hidden="true">
                    <i />
                    <i />
                    <i />
                    <i />
                  </div>
                  <span className="eyebrow">
                    {serial && connected ? 'device disconnected' : 'your studio starts here'}
                  </span>
                  <h2>{serial && connected ? 'this Block is away.' : 'connect a ROLI Block.'}</h2>
                  <p>
                    {serial && connected
                      ? 'reconnect your device or choose another connected Block above.'
                      : 'connect your Block over USB. attached DNA Blocks will appear alongside it when they are discovered.'}
                  </p>
                  {serial && (
                    <Link className="button secondary" to="/">
                      back to devices
                    </Link>
                  )}
                  <span className="empty-note">
                    {connected
                      ? 'blocksd is running and looking for hardware'
                      : 'start the blocksd service to connect'}
                  </span>
                </div>
              )}
            </>
          )}
          <details className="diagnostics">
            <summary>
              connection details <span aria-hidden="true">+</span>
            </summary>
            <div>
              <dl>
                <div>
                  <dt>daemon</dt>
                  <dd>{connected ? 'connected' : 'disconnected'}</dd>
                </div>
                <div>
                  <dt>version</dt>
                  <dd>{info?.version ?? 'unavailable'}</dd>
                </div>
                <div>
                  <dt>connected devices</dt>
                  <dd>{devices.length}</dd>
                </div>
                <div>
                  <dt>connection</dt>
                  <dd>{window.location.host}</dd>
                </div>
              </dl>
              <p>
                ROLI sends musical MIDI directly to your DAW. this dashboard manages hardware
                settings; touch feedback shows Blocks API input, not a MIDI monitor.
              </p>
            </div>
          </details>
        </main>
        <footer className="workspace-footer">
          <span>
            blocksd <span className="footer-divider">/</span> a little more expression.
          </span>
          <span>local. open. yours.</span>
        </footer>
      </div>
    </div>
  );
}
function Battery({ device }: { device: Device }) {
  const level = Math.max(0, Math.min(100, device.battery_level));
  return (
    <span
      className={`battery ${level < 20 ? 'low' : ''}`}
      role="img"
      aria-label={`${level}% battery${device.battery_charging ? ', charging' : ''}`}
    >
      <span className="battery-icon">
        <i className="battery-fill" style={{ width: `${level}%` }} />
      </span>
      {level}%{device.battery_charging && <span aria-hidden="true">↯</span>}
    </span>
  );
}
function DeviceWorkspace({
  device,
  library,
  devices,
}: {
  device: Device;
  library: Library;
  devices: Device[];
}) {
  const { connected } = useBlocksd();
  const settings = useDeviceSettings(device);
  const [group, setGroup] = useState('all');
  const metadata = new Map(settings.schema.map(item => [item.item, item]));
  const groups = [
    ...new Set(settings.values.map(value => metadata.get(value.item)?.group ?? 'device settings')),
  ];
  const presetPending = library.presets.some(
    preset =>
      preset.serial === device.serial && library.applications[preset.id]?.status === 'pending',
  );
  const pending =
    presetPending || Object.values(settings.writes).some(write => write.status === 'pending');
  const filtered = settings.values.filter(
    value => group === 'all' || (metadata.get(value.item)?.group ?? 'device settings') === group,
  );
  return (
    <>
      <section className="device-workspace" aria-label={`${device.name} settings`}>
        <div className="instrument-panel">
          <div className="instrument-header">
            <span className="eyebrow">selected instrument</span>
            <span className="badge">
              <span className="signal-dot active" />
              connected
            </span>
          </div>
          <h2>{device.name || blockTypeLabels[device.block_type] || 'ROLI Block'}</h2>
          <p className="instrument-type">
            {blockTypeLabels[device.block_type] ?? device.block_type}
          </p>
          <DeviceSurface device={device} />
          <dl className="instrument-facts">
            <div>
              <dt>battery</dt>
              <dd>
                <Battery device={device} />
              </dd>
            </div>
            <div>
              <dt>firmware</dt>
              <dd>{device.firmware_version || 'not reported'}</dd>
            </div>
            <div>
              <dt>serial</dt>
              <dd>{device.serial}</dd>
            </div>
          </dl>
          <div className="instrument-tip">
            <span aria-hidden="true">↗</span>
            <p>
              your sound starts in your DAW.
              <br />
              your feel starts here.
            </p>
          </div>
        </div>
        <div className="settings-panel">
          <div className="section-heading">
            <div>
              <span className="eyebrow">make it feel right</span>
              <h2>device settings</h2>
            </div>
            <button
              className="button subtle"
              type="button"
              disabled={!connected || settings.loading || pending}
              onClick={() => void settings.refresh()}
              aria-label="refresh device settings"
            >
              ↻ <span>refresh</span>
            </button>
          </div>
          <p className="settings-intro">
            values come from your device. changes are confirmed when the device reports them back.
          </p>
          {settings.error && (
            <p role="alert" className="message error">
              {settings.error}
            </p>
          )}
          {groups.length > 1 && (
            <fieldset className="setting-filters" aria-label="filter settings">
              <button type="button" aria-pressed={group === 'all'} onClick={() => setGroup('all')}>
                all settings
              </button>
              {groups.map(item => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={group === item}
                  onClick={() => setGroup(item)}
                >
                  {item}
                </button>
              ))}
            </fieldset>
          )}
          {settings.loading && !settings.values.length ? (
            <div className="settings-empty" role="status">
              <span className="loading-line" />
              reading device settings…
            </div>
          ) : !settings.values.length ? (
            <div className="settings-empty">
              <h3>no settings reported yet.</h3>
              <p>your device may still be syncing, or may not expose configurable settings.</p>
              <button
                type="button"
                className="button secondary"
                disabled={!connected || settings.loading}
                onClick={() => void settings.refresh()}
              >
                read settings again
              </button>
            </div>
          ) : (
            <div className="setting-list">
              {filtered.map(value => (
                <SettingControl
                  key={value.item}
                  value={value}
                  metadata={metadata.get(value.item)}
                  write={settings.writes[value.item]}
                  disabled={!connected || presetPending}
                  onChange={(item, next) => void settings.setValue(item, next)}
                />
              ))}
            </div>
          )}
        </div>
      </section>
      <SavePreset
        serial={device.serial}
        library={library}
        disabled={!connected || !settings.values.length || pending || settings.loading}
      />
      <PresetLibrary
        library={library}
        devices={devices}
        connected={connected}
        serial={device.serial}
      />
    </>
  );
}
