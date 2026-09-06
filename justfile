# blocksd development commands

default:
    @just --list

# Install all three projects from their lockfiles
install: install-python install-web install-docs

install-python:
    uv sync --locked

install-web:
    pnpm --dir web install --frozen-lockfile

install-docs:
    pnpm --dir docs install --frozen-lockfile

run *ARGS:
    uv run --locked blocksd {{ ARGS }}

test *ARGS:
    uv run --locked pytest {{ ARGS }}

test-v *ARGS:
    uv run --locked pytest -v {{ ARGS }}

test-mod MODULE *ARGS:
    uv run --locked pytest tests/{{ MODULE }} {{ ARGS }}

lint:
    uv run --locked ruff check src tests scripts

lint-fix:
    uv run --locked ruff check --fix src tests scripts

fmt:
    uv run --locked ruff format src tests scripts

fmt-docs:
    pnpm --dir docs exec prettier --write "**/*.md" ../README.md ../CONTRIBUTING.md "../.github/**/*.yml"

fmt-check:
    uv run --locked ruff format --check src tests scripts

typecheck:
    uv run --locked ty check src tests scripts

check-python: lint fmt-check typecheck test

# Same Python, dashboard, docs and installed-package gates as CI
check: check-python lint-web docs-build build-check

fix: lint-fix fmt

web-dev:
    pnpm --dir web dev

lint-web:
    pnpm --dir web check

check-web: lint-web web-build

web-build:
    pnpm --dir web build

docs-dev:
    pnpm --dir docs dev

docs-build:
    pnpm --dir docs lint
    pnpm --dir docs build

# Include the dashboard in the wheel and source distribution
build: web-build
    uv lock --check
    uv build --clear

# Use an isolated environment to prove the wheel works without the checkout
build-check: build
    uv run --no-project --with dist/*.whl python scripts/check_distribution.py

# Clean Python artifacts; JavaScript build commands replace their own output
clean:
    rm -rf dist build .pytest_cache .ruff_cache
    find src tests scripts -type d -name __pycache__ -exec rm -rf {} +

install-service:
    sudo cp systemd/blocksd.service /etc/systemd/system/
    sudo cp systemd/99-roli-blocks.rules /etc/udev/rules.d/
    sudo systemctl daemon-reload
    sudo udevadm control --reload-rules
    @echo "Service installed. Enable with: sudo systemctl enable --now blocksd"

aur-build:
    cd packaging/aur/blocksd && makepkg -si

deps:
    uv tree --locked
