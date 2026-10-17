# Live demonstration evidence

Date: 2026-10-17. Region: eu-west-3. Results were supplied by the user from their
AWS CLI session and browser. No passwords, access keys, signing headers, or
presigned form fields are recorded here.

## Confirmed results

| Check | Result |
|---|---|
| Initial infrastructure creation | 43 added, 0 changed, 0 destroyed |
| Enable processing and delivery | 0 added, 2 changed, 0 destroyed |
| Step Functions execution | SUCCEEDED |
| DynamoDB status | COMPLETED |
| Source dimensions | 2400 x 1600 |
| Main output | image.jpg, 18,752 bytes |
| Thumbnail output | thumbnail.jpg, 4,971 bytes |
| CloudFront | Both images load; Cloud & AI watermark confirmed by the user |
| API Gateway authentication | Unsigned rejected; IAM-signed upload request succeeded |
| Presigned S3 POST and API status | PASS after deploying the regional endpoint correction |

Sample job ID:

    51f9a0497141b637550c70ce543b9873d2b95b210ad3d6521bc2538177864729

- [Processed image](https://d3mu8ybos1wp84.cloudfront.net/processed/51f9a0497141b637550c70ce543b9873d2b95b210ad3d6521bc2538177864729/image.jpg)
- [Thumbnail](https://d3mu8ybos1wp84.cloudfront.net/processed/51f9a0497141b637550c70ce543b9873d2b95b210ad3d6521bc2538177864729/thumbnail.jpg)

These URLs are temporary demo evidence. Object lifecycle expiry and later cleanup
will make them unavailable. A recorded video or screenshots can retain evidence
without keeping AWS resources running. No recording has been created by this task.

## Suggested short recording

Show the architecture diagram, one sample upload, the Standard workflow's four
successful steps, the COMPLETED metadata record, and both watermarked results.
After the live API check, also show its PASS report. Use the prepared sample image.
SNS has no subscribers; the successful Store task includes publishing the completion
event, but no external email or SMS delivery is claimed.

## API-driven demonstration

The complete client reported PASS at 2026-10-17T01:01:07.043422+00:00:

- Job ID: e29144fc3722aa7ca68d11de20410f27d05a764fe2a104efab04293368f03390
- IAM-signed API request: accepted; unsigned request: rejected.
- Presigned S3 POST: succeeded.
- Status API: COMPLETED.
- Main JPEG: 1024 x 683. Thumbnail: 256 x 171.
- Both CloudFront JPEGs downloaded and decoded successfully.

[Safe JSON report](evidence/live-api-result.json) · [Main image](evidence/image.jpg)
· [Thumbnail](evidence/thumbnail.jpg)

The saved report contains no credentials or signed upload form fields. It records
a successful demonstration, not a guarantee that endpoints remain online after
cleanup. See [cleanup instructions](cleanup.md).
