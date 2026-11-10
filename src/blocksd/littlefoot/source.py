"""Resolve supplied LittleFoot sources and Dashboard metadata defaults."""

from __future__ import annotations

import math
import posixpath
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_NOTE = re.compile(r"([A-Ga-g])([#b]?)(-?\d+)\Z")
_MAX_SOURCE_BYTES = 262_144


def _normalize_newlines(source: str) -> str:
    return source.removeprefix("\ufeff").replace("\r\n", "\n").replace("\r", "\n")


def _without_comments(source: str) -> str:
    """Mask comments in one pass, retaining string literals and line positions."""
    masked = list(source)
    offset = 0
    while offset < len(source):
        if source.startswith("//", offset):
            end = source.find("\n", offset + 2)
            end = len(source) if end < 0 else end
        elif source.startswith("/*", offset):
            end = source.find("*/", offset + 2)
            end = len(source) if end < 0 else end + 2
        elif source[offset] in {"'", '"'}:
            quote = source[offset]
            offset += 1
            while offset < len(source):
                char = source[offset]
                offset += 1
                if char == "\\":
                    offset += 1
                elif char == quote:
                    break
            continue
        else:
            offset += 1
            continue
        masked[offset:end] = ["\n" if char == "\n" else " " for char in source[offset:end]]
        offset = end
    return "".join(masked)


def _include_directives(source: str) -> Iterator[tuple[int, int, str]]:
    """Find complete include lines without backtracking on malformed input."""
    offset = 0
    for line in _without_comments(source).splitlines(keepends=True):
        start = offset
        offset += len(line)
        directive = line.lstrip(" \t")
        if not directive.startswith("#"):
            continue
        directive = directive[1:].lstrip(" \t")
        if not directive.startswith("include"):
            continue
        argument = directive[len("include") :].lstrip(" \t")
        if not argument.startswith('"'):
            continue
        closing = argument.find('"', 1)
        if closing > 1 and argument[closing + 1 :].strip(" \t\n") in {"", ";"}:
            yield start, offset, argument[1:closing]


def _default_value(kind: str, value: str) -> tuple[str, str]:
    if kind == "bool":
        if value.lower() not in {"true", "false", "0", "1"}:
            raise ValueError(f"Invalid boolean metadata default: {value}")
        return "bool", "true" if value.lower() in {"true", "1"} else "false"
    if kind == "float":
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("Metadata defaults must be finite")
        return "float", repr(number)
    if kind == "midiNote":
        match = _NOTE.fullmatch(value)
        if match is None:
            raise ValueError(f"Invalid MIDI note metadata default: {value}")
        pitch, accidental, octave = match.groups()
        note = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}[pitch.upper()]
        number = (int(octave) + 2) * 12 + note + {"": 0, "#": 1, "b": -1}[accidental]
        if not 0 <= number <= 127:
            raise ValueError(f"MIDI note metadata default is outside 0..127: {value}")
        return "int", str(number)
    if kind == "int":
        number = int(value, 10)
        if not -(2**31) <= number < 2**31:
            raise ValueError("Integer metadata default exceeds signed 32-bit range")
        return "int", str(number)
    raise ValueError(f"Unsupported Dashboard metadata type: {kind}")


def _metadata_end(source: str, offset: int) -> int:
    quote = ""
    for position in range(offset, len(source)):
        char = source[position]
        if quote:
            if char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == ">":
            if source[position - 1] == "/":
                return position + 1
            closing = source.find("</metadata>", position + 1)
            if closing >= 0:
                return closing + len("</metadata>")
            break
    raise ValueError("Unterminated Dashboard metadata")


def _metadata_defaults(source: str) -> str:
    declarations: list[str] = []
    offset = 0
    while (start := source.find("<metadata", offset)) >= 0:
        offset = start + len("<metadata")
        if offset < len(source) and source[offset] not in " \t\r\n>/":
            continue
        offset = _metadata_end(source, offset)
        xml = source[start:offset]
        if "<!" in xml:
            raise ValueError("Dashboard metadata declarations are not supported")
        try:
            metadata = ET.fromstring(xml)  # noqa: S314 - DTD and entity declarations rejected above
        except ET.ParseError as exc:
            raise ValueError(f"Invalid Dashboard metadata: {exc}") from exc
        for variable in metadata.findall("./variables/*"):
            if variable.tag != "variable":
                raise ValueError(f"Unsupported Dashboard metadata element: {variable.tag}")
            name = variable.get("name", "")
            if not _IDENTIFIER.fullmatch(name):
                raise ValueError(f"Invalid Dashboard variable name: {name}")
            kind, value = _default_value(variable.get("type", "int"), variable.get("value", "0"))
            declarations.append(f"const {kind} {name} = {value};")
    return "\n".join(declarations)


