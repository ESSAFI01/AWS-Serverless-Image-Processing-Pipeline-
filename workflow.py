"""Step Functions tasks; large image bytes remain in S3, never in workflow state."""
from io import BytesIO
import json
import os
import time

from PIL import Image, ImageOps

from pipeline_common import MAX_IMAGE_PIXELS, client, download, validate_job
from processor import resize_image, watermark_image


def _metadata(job, status):
    item = {
        "job_id": {"S": job["job_id"]}, "status": {"S": status},
        "source_key": {"S": job["source_key"]},
        "uploaded_at": {"S": job.get("uploaded_at", "unknown")},
        "updated_at": {"N": str(int(time.time()))},
        "expires_at": {"N": str(int(time.time()) + 14 * 86400)},
    }
    for field in ("width", "height"):
        if field in job:
            item[field] = {"N": str(job[field])}
    for field in ("image_key", "thumbnail_key", "image_url", "thumbnail_url"):
        if field in job:
            item[field] = {"S": job[field]}
    if status == "FAILED":
        item["error_type"] = {"S": job.get("failure", {}).get("Error", "ProcessingFailed")[:128]}
    client("dynamodb").put_item(TableName=os.environ["METADATA_TABLE"], Item=item)


def _notify(job, status):
    # The topic has no subscriptions by default. Never include image data or URLs with credentials.
    client("sns").publish(
        TopicArn=os.environ["NOTIFICATION_TOPIC_ARN"],
        Message=json.dumps({"job_id": job["job_id"], "status": status}),
        Subject="Image processing " + status.lower(),
    )


def _stage_key(job, name):
    return "staging/" + job["job_id"] + "/" + name


def _put(bucket, key, data, content_type):
    client("s3").put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


def lambda_handler(event, context):
    action = event["action"]
    job = dict(event["job"])
    source, destination = validate_job(job)
    if action == "validate":
        data = download(source, job["source_key"], job.get("version_id"))
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise ValueError("Decoded image exceeds 20 million pixels")
            image.verify()
        with Image.open(BytesIO(data)) as image:
            oriented = ImageOps.exif_transpose(image)
            job.update(width=oriented.width, height=oriented.height)
        _metadata(job, "PROCESSING")
    elif action == "resize":
        data = download(source, job["source_key"], job.get("version_id"))
        for variant, size in (("image", (1024, 1024)), ("thumbnail", (256, 256))):
            _put(destination, _stage_key(job, variant + ".png"),
                 resize_image(data, size), "image/png")
    elif action == "watermark":
        for variant in ("image", "thumbnail"):
            data = download(destination, _stage_key(job, variant + ".png"))
            _put(destination, _stage_key(job, variant + ".jpg"),
                 watermark_image(data), "image/jpeg")
    elif action == "store":
        domain = os.environ["CLOUDFRONT_DOMAIN"]
        for variant in ("image", "thumbnail"):
            key = "processed/" + job["job_id"] + "/" + variant + ".jpg"
            client("s3").copy_object(
                Bucket=destination, Key=key,
                CopySource={"Bucket": destination, "Key": _stage_key(job, variant + ".jpg")},
                MetadataDirective="REPLACE", ContentType="image/jpeg",
                CacheControl="public,max-age=86400,immutable",
            )
            job[variant + "_key"] = key
            job[variant + "_url"] = "https://" + domain + "/" + key
        _metadata(job, "COMPLETED")
        _notify(job, "COMPLETED")
    elif action == "fail":
        _metadata(job, "FAILED")
        _notify(job, "FAILED")
    else:
        raise ValueError("Unsupported workflow action")
    return job
