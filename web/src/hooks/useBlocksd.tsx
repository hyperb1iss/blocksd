import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import type { ServerMessage } from '../lib/protocol';

type MessageListener = (msg: ServerMessage) => void;

interface BlocksdState {
  connected: boolean;
  send: (msg: Record<string, unknown>) => void;
  sendBinary: (data: ArrayBuffer) => void;
  subscribe: (listener: MessageListener) => () => void;
}

const BlocksdContext = createContext<BlocksdState | null>(null);

const RECONNECT_DELAY = 2000;
const ALL_EVENTS = ['device', 'touch', 'button', 'config', 'topology'];

export function BlocksdProvider({ children }: { children: React.ReactNode }) {
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const listenersRef = useRef(new Set<MessageListener>());
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;

    const connect = () => {
      if (!aliveRef.current) return;

      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const ws = new WebSocket(`${proto}//${window.location.host}/ws`);
      wsRef.current = ws;

      ws.binaryType = 'arraybuffer';

      ws.onopen = () => {
        setConnected(true);
        ws.send(JSON.stringify({ type: 'subscribe', events: ALL_EVENTS }));
      };

      ws.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        if (aliveRef.current) {
          reconnectRef.current = setTimeout(connect, RECONNECT_DELAY);
        }
      };

      ws.onerror = () => ws.close();

      ws.onmessage = event => {
        if (typeof event.data !== 'string') return;
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          for (const listener of listenersRef.current) {
            listener(msg);
          }
        } catch {
          // ignore malformed messages
        }
      };
    };

    connect();

    return () => {
      aliveRef.current = false;
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, []);

  const send = useCallback((msg: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(data);
    }
  }, []);

  const subscribe = useCallback((listener: MessageListener) => {
    listenersRef.current.add(listener);
    return () => {
      listenersRef.current.delete(listener);
    };
  }, []);

  return (
    <BlocksdContext.Provider value={{ connected, send, sendBinary, subscribe }}>
      {children}
    </BlocksdContext.Provider>
  );
}

export function useBlocksd(): BlocksdState {
  const ctx = useContext(BlocksdContext);
  if (!ctx) throw new Error('useBlocksd must be inside <BlocksdProvider>');
  return ctx;
}
