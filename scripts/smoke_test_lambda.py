"""Run the complete project's tests against application ZIP + Pillow layer in Docker."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

IMAGE = "public.ecr.aws/lambda/python:3.12"
ARTIFACTS = {"application.zip": "application_sha256", "pillow-layer.zip": "layer_sha256"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(archive, directory):
    with zipfile.ZipFile(archive) as source:
        for name in source.namelist():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise RuntimeError("Unsafe archive member")
        source.extractall(directory)


def inside_container():
    import platform
    import unittest
    assert sys.version_info[:2] == (3, 12), sys.version
    assert platform.system() == "Linux" and platform.machine() == "x86_64"
    root = Path("/project")
    with tempfile.TemporaryDirectory(prefix="lambda-project-") as temp:
        directory = Path(temp)
        app = directory / "application"
        layer = directory / "layer"
        extract(root / "build/application.zip", app)
        extract(root / "build/pillow-layer.zip", layer)
        sys.path[:0] = [str(app), str(layer / "python"), str(root)]
        import PIL
        import workflow
        import workflow_starter
        import upload_api
        assert Path(PIL.__file__).is_relative_to(layer / "python")
        for module in (workflow, workflow_starter, upload_api):
            assert Path(module.__file__).is_relative_to(app), module.__file__
        manifest = json.loads((root / "build/manifest.json").read_text())
        assert PIL.__version__ == manifest["pillow"]
        suite = unittest.defaultTestLoader.loadTestsFromNames(["test_lambda_function", "test_workflow"])
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful():
            raise SystemExit(1)
        report = {"status": "PASS", "python": platform.python_version(),
                  "pillow": PIL.__version__, "image": IMAGE, "tests": result.testsRun,
                  "checks": ["Linux x86_64", "application ZIP", "Pillow layer",
                             "validate-resize-watermark-store", "metadata", "notifications",
                             "upload API", "SQS dispatch", "failure handling"],
                  **{field: sha256(root / "build" / name) for name, field in ARTIFACTS.items()}}
        print(json.dumps(report))


def main():
    if sys.argv[1:] == ["--inside-container"]:
        inside_container()
        return
    root = Path(__file__).resolve().parents[1]
    manifest_path = root / "build/manifest.json"
    if not manifest_path.is_file():
        raise SystemExit("Build the ZIPs first using scripts/build_lambda.py.")
    manifest = json.loads(manifest_path.read_text())
    for name, field in ARTIFACTS.items():
        archive = root / "build" / name
        if not archive.is_file() or manifest.get(field) != sha256(archive):
            raise SystemExit("Missing or changed artifact. Rebuild using scripts/build_lambda.py.")
    mounted = ["build/application.zip", "build/pillow-layer.zip", "build/manifest.json",
               "scripts/smoke_test_lambda.py", "test_lambda_function.py", "test_workflow.py",
               "infra/workflow.asl.json.tftpl"]
    command = ["docker", "run", "--rm", "--platform", "linux/amd64",
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges",
               # Native Pillow libraries need executable mappings from tmpfs.
               "--tmpfs", "/tmp:rw,exec,size=128m"]
    for name in mounted:
        command.extend(["--mount", f"type=bind,source={root / name},target=/project/{name},readonly"])
    command.extend(["--entrypoint", "/var/lang/bin/python", IMAGE,
                    "/project/scripts/smoke_test_lambda.py", "--inside-container"])
    print("Testing application ZIP + Pillow layer locally. No AWS resources will be deployed.", flush=True)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=600)
    except FileNotFoundError:
        raise SystemExit("Docker CLI not found; open PowerShell with Docker Desktop available.")
    except subprocess.TimeoutExpired:
        raise SystemExit("Docker timed out; test was not marked passed.")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr, end="")
    if completed.returncode:
        print(completed.stdout, end="")
        raise SystemExit("Container test failed; test was not marked passed.")
    report = json.loads(completed.stdout.strip().splitlines()[-1])
    if report.get("status") != "PASS":
        raise SystemExit("Unexpected test result")
    for name, field in ARTIFACTS.items():
        if report.get(field) != manifest[field] or sha256(root / "build" / name) != manifest[field]:
            raise SystemExit("Artifact changed while testing; rebuild and retest.")
    manifest["layered_runtime_smoke_test"] = "PASS"
    manifest["layered_runtime_test_details"] = report
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Local runtime test passed. No AWS resources were deployed.")


if __name__ == "__main__":
    main()
