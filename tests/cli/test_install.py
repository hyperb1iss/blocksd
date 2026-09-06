"""Installer behavior without touching host service or device configuration."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from typer.testing import CliRunner

from blocksd.cli import install
from blocksd.cli.app import app


@pytest.fixture(autouse=True)
def linux_platform(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install.sys, "platform", "linux")


@pytest.fixture
def setup_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Mock:
    monkeypatch.setattr(install, "_SERVICE_DIR", tmp_path)
    monkeypatch.setattr(install, "_SERVICE_PATH", tmp_path / "blocksd.service")
    monkeypatch.setattr(install, "_find_blocksd_bin", lambda: "/opt/my tools/blocksd")
    commands = Mock(return_value=subprocess.CompletedProcess([], 0))
    monkeypatch.setattr(install.subprocess, "run", commands)
    return commands


def test_service_starts_and_restarts_on_repeated_install(setup_commands: Mock) -> None:
    for _ in range(2):
        result = CliRunner().invoke(app, ["install", "--no-udev"])
        assert result.exit_code == 0, result.output
    commands = [call.args[0] for call in setup_commands.call_args_list]
    assert (
        commands
        == [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "blocksd"],
            ["systemctl", "--user", "restart", "blocksd"],
        ]
        * 2
    )
    assert 'ExecStart="/opt/my tools/blocksd" run --daemon' in install._SERVICE_PATH.read_text()


def test_no_enable_does_not_restart_or_enable(setup_commands: Mock) -> None:
    result = CliRunner().invoke(app, ["install", "--no-udev", "--no-enable"])
    assert result.exit_code == 0, result.output
    setup_commands.assert_called_once_with(["systemctl", "--user", "daemon-reload"], check=True)


def test_no_service_skips_executable_lookup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(install, "_find_blocksd_bin", Mock(side_effect=AssertionError))
    result = CliRunner().invoke(app, ["install", "--no-udev", "--no-service"])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("failed_step", ["daemon-reload", "enable", "restart"])
def test_service_errors_fail_install(setup_commands: Mock, failed_step: str) -> None:
    def run(command: list[str], *, check: bool) -> subprocess.CompletedProcess:
        if failed_step in command:
            raise subprocess.CalledProcessError(1, command)
        return subprocess.CompletedProcess(command, 0)

    setup_commands.side_effect = run
    result = CliRunner().invoke(app, ["install", "--no-udev"])
    assert result.exit_code == 1
    assert "Command failed" in result.output
    assert "Installation failed" not in result.output
    assert "Installation complete" not in result.output


def test_failed_udev_copy_cleans_temp_file(setup_commands: Mock) -> None:
    setup_commands.side_effect = subprocess.CalledProcessError(1, ["sudo", "install"])
    result = CliRunner().invoke(app, ["install", "--no-service"])
    assert result.exit_code == 1
    assert "Installation complete" not in result.output
    command = setup_commands.call_args.args[0]
    assert command[:4] == ["sudo", "install", "-m", "0644"]
    assert not Path(command[4]).exists()


def test_missing_binary_fails_before_udev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        install, "_find_blocksd_bin", Mock(side_effect=FileNotFoundError("missing"))
    )
    udev = Mock()
    monkeypatch.setattr(install, "_install_udev", udev)
    result = CliRunner().invoke(app, ["install"])
    assert result.exit_code == 1
    udev.assert_not_called()


def test_find_binary_prefers_invoked_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    binary = tmp_path / "blocksd"
    binary.write_text("#!/bin/sh\n")
    binary.chmod(0o755)
    monkeypatch.setattr(install.sys, "argv", [str(binary)])
    monkeypatch.setattr(install.shutil, "which", lambda _: "/other/blocksd")
    assert install._find_blocksd_bin() == str(binary)


def test_find_binary_never_returns_nonexistent_guess(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(install.sys, "argv", ["pytest"])
    monkeypatch.setattr(install.shutil, "which", lambda _: None)
    monkeypatch.setattr(install.Path, "home", lambda: tmp_path)
    with pytest.raises(FileNotFoundError):
        install._find_blocksd_bin()


def test_service_escapes_specifiers_but_preserves_literal_dollar() -> None:
    content = install._generate_service("/opt/a %h $HOME/blocksd")
    assert 'ExecStart="/opt/a %%h $HOME/blocksd" run --daemon' in content


@pytest.mark.parametrize("path", ['/opt/a"b/blocksd', "/opt/a\\b/blocksd", "/opt/a\nb/blocksd"])
def test_service_rejects_unsupported_executable_paths(path: str) -> None:
    with pytest.raises(ValueError, match="systemd cannot use"):
        install._generate_service(path)


@pytest.fixture
def shell_env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    tool_dir = tmp_path / "tool bin"
    tool_dir.mkdir()
    scripts = {
        "id": "printf '1000\\n'",
        "uname": "printf 'Linux\\n'",
        "uv": (
            'printf "uv:%s\\n" "$*" >> "$INSTALL_LOG"\n'
            'if [ "$*" = "tool dir --bin" ]; then printf "%s\\n" "$TOOL_BIN"; fi\n'
            'if [ "${UV_FAIL:-0}" = 1 ]; then exit 8; fi'
        ),
    }
    for name, source in scripts.items():
        binary = bin_dir / name
        binary.write_text("#!/bin/sh\n" + source + "\n")
        binary.chmod(0o755)
    binary = tool_dir / "blocksd"
    binary.write_text(
        '#!/bin/sh\nprintf "blocksd:%s\\n" "$*" >> "$INSTALL_LOG"\nexit "${SETUP_EXIT:-0}"\n'
    )
    binary.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "HOME": str(tmp_path),
        "INSTALL_LOG": str(tmp_path / "commands"),
        "TOOL_BIN": str(tool_dir),
    }


def run_installer(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    # stdin simulates curl | bash; setup must never read script content as a prompt.
    return subprocess.run(  # noqa: S603
        ["/bin/bash", "-s", "--", *args],
        input=Path("install.sh").read_text(),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_piped_installer_upgrades_and_forwards_options(shell_env: dict[str, str]) -> None:
    result = run_installer(shell_env, "--version", "0.5.0", "--no-udev", "--no-enable")
    assert result.returncode == 0, result.stderr
    commands = Path(shell_env["INSTALL_LOG"]).read_text().splitlines()
    assert commands == [
        "uv:tool install --python 3.13 --managed-python --upgrade blocksd==0.5.0",
        "uv:tool dir --bin",
        "blocksd:install --no-udev --no-enable",
    ]
    assert "Installed:" in result.stdout


@pytest.mark.parametrize("env_change", [{"UV_FAIL": "1"}, {"SETUP_EXIT": "9"}])
def test_shell_failures_are_not_reported_as_success(
    shell_env: dict[str, str], env_change: dict[str, str]
) -> None:
    result = run_installer({**shell_env, **env_change}, "--no-udev", "--no-service")
    assert result.returncode != 0
    assert "Installed:" not in result.stdout


@pytest.mark.parametrize("args", [("--version",), ("--version", "--evil"), ("--bogus",)])
def test_shell_rejects_bad_options_before_install(
    shell_env: dict[str, str], args: tuple[str, ...]
) -> None:
    result = run_installer(shell_env, *args)
    assert result.returncode == 2
    assert not Path(shell_env["INSTALL_LOG"]).exists()


@pytest.fixture
def bootstrap_env(shell_env: dict[str, str]) -> dict[str, str]:
    bin_dir = Path(shell_env["HOME"]) / "bin"
    uv_source = (bin_dir / "uv").read_text()
    (bin_dir / "uv").unlink()
    for command in ("sh", "mktemp", "rm", "mkdir", "cp", "chmod"):
        executable = shutil.which(command)
        assert executable is not None
        (bin_dir / command).symlink_to(executable)
    source = bin_dir / "uv-source"
    source.write_text(uv_source)
    source.chmod(0o755)
    bootstrap = bin_dir / "bootstrap"
    bootstrap.write_text(
        '#!/bin/sh\nmkdir -p "$UV_UNMANAGED_INSTALL"\n'
        'cp "$HOME/bin/uv-source" "$UV_UNMANAGED_INSTALL/uv"\n'
    )
    curl = bin_dir / "curl"
    curl.write_text('#!/bin/sh\nfor last; do :; done\ncp "$HOME/bin/bootstrap" "$last"\n')
    curl.chmod(0o755)
    temp_dir = Path(shell_env["HOME"]) / "bootstrap temp"
    temp_dir.mkdir()
    return {**shell_env, "PATH": str(bin_dir), "TMPDIR": str(temp_dir)}


def test_bootstrap_without_uv_is_noninteractive(bootstrap_env: dict[str, str]) -> None:
    result = run_installer(bootstrap_env, "--no-udev", "--no-service")
    assert result.returncode == 0, result.stderr
    assert "Installing uv" in result.stdout
    assert (Path(bootstrap_env["HOME"]) / ".local/bin/uv").is_file()
    assert (
        "blocksd:install --no-udev --no-service" in Path(bootstrap_env["INSTALL_LOG"]).read_text()
    )
    assert not list(Path(bootstrap_env["TMPDIR"]).iterdir())


def test_bootstrap_supports_macos(bootstrap_env: dict[str, str]) -> None:
    (Path(bootstrap_env["HOME"]) / "bin" / "uname").write_text("#!/bin/sh\nprintf 'Darwin\\n'\n")
    result = run_installer(bootstrap_env, "--no-enable")
    assert result.returncode == 0, result.stderr
    assert "blocksd:install --no-enable" in Path(bootstrap_env["INSTALL_LOG"]).read_text()


def test_shell_rejects_unsupported_platform(shell_env: dict[str, str]) -> None:
    (Path(shell_env["HOME"]) / "bin" / "uname").write_text("#!/bin/sh\nprintf 'FreeBSD\\n'\n")
    result = run_installer(shell_env)
    assert result.returncode == 1
    assert "Linux and macOS only" in result.stderr
    assert not Path(shell_env["INSTALL_LOG"]).exists()


@pytest.mark.parametrize("failed_command", ["curl", "bootstrap"])
def test_bootstrap_failure_preserves_status_and_cleans_download(
    bootstrap_env: dict[str, str], failed_command: str
) -> None:
    command = Path(bootstrap_env["HOME"]) / "bin" / failed_command
    command.write_text("#!/bin/sh\nprintf 'bootstrap failure\\n' >&2\nexit 17\n")
    result = run_installer(bootstrap_env, "--no-udev", "--no-service")
    assert result.returncode == 17
    assert "bootstrap failure" in result.stderr
    assert "unbound variable" not in result.stderr
    assert "Installed:" not in result.stdout
    assert not Path(bootstrap_env["INSTALL_LOG"]).exists()
    assert not list(Path(bootstrap_env["TMPDIR"]).iterdir())
