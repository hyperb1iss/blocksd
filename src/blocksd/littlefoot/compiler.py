"""Compile LittleFoot with the bundled ISC-licensed vendor compiler."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from blocksd.littlefoot.source import collect_file_sources, prepare_source


def compile_source(source: str, *, includes: dict[str, str] | None = None) -> bytes:
    """Compile supplied text and includes without allowing compiler filesystem reads.

    Dashboard metadata variables use their declared defaults. Live editing of
    Dashboard metadata is not part of the LittleFoot compiler protocol.
    """
    prepared = prepare_source(source, includes=includes)
    executable = Path(__file__).with_name("_native") / (
        "blocksd-littlefoot.exe" if os.name == "nt" else "blocksd-littlefoot"
    )
    if not executable.is_file():
        raise ValueError("The LittleFoot compiler is missing. Reinstall blocksd to build it.")
    try:
        result = subprocess.run(  # noqa: S603 - only the bundled executable is invoked
            [str(executable)], input=prepared.encode(), capture_output=True, check=False, timeout=15
        )
    except subprocess.TimeoutExpired as exc:
        raise ValueError("LittleFoot compilation exceeded 15 seconds") from exc
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        raise ValueError(message or f"LittleFoot compiler exited with status {result.returncode}")
    if not result.stdout:
        raise ValueError("LittleFoot compiler returned no program")
    return result.stdout


def compile_file(path: Path) -> bytes:
    """Compile a local file with includes confined to its containing directory."""
    source, includes = collect_file_sources(path)
    return compile_source(source, includes=includes)
