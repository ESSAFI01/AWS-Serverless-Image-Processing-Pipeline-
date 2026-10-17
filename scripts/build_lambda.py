"""Build a Linux x86_64 / Python 3.12 ZIP without AWS calls or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
WHEELS = BUILD / "wheels"
REQUIREMENTS = ROOT / "requirements-lambda.txt"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true",
                        help="Download pinned Linux wheels from public PyPI (never AWS)")
    args = parser.parse_args()
    WHEELS.mkdir(parents=True, exist_ok=True)
    if args.download:
        subprocess.run([
            sys.executable, "-m", "pip", "--isolated", "download",
            "--index-url", "https://pypi.org/simple", "--disable-pip-version-check",
            "--no-cache-dir", "--retries", "0", "--timeout", "15",
            "--only-binary=:all:", "--no-deps",
            "--platform", "manylinux_2_28_x86_64", "--implementation", "cp",
            "--python-version", "3.12", "--abi", "cp312",
            "--requirement", str(REQUIREMENTS), "--dest", str(WHEELS),
        ], check=True)
    version = REQUIREMENTS.read_text().strip().split("==")[1]
    candidates = list(WHEELS.glob(f"pillow-{version}-cp312-cp312-manylinux*x86_64.whl"))
    if len(candidates) != 1:
        raise SystemExit("Need exactly one pinned Pillow cp312 Linux x86_64 wheel in build/wheels. "
                         "Run with --download if public PyPI access is permitted. No ZIP was built.")
    wheel = candidates[0]
    archive = BUILD / "lambda.zip"
    with zipfile.ZipFile(wheel) as source:
        files = {}
        for entry in source.infolist():
            if entry.is_dir():
                continue
            name = entry.filename
            if name.startswith("/") or ".." in Path(name).parts or ".data/" in name:
                raise SystemExit("Unsupported wheel layout")
            files[name] = source.read(entry)
        application_names = ("lambda_function.py", "processor.py", "pipeline_common.py",
                             "workflow_starter.py", "workflow.py", "upload_api.py")
        for name in application_names:
            files[name] = (ROOT / name).read_bytes()
        if not any(name.startswith("PIL/_imaging.") and name.endswith(".so") for name in files):
            raise SystemExit("Pillow Linux extension missing")
        if any(name.endswith((".pyd", ".dll")) for name in files):
            raise SystemExit("Windows binaries must not be in Lambda ZIP")
    temporary = archive.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as target:
        for name, content in sorted(files.items()):
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            target.writestr(entry, content)
    temporary.replace(archive)
    def write_zip(path, entries):
        temp = path.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as target:
            for name, data in sorted(entries.items()):
                entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                entry.create_system = 3
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                target.writestr(entry, data)
        temp.replace(path)

    application = BUILD / "application.zip"
    layer = BUILD / "pillow-layer.zip"
    write_zip(application, {name: files[name] for name in application_names})
    write_zip(layer, {"python/" + name: data for name, data in files.items()
                      if name not in application_names})
    manifest = {
        "runtime": "python3.12", "architecture": "x86_64",
        "pillow": version, "wheel": wheel.name,
        "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
        "zip_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
        "zip_bytes": archive.stat().st_size,
        "linux_runtime_smoke_test": "NOT RUN",
        "layered_runtime_smoke_test": "NOT RUN",
        "application_sha256": hashlib.sha256(application.read_bytes()).hexdigest(),
        "layer_sha256": hashlib.sha256(layer.read_bytes()).hexdigest(),
        "application_bytes": application.stat().st_size,
        "layer_bytes": layer.stat().st_size,
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError:
        raise SystemExit("Dependency download failed. No new Lambda ZIP was built. Check public PyPI access.")
