import { useCallback, useEffect, useRef, useState } from 'react';
import { programFilesError } from '../lib/program';
import type { ProgramStatusResponse } from '../lib/protocol';
import type { DeviceProgram } from '../lib/types';
import { useBlocksd } from './useBlocksd';

export function useDeviceProgram(serial: string) {
  const { connected, request } = useBlocksd();
  const [program, setProgram] = useState<DeviceProgram | null>(null);
  const [statusError, setStatusError] = useState('');
  const [loadError, setLoadError] = useState('');
  const [busy, setBusy] = useState<'compiling' | 'restoring' | null>(null);
  const generation = useRef(0);
  const operating = useRef(false);

  useEffect(() => {
    generation.current += 1;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setProgram(null);
    setStatusError('');
    setLoadError('');
    setBusy(null);
    operating.current = false;
    const poll = async () => {
      const revision = generation.current;
      try {
        if (operating.current) return;
        const result = await request<ProgramStatusResponse>({ type: 'program_status', serial });
        if (!stopped && revision === generation.current) {
          setProgram(result.program);
          setStatusError('');
        }
      } catch (cause) {
        if (!stopped && revision === generation.current)
          setStatusError(cause instanceof Error ? cause.message : 'could not read program status.');
      } finally {
        if (!stopped) timer = setTimeout(() => void poll(), 1000);
      }
    };
    if (connected) void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      generation.current += 1;
    };
  }, [connected, request, serial]);

  const load = useCallback(
    async (file: File, includeFiles: File[] = []) => {
      const revision = ++generation.current;
      operating.current = true;
      setBusy('compiling');
      setLoadError('');
      try {
        const invalid = programFilesError(file, includeFiles);
        if (invalid) throw new Error(invalid);
        const source = await file.text();
        const includes = Object.fromEntries(
          await Promise.all(
            includeFiles.map(async include => [include.name, await include.text()]),
          ),
        );
        if (revision !== generation.current) return;
        const result = await request<ProgramStatusResponse>(
          { type: 'program_load', serial, name: file.name, source, includes },
          { timeoutMs: 20_000 },
        );
        if (revision === generation.current) {
          setProgram(result.program);
          setStatusError('');
        }
      } catch (cause) {
        if (revision === generation.current)
          setLoadError(cause instanceof Error ? cause.message : 'could not load the program.');
      } finally {
        if (revision === generation.current) {
          operating.current = false;
          setBusy(null);
        }
      }
    },
    [request, serial],
  );

  const restore = useCallback(async () => {
    const revision = ++generation.current;
    operating.current = true;
    setBusy('restoring');
    setLoadError('');
    try {
      const result = await request<ProgramStatusResponse>({ type: 'program_reset', serial });
      if (revision === generation.current) {
        setProgram(result.program);
        setStatusError('');
      }
    } catch (cause) {
      if (revision === generation.current)
        setLoadError(
          cause instanceof Error ? cause.message : 'could not restore the saved program.',
        );
    } finally {
      if (revision === generation.current) {
        operating.current = false;
        setBusy(null);
      }
    }
  }, [request, serial]);

  return { program, statusError, loadError, busy, load, restore, connected };
}
