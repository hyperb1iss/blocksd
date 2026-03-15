import { useCallback, useEffect, useRef, useState } from 'react';
import type { ConfigValue } from '../lib/types';
import { useBlocksd } from './useBlocksd';

const DEBOUNCE_MS = 150;

/** Per-device config read/write with debounced set. */
export function useConfig(uid: number | undefined) {
  const { send, subscribe, connected } = useBlocksd();
  const [values, setValues] = useState<Map<number, ConfigValue>>(new Map());
  const timerRef = useRef<Map<number, ReturnType<typeof setTimeout>>>(new Map());

  // Request config on connect or uid change
  useEffect(() => {
    if (connected && uid != null) {
      send({ type: 'config_get', uid });
    }
  }, [connected, uid, send]);

  // Listen for config responses and changes
  useEffect(() => {
    return subscribe(msg => {
      if (msg.type === 'config_values' && msg.uid === uid) {
        const map = new Map<number, ConfigValue>();
        for (const v of msg.values) {
          map.set(v.item, v);
        }
        setValues(map);
      } else if (msg.type === 'config_changed' && msg.uid === uid) {
        setValues(prev => {
          const next = new Map(prev);
          const existing = next.get(msg.item);
          next.set(msg.item, {
            item: msg.item,
            value: msg.value,
            min: existing?.min ?? 0,
            max: existing?.max ?? 127,
          });
          return next;
        });
      }
    });
  }, [subscribe, uid]);

  const setValue = useCallback(
    (item: number, value: number) => {
      if (uid == null) return;

      // Optimistic update
      setValues(prev => {
        const next = new Map(prev);
        const existing = next.get(item);
        next.set(item, { item, value, min: existing?.min ?? 0, max: existing?.max ?? 127 });
        return next;
      });

      // Debounce the network send
      const existing = timerRef.current.get(item);
      if (existing) clearTimeout(existing);

      timerRef.current.set(
        item,
        setTimeout(() => {
          send({ type: 'config_set', uid, item, value });
          timerRef.current.delete(item);
        }, DEBOUNCE_MS),
      );
    },
    [uid, send],
  );

  return { values, setValue };
}
