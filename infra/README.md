# Infrastructure notes

The root [README](../README.md) contains the architecture diagram, feature
mapping, local commands, interface contracts, and cost boundary.

## Configuration files

- versions.tf: Terraform and AWS provider constraints.
- main.tf: private buckets, encryption, SQS, DLQ, and S3 event notifications.
- compute.tf: distinct Lambda roles/functions, Pillow layer, Standard workflow.
- services.tf: DynamoDB, SNS, S3 lifecycle, CloudFront OAC, HTTP API.
- variables.tf / outputs.tf: configuration and useful resource identifiers.
- workflow.asl.json.tftpl: validate → resize → watermark → store, with failure path.
- tests/pipeline.tftest.hcl: mocked plan assertions for resource wiring/defaults.

Region defaults to eu-west-3. All regional resources use that provider; CloudFront
is global. No cross-Region feature is configured. Bucket names need a unique
6-12 character suffix for any future deployment. terraform.tfvars.example has
example values only and contains no credentials.

Application ZIP path defaults to ../build/application.zip. Pillow layer path
defaults to ../build/pillow-layer.zip. Both are built locally. The mocked tests
use a deliberately non-deployable plain-text fixture only for hash/existence
checks, with no real provider calls.

## Default controls

- enable_processing=false keeps the SQS event source mapping disabled.
- enable_delivery=false keeps CloudFront delivery disabled.
- API routes require AWS_IAM; no anonymous presigning endpoint is exposed.
- Each Lambda has its own role. The dispatch role starts only this state machine
  and consumes only this queue. The worker reads uploads/staging, writes
  staging/processed, writes this table, and publishes only to this SNS topic.
- CloudFront reads processed/* through signed origin requests. It cannot read
  source images or staging objects. Buckets block public access and disable ACLs.
- DynamoDB has 1 provisioned RCU and WCU; throttling is possible under load.
- Lifecycle settings intentionally expire demo objects; review the root README
  before any future deployment involving real data.
- There are no SNS subscribers, external recipients, customer-managed KMS keys,
  VPC/NAT resources, provisioned concurrency, or paid plan activation resources.

## Verification

The expanded Terraform configuration passed fmt, validate, and the mocked test
(1 passed, 0 failed) in user PowerShell. The layered application passed all 35
Python tests in the Lambda Linux x86_64 Python 3.12.15 image with Pillow 12.3.0.
See [the validation record](../docs/validation.md) for tested artifact hashes.
These checks used mocked AWS calls and created no resources. They do not verify
live IAM permissions, quotas, endpoints, or service integrations in AWS.

Do not run real plan/apply/destroy for this stage. No deployment has been authorized.
