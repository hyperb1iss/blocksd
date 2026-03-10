"""Tests for sd_notify module."""

from __future__ import annotations

import os
from unittest.mock import patch

from blocksd import sdnotify


class TestSdnotifyNoSocket:
    """Without NOTIFY_SOCKET set, all operations are no-ops."""

    def setup_method(self):
        # Reset module state
        sdnotify._socket = None
        sdnotify._address = None

    def test_ready_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert sdnotify.ready() is False

    def test_stopping_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert sdnotify.stopping() is False

    def test_watchdog_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert sdnotify.watchdog() is False

    def test_status_returns_false(self):
        with patch.dict(os.environ, {}, clear=True):
            assert sdnotify.status("test") is False


class TestWatchdogUsec:
    def test_returns_none_without_env(self):
        with patch.dict(os.environ, {}, clear=True):
            assert sdnotify.watchdog_usec() is None

    def test_returns_value(self):
        with patch.dict(os.environ, {"WATCHDOG_USEC": "30000000"}):
            assert sdnotify.watchdog_usec() == 30_000_000

    def test_returns_none_on_invalid(self):
        with patch.dict(os.environ, {"WATCHDOG_USEC": "not_a_number"}):
            assert sdnotify.watchdog_usec() is None
