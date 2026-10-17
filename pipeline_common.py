"""Shared configuration and lazy SDK access; importing this module never calls AWS."""
import hashlib
import json
import os
import re
from urllib.parse import unquote_plus

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
EXTENSIONS = {"jpg", "jpeg", "png", "webp", "bmp", "tif", "tiff", "gif"}
_clients = {}


def client(service):
    if service not in _clients:
        import boto3
        if service == "s3":
            from botocore.config import Config
            _clients[service] = boto3.client(service, config=Config(signature_version="s3v4"))
        else:
            _clients[service] = boto3.client(service)
    return _clients[service]


def buckets():
    source = os.environ["SOURCE_BUCKET"]
    destination = os.environ["DESTINATION_BUCKET"]
    if not source or not destination or source == destination:
        raise ValueError("Distinct nonempty input and output buckets are required")
    return source, destination


def job_id(bucket, key):
    # API-generated uploads use unique keys; overwriting a key is unsupported.
    return hashlib.sha256((bucket + "/" + key).encode()).hexdigest()


def jobs_from_notification(notification):
    if notification.get("Event") == "s3:TestEvent":
        return []
    records = notification["Records"]
    if not isinstance(records, list) or not records:
        raise ValueError("Expected S3 notification Records")
    source, _ = buckets()
    jobs = []
    for record in records:
        if record["eventSource"] != "aws:s3":
            raise ValueError("Expected direct S3 notifications")
        if not record["eventName"].startswith("ObjectCreated:"):
            continue
        s3 = record["s3"]
        obj = s3["object"]
        key = unquote_plus(obj["key"])
        if s3["bucket"]["name"] != source or not key.startswith("uploads/"):
            raise ValueError("Unexpected source location")
        if key.rsplit(".", 1)[-1].lower() not in EXTENSIONS:
            continue
        jobs.append({"job_id": job_id(source, key), "source_bucket": source,
                     "source_key": key, "version_id": obj.get("versionId"),
                     "uploaded_at": record.get("eventTime", "unknown")})
    return jobs


def validate_job(job):
    source, destination = buckets()
    key = job["source_key"]
    if job["source_bucket"] != source or not key.startswith("uploads/"):
        raise ValueError("Unexpected source location")
    if not re.fullmatch(r"[a-f0-9]{64}", job["job_id"]):
        raise ValueError("Invalid job identifier")
    if job_id(source, key) != job["job_id"]:
        raise ValueError("Job identifier does not match source")
    return source, destination


def download(bucket, key, version=None):
    request = {"Bucket": bucket, "Key": key}
    if version:
        request["VersionId"] = version
    response = client("s3").get_object(**request)
    body = response["Body"]
    try:
        if response.get("ContentLength", 0) > MAX_IMAGE_BYTES:
            raise ValueError("Image exceeds 20 MiB")
        data = body.read(MAX_IMAGE_BYTES + 1)
    finally:
        body.close()
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("Image exceeds 20 MiB")
    return data


def json_response(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json",
            "Cache-Control": "no-store"}, "body": json.dumps(body)}
