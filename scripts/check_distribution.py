"""Check an installed wheel's CLI and bundled dashboard without MIDI hardware."""

import re
import subprocess
import sys
from pathlib import Path

import blocksd
from blocksd.littlefoot.compiler import compile_source
from blocksd.web import resolve_static_dir


def main() -> None:
    """Fail when packaging loses the CLI, type marker, or dashboard assets."""
    package_dir = Path(blocksd.__file__).resolve().parent
    checkout_src = Path(__file__).resolve().parents[1] / "src"
    if package_dir.is_relative_to(checkout_src):
        raise RuntimeError("Distribution check imported the checkout instead of an installed wheel")
    if not (package_dir / "py.typed").is_file():
        raise RuntimeError("Installed package is missing py.typed")
    static_dir = resolve_static_dir()
    index = (static_dir / "index.html").read_text()
    assets = re.findall(r'(?:src|href)="(/assets/[^"?#]+)', index)
    if not assets:
        raise RuntimeError("Dashboard index has no bundled asset references")
    for asset in assets:
        if not (static_dir / asset.lstrip("/")).is_file():
            raise RuntimeError(f"Dashboard asset is missing: {asset}")
    compiled = compile_source("void repaint() { fillPixel(0xff00ff00, 0, 0); }")
    if len(compiled) <= 10:
        raise RuntimeError("Bundled LittleFoot compiler returned an invalid program")
    subprocess.run([sys.executable, "-m", "blocksd", "--help"], check=True)


if __name__ == "__main__":
    main()
