import base64
import json
import unittest

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


if __name__ == "__main__":
    unittest.main()
