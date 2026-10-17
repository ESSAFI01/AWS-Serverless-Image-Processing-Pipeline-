"""Offline tests for the complete graduation-project pipeline."""
import base64
from io import BytesIO
import json
import os
from pathlib import Path
import socket
import unittest
from unittest.mock import Mock, patch
from urllib.parse import quote_plus

from PIL import Image
import pipeline_common as common
import upload_api
import workflow
import workflow_starter


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.streams = []
        self.posts = []

    def get_object(self, Bucket, Key, **kwargs):
        value = self.objects[(Bucket, Key)]
        body = BytesIO(value)
        self.streams.append(body)
        return {"Body": body, "ContentLength": len(value)}

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body

    def copy_object(self, Bucket, Key, CopySource, **kwargs):
        self.objects[(Bucket, Key)] = self.objects[(CopySource["Bucket"], CopySource["Key"])]

    def generate_presigned_post(self, **kwargs):
        self.posts.append(kwargs)
        return {"url": "https://mock-upload.invalid", "fields": {"key": kwargs["Key"]}}


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "SOURCE_BUCKET": "local-input", "DESTINATION_BUCKET": "local-output",
            "STATE_MACHINE_ARN": "arn:aws:states:eu-west-3:000000000000:stateMachine:mock",
            "METADATA_TABLE": "local-metadata", "NOTIFICATION_TOPIC_ARN": "mock-topic",
            "CLOUDFRONT_DOMAIN": "mock.cloudfront.net",
        }, clear=True)
        env.start()
        self.addCleanup(env.stop)
        block = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        block.start()
        self.addCleanup(block.stop)
        self.s3 = FakeS3()
        self.ddb = Mock()
        self.sns = Mock()
        self.sfn = Mock()
        clients = patch.dict(common._clients, {"s3": self.s3, "dynamodb": self.ddb,
                             "sns": self.sns, "stepfunctions": self.sfn}, clear=True)
        clients.start()
        self.addCleanup(clients.stop)
        buffer = BytesIO()
        Image.new("RGB", (1600, 800), "navy").save(buffer, "PNG")
        self.source_key = "uploads/café + sample.png"
        self.s3.objects[("local-input", self.source_key)] = buffer.getvalue()
        self.job = {"job_id": common.job_id("local-input", self.source_key),
                    "source_bucket": "local-input", "source_key": self.source_key,
                    "uploaded_at": "2026-10-17T10:00:00Z"}

    def message(self, key=None, identifier="one"):
        notification = {"Records": [{"eventSource": "aws:s3", "eventName": "ObjectCreated:Put",
            "eventTime": "2026-10-17T10:00:00Z",
            "s3": {"bucket": {"name": "local-input"},
                   "object": {"key": quote_plus(key or self.source_key)}}}]}
        return {"eventSource": "aws:sqs", "messageId": identifier, "body": json.dumps(notification)}

    def stage(self, action, job=None):
        return workflow.lambda_handler({"action": action, "job": job or self.job}, None)

    def test_complete_workflow_real_pillow_and_mocked_services(self):
        job = self.job
        for action in ("validate", "resize", "watermark", "store"):
            job = self.stage(action, job)
            self.assertLess(len(json.dumps(job)), 2048)
        self.assertEqual((job["width"], job["height"]), (1600, 800))
        for variant, expected in (("image", (1024, 512)), ("thumbnail", (256, 128))):
            key = job[variant + "_key"]
            with Image.open(BytesIO(self.s3.objects[("local-output", key)])) as image:
                self.assertEqual(image.format, "JPEG")
                self.assertEqual(image.size, expected)
                self.assertEqual(image.mode, "RGB")
                colors = image.crop((image.width // 2, image.height // 2,
                                     image.width, image.height)).getcolors(100000)
                self.assertGreater(len(colors), 1)
            self.assertEqual(job[variant + "_url"], "https://mock.cloudfront.net/" + key)
        self.assertTrue(all(stream.closed for stream in self.s3.streams))
        statuses = [call.kwargs["Item"]["status"]["S"] for call in self.ddb.put_item.call_args_list]
        self.assertEqual(statuses, ["PROCESSING", "COMPLETED"])
        self.assertEqual(json.loads(self.sns.publish.call_args.kwargs["Message"])["status"], "COMPLETED")

    def test_corrupt_image_failure_is_recorded_and_notified(self):
        self.s3.objects[("local-input", self.source_key)] = b"broken"
        with self.assertRaises(Exception):
            self.stage("validate")
        job = dict(self.job, failure={"Error": "UnidentifiedImageError", "Cause": "private details"})
        self.stage("fail", job)
        item = self.ddb.put_item.call_args.kwargs["Item"]
        self.assertEqual(item["status"]["S"], "FAILED")
        self.assertNotIn("private details", json.dumps(item))
        self.assertEqual(json.loads(self.sns.publish.call_args.kwargs["Message"])["status"], "FAILED")
        self.assertTrue(self.s3.streams[0].closed)

    def test_pixel_limit_is_enforced(self):
        with patch.object(workflow, "MAX_IMAGE_PIXELS", 100):
            with self.assertRaises(ValueError):
                self.stage("validate")
        self.ddb.put_item.assert_not_called()

    def test_oversized_download_is_closed(self):
        with patch.object(common, "MAX_IMAGE_BYTES", 2):
            with self.assertRaises(ValueError):
                self.stage("validate")
        self.assertTrue(self.s3.streams[0].closed)

    def test_invalid_job_identity_and_bucket_are_rejected(self):
        for change in ({"job_id": "0" * 64}, {"source_bucket": "other"},
                       {"source_key": "outside.png"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.stage("validate", dict(self.job, **change))
        self.assertEqual(self.s3.streams, [])

    def test_same_bucket_configuration_is_rejected(self):
        os.environ["DESTINATION_BUCKET"] = "local-input"
        with self.assertRaises(ValueError):
            self.stage("validate")

    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError):
            self.stage("erase")

    def test_dispatch_starts_workflow_with_decoded_key(self):
        result = workflow_starter.lambda_handler({"Records": [self.message()]}, None)
        self.assertEqual(result, {"batchItemFailures": []})
        args = self.sfn.start_execution.call_args.kwargs
        self.assertEqual(args["name"], "image-" + self.job["job_id"])
        self.assertEqual(json.loads(args["input"])["source_key"], self.source_key)

    def test_dispatch_failure_only_retries_failed_message(self):
        self.sfn.start_execution.side_effect = [RuntimeError("fake"), {}]
        result = workflow_starter.lambda_handler({"Records": [self.message(identifier="bad"),
                        self.message(key="uploads/second.png", identifier="good")]}, None)
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.assertEqual(self.sfn.start_execution.call_count, 2)

    def test_duplicate_execution_is_acknowledged(self):
        error = RuntimeError("already exists")
        error.response = {"Error": {"Code": "ExecutionAlreadyExists"}}
        self.sfn.start_execution.side_effect = error
        self.assertEqual(workflow_starter.lambda_handler({"Records": [self.message()]}, None),
                         {"batchItemFailures": []})

    def test_test_event_does_not_start_workflow(self):
        message = self.message()
        message["body"] = json.dumps({"Event": "s3:TestEvent"})
        self.assertEqual(workflow_starter.lambda_handler({"Records": [message]}, None),
                         {"batchItemFailures": []})
        self.sfn.start_execution.assert_not_called()

    def test_dispatch_rejects_wrong_bucket(self):
        record = self.message()
        value = json.loads(record["body"])
        value["Records"][0]["s3"]["bucket"]["name"] = "other"
        record["body"] = json.dumps(value)
        self.assertEqual(workflow_starter.lambda_handler({"Records": [record]}, None),
                         {"batchItemFailures": [{"itemIdentifier": "one"}]})
        self.sfn.start_execution.assert_not_called()

    def test_dispatch_validates_message_id(self):
        record = self.message()
        del record["messageId"]
        with self.assertRaises(ValueError):
            workflow_starter.lambda_handler({"Records": [record]}, None)

    def test_api_creates_unique_bounded_short_lived_upload(self):
        event = {"routeKey": "POST /uploads", "body": json.dumps({"filename": "../../photo.png"})}
        first = json.loads(upload_api.lambda_handler(event, None)["body"])
        second = json.loads(upload_api.lambda_handler(event, None)["body"])
        self.assertNotEqual(first["source_key"], second["source_key"])
        self.assertNotIn("..", first["source_key"])
        self.assertEqual(first["job_id"], common.job_id("local-input", first["source_key"]))
        params = self.s3.posts[0]
        self.assertEqual(params["ExpiresIn"], 300)
        self.assertIn(["content-length-range", 1, common.MAX_IMAGE_BYTES], params["Conditions"])
        self.assertEqual(params["Fields"]["Content-Type"], "image/png")

    def test_api_accepts_base64_body(self):
        result = upload_api.lambda_handler({"routeKey": "POST /uploads", "isBase64Encoded": True,
            "body": base64.b64encode(b'{"filename":"example.jpg"}').decode()}, None)
        self.assertEqual(result["statusCode"], 200)

    def test_api_rejects_unsupported_or_malformed_upload(self):
        for body in ('{"filename":"test.exe"}', '{invalid', '[]', '{"filename":123}'):
            with self.subTest(body=body):
                result = upload_api.lambda_handler({"routeKey": "POST /uploads", "body": body}, None)
                self.assertEqual(result["statusCode"], 400)
        self.assertEqual(self.s3.posts, [])

    def test_api_status_returns_typed_metadata(self):
        self.ddb.get_item.return_value = {"Item": {"job_id": {"S": self.job["job_id"]},
            "status": {"S": "COMPLETED"}, "width": {"N": "1600"}}}
        result = upload_api.lambda_handler({"routeKey": "GET /jobs/{job_id}",
            "pathParameters": {"job_id": self.job["job_id"]}}, None)
        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(json.loads(result["body"])["width"], 1600)
        self.assertEqual(result["headers"]["Cache-Control"], "no-store")

    def test_api_status_handles_missing_and_invalid_ids(self):
        self.ddb.get_item.return_value = {}
        for identifier, status in ((self.job["job_id"], 404), ("../bad", 400)):
            result = upload_api.lambda_handler({"routeKey": "GET /jobs/{job_id}",
                "pathParameters": {"job_id": identifier}}, None)
            self.assertEqual(result["statusCode"], status)

    def test_state_machine_definition_has_failure_paths_and_no_image_bytes(self):
        document = (Path(__file__).parent / "infra/workflow.asl.json.tftpl").read_text()
        states = json.loads(document)["States"]
        self.assertEqual([states[name]["Parameters"]["Payload"]["action"]
                          for name in ("Validate", "Resize", "Watermark", "Store")],
                         ["validate", "resize", "watermark", "store"])
        for name in ("Validate", "Resize", "Watermark", "Store"):
            self.assertEqual(states[name]["Catch"][0]["Next"], "RecordFailure")
            self.assertEqual(states[name]["Parameters"]["Payload"]["job.$"], "$")
        self.assertEqual(states["RecordFailure"]["Next"], "Failed")
        self.assertEqual(states["Failed"]["Type"], "Fail")


if __name__ == "__main__":
    unittest.main(verbosity=2)
