"""Platform defaults and isolation of the macOS local socket."""

# Expected socket addresses, never used as test write targets.
# ruff: noqa: S108

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from blocksd import paths
from blocksd.api import server
from blocksd.config.loader import load_config
from blocksd.topology.manager import TopologyManager


def test_macos_config_prefers_native_then_legacy(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    native, legacy, system = paths.config_paths()
    assert native == tmp_path / "Library/Application Support/blocksd/config.toml"
    assert legacy == tmp_path / ".config/blocksd/config.toml"
    assert system == Path("/etc/blocksd/config.toml")
    legacy.parent.mkdir(parents=True)
    legacy.write_text("[daemon]\nweb_port = 9011\n")
    assert load_config().web_port == 9011
    native.parent.mkdir(parents=True)
    native.write_text("[daemon]\nweb_port = 9012\n")
    assert load_config().web_port == 9012
    assert load_config(legacy).web_port == 9011


def test_linux_paths_are_unchanged(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.setattr(paths.Path, "home", lambda: tmp_path)
    assert paths.config_paths() == [
        tmp_path / ".config/blocksd/config.toml",
        Path("/etc/blocksd/config.toml"),
    ]
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    assert paths.default_socket_path() == tmp_path / "blocksd/blocksd.sock"
    monkeypatch.delenv("XDG_RUNTIME_DIR")
    assert paths.default_socket_path() == Path("/tmp/blocksd/blocksd.sock")


def test_macos_socket_is_short_and_user_specific(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    monkeypatch.setattr(paths.os, "getuid", lambda: 501)
    monkeypatch.setenv("TMPDIR", "/very/long/" * 30)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/other/runtime")
    assert paths.default_socket_path() == Path("/tmp/blocksd-501/blocksd.sock")
    monkeypatch.setattr(paths.os, "getuid", lambda: 502)
    assert paths.default_socket_path() == Path("/tmp/blocksd-502/blocksd.sock")


@pytest.mark.parametrize("unsafe", ["symlink", "shared", "foreign"])
async def test_macos_rejects_unsafe_default_socket_directory(monkeypatch, tmp_path, unsafe):
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    directory = tmp_path / "runtime"
    directory.mkdir(mode=0o700)
    if unsafe == "symlink":
        link = tmp_path / "link"
        link.symlink_to(directory, target_is_directory=True)
        directory = link
    elif unsafe == "shared":
        directory.chmod(0o755)
    else:
        monkeypatch.setattr(paths.os, "getuid", lambda: directory.stat().st_uid + 1)
    monkeypatch.setattr(server, "default_socket_path", lambda: directory / "api.sock")
    api = server.ApiServer(TopologyManager())
    with pytest.raises(PermissionError, match="private and owned"):
        await api.start()
    assert not (directory / "api.sock").exists()


async def test_macos_private_runtime_is_created(monkeypatch, tmp_path):
    monkeypatch.setattr(paths.sys, "platform", "darwin")
    directory = tmp_path / "runtime"
    monkeypatch.setattr(server, "default_socket_path", lambda: directory / "api.sock")
    # Stop before binding: the long pytest temp path is not a valid socket address.
    bind = Mock(side_effect=RuntimeError("reached bind"))
    monkeypatch.setattr(server.asyncio, "start_unix_server", bind)
    api = server.ApiServer(TopologyManager())
    with pytest.raises(RuntimeError, match="reached bind"):
        await api.start()
    assert directory.stat().st_mode & 0o777 == 0o700
    assert directory.stat().st_uid == os.getuid()
