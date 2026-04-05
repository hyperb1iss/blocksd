# Contributing to blocksd

Contributions welcome! Whether it's fixing a bug, adding device support, or building new features — we'd love your help.

## Setup

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
uv sync          # installs all dependencies including dev tools
```

## Development Workflow

The project includes a [justfile](https://just.systems/) for common tasks:

```bash
just check          # lint + format check + typecheck + tests (the full gate)
just test           # run all tests
just test-v         # verbose test output
just test-mod protocol  # tests for a specific module
just lint           # ruff lint
just fmt            # auto-format
just typecheck      # ty check
just fix            # auto-fix lint + format
```

Or run tools directly:

```bash
uv run pytest                  # all tests
uv run pytest -v               # verbose
uv run pytest tests/protocol/  # specific module
uv run ruff check .            # lint
uv run ruff format .           # auto-format
uv run ty check                # type check
uv run blocksd run -v          # run the daemon (requires hardware)
```

## Project Structure

- **`src/blocksd/protocol/`** — Pure protocol logic (packing, builder, decoder). No I/O, fully testable.
- **`src/blocksd/device/`** — Device models, config IDs, connection layer.
- **`src/blocksd/topology/`** — Device discovery, lifecycle management, topology tracking.
- **`src/blocksd/led/`** — LED bitmap grid and pattern generators.
- **`src/blocksd/littlefoot/`** — LittleFoot VM opcodes, assembler, programs.
- **`src/blocksd/api/`** — Unix socket + WebSocket server, event broadcasting.
- **`src/blocksd/web/`** — Web dashboard assets.
- **`src/blocksd/config/`** — Daemon configuration (Pydantic schema, TOML loader).
- **`src/blocksd/cli/`** — Typer CLI commands.
- **`tests/`** — Mirrors source structure.

## Best Areas to Contribute

- **LED patterns** — New visual patterns for Lightpad blocks
- **Touch event handling** — Higher-level gestures, MIDI mapping
- **Web dashboard** — Enhance the `blocksd ui` real-time interface
- **D-Bus interface** — IPC for desktop integration
- **Device support** — Testing with Seaboard, Live, Loop, or Developer blocks
- **Documentation** — Usage guides, API examples (see `docs/` for protocol reference)

## Guidelines

- All code must pass `ruff check`, `ruff format --check`, and `ty check`
- Add tests for new functionality — the protocol layer especially should have exhaustive coverage
- Keep commits focused and descriptive
- The protocol layer is pure functions with no I/O — keep it that way

## Testing Without Hardware

Most of the codebase is testable without a physical ROLI device. The protocol layer, LED bitmap logic, and LittleFoot assembler are all pure computation. Only the topology/connection layer requires hardware.

```bash
# Run just the hardware-free tests
uv run pytest tests/protocol/ tests/led/ tests/littlefoot/ tests/device/
```
