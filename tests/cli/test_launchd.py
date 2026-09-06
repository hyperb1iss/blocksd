"""LaunchAgent lifecycle checks with all launchctl calls intercepted."""

from __future__ import annotations

import plistlib
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from blocksd.cli import install, launchd
from blocksd.cli.app import app


@pytest.fixture
def agent_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mock:
    monkeypatch.setattr(install.sys, "platform", "darwin")
    monkeypatch.setattr(launchd.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(launchd.os, "getuid", lambda: 501)
    monkeypatch.setattr(install, "_find_blocksd_bin", lambda: '/opt/a & "b"/blocksd')
    monkeypatch.setattr(install, "_install_udev", Mock(side_effect=AssertionError))
    commands = Mock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(launchd.subprocess, "run", commands)
    return commands


def test_generated_plist_preserves_executable_and_log_paths(agent_env: Mock) -> None:
    result = CliRunner().invoke(app, ["install", "--no-enable"])
    assert result.exit_code == 0, result.output
    agent_env.assert_not_called()
    path = launchd._plist_path()
    data = plistlib.loads(path.read_bytes())
    assert data["Label"] == launchd.LABEL
    assert data["ProgramArguments"] == ['/opt/a & "b"/blocksd', "run", "--daemon"]
    assert data["RunAtLoad"] is True
    assert data["KeepAlive"] == {"SuccessfulExit": False}
    assert Path(data["StandardOutPath"]).parent.is_dir()
    assert data["StandardErrorPath"].endswith("/Library/Logs/blocksd/stderr.log")
    assert path.stat().st_mode & 0o777 == 0o644


def test_install_and_reinstall_load_current_definition(agent_env: Mock) -> None:
    target = f"gui/501/{launchd.LABEL}"
    agent_env.side_effect = [
        subprocess.CompletedProcess([], 113, "", "service missing"),
        *[subprocess.CompletedProcess([], 0, "", "")] * 5,
        subprocess.CompletedProcess([], 113, "", "service missing"),
        *[subprocess.CompletedProcess([], 0, "", "")] * 3,
    ]
    for _ in range(2):
        result = CliRunner().invoke(app, ["install"])
        assert result.exit_code == 0, result.output
    assert [call.args[0] for call in agent_env.call_args_list] == [
        ["launchctl", "print", target],
        ["launchctl", "enable", target],
        ["launchctl", "bootstrap", "gui/501", str(launchd._plist_path())],
        ["launchctl", "kickstart", target],
        ["launchctl", "print", target],
        ["launchctl", "bootout", target],
        ["launchctl", "print", target],
        ["launchctl", "enable", target],
        ["launchctl", "bootstrap", "gui/501", str(launchd._plist_path())],
        ["launchctl", "kickstart", target],
    ]


@pytest.mark.parametrize("failed_step", ["print", "bootout", "enable", "bootstrap", "kickstart"])
def test_install_reports_launchctl_errors(agent_env: Mock, failed_step: str) -> None:
    loaded = True

    def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        nonlocal loaded
        code = 5 if command[1] == failed_step else 0
        if code == 0 and command[1] == "print" and not loaded:
            code = 113
        if command[1] == "bootout":
            loaded = False
        return subprocess.CompletedProcess(command, code, "", "operation denied")

    agent_env.side_effect = run
    result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 1
    assert failed_step in result.output
    assert "operation denied" in result.output
    assert "Installation complete" not in result.output
    assert agent_env.call_args.args[0][1] == failed_step


def test_no_service_does_not_touch_host(agent_env: Mock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install, "_find_blocksd_bin", Mock(side_effect=AssertionError))
    result = CliRunner().invoke(app, ["install", "--no-service"])
    assert result.exit_code == 0, result.output
    agent_env.assert_not_called()
    assert not launchd._plist_path().exists()


def test_repeated_uninstall_preserves_logs(agent_env: Mock) -> None:
    assert CliRunner().invoke(app, ["install", "--no-enable"]).exit_code == 0
    agent_env.side_effect = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 113, "", "service missing"),
        subprocess.CompletedProcess([], 113, "", "service missing"),
    ]
    for _ in range(2):
        result = CliRunner().invoke(app, ["uninstall"])
        assert result.exit_code == 0, result.output
    assert not launchd._plist_path().exists()
    assert (Path.home() / "Library" / "Logs" / "blocksd").is_dir()
    assert [call.args[0][1] for call in agent_env.call_args_list] == [
        "print",
        "bootout",
        "print",
        "print",
    ]


def test_reinstall_waits_until_launchd_reaps_previous_service(
    agent_env: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    pause = Mock()
    monkeypatch.setattr(launchd.time, "sleep", pause)
    agent_env.side_effect = [
        *[subprocess.CompletedProcess([], 0, "", "")] * 4,
        subprocess.CompletedProcess([], 113, "", "service missing"),
        *[subprocess.CompletedProcess([], 0, "", "")] * 3,
    ]
    result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 0, result.output
    assert [call.args[0][1] for call in agent_env.call_args_list] == [
        "print",
        "bootout",
        "print",
        "print",
        "print",
        "enable",
        "bootstrap",
        "kickstart",
    ]
    assert pause.call_count == 2


@pytest.mark.parametrize("command", ["install", "uninstall"])
def test_unload_timeout_stops_mutations_and_keeps_plist(
    agent_env: Mock, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    assert CliRunner().invoke(app, ["install", "--no-enable"]).exit_code == 0
    monkeypatch.setattr(launchd.time, "monotonic", Mock(side_effect=[0, 36]))
    result = CliRunner().invoke(app, [command])
    assert result.exit_code == 1
    assert "Timed out waiting for launchd to unload" in result.output
    assert launchd._plist_path().exists()
    assert [call.args[0][1] for call in agent_env.call_args_list] == ["print", "bootout", "print"]


def test_uninstall_keeps_plist_when_unload_fails(agent_env: Mock) -> None:
    assert CliRunner().invoke(app, ["install", "--no-enable"]).exit_code == 0
    agent_env.side_effect = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 5, "", "permission denied"),
    ]
    result = CliRunner().invoke(app, ["uninstall"])
    assert result.exit_code == 1
    assert "permission denied" in result.output
    assert launchd._plist_path().exists()


@pytest.mark.parametrize("command", ["install", "uninstall"])
def test_unsupported_platform_fails_before_mutation(
    agent_env: Mock, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    monkeypatch.setattr(install.sys, "platform", "win32")
    result = CliRunner().invoke(app, [command])
    assert result.exit_code == 1
    assert "Linux and macOS only" in result.output
    agent_env.assert_not_called()


def test_launchagent_requires_absolute_executable() -> None:
    with pytest.raises(ValueError, match="must be absolute"):
        launchd._generate_plist("blocksd")
