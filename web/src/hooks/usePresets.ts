import { useCallback, useEffect, useRef, useState } from 'react';
import type { Preset } from '../lib/types';
import { useBlocksd } from './useBlocksd';

type ApplyState = { status: 'pending' | 'confirmed' | 'error'; message: string };
export function usePresets() {
  const { connected, request, subscribe } = useBlocksd();
  const [presets, setPresets] = useState<Preset[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [applications, setApplications] = useState<Record<string, ApplyState>>({});
  const awaiting = useRef(
    new Map<
      string,
      { serial: string; remaining: Map<number, number>; timer: ReturnType<typeof setTimeout> }
    >(),
  );
  const alive = useRef(true);
  const refresh = useCallback(async () => {
    const result = await request<{ presets: Preset[] }>({ type: 'preset_list' });
    if (alive.current) setPresets(result.presets);
  }, [request]);
  useEffect(() => {
    alive.current = true;
    if (connected)
      void refresh().catch(cause => {
        if (alive.current) setError(String(cause.message));
      });
    else {
      for (const entry of awaiting.current.values()) clearTimeout(entry.timer);
      awaiting.current.clear();
      setApplications({});
    }
    return () => {
      alive.current = false;
      for (const entry of awaiting.current.values()) clearTimeout(entry.timer);
      awaiting.current.clear();
    };
  }, [connected, refresh]);
  useEffect(
    () =>
      subscribe(msg => {
        if (msg.type !== 'config_changed') return;
        for (const [id, entry] of awaiting.current) {
          if (entry.serial !== msg.serial || entry.remaining.get(msg.item) !== msg.value) continue;
          entry.remaining.delete(msg.item);
          if (entry.remaining.size === 0) {
            clearTimeout(entry.timer);
            awaiting.current.delete(id);
            setApplications(previous => ({
              ...previous,
              [id]: { status: 'confirmed', message: 'all settings confirmed by device' },
            }));
          }
        }
      }),
    [subscribe],
  );
  const perform = useCallback(async <T>(operation: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      return await operation();
    } catch (cause) {
      if (alive.current) setError(cause instanceof Error ? cause.message : 'operation failed.');
      return undefined;
    } finally {
      if (alive.current) setBusy(false);
    }
  }, []);
  const save = useCallback(
    (serial: string, name: string) =>
      perform(async () => {
        const result = await request<{ skipped_items?: number[] }>({
          type: 'preset_save',
          serial,
          name,
        });
        await refresh();
        if (alive.current) {
          const skipped = result.skipped_items?.length ?? 0;
          setNotice(
            skipped
              ? `preset saved. ${skipped} unsupported or read-only setting${skipped === 1 ? ' was' : 's were'} excluded.`
              : 'preset saved from the settings reported by your device.',
          );
        }
        return true;
      }),
    [perform, request, refresh],
  );
  const apply = useCallback(
    (preset: Preset) =>
      perform(async () => {
        const old = awaiting.current.get(preset.id);
        if (old) clearTimeout(old.timer);
        const timer = setTimeout(() => {
          awaiting.current.delete(preset.id);
          if (alive.current)
            setApplications(previous => ({
              ...previous,
              [preset.id]: {
                status: 'error',
                message: 'not all settings were confirmed. check the device before playing.',
              },
            }));
        }, 6500);
        awaiting.current.set(preset.id, {
          serial: preset.serial,
          remaining: new Map(preset.values.map(value => [value.item, value.value])),
          timer,
        });
        setApplications(previous => ({
          ...previous,
          [preset.id]: { status: 'pending', message: 'waiting for device readback' },
        }));
        try {
          await request({ type: 'preset_apply', serial: preset.serial, preset_id: preset.id });
        } catch (cause) {
          clearTimeout(timer);
          awaiting.current.delete(preset.id);
          if (alive.current)
            setApplications(previous => ({
              ...previous,
              [preset.id]: { status: 'error', message: 'preset could not be applied' },
            }));
          throw cause;
        }
      }),
    [perform, request],
  );
  const updateDefault = useCallback(
    (preset: Preset) =>
      perform(async () => {
        await request({
          type: 'preset_update',
          preset_id: preset.id,
          auto_restore: !preset.auto_restore,
        });
        await refresh();
      }),
    [perform, request, refresh],
  );
  const remove = useCallback(
    (preset: Preset) =>
      perform(async () => {
        await request({ type: 'preset_delete', preset_id: preset.id });
        await refresh();
        if (alive.current) setNotice('preset deleted. device settings are unchanged.');
      }),
    [perform, request, refresh],
  );
  const exportPreset = useCallback(
    (preset: Preset) =>
      perform(async () => {
        const result = await request<{ preset: Preset }>({
          type: 'preset_export',
          preset_id: preset.id,
        });
        const url = URL.createObjectURL(
          new Blob([JSON.stringify(result.preset, null, 2)], { type: 'application/json' }),
        );
        const link = document.createElement('a');
        link.href = url;
        link.download = `${preset.name.replace(/[^a-zA-Z0-9_-]+/g, '-') || 'blocksd-preset'}.json`;
        link.click();
        URL.revokeObjectURL(url);
      }),
    [perform, request],
  );
  const importPreset = useCallback(
    (file: File) =>
      perform(async () => {
        if (file.size > 1_000_000) throw new Error('choose a preset JSON file smaller than 1 MB.');
        let preset: unknown;
        try {
          preset = JSON.parse(await file.text());
        } catch {
          throw new Error('this file is not valid preset JSON.');
        }
        await request({ type: 'preset_import', preset });
        await refresh();
        if (alive.current)
          setNotice('preset imported. automatic restore is off until you enable it.');
      }),
    [perform, request, refresh],
  );
  return {
    presets,
    busy,
    error,
    notice,
    applications,
    save,
    apply,
    updateDefault,
    remove,
    exportPreset,
    importPreset,
  };
}
export type PresetLibrary = ReturnType<typeof usePresets>;
