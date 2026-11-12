#!/usr/bin/env python3
"""Keeps the extension version honest: it must change exactly when the extension's files change.

  python3 tools/extension_version.py check   exit 1 if files changed without a version bump (or the other way round)
  python3 tools/extension_version.py stamp   record the current files and version as the released state

The program compares only this version with the one the browser runs, so a change that does not touch the extension
never asks you to reload it. rules.json is left out: the program delivers the rules itself.
"""
import hashlib
import json
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
EXT = os.path.join(ROOT, 'extension')
STATE = os.path.join(EXT, 'released.json')
SKIP = {'rules.json', 'released.json', 'package.json'}


def current():
    """(version, hash of all extension files except the version number itself)."""
    h = hashlib.sha256()
    manifest = json.load(open(os.path.join(EXT, 'manifest.json'), encoding='utf-8'))
    version = manifest.pop('version')
    for folder, _, files in sorted(os.walk(EXT)):
        for name in sorted(files):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, EXT)
            if name in SKIP or '__pycache__' in rel:
                continue
            h.update(rel.encode('utf-8') + b'\0')
            h.update(json.dumps(manifest, sort_keys=True).encode('utf-8') if rel == 'manifest.json' else open(path, 'rb').read())
    return version, h.hexdigest()


def problem():
    """None if everything is consistent, else a message for the developer."""
    version, digest = current()
    try:
        released = json.load(open(STATE, encoding='utf-8'))
    except (OSError, ValueError):
        return 'extension/released.json is missing: run python3 tools/extension_version.py stamp'
    changed = digest != released.get('hash')
    if changed and version == released.get('version'):
        return ('The extension files changed but the version is still %s: bump "version" in extension/manifest.json, '
                'then run python3 tools/extension_version.py stamp' % version)
    if not changed and version != released.get('version'):
        return ('The extension version changed to %s but no extension file did: revert the version, or run '
                'python3 tools/extension_version.py stamp if this is intended' % version)
    if changed:
        return 'New extension version %s: run python3 tools/extension_version.py stamp to record it' % version
    return None


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    if cmd == 'stamp':
        version, digest = current()
        with open(STATE, 'w', encoding='utf-8') as f:
            json.dump({'version': version, 'hash': digest}, f, indent=2)
            f.write('\n')
        print('Recorded extension version ' + version)
        return 0
    msg = problem()
    print(msg or 'Extension version is consistent.')
    return 1 if msg else 0


if __name__ == '__main__':
    sys.exit(main())
