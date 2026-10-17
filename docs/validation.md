# Validation record

## Original core pipeline (before the full project extension)

- 16 Python integration tests: passed locally.
- Terraform fmt/init/validate: passed in user PowerShell.
- Terraform mock test: 1 passed, 0 failed in user PowerShell.
- Standalone ZIP runtime test: PASS in Lambda Linux x86_64 Python 3.12.15 with
  Pillow 12.3.0, reported by the user. This result applies to the older ZIP hash
  4b98b6fd8adeffde2d40ae99ce558f6865600d5abc674ec8eab43dc0b50fda08.

## Expanded Project 2 implementation (2026-10-17)

- 35 Python tests (16 core + 19 workflow/API): passed locally, with fake AWS clients
  and socket connections blocked during each test.
- Python syntax compilation: passed for handlers, builder, runtime test, and
  diagram renderer.
- Application ZIP + Linux Pillow layer: built from the existing pinned wheel;
  hashes are recorded in the local build/manifest.json.
- Architecture SVG and PNG: generated; PNG visually inspected.
- Expanded Terraform fmt and validate: PASS, reported from user PowerShell.
- Expanded Terraform mock test: PASS, 1 passed and 0 failed. No real provider calls.
- Expanded application-plus-layer Lambda runtime test: PASS. All 35 tests passed
  in the Lambda Linux x86_64 Python 3.12.15 image with Pillow 12.3.0. The user
  supplied the console output, and the local manifest records PASS for these hashes.
- Tested application SHA256:
  2bfb11c6624dfe558d80afc3b8239f78f3e4a5ec9d8a3903cca9f38f82a4c12b
- Tested Pillow layer SHA256:
  7afdc5fbf96f0aa24195cd39d0c2fec277c38840b84473a21098c2a4a222747a
- Warning lines for corrupt images and simulated service failures are expected.
  They are intentional tests of retry and error handling.
- Real AWS execution, CDN access, API authentication, SNS delivery: NOT TESTED.
  No resources are deployed. Mock tests cannot establish live IAM effectiveness,
  account quotas, regional entitlements, or actual runtime service behavior.

Rebuilding resets the artifact runtime test flags. Only a successful test for the
current hashes marks the local manifest as passed. Never reuse the older standalone
ZIP's PASS as evidence for a changed application/layer.
