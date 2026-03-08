"""Structured logging setup for blocksd."""

from __future__ import annotations

import logging
import sys


def setup_logging(*, verbose: bool = False) -> None:
    """Configure logging for the daemon."""
    level = logging.DEBUG if verbose else logging.INFO

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    root = logging.getLogger("blocksd")
    root.setLevel(level)
    root.addHandler(handler)

    # Quiet noisy libraries
    logging.getLogger("rtmidi").setLevel(logging.WARNING)
