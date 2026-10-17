"""IAM-authenticated HTTP API: bounded presigned uploads and job status."""
import base64
import binascii
import json
import logging
import os
import re
import uuid

from pipeline_common import MAX_IMAGE_BYTES, client, job_id, json_response

logger = logging.getLogger(__name__)
CONTENT_TYPES = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                 "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp",
                 "tif": "image/tiff", "tiff": "image/tiff"}


def lambda_handler(event, context):
    try:
        route = event.get("routeKey")
        if route == "POST /uploads":
            body = event.get("body") or "{}"
            if event.get("isBase64Encoded"):
                body = base64.b64decode(body, validate=True).decode("utf-8")
            payload = json.loads(body)
            if not isinstance(payload, dict):
                return json_response(400, {"error": "Expected a JSON object"})
            name = payload.get("filename", "")
            if not isinstance(name, str):
                return json_response(400, {"error": "Invalid filename"})
            extension = name.rsplit(".", 1)[-1].lower()
            if extension not in CONTENT_TYPES:
                return json_response(400, {"error": "Unsupported image extension"})
            content_type = CONTENT_TYPES[extension]
            bucket = os.environ["SOURCE_BUCKET"]
            key = "uploads/" + uuid.uuid4().hex + "." + extension
            upload = client("s3").generate_presigned_post(
                Bucket=bucket, Key=key,
                Fields={"Content-Type": content_type},
                Conditions=[{"Content-Type": content_type},
                            ["content-length-range", 1, MAX_IMAGE_BYTES]],
                ExpiresIn=300,
            )
            return json_response(200, {"job_id": job_id(bucket, key), "source_key": key,
                                       "expires_in": 300, "upload": upload})
        if route == "GET /jobs/{job_id}":
            identifier = (event.get("pathParameters") or {}).get("job_id", "")
            if not re.fullmatch(r"[a-f0-9]{64}", identifier):
                return json_response(400, {"error": "Invalid job identifier"})
            response = client("dynamodb").get_item(
                TableName=os.environ["METADATA_TABLE"],
                Key={"job_id": {"S": identifier}}, ConsistentRead=True,
            )
            if "Item" not in response:
                return json_response(404, {"error": "Job not found or not started yet"})
            item = response["Item"]
            result = {name: (int(value["N"]) if "N" in value else value["S"])
                      for name, value in item.items()}
            return json_response(200, result)
        return json_response(404, {"error": "Route not found"})
    except (ValueError, TypeError, UnicodeDecodeError, binascii.Error):
        return json_response(400, {"error": "Invalid request"})
    except Exception as error:
        logger.warning("Image API failed (%s)", type(error).__name__)
        return json_response(500, {"error": "Request could not be completed"})
