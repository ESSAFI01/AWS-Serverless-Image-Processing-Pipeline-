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
- All three functions use unreserved concurrency (-1), compatible with the
  observed shared account quota of 10. SQS dispatch has a separate maximum of 2.
  The worker and API share remaining account capacity; they have no per-function
  reservation or dedicated concurrency cap.
- DynamoDB has 1 provisioned RCU and WCU; throttling is possible under load.
- Lifecycle settings intentionally expire demo objects; review the root README
  before any future deployment involving real data.
- There are no SNS subscribers, external recipients, customer-managed KMS keys,
  VPC/NAT resources, provisioned concurrency, or paid plan activation resources.

## Verification

I ran Terraform formatting, validation, and the mocked infrastructure test
(1 passed, 0 failed). I also tested the application ZIP and Pillow layer in the
Lambda Linux x86_64 Python 3.12.15 image: all 36 application tests passed.
The complete local suite, including the API client, passed all 44 tests.
See [the validation record](../docs/validation.md) for tested artifact hashes.

Before deploying, I checked the regional Lambda quota and found a total limit
of 10 concurrent executions. I used unreserved concurrency for all three
functions and kept the SQS dispatch maximum at 2.

I reviewed and applied the deployment plan, which created 43 resources, then
enabled processing and CloudFront delivery. The live workflow, DynamoDB
metadata, authenticated API upload, and CloudFront image checks all passed.
I also corrected the S3 presigner to use the regional endpoint, tested the
updated package, and deployed the fix.

## Cleanup status

After saving the evidence on October 17, 2026, I disabled processing and delivery,
removed the demo data, and destroyed all 43 Terraform-managed resources.
I verified that the Terraform state was empty. The live demo is now offline.

For a new deployment, review fresh plans using a unique bucket suffix.
Processing and delivery default to disabled; enable them explicitly when ready
to test. Do not reuse saved plans from the previous deployment.
