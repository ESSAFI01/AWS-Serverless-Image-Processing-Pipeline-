# Demo cleanup runbook

**Cleanup completed on October 17, 2026.** I saved the demo evidence, disabled
processing and delivery, confirmed that no workflows were running, and removed
the demo objects. Terraform then removed all 43 project resources. I ran
`terraform -chdir=infra state list` and confirmed that the output was empty.

The commands below document the cleanup procedure for a future deployment.
Keep Terraform state locally until cleanup is complete; never upload state,
saved plans, credentials, or signed upload fields to GitHub.

## 1. Save evidence

The checked-in docs/evidence/ images and JSON report remain useful after the
CloudFront links stop working. Save any desired recording or console screenshots
and push the final documentation before deleting the demo.

## 2. Disable new processing and image delivery

From the project root in regular PowerShell, preview this change:

    terraform '-chdir=infra' plan '-var=bucket_suffix=essafi01demo' '-var=enable_processing=false' '-var=enable_delivery=false' '-out=demo-pause.tfplan'

Review the plan, then apply that saved plan if it only changes this demo as
intended. A saved-plan apply executes immediately:

    terraform '-chdir=infra' apply 'demo-pause.tfplan'

Stop the live API client. Confirm no workflow executions are RUNNING before
removing objects. Get the ARN from the project's Terraform outputs:

    $projectWorkflowArn = terraform '-chdir=infra' output -raw workflow_arn
    aws stepfunctions list-executions --state-machine-arn $projectWorkflowArn --status-filter RUNNING --region eu-west-3 --query 'executions[].name'

If any jobs are running, wait for them to finish and recheck. Disabling the SQS
mapping does not stop workflows that have already started. Disabling resources
alone does not remove storage or other provisioned resources.

## 3. Review and remove only the demo objects

List the two named project buckets first:

    aws s3 ls s3://graduation-images-input-essafi01demo/ --recursive --region eu-west-3
    aws s3 ls s3://graduation-images-output-essafi01demo/ --recursive --region eu-west-3

Only if the listed uploads, staging files, and processed files are the disposable
demo data you intend to delete, remove these exact prefixes:

    aws s3 rm s3://graduation-images-input-essafi01demo/uploads/ --recursive --region eu-west-3
    aws s3 rm s3://graduation-images-output-essafi01demo/staging/ --recursive --region eu-west-3
    aws s3 rm s3://graduation-images-output-essafi01demo/processed/ --recursive --region eu-west-3

Do not delete unfamiliar objects. The buckets use force_destroy=false, so an
unexpected remaining object will prevent bucket destruction instead of being
silently removed. Lifecycle expiration is not immediate cleanup.

## 4. Review the destruction plan

    terraform '-chdir=infra' plan '-destroy' '-var=bucket_suffix=essafi01demo' '-var=enable_processing=false' '-var=enable_delivery=false' '-out=demo-cleanup.tfplan'

The plan must contain only the intended project resources. Review it before the
following deletion command. This removes tables/metadata, queues/messages, logs,
Lambda functions/layer, the API, the workflow, CDN resources, SNS, buckets, and
project IAM roles/policies tracked in this state:

    terraform '-chdir=infra' apply 'demo-cleanup.tfplan'

## 5. Confirm completion

    terraform '-chdir=infra' state list

After a successful full cleanup, no managed project resources should remain in
state. Also check the AWS console for remaining project resources and billing
usage/credits; billing views can lag. The Free account plan must remain unchanged.
Record the cleanup status in the README while preserving the demo evidence.
If destruction fails, retain the state and resolve the error rather than deleting
state files or force-removing unrelated resources.
