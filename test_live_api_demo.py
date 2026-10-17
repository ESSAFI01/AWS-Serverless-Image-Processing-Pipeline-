"""Offline checks for the live-demo client's HTTP and credential-handling boundaries."""
from io import BytesIO
import tempfile
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError

from PIL import Image
from scripts import live_api_demo as demo


class DemoClientTests(unittest.TestCase):
    def setUp(self):
        network = patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden"))
        network.start()
        self.addCleanup(network.stop)

    def test_endpoint_validation_rejects_unsafe_urls(self):
        pattern = r"[a-z0-9]+\.execute-api\.eu-west-3\.amazonaws\.com"
        demo.validate_url("https://abc123.execute-api.eu-west-3.amazonaws.com", pattern)
        for url in ("http://abc123.execute-api.eu-west-3.amazonaws.com",
                    "https://abc123.execute-api.eu-west-3.amazonaws.com.attacker.invalid",
                    "https://user:password@abc123.execute-api.eu-west-3.amazonaws.com",
                    "https://abc123.execute-api.eu-west-3.amazonaws.com?secret=value"):
            with self.subTest(url=url), self.assertRaises(demo.DemoError):
                demo.validate_url(url, pattern)

    def test_redirects_do_not_forward_signed_requests(self):
        handler = demo.NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 307, "redirect", {},
                                                  "https://other.invalid"))

    def test_multipart_preserves_binary_and_places_file_last(self):
        body, content_type = demo.multipart({"key": "uploads/example.jpg", "Content-Type": "image/jpeg",
                                             "policy": "fake-policy"}, 'photo"\r\n.jpg', b"\x00\xffimage")
        self.assertTrue(content_type.startswith("multipart/form-data; boundary="))
        self.assertIn(b"\x00\xffimage", body)
        self.assertLess(body.index(b'name="policy"'), body.index(b'name="file"'))
        self.assertIn(b'filename="photo___.jpg"', body)
        self.assertTrue(body.endswith(b"--\r\n"))

    def test_multipart_rejects_header_injection(self):
        for fields in ({"bad\r\nheader": "value"}, {"Content-Type": "image/jpeg\r\nInjected: value"}):
            with self.assertRaises(demo.DemoError):
                demo.multipart(fields, "image.jpg", b"image")

    def test_unsigned_403_is_expected_but_200_is_failure(self):
        opener = Mock()
        opener.open.side_effect = HTTPError("https://mock.invalid", 403, "Forbidden", {}, BytesIO())
        demo.reject_unsigned(opener, "https://mock.invalid/uploads", "image.jpg")
        opener = Mock()
        opener.open.return_value = MagicMock()
        with self.assertRaises(demo.DemoError):
            demo.reject_unsigned(opener, "https://mock.invalid/uploads", "image.jpg")

    def test_poll_handles_not_started_processing_and_completion(self):
        error = HTTPError("https://mock.invalid", 404, "Not found", {}, BytesIO())
        with patch.object(demo, "signed_json", side_effect=[error, {"status": "PROCESSING"},
                         {"status": "COMPLETED"}]), patch.object(demo.time, "sleep"):
            result = demo.poll_status(None, None, "eu-west-3", "https://mock.invalid", "job")
        self.assertEqual(result["status"], "COMPLETED")

    def test_missing_crt_reports_install_command_without_credentials(self):
        class MissingDependency(Exception):
            pass

        modules = {
            "botocore.auth": SimpleNamespace(SigV4Auth=Mock()),
            "botocore.awsrequest": SimpleNamespace(AWSRequest=Mock()),
            "botocore.exceptions": SimpleNamespace(MissingDependencyException=MissingDependency),
        }
        session = Mock()
        session.get_credentials.side_effect = MissingDependency("private credential-provider details")
        opener = Mock()
        with patch.dict(sys.modules, modules):
            with self.assertRaises(demo.DemoError) as caught:
                demo.signed_json(opener, session, "eu-west-3", "POST", "https://mock.invalid")
        self.assertIn("boto3[crt]", str(caught.exception))
        self.assertNotIn("private", str(caught.exception))
        opener.open.assert_not_called()

    def test_cloudfront_outputs_are_validated_and_saved(self):
        identifier = "a" * 64
        job = {"job_id": identifier}
        responses = []
        for variant, size in (("image", (1024, 683)), ("thumbnail", (256, 171))):
            job[variant + "_url"] = "https://demo.cloudfront.net/processed/" + identifier + "/" + variant + ".jpg"
            data = BytesIO()
            Image.new("RGB", size, "navy").save(data, "JPEG")
            response = MagicMock()
            response.__enter__.return_value = response
            response.headers.get_content_type.return_value = "image/jpeg"
            response.read.return_value = data.getvalue()
            responses.append(response)
        opener = Mock()
        opener.open.side_effect = responses
        with tempfile.TemporaryDirectory() as directory:
            sizes = demo.check_outputs(opener, job, Path(directory))
            self.assertEqual(sizes["thumbnail"], [256, 171])
            self.assertTrue((Path(directory) / "image.jpg").is_file())
            self.assertTrue((Path(directory) / "thumbnail.jpg").is_file())


if __name__ == "__main__":
    unittest.main()
