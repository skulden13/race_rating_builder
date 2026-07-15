import base64
import json
import unittest
from unittest.mock import Mock

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from trail_rating_builder.providers.itra import ItraClient, decrypt_itra_payload


class ItraProviderTests(unittest.TestCase):
    def test_decrypts_itra_payload_shape(self):
        key = b"0123456789abcdef"
        iv = b"abcdef0123456789"
        plaintext = json.dumps({"ResultCount": 1, "Results": [{"Pi": 700}]}).encode()
        ciphertext = AES.new(key, AES.MODE_CBC, iv).encrypt(pad(plaintext, AES.block_size))
        payload = {
            "response1": base64.b64encode(ciphertext).decode(),
            "response2": base64.b64encode(iv).decode(),
            "response3": base64.b64encode(key).decode(),
        }
        self.assertEqual(decrypt_itra_payload(payload)["Results"][0]["Pi"], 700)

    def test_builds_runner_profile_url(self):
        client = ItraClient()
        self.assertEqual(client.profile_url({"RunnerId": 2}), "https://itra.run/RunnerSpace/2")
        self.assertEqual(client.profile_url({}), "")

    def test_stops_after_repeated_403(self):
        client = ItraClient(delay=0, max_403_retries=1)
        token_response = Mock(text='<input name="__RequestVerificationToken" value="token">')
        token_response.raise_for_status = Mock()
        forbidden_response = Mock(status_code=403)
        forbidden_response.raise_for_status = Mock()
        client.session = Mock()
        client.session.get.return_value = token_response
        client.session.post.return_value = forbidden_response

        with self.assertLogs("trail_rating_builder.providers.itra", level="WARNING"):
            with self.assertRaisesRegex(RuntimeError, "ITRA returned 403"):
                client.find_runner("SMITH Will")

        self.assertEqual(client.session.get.call_count, 2)
        self.assertEqual(client.session.post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
