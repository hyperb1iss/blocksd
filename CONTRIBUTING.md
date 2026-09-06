# Contributing to blocksd

## Setup

Install Python 3.13 or 3.14, [uv](https://docs.astral.sh/uv/getting-started/installation/), Node 24.13 or newer, [pnpm](https://pnpm.io/installation), and [just](https://just.systems/). Both JavaScript projects declare their pnpm version in `package.json`. The default Python version is in `.python-version`.

The RtMidi extension needs native development headers when a wheel is unavailable. On Debian or Ubuntu:

```bash
sudo apt-get install build-essential pkg-config libasound2-dev libjack-jackd2-dev
```

On macOS, install Xcode Command Line Tools (`xcode-select --install`) if RtMidi needs to compile. macOS uses CoreMIDI and does not require ALSA/JACK headers. Python tests and installed-wheel checks run on both Linux and macOS in CI.

Clone the repository and install the locked dependencies:

```bash
git clone https://github.com/hyperb1iss/blocksd.git
cd blocksd
just install
uv run --locked pre-commit install
```

For Python-only work, use `just install-python`. The dashboard and documentation have separate dependency installs (`just install-web` and `just install-docs`).

## Development workflow

Run `just check` before submitting a change. The gate covers Python lint, formatting, types and tests; dashboard lint, types and build; the documentation build; and an installed-wheel smoke check.

```bash
just check-python       # backend checks, no hardware needed
just test               # all Python tests
just test-mod protocol  # one test directory
just web-dev            # dashboard with /ws proxied to localhost:9010
just check-web          # dashboard lint, types and production build
just docs-dev           # documentation preview
just docs-build         # documentation production build
just build-check        # build and verify the installed distribution
```

Stop any installed blocksd service before starting a development daemon. Run the daemon in a separate terminal for dashboard development:

```bash
uv run --locked blocksd ui --no-browser
```

The live daemon controls connected hardware. The Python test suite uses simulated transports and does not need physical ROLI devices. A passing suite does not establish device compatibility or LED timing on hardware.

The source of truth for Python tool versions is `uv.lock`, including the local Ruff hooks. Installs and checks use locked resolution so a stale manifest fails visibly. JavaScript installs use `--frozen-lockfile`. These follow the [uv locking model](https://docs.astral.sh/uv/concepts/projects/sync/) and each project's committed pnpm lockfile.

Use `just fix` for Python lint fixes and formatting, `pnpm --dir web format` for the dashboard, and `just fmt-docs` for documentation. Formatting is explicit; normal checks do not rewrite source.

The LED and config CLI commands currently open their own MIDI sessions. The daemon skips LittleFoot renderer upload, so tests of frame acceptance do not establish visible LED output. Timing fields in DaemonConfig are parsed but not forwarded to the topology runtime. Keep documentation and release notes explicit about these limitations.

## Architecture

The pure protocol layer owns binary packing, decoding and packet construction. Device models describe capabilities; the MIDI transport boundary handles I/O. Topology owns discovery and device lifecycles. The daemon owns background tasks and unwinds startup and shutdown. API transports share command handling and own their connected clients.

| Directory                 | Responsibility                                        |
| ------------------------- | ----------------------------------------------------- |
| `src/blocksd/protocol/`   | Pure wire protocol and remote heap logic              |
| `src/blocksd/device/`     | Models, configuration IDs and MIDI transport          |
| `src/blocksd/topology/`   | Discovery and device lifecycle                        |
| `src/blocksd/led/`        | Bitmap and pattern generation                         |
| `src/blocksd/littlefoot/` | VM opcodes, assembler and programs                    |
| `src/blocksd/api/`        | Shared commands, event delivery and socket transports |
| `src/blocksd/config/`     | TOML loading and validated settings                   |
| `src/blocksd/cli/`        | Command-line interface                                |
| `web/`                    | Dashboard source                                      |
| `docs/`                   | Documentation site                                    |
| `tests/`                  | Hardware-independent regression tests                 |

Keep protocol logic free of I/O. Add command behavior in the shared dispatcher so Unix socket and WebSocket clients receive the same validation. New background tasks need an explicit owner that handles failure and joins cleanup. Test startup failures, cancellation and reconnects alongside successful operation.

## Building and dependency updates

Use `just build` to create the complete wheel and source distribution. The recipe builds the dashboard first into `src/blocksd/web/static/`; Hatch includes those generated assets in both artifacts. A direct `uv build` is available for backend-only development and does not generate dashboard assets.

Use `just build-check` to install the wheel into an isolated environment and verify CLI startup, the typing marker, and dashboard asset references. CI runs the same check. Release and publish workflows depend on the full CI gate and build the dashboard before packaging.

Refresh dependencies deliberately, then run the gate:

```bash
uv lock --upgrade
pnpm --dir web update --latest
pnpm --dir docs update
just install
just check
pnpm --dir web audit
pnpm --dir docs audit
```

The docs site pins VitePress to an explicit prerelease while that supported dependency graph is needed. Review its release notes and build the site before changing the pin. Dependabot proposes weekly Python, JavaScript and GitHub Actions updates; action references use commit SHAs.

Keep commits focused, include regression tests for behavior changes, and document any hardware verification separately from automated test results.

## Releases

Run `just check`, merge the changes, then dispatch Release with an explicit version (for example, `0.5.0`). Use its `dry_run` option to exercise preparation without tagging or publishing. The publication workflow generates release notes with git-iris using the Anthropic provider and `claude-opus-5`. Review the generated notes for accurate upgrade instructions and hardware limitations.

The release workflow updates package metadata, builds and verifies distributions, creates a tag, and dispatches publication. The GitHub release includes the wheel, source archive, `install.sh`, and `SHA256SUMS`; PyPI publication uses trusted publishing. Check the release and publish workflow results before announcing availability. The latest installer URL follows the latest GitHub release, while `--version` selects the package version from PyPI.
