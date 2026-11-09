import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConfigAckResponse, ConfigValuesResponse } from '../lib/protocol';
import type { ConfigMetadata, ConfigValue, Device } from '../lib/types';
import { useBlocksd } from './useBlocksd';

export interface WriteState {
  status: 'pending' | 'confirmed' | 'error';
  value: number;
  message?: string;
}
export function useDeviceSettings(device: Device) {
  const { request, subscribe, connected } = useBlocksd();
  const [values, setValues] = useState<ConfigValue[]>([]);
  const [schema, setSchema] = useState<ConfigMetadata[]>([]);
  const [writes, setWrites] = useState<Record<number, WriteState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());
  const active = useRef(true);
  const generation = useRef(0);

  const refresh = useCallback(async () => {
    const current = generation.current;
    setLoading(true);
    setError('');
    try {
      const result = await request<ConfigValuesResponse>({
        type: 'config_get',
        serial: device.serial,
        refresh: true,
      });
      if (!active.current || current !== generation.current) return;
      setValues(result.values);
      setSchema(result.schema ?? []);
    } catch (cause) {
      if (active.current && current === generation.current)
        setError(cause instanceof Error ? cause.message : 'could not read settings.');
    } finally {
      if (active.current && current === generation.current) setLoading(false);
    }
  }, [request, device.serial]);

  useEffect(() => {
    active.current = true;
    generation.current += 1;
    if (connected) void refresh();
    else {
      setValues([]);
      setWrites({});
      setLoading(false);
    }
    return () => {
      active.current = false;
      generation.current += 1;
      for (const timer of timers.current.values()) clearTimeout(timer);
      timers.current.clear();
    };
  }, [connected, refresh]);

  useEffect(
    () =>
      subscribe(msg => {
        if (msg.type === 'config_reset' && msg.serial === device.serial) {
          generation.current += 1;
          for (const timer of timers.current.values()) clearTimeout(timer);
          timers.current.clear();
          setValues([]);
          setSchema([]);
          setWrites({});
          setError('');
          setLoading(false);
          return;
        }
        if (msg.type !== 'config_changed' || msg.serial !== device.serial) return;
        const metadata = msg.schema;
        if (metadata) {
          setSchema(previous => [
            ...previous.filter(item => item.item !== metadata.item),
            metadata,
          ]);
        }
        setValues(previous => {
          const existing = previous.find(value => value.item === msg.item);
          if (!existing && (msg.min === undefined || msg.max === undefined)) return previous;
          const next = {
            item: msg.item,
            value: msg.value,
            min: msg.min ?? existing!.min,
            max: msg.max ?? existing!.max,
            writable: msg.writable ?? existing?.writable,
          };
          return [...previous.filter(value => value.item !== msg.item), next].sort(
            (a, b) => a.item - b.item,
          );
        });
        setWrites(previous => {
          const write = previous[msg.item];
          if (write?.status !== 'pending' || write.value !== msg.value) return previous;
          clearTimeout(timers.current.get(msg.item));
          timers.current.delete(msg.item);
          return { ...previous, [msg.item]: { ...write, status: 'confirmed' } };
        });
      }),
    [device.serial, subscribe],
  );

  const markPending = useCallback((items: { item: number; value: number }[]) => {
    setWrites(previous => {
      const next = { ...previous };
      for (const entry of items) next[entry.item] = { status: 'pending', value: entry.value };
      return next;
    });
    for (const entry of items) {
      clearTimeout(timers.current.get(entry.item));
      timers.current.set(
        entry.item,
        setTimeout(() => {
          timers.current.delete(entry.item);
          if (!active.current) return;
          setWrites(previous => ({
            ...previous,
            [entry.item]: {
              status: 'error',
              value: entry.value,
              message: 'device has not confirmed this value. refresh to check.',
            },
          }));
        }, 6000),
      );
    }
  }, []);

  const setValue = useCallback(
    async (item: number, value: number) => {
      const current = generation.current;
      markPending([{ item, value }]);
      try {
        const response = await request<ConfigAckResponse>({
          type: 'config_set',
          serial: device.serial,
          item,
          value,
        });
        if (!response.ok) throw new Error(response.message ?? 'device rejected this setting.');
      } catch (cause) {
        if (!active.current || generation.current !== current) return;
        clearTimeout(timers.current.get(item));
        timers.current.delete(item);
        setWrites(previous => ({
          ...previous,
          [item]: {
            status: 'error',
            value,
            message: cause instanceof Error ? cause.message : 'could not change this setting.',
          },
        }));
      }
    },
    [request, device.serial, markPending],
  );
  return { values, schema, writes, loading, error, refresh, setValue, markPending };
}
