"""MIDI device scanning — finds ROLI Blocks by matching port names.

Ported from roli_MIDIDeviceDetector.cpp.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

log = logging.getLogger(__name__)

# ROLI MIDI port names contain "BLOCK" or "Block"
_BLOCK_PATTERN = re.compile(r"\bBLOCK\b|\bBlock\b")

# Suffixes added by ALSA/JACK that differ between input and output
_STRIP_SUFFIXES = re.compile(r"\s*(IN|OUT)\)$|\s*\[\d+\]$")


@dataclass(frozen=True)
class MidiPortPair:
    """Matched MIDI input + output port for a single ROLI device."""

    input_port: int
    output_port: int
    name: str


def _is_blocks_port(name: str) -> bool:
    """Check if a MIDI port name belongs to a ROLI Blocks device."""
    return _BLOCK_PATTERN.search(name) is not None


def _clean_port_name(name: str) -> str:
    """Normalize port name for input/output matching.

    Strips trailing suffixes like ' IN)', ' OUT)', '[0]' that differ
    between the input and output side of the same device.
    """
    return _STRIP_SUFFIXES.sub("", name.strip())


def scan_for_blocks() -> list[MidiPortPair]:
    """Scan MIDI ports and return matched input/output pairs for ROLI Blocks.

    Uses the same matching strategy as roli_MIDIDeviceDetector:
    1. Find all MIDI inputs containing "BLOCK" or "Block"
    2. For each input, find the corresponding output by cleaned name
    3. Handle duplicate names (multiple blocks of same type) via occurrence counting
    """
    import rtmidi

    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()

    try:
        input_ports = midi_in.get_ports()
        output_ports = midi_out.get_ports()
    except Exception:
        midi_in.delete()
        midi_out.delete()
        raise

    pairs: list[MidiPortPair] = []

    for in_idx, in_name in enumerate(input_ports):
        if not _is_blocks_port(in_name):
            continue

        cleaned_in = _clean_port_name(in_name)

        # Count how many times we've already matched this cleaned name
        input_occurrences = sum(1 for p in pairs if _clean_port_name(p.name) == cleaned_in)

        # Find the Nth matching output
        output_occurrences = 0
        matched_out_idx = -1

        for out_idx, out_name in enumerate(output_ports):
            if _clean_port_name(out_name) == cleaned_in:
                if output_occurrences == input_occurrences:
                    matched_out_idx = out_idx
                    break
                output_occurrences += 1

        if matched_out_idx >= 0:
            pairs.append(MidiPortPair(in_idx, matched_out_idx, in_name))
            log.debug("Found ROLI device: %s (in=%d, out=%d)", in_name, in_idx, matched_out_idx)
        else:
            log.warning("No matching output for ROLI input: %s", in_name)

    # Close ALSA sequencer clients to avoid exhausting /dev/snd/seq slots
    midi_in.delete()
    midi_out.delete()

    return pairs
