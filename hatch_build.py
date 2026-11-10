"""Bundle the standalone LittleFoot compiler in each platform wheel."""

from __future__ import annotations

import os
import shutil
import subprocess
import sysconfig
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def dependencies(self) -> list[str]:
        if self.target_name == "wheel" and shutil.which("cmake") is None:
            return ["cmake>=3.24"]
        return []

    def initialize(self, _version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != "wheel":
            return
        cmake = shutil.which("cmake")
        if cmake is None:
            raise RuntimeError("CMake is required to build the LittleFoot compiler")
        root = Path(self.root)
        build = root / "build" / "littlefoot"
        destination = root / "src" / "blocksd" / "littlefoot" / "_native"
        configure = [
            cmake,
            "-S",
            str(root / "native" / "littlefoot"),
            "-B",
            str(build),
            "-DCMAKE_BUILD_TYPE=Release",
            f"-DCMAKE_INSTALL_PREFIX={destination}",
        ]
        if deployment_target := os.environ.get("MACOSX_DEPLOYMENT_TARGET"):
            configure.append(f"-DCMAKE_OSX_DEPLOYMENT_TARGET={deployment_target}")
        subprocess.run(configure, check=True)  # noqa: S603 - project-owned build inputs
        subprocess.run(  # noqa: S603 - fixed build commands with project-owned paths
            [cmake, "--build", str(build), "--config", "Release", "--parallel"], check=True
        )
        subprocess.run(  # noqa: S603 - fixed build commands with project-owned paths
            [cmake, "--install", str(build), "--config", "Release"], check=True
        )
        name = "blocksd-littlefoot.exe" if os.name == "nt" else "blocksd-littlefoot"
        build_data["force_include"][str(destination / name)] = f"blocksd/littlefoot/_native/{name}"
        for asset in ("vendor.tar.gz", "README.md"):
            build_data["force_include"][str(root / "native" / "littlefoot" / asset)] = (
                f"blocksd/littlefoot/_native/{asset}"
            )
        build_data["pure_python"] = False
        platform = sysconfig.get_platform().replace("-", "_").replace(".", "_")
        build_data["tag"] = f"py3-none-{platform}"
