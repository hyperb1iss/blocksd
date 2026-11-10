import { useId, useState } from 'react';
import { useDeviceProgram } from '../../hooks/useDeviceProgram';
import { programFilesError } from '../../lib/program';
import type { DeviceProgram } from '../../lib/types';

const stateLabels: Record<DeviceProgram['state'], string> = {
  idle: 'device program',
  compiling: 'compiling',
  uploading: 'uploading',
  waiting: 'waiting for device',
  ready: 'renderer ready',
  uploaded: 'upload acknowledged',
  unresponsive: 'device has not answered',
};

export function ProgramPanel({ serial }: { serial: string }) {
  const { program, statusError, loadError, busy, load, restore, connected } =
    useDeviceProgram(serial);
  const [file, setFile] = useState<File | null>(null);
  const [includes, setIncludes] = useState<File[]>([]);
  const fileError = programFilesError(file, includes);
  const inputId = useId();
  const includesId = useId();
  const headingId = useId();
  const noteId = useId();
  const loading = busy !== null || program?.state === 'compiling' || program?.state === 'uploading';
  const disabled = !connected || loading;

  return (
    <section className="program-panel" aria-labelledby={headingId}>
      <div className="section-heading">
        <h2 id={headingId}>device program</h2>
        <span className={`program-state ${program?.state ?? 'idle'}`} role="status">
          {!connected
            ? 'disconnected'
            : busy
              ? busy
              : program
                ? stateLabels[program.state]
                : 'reading status'}
        </span>
      </div>
      <div className="program-current" aria-live="polite">
        {program?.name && <h3>{program.name}</h3>}
        <p>
          {!connected
            ? 'reconnect to read the current program.'
            : program?.state === 'uploaded' && program.owner === 'custom'
              ? 'upload acknowledged; execution is not verified.'
              : program?.state === 'unresponsive'
                ? program.owner === 'custom'
                  ? 'the device has not acknowledged the complete upload. check the device connection and open transfer details below.'
                  : 'the lighting program has not answered. check the device connection and open transfer details below.'
                : (program?.message ?? 'reading the current program from blocksd.')}
        </p>
      </div>
      {statusError && (
        <p className="message error" role="alert">
          {statusError}
        </p>
      )}
      <form
        className="program-load"
        onSubmit={event => {
          event.preventDefault();
          if (file && !disabled && !fileError) void load(file, includes);
        }}
      >
        <label htmlFor={inputId}>LittleFoot file</label>
        <div className="program-file-row">
          <input
            id={inputId}
            type="file"
            accept=".littlefoot"
            disabled={disabled}
            aria-describedby={noteId}
            onChange={event => setFile(event.target.files?.[0] ?? null)}
          />
          <button
            type="submit"
            className="button primary"
            disabled={disabled || !file || Boolean(fileError)}
          >
            {busy === 'compiling' ? 'compiling…' : 'load program'}
          </button>
        </div>
        <p id={noteId} className="program-note">
          loading replaces the active program on this device. it does not save a startup default.
        </p>
        <details className="program-includes">
          <summary>
            additional include files{includes.length > 0 && ` (${includes.length})`}
          </summary>
          <p>
            standard LittleFoot library files are included. select any other files your program
            imports.
          </p>
          <label htmlFor={includesId}>include files</label>
          <input
            id={includesId}
            type="file"
            multiple
            disabled={disabled}
            onChange={event => setIncludes(Array.from(event.target.files ?? []))}
          />
        </details>
      </form>
      {program && program.owner !== 'device' && (
        <div className="program-restore">
          <button
            type="button"
            className="button secondary"
            disabled={!connected || busy !== null || program.state === 'compiling'}
            onClick={() => void restore()}
          >
            {busy === 'restoring' ? 'restoring…' : 'restore saved program'}
          </button>
          <p>restores the program saved on your device. device settings are not factory-reset.</p>
        </div>
      )}
      {(fileError || loadError) && (
        <pre className="message error program-error" role="alert">
          {fileError || loadError}
        </pre>
      )}
      {program && program.owner !== 'device' && (
        <details className="program-details">
          <summary>transfer details</summary>
          <dl>
            <div>
              <dt>program</dt>
              <dd>{program.code_size} bytes</dd>
            </div>
            <div>
              <dt>memory</dt>
              <dd>{program.heap_size} bytes</dd>
            </div>
          </dl>
          <p>{program.message}</p>
        </details>
      )}
    </section>
  );
}
