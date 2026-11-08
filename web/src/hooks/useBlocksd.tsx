import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ServerMessage } from '../lib/protocol';

type MessageListener = (msg: ServerMessage) => void;
type PendingRequest = {
  resolve: (msg: unknown) => void;
  reject: (error: Error) => void;
  timer: ReturnType<typeof setTimeout>;
};
interface BlocksdState {
  connected: boolean;
  send: (msg: Record<string, unknown>) => boolean;
  request: <T>(msg: Record<string, unknown>) => Promise<T>;
  sendBinary: (data: ArrayBuffer) => void;
  subscribe: (listener: MessageListener) => () => void;
}
const BlocksdContext = createContext<BlocksdState | null>(null);
const ALL_EVENTS = ['device', 'touch', 'button', 'config', 'topology'];

export function BlocksdProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef(new Set<MessageListener>());
  const pending = useRef(new Map<string, PendingRequest>());
  const sequence = useRef(0);

  useEffect(() => {
    let alive = true;
    let reconnect: ReturnType<typeof setTimeout> | undefined;
    const rejectPending = () => {
      for (const entry of pending.current.values()) {
        clearTimeout(entry.timer);
        entry.reject(new Error('connection lost. reconnect before trying again.'));
      }
      pending.current.clear();
    };
    const connect = () => {
      if (!alive) return;
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${window.location.host}/ws`);
      wsRef.current = ws;
      ws.binaryType = 'arraybuffer';
      ws.onopen = () => {
        if (!alive || wsRef.current !== ws) return;
        ws.send(JSON.stringify({ type: 'subscribe', events: ALL_EVENTS }));
        setConnected(true);
      };
      ws.onclose = () => {
        if (!alive || wsRef.current !== ws) return;
        wsRef.current = null;
        setConnected(false);
        rejectPending();
        reconnect = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = event => {
        if (!alive || wsRef.current !== ws || typeof event.data !== 'string') return;
        let msg: ServerMessage;
        try {
          msg = JSON.parse(event.data) as ServerMessage;
        } catch {
          return;
        }
        if (!msg || typeof msg.type !== 'string') return;
        if ('id' in msg && typeof msg.id === 'string') {
          const entry = pending.current.get(msg.id);
          if (entry) {
            clearTimeout(entry.timer);
            pending.current.delete(msg.id);
            if (msg.type === 'error') entry.reject(new Error(msg.message));
            else entry.resolve(msg);
          }
        }
        for (const listener of listenersRef.current) listener(msg);
      };
    };
    connect();
    return () => {
      alive = false;
      clearTimeout(reconnect);
      wsRef.current?.close();
      wsRef.current = null;
      rejectPending();
    };
  }, []);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return false;
    wsRef.current.send(JSON.stringify(msg));
    return true;
  }, []);
  const request = useCallback(<T,>(msg: Record<string, unknown>): Promise<T> => {
    if (wsRef.current?.readyState !== WebSocket.OPEN)
      return Promise.reject(new Error('daemon is disconnected.'));
    const id = `dashboard-${++sequence.current}`;
    return new Promise<T>((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.current.delete(id);
        reject(new Error('no response from the daemon. try refreshing.'));
      }, 8000);
      pending.current.set(id, { resolve: value => resolve(value as T), reject, timer });
      wsRef.current?.send(JSON.stringify({ ...msg, id }));
    });
  }, []);
  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(data);
  }, []);
  const subscribe = useCallback((listener: MessageListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);
  return (
    <BlocksdContext.Provider value={{ connected, send, request, sendBinary, subscribe }}>
      {children}
    </BlocksdContext.Provider>
  );
}
export function useBlocksd(): BlocksdState {
  const ctx = useContext(BlocksdContext);
  if (!ctx) throw new Error('useBlocksd must be inside <BlocksdProvider>');
  return ctx;
}
