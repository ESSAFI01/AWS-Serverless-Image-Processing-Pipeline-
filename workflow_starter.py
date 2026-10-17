"""SQS consumer: acknowledge only after a Standard workflow is accepted."""
import json
import logging
import os

from pipeline_common import client, jobs_from_notification

logger = logging.getLogger(__name__)


def lambda_handler(event, context):
    state_machine = os.environ["STATE_MACHINE_ARN"]
    records = event["Records"]
    if not isinstance(records, list) or any(
        record.get("eventSource") != "aws:sqs" or not record.get("messageId")
        for record in records
    ):
        raise ValueError("Expected SQS messages with IDs")
    failures = []
    for record in records:
        try:
            for job in jobs_from_notification(json.loads(record["body"])):
                try:
                    client("stepfunctions").start_execution(
                        stateMachineArn=state_machine, name="image-" + job["job_id"],
                        input=json.dumps(job, sort_keys=True),
                    )
                except Exception as error:
                    # Standard execution names deduplicate S3/SQS deliveries for 90 days.
                    # Deliberate reprocessing must use a new upload key.
                    if getattr(error, "response", {}).get("Error", {}).get("Code") != "ExecutionAlreadyExists":
                        raise
        except Exception as error:
            logger.warning("Workflow dispatch failed (%s)", type(error).__name__)
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
