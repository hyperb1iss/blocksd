#!/usr/bin/env bash
# blocksd installer — installs via uv/pipx and sets up systemd + udev
set -euo pipefail

ELECTRIC_PURPLE='\033[38;2;225;53;255m'
NEON_CYAN='\033[38;2;128;255;234m'
SUCCESS_GREEN='\033[38;2;80;250;123m'
ERROR_RED='\033[38;2;255;99;99m'
ELECTRIC_YELLOW='\033[38;2;241;250;140m'
BOLD='\033[1m'
RESET='\033[0m'

info()  { printf "${NEON_CYAN}${BOLD}>>>${RESET} %s\n" "$*"; }
ok()    { printf "${SUCCESS_GREEN}${BOLD} ✓${RESET} %s\n" "$*"; }
warn()  { printf "${ELECTRIC_YELLOW}${BOLD} !${RESET} %s\n" "$*"; }
fail()  { printf "${ERROR_RED}${BOLD} ✗${RESET} %s\n" "$*" >&2; exit 1; }

printf "\n${ELECTRIC_PURPLE}${BOLD}"
printf "  ┌──────────────────────────────────┐\n"
printf "  │         🔌 blocksd               │\n"
printf "  │   ROLI Blocks Linux Daemon       │\n"
printf "  └──────────────────────────────────┘\n"
printf "${RESET}\n"

# ─── Install blocksd ──────────────────────────────────────────────
info "Installing blocksd..."

if command -v uv &>/dev/null; then
    uv tool install blocksd
    ok "Installed via uv"
elif command -v pipx &>/dev/null; then
    pipx install blocksd
    ok "Installed via pipx"
elif command -v pip &>/dev/null; then
    pip install --user blocksd
    ok "Installed via pip"
else
    fail "No Python package manager found. Install uv: https://docs.astral.sh/uv/"
fi

# ─── Verify ───────────────────────────────────────────────────────
if ! command -v blocksd &>/dev/null; then
    warn "blocksd not found on PATH — you may need to add ~/.local/bin to your PATH"
    warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

# ─── udev rules ──────────────────────────────────────────────────
info "Installing udev rules for ROLI devices..."

UDEV_RULE='# ROLI Blocks devices (VID 0x2AF4)
SUBSYSTEM=="usb", ATTR{idVendor}=="2af4", MODE="0666", TAG+="uaccess"
SUBSYSTEM=="sound", ATTR{idVendor}=="2af4", MODE="0666", TAG+="uaccess"'

UDEV_PATH="/etc/udev/rules.d/99-roli-blocks.rules"

if [[ -f "$UDEV_PATH" ]]; then
    warn "udev rules already exist at $UDEV_PATH — skipping"
else
    echo "$UDEV_RULE" | sudo tee "$UDEV_PATH" >/dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    ok "udev rules installed"
fi

# ─── systemd user service ────────────────────────────────────────
info "Installing systemd user service..."

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_PATH="$SERVICE_DIR/blocksd.service"
mkdir -p "$SERVICE_DIR"

BLOCKSD_BIN=$(command -v blocksd 2>/dev/null || echo "$HOME/.local/bin/blocksd")

cat > "$SERVICE_PATH" <<EOF
[Unit]
Description=blocksd — ROLI Blocks Linux Daemon
Documentation=https://github.com/hyperb1iss/blocksd
After=sound.target

[Service]
Type=notify
ExecStart=$BLOCKSD_BIN run --daemon
Restart=on-failure
RestartSec=5
WatchdogSec=30

# Security hardening
ProtectSystem=strict
PrivateTmp=true
NoNewPrivileges=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
ok "systemd service installed"

# ─── Enable? ─────────────────────────────────────────────────────
printf "\n"
read -rp "$(printf "${NEON_CYAN}${BOLD}>>>${RESET} Enable and start blocksd now? [Y/n] ")" ENABLE
ENABLE="${ENABLE:-Y}"

if [[ "$ENABLE" =~ ^[Yy]$ ]]; then
    systemctl --user enable --now blocksd
    ok "blocksd is running"
    printf "\n"
    info "Check status:  systemctl --user status blocksd"
    info "View logs:     journalctl --user -u blocksd -f"
else
    ok "Service installed but not started"
    printf "\n"
    info "Start later:   systemctl --user enable --now blocksd"
fi

printf "\n${SUCCESS_GREEN}${BOLD} ✓ Installation complete${RESET}\n\n"
