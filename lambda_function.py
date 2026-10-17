"""S3 -> standard SQS -> Lambda -> separate S3 bucket.

No AWS client is created until an eligible object is processed.
"""
import json
import logging
import os
from urllib.parse import unquote_plus

from processor import process_image

logger = logging.getLogger(__name__)
_s3_client = None
MAX_IMAGE_BYTES = 20 * 1024 * 1024
IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif")


def _get_s3_client():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client("s3")
    return _s3_client


def _process_notification(notification, source_bucket, destination_bucket):
    if notification.get("Event") == "s3:TestEvent":
        return
    records = notification["Records"]
    if not isinstance(records, list) or not records:
        raise ValueError("S3 notification must contain a nonempty Records list")
    for record in records:
        if record["eventSource"] != "aws:s3":
            raise ValueError("Expected an S3 notification")
        if not record["eventName"].startswith("ObjectCreated:"):
            continue
        bucket = record["s3"]["bucket"]["name"]
        if bucket != source_bucket:
            raise ValueError("Unexpected source bucket")
        obj = record["s3"]["object"]
        key = unquote_plus(obj["key"])
        if not key.lower().endswith(IMAGE_EXTENSIONS):
            continue
        if obj.get("size", 0) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the 20 MiB input limit")
        request = {"Bucket": bucket, "Key": key}
        if obj.get("versionId"):
            request["VersionId"] = obj["versionId"]
        s3 = _get_s3_client()
        response = s3.get_object(**request)
        body = response["Body"]
        try:
            if response.get("ContentLength", 0) > MAX_IMAGE_BYTES:
                raise ValueError("Image exceeds the 20 MiB input limit")
            image_bytes = body.read(MAX_IMAGE_BYTES + 1)
        finally:
            body.close()
        if len(image_bytes) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds the 20 MiB input limit")
        result = process_image(image_bytes)
        # Retain the full source name so photo.png and photo.jpg do not collide.
        s3.put_object(
            Bucket=destination_bucket,
            Key="processed/" + key + ".jpg",
            Body=result,
            ContentType="image/jpeg",
        )


def lambda_handler(event, context):
    """Return failed SQS IDs; requires ReportBatchItemFailures when deployed."""
    source_bucket = os.environ["SOURCE_BUCKET"]
    destination_bucket = os.environ["DESTINATION_BUCKET"]
    if not source_bucket or not destination_bucket or source_bucket == destination_bucket:
        raise ValueError("Configure distinct, nonempty source and destination buckets")
    records = event["Records"]
    if not isinstance(records, list):
        raise ValueError("Expected an SQS Records list")
    # Validate IDs before processing so malformed events cannot acknowledge failures.
    for record in records:
        if record.get("eventSource") != "aws:sqs" or not record.get("messageId"):
            raise ValueError("Expected SQS records with messageId")
    failures = []
    for record in records:
        try:
            notification = json.loads(record["body"])
            _process_notification(notification, source_bucket, destination_bucket)
        except Exception as error:
            # Do not log raw payloads, object data, or SDK exception contents.
            logger.warning("SQS image processing failed (%s)", type(error).__name__)
            failures.append({"itemIdentifier": record["messageId"]})
    return {"batchItemFailures": failures}
