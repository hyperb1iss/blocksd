"""Resolve supplied LittleFoot sources and Dashboard metadata defaults."""

from __future__ import annotations

import math
import posixpath
import re
import xml.etree.ElementTree as ET
from pathlib import Path

_INCLUDE = re.compile(r'(?m)^[ \t]*#[ \t]*include[ \t]*"([^"\n]+)"[ \t]*;?[ \t]*(?:\n|$)')
_COMMENTS = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"')
_METADATA = re.compile(r"<metadata\b[^>]*>.*?</metadata>", re.DOTALL)
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_NOTE = re.compile(r"([A-Ga-g])([#b]?)(-?\d+)\Z")
_MAX_SOURCE_BYTES = 262_144


def _without_comments(source: str) -> str:
    def mask(match: re.Match[str]) -> str:
        text = match.group()
        return text if text.startswith('"') else re.sub(r"[^\n]", " ", text)

    return _COMMENTS.sub(mask, source)


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


def _metadata_defaults(source: str) -> str:
    declarations: list[str] = []
    for match in _METADATA.finditer(source):
        xml = match.group()
        if "<!" in xml:
            raise ValueError("Dashboard metadata declarations are not supported")
        try:
            metadata = ET.fromstring(xml)  # noqa: S314 - DTD and entity declarations rejected above
        except ET.ParseError as exc:
            raise ValueError(f"Invalid Dashboard metadata: {exc}") from exc
        for variable in metadata.findall("./variables/variable"):
            name = variable.get("name", "")
            if not _IDENTIFIER.fullmatch(name):
                raise ValueError(f"Invalid Dashboard variable name: {name}")
            kind, value = _default_value(variable.get("type", "int"), variable.get("value", "0"))
            declarations.append(f"const {kind} {name} = {value};")
    return "\n".join(declarations)


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
    library = Path(__file__).with_name("library")
    included: set[str] = set()
    active: set[str] = set()
    expanded_bytes = 0

    def expand(text: str, filename: str) -> str:
        nonlocal expanded_bytes
        chunks: list[str] = []
        end = 0
        for match in _INCLUDE.finditer(_without_comments(text)):
            requested = match.group(1)
            name = posixpath.normpath(posixpath.join(posixpath.dirname(filename), requested))
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
                child = bundled.read_text(encoding="utf-8")
            else:
                raise ValueError(f"Include not supplied: {requested}")
            if name in active:
                raise ValueError(f"Circular LittleFoot include: {name}")
            chunks.append(text[end : match.start()])
            if name not in included:
                active.add(name)
                chunks.append(expand(child, name))
                active.remove(name)
                included.add(name)
            chunks.append("\n")
            end = match.end()
        chunks.append(text[end:])
        result = "".join(chunks)
        expanded_bytes += len(result.encode())
        if expanded_bytes > _MAX_SOURCE_BYTES:
            raise ValueError("Expanded LittleFoot source exceeds 256 KiB")
        return result

    try:
        expanded = expand(source, "")
    except RecursionError as exc:
        raise ValueError("LittleFoot include nesting exceeds the compiler host stack") from exc
    defaults = _metadata_defaults(source)
    return defaults + "\n" + expanded if defaults else expanded


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
        return text

    source = read(path)
    pending = [(source, path)]
    while pending:
        text, current = pending.pop()
        for match in _INCLUDE.finditer(_without_comments(text)):
            requested = match.group(1)
            child = (current.parent / requested).resolve()
            if not child.is_relative_to(root):
                continue  # Bundled library paths are resolved by prepare_source.
            name = child.relative_to(root).as_posix()
            if name not in includes and child.is_file():
                content = read(child)
                includes[name] = content
                pending.append((content, child))
    return source, includes
