#!/usr/bin/env python3
# URL Trackbye - build the published rule list.
# Copyright (C) 2026 Robin Zimmermann
# SPDX-License-Identifier: GPL-3.0-or-later
"""Builds the rule list that the program downloads: our own rules (rules.json) + the converted ClearURLs names.

  python3 tools/build_rules.py                      download ClearURLs (hash checked), write build/rules.json
  python3 tools/build_rules.py --out DIR            write into DIR
  python3 tools/build_rules.py --clearurls-file F   use a local copy of the ClearURLs data

Besides rules.json the output folder gets NOTICE.md and COPYING.LESSER (the ClearURLs part stays under the LGPL-3.0).
The GitHub workflow .github/workflows/rules.yml runs this weekly and publishes the result on the branch "rules"; that
file is what the program downloads (DEFAULT_RULES_URL in trackbye.py).
"""
import hashlib
import json
import os
import shutil
import sys
import time

TOOLS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(TOOLS, '..')
sys.path.insert(0, TOOLS)
sys.path.insert(0, ROOT)
import import_clearurls  # noqa: E402
import trackbye  # noqa: E402


def build(own, clearurls_data, sha256, today=None):
    """The published document from our rules and the parsed ClearURLs data (pure, so it can be tested)."""
    community, stats = import_clearurls.convert(clearurls_data)
    today = today or time.strftime('%Y-%m-%d')
    doc = {
        'version': int(today.replace('-', '')),
        'built': today,
        'sources': [
            {'name': 'URL Trackbye rules', 'license': 'GPL-3.0-or-later', 'url': 'https://github.com/Spider19996/URL-Trackbye'},
            {'name': 'ClearURLs Rules (converted to exact names)', 'license': 'LGPL-3.0', 'url': 'https://github.com/ClearURLs/Rules',
             'sha256': sha256},
        ],
        'exclude_hosts': own.get('exclude_hosts', []),
        'global_remove': list(dict.fromkeys(own.get('global_remove', []) + community['global_remove'])),
        'sites': own.get('sites', []) + community['sites'],
    }
    return trackbye.validate_rules(doc), stats


def main():
    out = sys.argv[sys.argv.index('--out') + 1] if '--out' in sys.argv else os.path.join(ROOT, 'build')
    if '--clearurls-file' in sys.argv:
        raw = open(sys.argv[sys.argv.index('--clearurls-file') + 1], 'rb').read()
    else:
        raw = import_clearurls.fetch('data.minify.json')
        published = import_clearurls.fetch('rules.minify.hash').decode('ascii').strip()
        if hashlib.sha256(raw).hexdigest() != published:
            sys.exit('The ClearURLs download does not match its published hash; nothing was built.')
    doc, stats = build(trackbye.shipped_rules(), json.loads(raw), hashlib.sha256(raw).hexdigest())
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'rules.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
        f.write('\n')
    shutil.copyfile(os.path.join(ROOT, 'NOTICE.md'), os.path.join(out, 'NOTICE.md'))
    shutil.copyfile(os.path.join(ROOT, 'COPYING.LESSER'), os.path.join(out, 'COPYING.LESSER'))
    print('Built %s: version %s, %d global names, %d sites (ClearURLs: %d sites taken, %d skipped).' % (
        os.path.join(out, 'rules.json'), doc['version'], len(doc['global_remove']), len(doc['sites']),
        stats['sites_taken'], stats['sites_skipped']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
