/** Block configuration item IDs (mirrors blocksd/device/config_ids.py). */
export const ConfigId = {
  PITCHBEND_RANGE: 3,
  OCTAVE: 4,
  TRANSPOSE: 5,
  SLIDE_CC: 6,
  MIDI_CHANNEL_MODE: 7,
  VELOCITY_SENSITIVITY: 10,
  SLIDE_SENSITIVITY: 11,
  GLIDE_SENSITIVITY: 12,
  PRESSURE_SENSITIVITY: 13,
  LIFT_SENSITIVITY: 14,
  FIXED_VELOCITY: 15,
  FIXED_VELOCITY_VALUE: 16,
  PIANO_MODE: 17,
  GLIDE_LOCK_RATE: 18,
  GLIDE_LOCK_ENABLED: 19,
  GRID_SIZE: 20,
  SCALE: 22,
  HIDE_MODE: 23,
  COLOUR_PRESET: 24,
  MPE_ZONE: 30,
  MPE_CHANNEL_START: 31,
  MPE_CHANNEL_END: 32,
  GAMMA_CORRECTION: 33,
} as const;

/** Config groups for the settings panel. */
export const configGroups = [
  {
    label: 'MIDI',
    items: [
      ConfigId.MPE_CHANNEL_START,
      ConfigId.MPE_CHANNEL_END,
      ConfigId.MPE_ZONE,
      ConfigId.PITCHBEND_RANGE,
      ConfigId.MIDI_CHANNEL_MODE,
    ],
  },
  {
    label: 'Sensitivity',
    items: [
      ConfigId.VELOCITY_SENSITIVITY,
      ConfigId.GLIDE_SENSITIVITY,
      ConfigId.SLIDE_SENSITIVITY,
      ConfigId.PRESSURE_SENSITIVITY,
      ConfigId.LIFT_SENSITIVITY,
    ],
  },
  {
    label: 'Musical',
    items: [ConfigId.SCALE, ConfigId.OCTAVE, ConfigId.TRANSPOSE, ConfigId.GRID_SIZE],
  },
  {
    label: 'Expression',
    items: [
      ConfigId.FIXED_VELOCITY,
      ConfigId.FIXED_VELOCITY_VALUE,
      ConfigId.GLIDE_LOCK_ENABLED,
      ConfigId.GLIDE_LOCK_RATE,
      ConfigId.PIANO_MODE,
    ],
  },
  {
    label: 'Visual',
    items: [ConfigId.GAMMA_CORRECTION, ConfigId.COLOUR_PRESET],
  },
] as const;

/** Human-readable config names. */
export const configLabels: Record<number, string> = {
  [ConfigId.PITCHBEND_RANGE]: 'Pitch Bend Range',
  [ConfigId.OCTAVE]: 'Octave',
  [ConfigId.TRANSPOSE]: 'Transpose',
  [ConfigId.SLIDE_CC]: 'Slide CC',
  [ConfigId.MIDI_CHANNEL_MODE]: 'MIDI Channel Mode',
  [ConfigId.VELOCITY_SENSITIVITY]: 'Velocity',
  [ConfigId.SLIDE_SENSITIVITY]: 'Slide',
  [ConfigId.GLIDE_SENSITIVITY]: 'Glide',
  [ConfigId.PRESSURE_SENSITIVITY]: 'Pressure',
  [ConfigId.LIFT_SENSITIVITY]: 'Lift',
  [ConfigId.FIXED_VELOCITY]: 'Fixed Velocity',
  [ConfigId.FIXED_VELOCITY_VALUE]: 'Fixed Velocity Value',
  [ConfigId.PIANO_MODE]: 'Piano Mode',
  [ConfigId.GLIDE_LOCK_RATE]: 'Glide Lock Rate',
  [ConfigId.GLIDE_LOCK_ENABLED]: 'Glide Lock',
  [ConfigId.GRID_SIZE]: 'Grid Size',
  [ConfigId.SCALE]: 'Scale',
  [ConfigId.HIDE_MODE]: 'Hide Mode',
  [ConfigId.COLOUR_PRESET]: 'Colour Preset',
  [ConfigId.MPE_ZONE]: 'MPE Zone',
  [ConfigId.MPE_CHANNEL_START]: 'MIDI Start Channel',
  [ConfigId.MPE_CHANNEL_END]: 'MIDI End Channel',
  [ConfigId.GAMMA_CORRECTION]: 'Gamma Correction',
};

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
