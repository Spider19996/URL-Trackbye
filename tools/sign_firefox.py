#!/usr/bin/env python3
# URL Trackbye - sign the Firefox extension with Mozilla (unlisted channel).
# Copyright (C) 2026 Robin Zimmermann
# SPDX-License-Identifier: GPL-3.0-or-later
"""Signs the Firefox build of the extension through the addons.mozilla.org API and saves the signed .xpi in dist/.

Unlisted means: Mozilla checks and signs the file automatically; nothing is published on the add-on site.

Credentials (API key from https://addons.mozilla.org/developers/addon/api/key/) are NEVER stored in this repository:
  * environment variables AMO_JWT_ISSUER and AMO_JWT_SECRET, or
  * the file ~/.config/trackbye/amo-credentials.json (outside the project), content:
        {"issuer": "user:NNNNN:NN", "secret": "..."}
    It must only be readable by you (chmod 600); the tool refuses to use it otherwise.
The secret is only used to sign a short-lived token and is never printed.

  python3 tools/sign_firefox.py --dry-run     check credentials and package, send nothing
  python3 tools/sign_firefox.py               upload, wait for the signature, download dist/url-trackbye-<version>.xpi
"""
import base64
import hashlib
import hmac
import json
import os
import stat
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import package_extension  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
API = 'https://addons.mozilla.org/api/v5/addons/'
CREDENTIALS_FILE = os.path.join(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config')), 'trackbye', 'amo-credentials.json')


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def make_jwt(issuer, secret, now=None, lifetime=60):
    """HS256 token as the add-ons API wants it (short-lived, one per request)."""
    now = int(now if now is not None else time.time())
    header = b64url(json.dumps({'alg': 'HS256', 'typ': 'JWT'}, separators=(',', ':')).encode())
    payload = b64url(json.dumps({'iss': issuer, 'jti': str(uuid.uuid4()), 'iat': now, 'exp': now + lifetime},
                                separators=(',', ':')).encode())
    signature = hmac.new(secret.encode('utf-8'), (header + '.' + payload).encode('ascii'), hashlib.sha256).digest()
    return header + '.' + payload + '.' + b64url(signature)


def load_credentials():
    issuer, secret = os.environ.get('AMO_JWT_ISSUER'), os.environ.get('AMO_JWT_SECRET')
    if issuer and secret:
        return issuer.strip(), secret.strip()
    try:
        mode = os.stat(CREDENTIALS_FILE).st_mode
    except OSError:
        sys.exit('No credentials found. Put {"issuer": "...", "secret": "..."} into %s (chmod 600) or set AMO_JWT_ISSUER and '
                 'AMO_JWT_SECRET. Get the key at https://addons.mozilla.org/developers/addon/api/key/' % CREDENTIALS_FILE)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        sys.exit('%s can be read by others. Run: chmod 600 %s' % (CREDENTIALS_FILE, CREDENTIALS_FILE))
    data = json.load(open(CREDENTIALS_FILE, encoding='utf-8'))
    issuer, secret = str(data.get('issuer', '')).strip(), str(data.get('secret', '')).strip()
    if not issuer or not secret or 'PASTE' in issuer + secret:
        sys.exit('%s is not filled in yet (issuer and secret).' % CREDENTIALS_FILE)
    return issuer, secret


def multipart(fields, filename, content):
    boundary = uuid.uuid4().hex
    body = b''
    for name, value in fields.items():
        body += ('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (boundary, name, value)).encode()
    body += ('--%s\r\nContent-Disposition: form-data; name="upload"; filename="%s"\r\nContent-Type: application/zip\r\n\r\n'
             % (boundary, filename)).encode() + content + ('\r\n--%s--\r\n' % boundary).encode()
    return body, 'multipart/form-data; boundary=' + boundary


def request(method, url, issuer, secret, body=None, content_type=None):
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header('Authorization', 'JWT ' + make_jwt(issuer, secret))
    req.add_header('User-Agent', 'url-trackbye-signing')
    if content_type:
        req.add_header('Content-Type', content_type)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def main():
    dry = '--dry-run' in sys.argv
    manifest = package_extension.manifests()['firefox']
    guid, version = manifest['browser_specific_settings']['gecko']['id'], manifest['version']
    package_extension.main()
    zip_path = os.path.join(package_extension.DIST, 'url-trackbye-firefox-%s.zip' % version)
    issuer, secret = load_credentials()
    print('Credentials found (not shown). Extension %s version %s.' % (guid, version))
    if dry:
        print('Dry run: package is ready (%s), nothing was sent.' % os.path.relpath(zip_path, ROOT))
        return 0
    content = open(zip_path, 'rb').read()
    url = API + '%s/versions/%s/' % (urllib.request.quote(guid), version)
    body, ctype = multipart({'channel': 'unlisted'}, os.path.basename(zip_path), content)
    print('Uploading to Mozilla (unlisted, nothing is published) ...')
    status, answer = request('PUT', url, issuer, secret, body, ctype)
    if status >= 300:
        sys.exit('Upload refused (HTTP %d): %s' % (status, answer.decode('utf-8', 'replace')[:600]))
    for _ in range(60):  # up to about 5 minutes
        time.sleep(5)
        status, answer = request('GET', url, issuer, secret)
        info = json.loads(answer or b'{}') if status < 300 else {}
        files = info.get('files') or []
        if files and files[0].get('signed') and files[0].get('download_url'):
            dest = os.path.join(package_extension.DIST, 'url-trackbye-%s.xpi' % version)
            code, data = request('GET', files[0]['download_url'], issuer, secret)
            if code >= 300:
                sys.exit('Download failed (HTTP %d).' % code)
            open(dest, 'wb').write(data)
            print('Signed. Saved ' + os.path.relpath(dest, ROOT))
            return 0
        if info.get('processed') and not info.get('valid', True):
            sys.exit('Mozilla rejected the package: %s' % json.dumps(info.get('validation_results', info), indent=1)[:900])
        print('  waiting for the signature ...')
    sys.exit('Timed out waiting for the signature; check https://addons.mozilla.org/developers/')


if __name__ == '__main__':
    sys.exit(main())
