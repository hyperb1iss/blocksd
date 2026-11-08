/** Human-readable block type labels. */
export const blockTypeLabels: Record<string, string> = {
  lightpad: 'Lightpad Block',
  lightpad_m: 'Lightpad Block M',
  seaboard: 'Seaboard Block',
  lumi_keys: 'LUMI Keys',
  live: 'Live Block',
  loop: 'Loop Block',
  touch: 'Touch Block',
  developer: 'Developer Block',
  unknown: 'Unknown',
};

/** Block type → icon character. */
export const blockTypeIcons: Record<string, string> = {
  lightpad: '\u25A3',
  lightpad_m: '\u25A3',
  seaboard: '\u2328',
  lumi_keys: '\u2328',
  live: '\u25B6',
  loop: '\u21BB',
  touch: '\u261B',
  developer: '\u2699',
  unknown: '\u2753',
};

/** Binary LED frame constants (matches blocksd protocol). */
export const BINARY_MAGIC = 0xbd;
export const BINARY_TYPE_FRAME = 0x01;
export const FRAME_SIZE = 685;
export const PIXEL_COUNT = 225; // 15x15
export const GRID_SIZE = 15;
