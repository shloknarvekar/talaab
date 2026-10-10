"""Build the Strands Agents Lambda layer (python3.12, arm64) without Docker -> .build/strands-layer.zip

    pip install uv          # once (the repo .venv already has it)
    python backend/scripts/build_layer.py [--name strands-layer|pipeline-layer] [--reuse]

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
LAYERS = {  # name -> (requirements file, wheel platform; Lambda python3.12 = Amazon Linux 2023, glibc 2.34)
    "strands-layer": (ROOT / "backend" / "agent" / "requirements.txt", "aarch64-manylinux2014"),
    "pipeline-layer": (ROOT / "backend" / "pipeline_lambda" / "requirements.txt", "aarch64-manylinux_2_28"),  # rasterio ships 2_28 wheels
    "llm-layer": (ROOT / "backend" / "agent" / "llm-requirements.txt", "x86_64-manylinux2014"),  # llama.cpp: the x86 wheel has AVX2, the arm one is generic (4x slower)
}
SKIP_DIRS = {"__pycache__", "tests"}
# Lambda allows 250 MiB unzipped for function + layers. The pipeline only uses scipy.ndimage (and the
# linalg/special it imports), so unused scipy subpackages and numpy's build tooling are dropped.
PRUNE = {
    "pipeline-layer": [f"scipy/{x}" for x in ("optimize", "stats", "sparse", "spatial", "io", "signal", "interpolate",
                                              "fft", "integrate", "cluster", "fftpack", "odr", "constants", "differentiate")]
                      + ["numpy/_core/include", "numpy/_pyinstaller"],  # keep numpy.typing/f2py: scipy.ndimage loads them
    # llama_cpp loads its libraries from llama_cpp/lib; the wheel's top-level copies, headers and CLI are unused
    "llm-layer": ["lib64", "lib", "include", "bin", "numpy/_core/include", "numpy/_pyinstaller"],
}
# Shared libraries a wheel expects from the OS but the Lambda python3.12 image lacks. rasterio's libgdal
# links the system libexpat.so.1; we take it from conda-forge (pinned + sha256-checked) into the layer's
# lib/ folder, which Lambda puts on LD_LIBRARY_PATH (/opt/lib).
VENDOR_LIBS = {
    "pipeline-layer": [(
        "https://conda.anaconda.org/conda-forge/linux-aarch64/libexpat-2.8.1-hfae3067_1.conda",
        "20a5726bc8705d91437c9e6ef83b30da64a1719b869656d20a1ee818333ea5ac",
        "lib/libexpat.so.1.12.1", "libexpat.so.1")],
}


def find_uv() -> str:
    for c in (ROOT / ".venv" / "Scripts" / "uv.exe", ROOT / ".venv" / "bin" / "uv"):
        if c.exists():
            return str(c)
    return shutil.which("uv") or sys.exit("uv not found: pip install uv")


def install(reqs: Path, STAGE: Path, platform: str) -> None:
    if STAGE.exists():
        shutil.rmtree(STAGE)
    subprocess.run(
        [find_uv(), "pip", "install", "-r", str(reqs),
         "--python-platform", platform, "--python-version", "3.12",
         "--only-binary", ":all:", "--link-mode", "copy", "--target", str(STAGE / "python")],
        check=True,
    )


def vendor_libs(name: str, STAGE: Path) -> None:
    import hashlib
    import io
    import tarfile
    specs = VENDOR_LIBS.get(name, [])
    if not specs:
        return
    zstd_dir = Path(tempfile.gettempdir()) / "talaab-zstd"
    if not (zstd_dir / "zstandard").exists():
        subprocess.run([find_uv(), "pip", "install", "zstandard", "--target", str(zstd_dir), "-q"], check=True)
    sys.path.insert(0, str(zstd_dir))
    import zstandard
    (STAGE / "lib").mkdir(parents=True, exist_ok=True)
    for url, sha256, member, dest in specs:
        # curl uses the OS trust store (Python's bundled one can be stale on Windows); the sha256 pins the bytes
        blob = subprocess.run(["curl", "-sSfL", url], check=True, capture_output=True).stdout
        if hashlib.sha256(blob).hexdigest() != sha256:
            sys.exit(f"sha256 mismatch for {url}")
        conda = zipfile.ZipFile(io.BytesIO(blob))
        pkg = next(n for n in conda.namelist() if n.startswith("pkg-"))
        tar = tarfile.open(fileobj=io.BytesIO(zstandard.ZstdDecompressor().stream_reader(io.BytesIO(conda.read(pkg))).read()))
        (STAGE / "lib" / dest).write_bytes(tar.extractfile(member).read())
        print(f"vendored lib/{dest} from {url.rsplit('/', 1)[-1]}")


def zip_layer(STAGE: Path, OUT: Path) -> None:
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
    ap.add_argument("--name", default="strands-layer", choices=sorted(LAYERS))
    args = ap.parse_args()
    stage = Path(tempfile.gettempdir()) / f"talaab-{args.name}"
    out = ROOT / ".build" / f"{args.name}.zip"
    if not (args.reuse and (stage / "python").exists()):
        install(*LAYERS[args.name][:1], stage, LAYERS[args.name][1])
    for rel in PRUNE.get(args.name, []):
        shutil.rmtree(stage / "python" / rel, ignore_errors=True)
    vendor_libs(args.name, stage)
    zip_layer(stage, out)
