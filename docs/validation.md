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
- Subsequent live AWS checks are recorded below. Mock tests alone do not establish
  live IAM effectiveness, account quotas, or actual service behavior.

Rebuilding resets the artifact runtime test flags. Only a successful test for the
current hashes marks the local manifest as passed. Never reuse the older standalone
ZIP's PASS as evidence for a changed application/layer.

## Account quota adjustment after the deployment preview

The user reported Lambda Total=10 and Unreserved=10 in eu-west-3. Before any
resource creation, all three function reservations were changed from 2 to -1
(unreserved), while SQS dispatch maximum concurrency remains 2. The Terraform
mock assertions were adjusted to verify these settings. Terraform formatting,
validation, and the mock test subsequently PASSED in user PowerShell. A fresh
plan reported 43 additions with -1 on all three functions. Python code
and the tested application/layer ZIPs are unchanged. The old demo.tfplan must
not be applied because it still requests the reservations.

## Live AWS demonstration (2026-10-17)

Evidence supplied by the user from PowerShell and browser checks:

- Initial apply: 43 added, 0 changed, 0 destroyed.
- Enable apply: 0 added, 2 changed, 0 destroyed; processing and delivery true.
- S3 upload produced image.jpg and thumbnail.jpg in processed/<job_id>/.
- Step Functions execution: SUCCEEDED.
- DynamoDB metadata: COMPLETED, source dimensions 2400 x 1600, both CDN URLs.
- CloudFront: user confirmed both JPEG links load and show Cloud & AI.
- SNS publish path completed within the successful Store task; external delivery
  is not tested and no subscribers are configured.
- Live API authentication, presigned POST, and status route: subsequently PASS;
  see the final verification below.
- New live-client offline checks: 8 passed; no AWS credentials or calls required.

See [the live evidence record](live-demo.md) for the sample job and links.

The first live API attempt confirmed unsigned requests are rejected, then stopped
during login credential loading because the local AWS CRT dependency was missing.
No API-based image upload occurred. The helper now gives an actionable CRT install
message without printing credential-provider details; its regression test passes.
Installing boto3[crt] resolved the local login dependency. No Lambda change was
needed for that dependency.

## Regional presigned-upload correction

After CRT installation, the live client successfully made its signed upload API
request. The subsequent S3 POST returned HTTP 307. The S3 client now explicitly
sets the bucket Region and regional endpoint with virtual-hosted addressing,
rather than relying on the SDK global-endpoint behavior. A regression test
verifies this configuration. All 44 offline tests passed (36 application and
8 client tests). Application ZIPs were rebuilt from the cached wheel; the updated
ZIP subsequently passed all 36 application tests in the Lambda Linux runtime
and was deployed with 0 added, 4 changed, 0 destroyed (three Lambda code updates
and the CloudFront origin configuration). The Pillow layer is unchanged.
Previous runtime hashes above remain historical evidence only.

[Regional S3 endpoint guidance](https://repost.aws/knowledge-center/s3-http-307-response)

## Final verification: regional fix and API-driven upload

- Lambda runtime: Python 3.12.15, Pillow 12.3.0, 36 tests PASS.
- Local application and live-client suite: 44 tests PASS.
- Current application SHA256:
  933fbe8edf267f22e2644b6e5c5256b1ad865981e6f88c8ec0273c4cfd80ae33
- Pillow layer SHA256:
  7afdc5fbf96f0aa24195cd39d0c2fec277c38840b84473a21098c2a4a222747a
- Signed API upload + S3 POST + status API + CloudFront JPEGs: PASS.
- Job e29144fc3722aa7ca68d11de20410f27d05a764fe2a104efab04293368f03390
  completed; unsigned upload was rejected. Outputs are 1024 x 683 and 256 x 171.
- [Safe report](evidence/live-api-result.json) and JPEG samples are checked in.
- SNS external subscriber delivery, live failure/DLQ exercises, teardown, and
  post-demo billing verification are not claimed as tested.
