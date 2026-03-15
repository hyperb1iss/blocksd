"""Web UI — static file resolution for the bundled SPA."""

from __future__ import annotations

from pathlib import Path


def resolve_static_dir() -> Path:
    """Locate the Vite build output directory.

    Returns the ``static/`` directory next to this file — works both for installed
    packages (hatch wheel) and development (``uv run``).
    """
    return Path(__file__).parent / "static"
