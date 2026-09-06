#!/usr/bin/env bash
# Install or upgrade blocksd and configure native device/service integration.
set -euo pipefail

bootstrap_uv() (
    # The subshell owns both the temporary file and its EXIT cleanup.
    bootstrap=$(mktemp)
    trap 'rm -f "$bootstrap"' EXIT
    curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh -o "$bootstrap"
    UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh "$bootstrap"
)

main() {
    local requirement='blocksd' uv_bin tool_bin
    local -a setup_args=()
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --version)
                [[ $# -ge 2 && "$2" =~ ^[0-9]+(\.[0-9]+)*([abrc]|post|dev|[0-9.])*([+][a-zA-Z0-9.]+)?$ ]] || {
                    printf 'Expected a package version after --version\n' >&2; return 2;
                }
                requirement="blocksd==$2"
                shift 2
                ;;
            --no-udev|--no-service|--no-enable) setup_args+=("$1"); shift ;;
            -h|--help)
                cat <<'HELP'
Usage: bash install.sh [--version VERSION] [--no-udev] [--no-service] [--no-enable]

Install or upgrade blocksd using uv and managed Python 3.13.
By default enable and restart the user service; Linux also installs udev rules (sudo).
  --version VERSION  Install a specific PyPI version (default: latest)
  --no-udev          Skip device permission rules (no sudo needed)
  --no-service       Skip all background service setup
  --no-enable        Write service without enabling or restarting (Linux reloads)
Run as your normal user. Requires Linux or macOS and curl for uv bootstrap.
Service setup requires a systemd user session on Linux or a GUI login on macOS.
Re-running upgrades the package and restarts the service.
HELP
                return 0
                ;;
            *) printf 'Unknown option: %s\n' "$1" >&2; return 2 ;;
        esac
    done

    case "$(uname -s)" in
        Linux|Darwin) ;;
        *) printf 'This installer supports Linux and macOS only\n' >&2; return 1 ;;
    esac
    [[ "$(id -u)" != 0 ]] || { printf 'Run as your normal user, without sudo\n' >&2; return 1; }
    uv_bin=$(command -v uv || true)
    if [[ -z "$uv_bin" ]]; then
        command -v curl >/dev/null || { printf 'Install curl first\n' >&2; return 1; }
        printf 'Installing uv...\n'
        bootstrap_uv
        uv_bin="$HOME/.local/bin/uv"
    fi

    printf 'Installing %s...\n' "$requirement"
    "$uv_bin" tool install --python 3.13 --managed-python --upgrade "$requirement"
    tool_bin=$("$uv_bin" tool dir --bin)
    [[ -x "$tool_bin/blocksd" ]] || { printf 'uv did not install an executable blocksd\n' >&2; return 1; }
    "$tool_bin/blocksd" install "${setup_args[@]}"
    printf 'Installed: %s/blocksd\n' "$tool_bin"
    case ":$PATH:" in
        *":$tool_bin:"*) ;;
        *) printf 'Add %s to PATH to run blocksd from your shell.\n' "$tool_bin" ;;
    esac
}

# Parse the whole script before executing commands that might consume stdin.
main "$@"