@dataclass
class _SourceFrame:
    text: str
    name: str
    directives: Iterator[tuple[int, int, str]]
    cursor: int = 0


def prepare_source(source: str, *, includes: dict[str, str] | None = None) -> str:
    """Expand virtual include files, never arbitrary filesystem paths."""
    if not isinstance(source, str) or not source.strip():
        raise ValueError("LittleFoot source must be non-empty text")
    supplied = includes or {}
    for name, text in supplied.items():
        if not isinstance(name, str) or not isinstance(text, str):
            raise TypeError("Include names and contents must be text")
        if name.startswith(("/", "../")) or "\\" in name or posixpath.normpath(name) != name:
            raise ValueError(f"Invalid include name: {name}")
    if sum(len(text.encode()) for text in (source, *supplied.values())) > _MAX_SOURCE_BYTES:
        raise ValueError("LittleFoot source and includes exceed 256 KiB")
    source = _normalize_newlines(source)
    supplied = {name: _normalize_newlines(text) for name, text in supplied.items()}
    library = Path(__file__).with_name("library")
    included: set[str] = set()
    active: set[str] = set()
    chunks: list[str] = []
    expanded_bytes = 0

    def append(text: str) -> None:
        nonlocal expanded_bytes
        expanded_bytes += len(text.encode())
        if expanded_bytes > _MAX_SOURCE_BYTES:
            raise ValueError("Expanded LittleFoot source exceeds 256 KiB")
        chunks.append(text)

    defaults = _metadata_defaults(source)
    if defaults:
        append(defaults + "\n")
    frames = [_SourceFrame(source, "", _include_directives(source))]
    while frames:
        frame = frames[-1]
        directive = next(frame.directives, None)
        if directive is None:
            append(frame.text[frame.cursor :])
            frames.pop()
            if frame.name:
                active.remove(frame.name)
                included.add(frame.name)
                append("\n")
            continue
        start, end, requested = directive
        append(frame.text[frame.cursor : start])
        frame.cursor = end
        name = posixpath.normpath(posixpath.join(posixpath.dirname(frame.name), requested))
        if name in supplied:
            child = supplied[name]
        elif (
            requested == posixpath.basename(requested)
            or requested.startswith(("LittleFootLibrary/", "../LittleFootLibrary/"))
        ) and (library / posixpath.basename(requested)).suffix == ".littlefoot":
            name = "LittleFootLibrary/" + posixpath.basename(requested)
            bundled = library / posixpath.basename(requested)
            if not bundled.is_file():
                raise ValueError(f"Include not supplied: {requested}")
            child = None
        else:
            raise ValueError(f"Include not supplied: {requested}")
        if name in active:
            raise ValueError(f"Circular LittleFoot include: {name}")
        if name in included:
            append("\n")
        else:
            active.add(name)
            if child is None:
                child = _normalize_newlines(bundled.read_text(encoding="utf-8"))
            frames.append(_SourceFrame(child, name, _include_directives(child)))
    return "".join(chunks)


def collect_file_sources(path: Path) -> tuple[str, dict[str, str]]:
    """Read referenced local includes only, confined to the selected directory."""
    root = path.resolve().parent
    includes: dict[str, str] = {}
    total_bytes = 0

    def read(file: Path) -> str:
        nonlocal total_bytes
        if not file.resolve().is_relative_to(root):
            raise ValueError(f"Include is outside the selected source directory: {file.name}")
        size = file.stat().st_size
        if total_bytes + size > _MAX_SOURCE_BYTES:
            raise ValueError("LittleFoot source and includes exceed 256 KiB")
        text = file.read_text(encoding="utf-8")
        total_bytes += len(text.encode())
        return _normalize_newlines(text)

    source = read(path)
    pending = [(source, path)]
    while pending:
        text, current = pending.pop()
        for _, _, requested in _include_directives(text):
            child = (current.parent / requested).resolve()
            if not child.is_relative_to(root):
                continue  # Bundled library paths are resolved by prepare_source.
            name = child.relative_to(root).as_posix()
            if name not in includes and child.is_file():
                content = read(child)
                includes[name] = content
                pending.append((content, child))
    return source, includes
