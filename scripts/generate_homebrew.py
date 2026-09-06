"""Generate a release formula from the built sdist and locked runtime dependencies."""

import argparse
import hashlib
import re
import tarfile
import tomllib
from pathlib import Path
from typing import TypedDict


class Dependency(TypedDict):
    """Dependency identity from the uv lockfile."""

    name: str


class SourceArchive(TypedDict):
    """A checksummed source archive from the lockfile."""

    url: str
    hash: str


class Package(TypedDict):
    """Fields consumed from a locked package."""

    name: str
    version: str
    dependencies: list[Dependency]
    sdist: SourceArchive


def runtime_resources(packages: list[Package]) -> str:
    """Include the runtime closure, rejecting ambiguous package versions."""
    by_name = {package["name"]: package for package in packages}
    if len(by_name) != len(packages):
        raise ValueError("Multiple versions of a package require explicit platform resolution")
    pending = [dep["name"] for dep in by_name["blocksd"].get("dependencies", [])]
    selected: set[str] = set()
    while pending:
        name = pending.pop()
        if name in selected:
            continue
        selected.add(name)
        pending.extend(dep["name"] for dep in by_name[name].get("dependencies", []))

    resources = []
    for name in sorted(selected):
        source = by_name[name]["sdist"]
        url, checksum = source["url"], source["hash"]
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name):
            raise ValueError(f"Unsafe package name: {name}")
        if not re.fullmatch(r"https://files\.pythonhosted\.org/[A-Za-z0-9/_.+-]+", url):
            raise ValueError(f"Unsafe source URL for {name}")
        if not re.fullmatch(r"sha256:[a-f0-9]{64}", checksum):
            raise ValueError(f"Invalid source checksum for {name}")
        resources.append(
            f'  resource "{name}" do\n'
            f'    url "{url}"\n'
            f'    sha256 "{checksum.removeprefix("sha256:")}"\n'
            "  end"
        )
    return "\n\n".join(resources)


def generate_formula(sdist: Path, template: Path) -> str:
    """Use the archive's own metadata and lockfile, never the checkout's version."""
    with tarfile.open(sdist) as archive:
        roots = {member.name.split("/")[0] for member in archive.getmembers()}
        if len(roots) != 1:
            raise ValueError("Expected one source archive root")
        root = roots.pop()

        def read_member(name: str) -> bytes:
            member = archive.getmember(f"{root}/{name}")
            if not member.isfile():
                raise ValueError(f"Expected regular archive member: {name}")
            contents = archive.extractfile(member)
            if contents is None:
                raise ValueError(f"Missing archive member: {name}")
            return contents.read()

        project = tomllib.loads(read_member("pyproject.toml").decode())["project"]
        lock = tomllib.loads(read_member("uv.lock").decode())
        read_member("src/blocksd/web/static/index.html")

    version = project["version"]
    if project["name"] != "blocksd" or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a stable blocksd release")
    if sdist.name != f"blocksd-{version}.tar.gz":
        raise ValueError("Archive filename does not match its package version")
    locked = [package for package in lock["package"] if package["name"] == "blocksd"]
    if len(locked) != 1 or locked[0]["version"] != version:
        raise ValueError("Archive lockfile does not match its package version")
    return (
        template.read_text()
        .replace("@VERSION@", version)
        .replace("@SHA256@", hashlib.sha256(sdist.read_bytes()).hexdigest())
        .replace("@RESOURCES@", runtime_resources(lock["package"]))
    )


def main() -> None:
    """Write the formula next to the release distributions."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sdist", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--local", action="store_true", help="Use the local archive URL for build verification"
    )
    args = parser.parse_args()
    template = Path(__file__).resolve().parents[1] / "packaging/homebrew/blocksd.rb.in"
    formula = generate_formula(args.sdist, template)
    if args.local:
        formula = re.sub(
            r'^  url "https://github.com/hyperb1iss/blocksd/releases/[^"\n]+"$',
            f'  url "{args.sdist.resolve().as_uri()}"',
            formula,
            count=1,
            flags=re.MULTILINE,
        )
    args.output.write_text(formula)


if __name__ == "__main__":
    main()
