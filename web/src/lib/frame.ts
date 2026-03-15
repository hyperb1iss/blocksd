import { BINARY_MAGIC, BINARY_TYPE_FRAME, FRAME_SIZE } from './constants';

/** Build a 685-byte binary LED frame for WebSocket transmission. */
export function buildLEDFrame(uid: number, pixels: Uint8Array): ArrayBuffer {
  const buf = new ArrayBuffer(FRAME_SIZE);
  const view = new DataView(buf);

  view.setUint8(0, BINARY_MAGIC);
  view.setUint8(1, BINARY_TYPE_FRAME);
  // UID as u64 LE — split into low/high 32-bit words
  view.setUint32(2, uid & 0xffffffff, true);
  view.setUint32(6, Math.floor(uid / 0x100000000) & 0xffffffff, true);

  const dest = new Uint8Array(buf, 10, 675);
  dest.set(pixels.subarray(0, 675));

  return buf;
}
