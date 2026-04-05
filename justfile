# blocksd — ROLI Blocks Linux Daemon

# Default: show available recipes
default:
    @just --list

# Install all dependencies (including dev)
install:
    uv sync

# Run the daemon
run *ARGS:
    uv run blocksd {{ ARGS }}

# Run the full test suite
test *ARGS:
    uv run pytest {{ ARGS }}

# Run tests with verbose output
test-v *ARGS:
    uv run pytest -v {{ ARGS }}

# Run a specific test module (e.g., just test-mod protocol)
test-mod MODULE *ARGS:
    uv run pytest tests/{{ MODULE }} {{ ARGS }}

# Lint with ruff
lint:
    uv run ruff check src tests

# Auto-fix lint issues
lint-fix:
    uv run ruff check --fix src tests

# Format code
fmt:
    uv run ruff format src tests

# Check formatting without changes
fmt-check:
    uv run ruff format --check src tests

# Type check with ty
typecheck:
    uv run ty check src

# Run all checks (lint + format check + typecheck + tests)
check: lint fmt-check typecheck test

# Fix everything auto-fixable (lint + format)
fix: lint-fix fmt

# Clean build artifacts and caches
clean:
    rm -rf dist build .pytest_cache .ruff_cache
    find src tests -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Build the package
build:
    uv build

# Install systemd service (requires sudo)
install-service:
    sudo cp systemd/blocksd.service /etc/systemd/system/
    sudo cp systemd/99-roli-blocks.rules /etc/udev/rules.d/
    sudo systemctl daemon-reload
    sudo udevadm control --reload-rules
    @echo "Service installed. Enable with: sudo systemctl enable --now blocksd"

# Show dependency tree
deps:
    uv tree
