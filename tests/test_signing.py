import base64
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import sign_firefox  # noqa: E402


class Signing(unittest.TestCase):
    def test_jwt_is_a_valid_hs256_token(self):
        token = sign_firefox.make_jwt('user:1:2', 'topsecret', now=1000, lifetime=60)
        header, payload, signature = token.split('.')
        pad = lambda s: s + '=' * (-len(s) % 4)  # noqa: E731
        self.assertEqual(json.loads(base64.urlsafe_b64decode(pad(header))), {'alg': 'HS256', 'typ': 'JWT'})
        claims = json.loads(base64.urlsafe_b64decode(pad(payload)))
        self.assertEqual((claims['iss'], claims['iat'], claims['exp']), ('user:1:2', 1000, 1060))
        expected = hmac.new(b'topsecret', (header + '.' + payload).encode(), hashlib.sha256).digest()
        self.assertEqual(base64.urlsafe_b64decode(pad(signature)), expected)
        self.assertNotIn('topsecret', token)

    def test_multipart_contains_channel_and_file(self):
        body, ctype = sign_firefox.multipart({'channel': 'unlisted'}, 'x.zip', b'DATA')
        boundary = ctype.split('boundary=')[1].encode()
        self.assertIn(b'name="channel"\r\n\r\nunlisted', body)
        self.assertIn(b'filename="x.zip"', body)
        self.assertIn(b'DATA', body)
        self.assertTrue(body.endswith(b'--' + boundary + b'--\r\n'))

    def test_credentials_never_live_in_the_repository(self):
        self.assertTrue(os.path.abspath(sign_firefox.CREDENTIALS_FILE).startswith(os.path.expanduser('~')))
        self.assertFalse(os.path.abspath(sign_firefox.CREDENTIALS_FILE).startswith(os.path.abspath(ROOT)))
        ignored = open(os.path.join(ROOT, '.gitignore'), encoding='utf-8').read()
        for pattern in ('*.xpi', '.env', 'amo-credentials*', 'dist/'):
            self.assertIn(pattern, ignored)

    def test_no_tracked_file_contains_an_api_key(self):
        files = subprocess.run(['git', 'ls-files'], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
        pattern = re.compile(r'user:\d{4,}:\d+|AMO_JWT_' + r'SECRET=\S+')
        for name in files:
            path = os.path.join(ROOT, name)
            if name.endswith(('.png', '.zip')) or not os.path.isfile(path) or name in ('tests/test_signing.py', '.githooks/pre-commit'):  # these contain the patterns themselves
                continue
            text = open(path, encoding='utf-8', errors='ignore').read()
            self.assertIsNone(pattern.search(text), 'looks like a credential in ' + name)


if __name__ == '__main__':
    unittest.main()
