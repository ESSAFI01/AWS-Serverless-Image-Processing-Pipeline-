# Free plan service review

Reviewed against public AWS documentation on 2026-10-17. No authenticated AWS
account or billing APIs were called to perform this review.

## Selected services

AWS lists S3, SQS, Lambda, Step Functions, API Gateway, DynamoDB, CloudFront,
SNS, CloudWatch, and IAM among services supported in its Free plan experience.
This project uses those services and standard features. A Pillow Lambda Layer
is a Lambda dependency package, not a separate paid subscription.

Sources:
- [Supported services and feature exceptions](https://docs.aws.amazon.com/accounts/latest/reference/supported-services-sign-up-new.html)
- [Serverless Free plan offers](https://aws.amazon.com/free/serverless/)
- [Free plan billing rules](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier.html)

Availability is not unlimited free usage. Some eligible usage consumes account
credits. This is a documented service-level compatibility review, not a live
verification of this specific account's entitlements or remaining credit balance.
Stop if the console requests an upgrade or activating advanced/paid-only features.

## Account constraint

The user reports FREE, ACTIVE, USD 100 credits, with a displayed expiration of
2027-03-18. Treat that date as user-reported; credit expiry and Free plan expiry
can differ. AWS documents that the Free plan ends at six months or credit
exhaustion, whichever happens first. Recheck the console before any future
resource creation, without changing the plan.

A small demo deployment was subsequently authorized and completed. Before it,
the user confirmed the console showed Free plan, USD 100 credits, and 154 days
remaining. Usage after deployment has not been audited. Never upgrade the account, activate
paid-only services, join Organizations, or use Control Tower for this project.
No bank charge guarantee is being inferred from the code's resource settings.

## Configuration choices

| Component | Setting and purpose |
|---|---|
| Lambda | No provisioned concurrency or VPC; dispatcher/API 128 MiB, worker 512 MiB; unreserved concurrency (account quota is shared); SQS dispatch maximum 2 |
| SQS | Standard queue, batch size 1, bounded dispatch retries, DLQ |
| Step Functions | Standard, short workflow, bounded task retries, 300-second execution timeout |
| DynamoDB | Provisioned 1 RCU and 1 WCU; no autoscaling, replicas, backups, or indexes |
| CloudFront | Standard distribution, default certificate, no Lambda@Edge or custom domain; delivery disabled by default |
| SNS | Topic only, no SMS, emails, or external subscribers configured |
| S3 | Standard storage with AES256 managed encryption; no Glacier transitions, versioning, or cross-Region replication |
| Retention | Uploads/results 7 days; staging 1 day; metadata TTL 14 days; Lambda logs 3 days |
| API | IAM required; 1 request/second, burst 2; presigned uploads expire after 300 seconds |

Limits, throttles, lifecycle rules, and a disabled event mapping are not billing
caps. A disabled mapping can still leave stored objects, queued messages, and
other resources after a future deployment. Do not deploy under an assumed cost
estimate. The current local tests do not generate AWS resource usage.

## Account concurrency preflight

The user checked Lambda account settings in eu-west-3 and reported total and
unreserved concurrency of 10. The configuration therefore uses -1 (unreserved)
for all three functions, rather than reserving capacity. The shared account limit
still applies; SQS dispatch is limited to two concurrent invocations, but this
does not cap the number of workflows in progress or reserve worker capacity.
Use a few sample images for the demonstration.

[Terraform unreserved setting](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/lambda_function) · [AWS reserved concurrency rules](https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html)
