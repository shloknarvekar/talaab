"""Build the Strands Agents Lambda layer (python3.12, arm64) without Docker -> .build/strands-layer.zip

    pip install uv          # once (the repo .venv already has it)
    python backend/scripts/build_layer.py [--reuse]

uv resolves dependencies for the Linux target (plain pip on Windows applies Windows-only
markers such as pywin32) and installs prebuilt aarch64 wheels; nothing is compiled or run.
Packages are installed into the system temp dir (fast, not synced by OneDrive) and zipped
into one file with forward-slash paths, which is what Lambda's Linux unzip expects.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQS = ROOT / "backend" / "agent" / "requirements.txt"
OUT = ROOT / ".build" / "strands-layer.zip"
STAGE = Path(tempfile.gettempdir()) / "talaab-strands-layer"
SKIP_DIRS = {"__pycache__", "tests"}


def find_uv() -> str:
    for c in (ROOT / ".venv" / "Scripts" / "uv.exe", ROOT / ".venv" / "bin" / "uv"):
        if c.exists():
            return str(c)
    return shutil.which("uv") or sys.exit("uv not found: pip install uv")


def install() -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    subprocess.run(
        [find_uv(), "pip", "install", "-r", str(REQS),
         "--python-platform", "aarch64-manylinux2014", "--python-version", "3.12",
         "--only-binary", ":all:", "--link-mode", "copy", "--target", str(STAGE / "python")],
        check=True,
    )


def zip_layer() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dirpath, dirnames, filenames in os.walk(STAGE):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                path = Path(dirpath) / name
                z.write(path, path.relative_to(STAGE).as_posix())
                count += 1
    print(f"{OUT} : {count} files, {OUT.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reuse", action="store_true", help="skip install, zip the existing staged packages")
    args = ap.parse_args()
    if not (args.reuse and (STAGE / "python").exists()):
        install()
    zip_layer()
