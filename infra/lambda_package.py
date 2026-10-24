"""Build a Python 3.12 Linux Lambda asset with runtime dependencies."""

from __future__ import annotations

import hashlib
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


def prepare_lambda_package(project_root: Path) -> Path:
    """Install runtime wheels for Lambda and copy the ChainMind application package."""

    requirements = project_root / "infra" / "lambda-requirements.txt"
    source_package = project_root / "src" / "chainmind"
    destination = project_root / "infra" / ".lambda-package"
    marker = destination / ".package-hash"
    digest = hashlib.sha256(
        requirements.read_bytes()
        + b"\0"
        + b"".join(
            path.relative_to(source_package).as_posix().encode() + b"\0" + path.read_bytes()
            for path in sorted(source_package.rglob("*"))
            if path.is_file() and path.suffix in {".py", ".json"}
        )
    ).hexdigest()
    if marker.is_file() and marker.read_text(encoding="ascii") == digest:
        return destination

    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    if importlib.util.find_spec("pip") is None:
        subprocess.run(
            [sys.executable, "-m", "ensurepip", "--upgrade"],
            check=True,
        )
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--platform",
            "manylinux2014_x86_64",
            "--implementation",
            "cp",
            "--python-version",
            "3.12",
            "--abi",
            "cp312",
            "--target",
            str(destination),
            "--requirement",
            str(requirements),
        ],
        check=True,
    )
    shutil.copytree(
        source_package,
        destination / "chainmind",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    marker.write_text(digest, encoding="ascii")
    return destination
