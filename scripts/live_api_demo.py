"""Upload one demo image through the real IAM-protected API; never print credentials."""
import argparse
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import build_opener, HTTPRedirectHandler, Request
import uuid

ROOT = Path(__file__).resolve().parents[1]
LIMIT = 20 * 1024 * 1024


class DemoError(Exception):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_url(url, host_pattern):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment or parsed.query
            or not re.fullmatch(host_pattern, parsed.hostname or "")):
        raise DemoError("Unexpected HTTPS endpoint; request was not sent")
    return parsed


def multipart(fields, filename, data):
    boundary = "demo-" + uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
            raise DemoError("Invalid upload field name")
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                      + str(value) + "\r\n").encode())
    safe_name = re.sub(r'[^A-Za-z0-9_.-]', "_", filename)
    content_type = fields.get("Content-Type", "application/octet-stream")
    if not re.fullmatch(r"image/[a-z0-9.+-]+", content_type):
        raise DemoError("Invalid image Content-Type")
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                  f'filename="{safe_name}"\r\nContent-Type: {content_type}\r\n\r\n').encode())
    parts.extend([data, f"\r\n--{boundary}--\r\n".encode()])
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def signed_json(opener, session, region, method, url, body=None):
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest

    from botocore.exceptions import MissingDependencyException

    try:
        credentials = session.get_credentials()
        if credentials is None:
            raise DemoError("No existing AWS login found; use the same profile as your working AWS CLI")
        frozen = credentials.get_frozen_credentials()
    except MissingDependencyException:
        raise DemoError(
            'Your AWS login requires CRT. Install: python -m pip install "boto3[crt]"'
        ) from None
    payload = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    request = AWSRequest(method=method, url=url, data=payload, headers=headers)
    SigV4Auth(frozen, "execute-api", region).add_auth(request)
    # Signing headers and S3 form fields stay in memory and are never logged or saved.
    with opener.open(Request(url, data=payload, headers=dict(request.headers.items()), method=method),
                     timeout=20) as response:
        return json.load(response)


def reject_unsigned(opener, url, filename):
    for attempt in range(3):
        try:
            with opener.open(Request(url, data=json.dumps({"filename": filename}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST"),
                             timeout=20):
                raise DemoError("Unsigned upload request was accepted; stop and review IAM authorization")
        except HTTPError as error:
            code = error.code
            error.close()
            if code in (401, 403):
                return
            if code == 429 and attempt < 2:
                time.sleep(3)
                continue
            raise DemoError("Unsigned authorization check returned HTTP " + str(code))


def poll_status(opener, session, region, url, identifier):
    for attempt in range(30):
        time.sleep(3)
        try:
            job = signed_json(opener, session, region, "GET", url + "/jobs/" + identifier)
        except HTTPError as error:
            if error.code not in (404, 429):
                raise
            error.close()
            continue
        if job.get("status") == "FAILED":
            raise DemoError("Image job failed; inspect its Step Functions execution")
        if job.get("status") == "COMPLETED":
            return job
    raise DemoError("Job not complete after 90 seconds; inspect its execution before uploading again")


def check_outputs(opener, job, directory):
    from PIL import Image

    directory.mkdir(parents=True, exist_ok=True)
    sizes = {}
    for variant, maximum in (("image", 1024), ("thumbnail", 256)):
        url = job[variant + "_url"]
        parsed = validate_url(url, r"[a-z0-9]+\.cloudfront\.net")
        if not parsed.path.startswith("/processed/" + job["job_id"] + "/"):
            raise DemoError("Unexpected processed-image path")
        with opener.open(url, timeout=20) as response:
            if response.headers.get_content_type() != "image/jpeg":
                raise DemoError("CloudFront did not return a JPEG")
            data = response.read(LIMIT + 1)
        if len(data) > LIMIT:
            raise DemoError("Unexpected output size")
        with Image.open(BytesIO(data)) as image:
            if image.format != "JPEG" or max(image.size) > maximum:
                raise DemoError("Unexpected processed image dimensions")
            image.load()
            sizes[variant] = list(image.size)
        (directory / (variant + ".jpg")).write_bytes(data)
    return sizes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--region", default="eu-west-3")
    parser.add_argument("--image", type=Path, default=ROOT / "output/original.jpg")
    parser.add_argument("--profile", help="Optional existing AWS profile; no keys are accepted")
    args = parser.parse_args()
    try:
        import boto3
    except ImportError:
        raise DemoError('Install the local client dependency: python -m pip install "boto3[crt]"')
    url = args.api_url.rstrip("/")
    parsed = validate_url(url, r"[a-z0-9]+\.execute-api\." + re.escape(args.region) + r"\.amazonaws\.com")
    if parsed.path:
        raise DemoError("Use the HTTP API base URL without a path")
    data = args.image.read_bytes()
    if not 0 < len(data) <= LIMIT:
        raise DemoError("Choose an image between 1 byte and 20 MiB")
    opener = build_opener(NoRedirect())
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    print("Checking that unsigned upload requests are rejected...", flush=True)
    reject_unsigned(opener, url + "/uploads", args.image.name)
    print("Requesting an upload through the IAM-authenticated API...", flush=True)
    response = signed_json(opener, session, args.region, "POST", url + "/uploads",
                           {"filename": args.image.name})
    identifier = response["job_id"]
    if not re.fullmatch(r"[a-f0-9]{64}", identifier):
        raise DemoError("Invalid job identifier in API response")
    upload = response["upload"]
    validate_url(upload["url"], r"(?:[a-z0-9.-]+\.)?s3(?:[.-][a-z0-9-]+)?\.amazonaws\.com")
    body, content_type = multipart(upload["fields"], args.image.name, data)
    print("Uploading one image directly to S3 using the signed form...", flush=True)
    with opener.open(Request(upload["url"], data=body,
                             headers={"Content-Type": content_type}, method="POST"), timeout=30):
        pass
    print("Job " + identifier + ": waiting for completion through the status API...", flush=True)
    job = poll_status(opener, session, args.region, url, identifier)
    directory = ROOT / "output/live-api" / identifier
    sizes = check_outputs(opener, job, directory)
    report = {"status": "PASS", "timestamp": datetime.now(timezone.utc).isoformat(),
              "api_url": url, "job_id": identifier, "job_status": job["status"],
              "unsigned_request_rejected": True, "sizes": sizes,
              "image_url": job["image_url"], "thumbnail_url": job["thumbnail_url"],
              "checks": ["IAM authentication", "presigned S3 POST", "job status API", "CloudFront JPEGs"]}
    (ROOT / "build").mkdir(exist_ok=True)
    (ROOT / "build/live-api-result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    print("Live test passed. Only one demo image was uploaded; no infrastructure was changed.")


if __name__ == "__main__":
    try:
        main()
    except DemoError as error:
        raise SystemExit(str(error))
    except HTTPError as error:
        code = error.code
        error.close()
        if code in (301, 302, 307, 308):
            raise SystemExit("Upload was redirected. Deploy the regional S3 presigner fix, then request a fresh upload form. No credentials were printed.")
        raise SystemExit(f"HTTP {code} during the demo. For 403 on the API, verify execute-api:Invoke permission. No credentials were printed.")
    except Exception as error:
        raise SystemExit("Live demo stopped (" + type(error).__name__ + "). No credentials were printed.")
