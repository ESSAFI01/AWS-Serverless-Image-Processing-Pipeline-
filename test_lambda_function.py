"""Offline integration tests: real Pillow processing, fake boto3/S3, no network."""
import copy
from io import BytesIO
import json
import os
import socket
import sys
import types
import unittest
from unittest.mock import Mock, patch

from PIL import Image
import lambda_function as handler


def notification(key="photos/my+image.png", **object_fields):
    return {"Records": [{
        "eventSource": "aws:s3", "eventName": "ObjectCreated:Put",
        "s3": {"bucket": {"name": "local-input"},
               "object": {"key": key, **object_fields}},
    }]}


def message(message_id, payload):
    return {"eventSource": "aws:sqs", "messageId": message_id,
            "body": json.dumps(payload)}


class LambdaTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "SOURCE_BUCKET": "local-input", "DESTINATION_BUCKET": "local-output"
        }, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch.object(socket.socket, "connect",
                                    side_effect=AssertionError("Network forbidden in tests"))
        self.network.start()
        self.addCleanup(self.network.stop)
        image = BytesIO()
        Image.new("RGB", (1600, 800), "navy").save(image, format="PNG")
        self.image_bytes = image.getvalue()
        self.s3 = Mock()
        self.streams = []

        def get_object(**kwargs):
            body = BytesIO(self.image_bytes)
            self.streams.append(body)
            return {"Body": body, "ContentLength": len(self.image_bytes)}

        self.s3.get_object.side_effect = get_object
        self.boto3 = types.ModuleType("boto3")
        self.boto3.client = Mock(return_value=self.s3)
        self.modules = patch.dict(sys.modules, {"boto3": self.boto3})
        self.modules.start()
        self.addCleanup(self.modules.stop)
        handler._s3_client = None
        self.addCleanup(setattr, handler, "_s3_client", None)

    def invoke(self, *messages):
        return handler.lambda_handler({"Records": list(messages)}, None)

    def test_real_processor_outputs_resized_watermarked_jpeg(self):
        result = self.invoke(message("one", notification()))
        self.assertEqual(result, {"batchItemFailures": []})
        self.boto3.client.assert_called_once_with("s3")
        self.s3.get_object.assert_called_once_with(Bucket="local-input", Key="photos/my image.png")
        kwargs = self.s3.put_object.call_args.kwargs
        self.assertEqual(kwargs["Bucket"], "local-output")
        self.assertEqual(kwargs["Key"], "processed/photos/my image.png.jpg")
        self.assertEqual(kwargs["ContentType"], "image/jpeg")
        with Image.open(BytesIO(kwargs["Body"])) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.size, (1024, 512))
            self.assertEqual(image.mode, "RGB")
            # The watermark changes pixels in an otherwise solid-color image.
            self.assertGreater(len(image.crop((800, 440, 1024, 512)).getcolors(100000)), 1)
        self.assertTrue(self.streams[0].closed)

    def test_only_failed_message_is_retried_and_batch_continues(self):
        self.s3.put_object.side_effect = [RuntimeError("fake failure"), None]
        result = self.invoke(message("bad", notification()), message("good", notification("next.png")))
        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.assertEqual(self.s3.put_object.call_count, 2)

    def test_malformed_json_is_reported(self):
        record = message("bad", {})
        record["body"] = "{invalid"
        self.assertEqual(self.invoke(record), {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.boto3.client.assert_not_called()

    def test_missing_s3_records_is_reported(self):
        self.assertEqual(self.invoke(message("bad", {})),
                         {"batchItemFailures": [{"itemIdentifier": "bad"}]})

    def test_test_event_is_acknowledged_without_aws(self):
        self.assertEqual(self.invoke(message("test", {"Event": "s3:TestEvent"})),
                         {"batchItemFailures": []})
        self.boto3.client.assert_not_called()

    def test_non_image_and_non_creation_events_are_skipped(self):
        deleted = notification()
        deleted["Records"][0]["eventName"] = "ObjectRemoved:Delete"
        self.assertEqual(self.invoke(message("txt", notification("notes.txt")),
                                     message("deleted", deleted)), {"batchItemFailures": []})
        self.boto3.client.assert_not_called()

    def test_unexpected_bucket_is_rejected_before_aws(self):
        event = notification()
        event["Records"][0]["s3"]["bucket"]["name"] = "other-input"
        self.assertEqual(self.invoke(message("bad", event)),
                         {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.boto3.client.assert_not_called()

    def test_same_bucket_and_missing_configuration_fail_before_aws(self):
        os.environ["DESTINATION_BUCKET"] = "local-input"
        with self.assertRaises(ValueError):
            self.invoke(message("one", notification()))
        del os.environ["SOURCE_BUCKET"]
        with self.assertRaises(KeyError):
            self.invoke(message("one", notification()))
        self.boto3.client.assert_not_called()

    def test_version_and_encoded_unicode_plus_key(self):
        self.invoke(message("one", notification("caf%C3%A9%2Bimage.PNG", versionId="v1")))
        self.s3.get_object.assert_called_once_with(Bucket="local-input", Key="café+image.PNG", VersionId="v1")

    def test_multiple_s3_records_and_replay_use_stable_distinct_keys(self):
        event = notification("photo.png")
        event["Records"].extend(notification("photo.jpg")["Records"])
        self.invoke(message("one", event))
        self.invoke(message("replay", copy.deepcopy(event)))
        keys = [call.kwargs["Key"] for call in self.s3.put_object.call_args_list]
        self.assertEqual(keys, ["processed/photo.png.jpg", "processed/photo.jpg.jpg"] * 2)
        self.boto3.client.assert_called_once()

    def test_corrupt_image_is_failed_and_body_closed(self):
        self.image_bytes = b"not an image"
        self.assertEqual(self.invoke(message("bad", notification())),
                         {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.assertTrue(self.streams[0].closed)
        self.s3.put_object.assert_not_called()

    def test_download_failure_is_reported(self):
        self.s3.get_object.side_effect = RuntimeError("fake download failure")
        self.assertEqual(self.invoke(message("bad", notification())),
                         {"batchItemFailures": [{"itemIdentifier": "bad"}]})
        self.s3.put_object.assert_not_called()

    def test_oversized_notification_is_rejected_before_download(self):
        self.assertEqual(self.invoke(message("large", notification(size=handler.MAX_IMAGE_BYTES + 1))),
                         {"batchItemFailures": [{"itemIdentifier": "large"}]})
        self.boto3.client.assert_not_called()

    def test_oversized_body_is_bounded_and_closed(self):
        with patch.object(handler, "MAX_IMAGE_BYTES", 4):
            stream = BytesIO(b"123456789")
            self.s3.get_object.side_effect = None
            self.s3.get_object.return_value = {"Body": stream}
            self.assertEqual(self.invoke(message("large", notification())),
                             {"batchItemFailures": [{"itemIdentifier": "large"}]})
        self.assertTrue(stream.closed)
        self.s3.put_object.assert_not_called()

    def test_reported_content_length_is_checked_and_body_closed(self):
        stream = BytesIO(b"abc")
        self.s3.get_object.side_effect = None
        self.s3.get_object.return_value = {"Body": stream, "ContentLength": handler.MAX_IMAGE_BYTES + 1}
        self.assertEqual(self.invoke(message("large", notification())),
                         {"batchItemFailures": [{"itemIdentifier": "large"}]})
        self.assertTrue(stream.closed)

    def test_empty_batch_and_invalid_envelope(self):
        self.assertEqual(self.invoke(), {"batchItemFailures": []})
        with self.assertRaises(ValueError):
            self.invoke({"eventSource": "aws:sqs", "body": "{}"})
        with self.assertRaises(ValueError):
            handler.lambda_handler({"Records": {}}, None)
        self.boto3.client.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
