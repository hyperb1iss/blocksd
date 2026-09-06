"""Release formula generation must use the built archive and runtime lock closure."""

import hashlib
import io
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def make_sdist(tmp_path: Path, *, dashboard: bool = True, lock_version: str = "0.6.0") -> Path:
    """Create a small archive with an unused dev package and a transitive dependency."""
    files = {
        "pyproject.toml": '[project]\nname = "blocksd"\nversion = "0.6.0"\n',
        "uv.lock": f'''
[[package]]
name = "blocksd"
version = "{lock_version}"
dependencies = [{{name = "runtime"}}]
[[package]]
name = "runtime"
version = "1.0.0"
dependencies = [{{name = "transitive"}}]
sdist = {{url = "https://files.pythonhosted.org/runtime-1.0.0.tar.gz", hash = "sha256:{"a" * 64}"}}
[[package]]
name = "transitive"
version = "2.0.0"
sdist = {{url = "https://files.pythonhosted.org/transitive-2.0.0.tar.gz", hash = "sha256:{"b" * 64}"}}
[[package]]
name = "unused-dev"
version = "3.0.0"
''',
    }
    if dashboard:
        files["src/blocksd/web/static/index.html"] = "<html>dashboard</html>"
    path = tmp_path / "blocksd-0.6.0.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        for name, text in files.items():
            data = text.encode()
            member = tarfile.TarInfo(f"blocksd-0.6.0/{name}")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
    return path


def generate(path: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository-owned generator
        [
            sys.executable,
            str(ROOT / "scripts/generate_homebrew.py"),
            str(path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def test_formula_uses_archive_version_checksum_and_runtime_closure(tmp_path: Path) -> None:
    path = make_sdist(tmp_path)
    output = tmp_path / "blocksd.rb"
    result = generate(path, output)
    assert result.returncode == 0, result.stderr
    formula = output.read_text()
    assert 'version "0.6.0"' in formula
    assert hashlib.sha256(path.read_bytes()).hexdigest() in formula
    assert 'resource "runtime"' in formula
    assert 'resource "transitive"' in formula
    assert "unused-dev" not in formula
    assert "@VERSION@" not in formula
    assert "@RESOURCES@" not in formula
    assert "virtualenv_install_with_resources" in formula


@pytest.mark.parametrize(("dashboard", "lock_version"), [(False, "0.6.0"), (True, "0.5.0")])
def test_invalid_sdist_does_not_publish_formula(
    tmp_path: Path, dashboard: bool, lock_version: str
) -> None:
    path = make_sdist(tmp_path, dashboard=dashboard, lock_version=lock_version)
    output = tmp_path / "blocksd.rb"
    assert generate(path, output).returncode != 0
    assert not output.exists()
