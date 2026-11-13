#!/usr/bin/env python3
"""Build the zip files for the browser stores: dist/url-trackbye-firefox-<version>.zip and ...-chrome-<version>.zip.

The folder extension/ works unpacked in both browsers. A store upload wants a manifest without the other browser's
keys, so this tool writes one manifest per store into the zip.
  Firefox: upload the zip at https://addons.mozilla.org/developers/ (choose "On your own" = unlisted: signed in minutes,
           you get a .xpi that stays installed). Or: web-ext sign --channel=unlisted --source-dir <unpacked copy>.
  Chrome:  upload at https://chrome.google.com/webstore/devconsole (one-time fee, review).
"""
import json
import os
import sys
import zipfile

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXT = os.path.join(ROOT, 'extension')
DIST = os.path.join(ROOT, 'dist')
SKIP = {'manifest.json', 'released.json', 'package.json'}


def manifests():
    base = json.load(open(os.path.join(EXT, 'manifest.json'), encoding='utf-8'))
    firefox = json.loads(json.dumps(base))
    firefox.pop('key', None)
    firefox.pop('minimum_chrome_version', None)
    firefox['background'] = {'scripts': ['background.js'], 'type': 'module'}
    firefox['browser_specific_settings']['gecko']['data_collection_permissions'] = {'required': ['none']}
    firefox['browser_specific_settings']['gecko_android'] = {'strict_min_version': '142.0'}
    chrome = json.loads(json.dumps(base))
    chrome.pop('browser_specific_settings', None)
    chrome['background'] = {'service_worker': 'background.js', 'type': 'module'}
    return {'firefox': firefox, 'chrome': chrome}


def main():
    os.makedirs(DIST, exist_ok=True)
    for target, manifest in manifests().items():
        path = os.path.join(DIST, 'url-trackbye-%s-%s.zip' % (target, manifest['version']))
        with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json', json.dumps(manifest, indent=2) + '\n')
            for folder, _, files in os.walk(EXT):
                for name in sorted(files):
                    full = os.path.join(folder, name)
                    rel = os.path.relpath(full, EXT)
                    if name in SKIP and rel == name:
                        continue
                    z.write(full, rel)
        print('Wrote ' + os.path.relpath(path, ROOT))
    return 0


if __name__ == '__main__':
    sys.exit(main())
