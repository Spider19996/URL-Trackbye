#!/usr/bin/env python3
# URL Trackbye - import tracking parameter names from the ClearURLs rules database.
# Copyright (C) 2026 Robin Zimmermann
# SPDX-License-Identifier: GPL-3.0-or-later
"""Converts the ClearURLs rules (used by tools/build_rules.py) from the ClearURLs rules (https://github.com/ClearURLs/Rules, LGPL-3.0).

ClearURLs describes parameters with regular expressions. URL Trackbye (and the browser's declarativeNetRequest) removes
parameters by exact name, so only what converts safely is taken over:
  * plain names ("fbclid") and simple alternations ("mc_(?:eid|cid|tc)" -> mc_eid, mc_cid, mc_tc),
  * providers whose address pattern is a plain domain list (a missing top level domain is expanded to common ones),
  * only providers WITHOUT exceptions, complete-provider blocks or raw rules (those need more than names),
  * never names that are often functional (ref, source, th, ... see FUNCTIONAL) and never names shorter than 3 characters.
Everything else is skipped and counted, so nothing half-understood changes how a site behaves.

  python3 tools/import_clearurls.py                 download and show what would be taken over (writes nothing)
  python3 tools/import_clearurls.py --file data.json   the same with a local copy

The result stays under the LGPL-3.0 of ClearURLs (see NOTICE.md and COPYING.LESSER).
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
BASE = 'https://rules2.clearurls.xyz/'
TLDS = ['com', 'de', 'co.uk', 'fr', 'it', 'es', 'nl', 'pl', 'ca', 'com.au', 'co.jp', 'in', 'com.br', 'com.mx', 'se', 'ch', 'at', 'be', 'ie', 'dk', 'no', 'fi', 'pt', 'cz', 'ru']
# Names that are often needed by the page itself (search terms, language, product options, branches, ...).
FUNCTIONAL = {'ref', 'referrer', 'source', 'site', 'ie', 'sa', 'cd', 'cad', 'th', 'psc', 'keywords', 'query', 'id', 'page', 'url',
              'lang', 'language', 'dib', 'dib_tag', 'rnid', 'dchild', 'camp', 'creative', 'qualifier', 'field-lbr_brands_browse-bin',
              'tag', 'content-id', 'smid', 'sprefix', 'crid', 'linkcode'}
NAME = re.compile(r'^[A-Za-z0-9_\-]+$')
ALT = re.compile(r'^([A-Za-z0-9_\-]*)\(\?:([A-Za-z0-9_\-|]+)\)([A-Za-z0-9_\-]*)$')


def expand(pattern):
    """Exact names for a ClearURLs parameter pattern, or None if it is not a plain name / simple alternation."""
    p = pattern.replace('(?:%3F)?', '', 1) if pattern.startswith('(?:%3F)?') else pattern
    if NAME.match(p):
        return [p]
    m = ALT.match(p)
    if m:
        return [m.group(1) + a + m.group(3) for a in m.group(2).split('|')]
    return None


def usable(name):
    return len(name) >= 3 and name.lower() not in FUNCTIONAL


def hosts_of(url_pattern):
    """Domains a provider's address pattern stands for, or None when it is more than a plain domain list."""
    m = re.match(r'^\^https\?:\\/\\/\(\?:\[a-z0-9-\]\+\\\.\)\*\?(.*)$', url_pattern)
    if not m:
        return None
    rest = m.group(1)
    wildcard_tld = rest.endswith(r'(?:\.[a-z]{2,}){1,}')
    if wildcard_tld:
        rest = rest[:-len(r'(?:\.[a-z]{2,}){1,}')]
    group = re.match(r'^\(([A-Za-z0-9\\.\-|]+)\)$', rest)
    names = (group.group(1) if group else rest).split('|')
    if not all(re.match(r'^[A-Za-z0-9\\.\-]+$', n) for n in names):
        return None
    names = [n.replace('\\.', '.').lower() for n in names]
    if wildcard_tld:
        if len(names) != 1 or '.' in names[0]:
            return None
        return [names[0] + '.' + tld for tld in TLDS]
    return names


def convert(data):
    """(rules dict, statistics) from the parsed ClearURLs data."""
    providers = data['providers']
    stats = {'providers': len(providers), 'sites_taken': 0, 'sites_skipped': 0, 'names_taken': 0, 'patterns_skipped': 0}
    glob = providers.get('globalRules', {})
    global_names = []
    for pattern in glob.get('rules', []):
        names = expand(pattern)
        if names is None:
            stats['patterns_skipped'] += 1
            continue
        global_names += [n for n in names if usable(n)]
    sites = []
    for name, p in sorted(providers.items()):
        if name == 'globalRules':
            continue
        hosts = hosts_of(p.get('urlPattern', ''))
        if hosts is None or p.get('exceptions') or p.get('completeProvider') or p.get('rawRules'):
            stats['sites_skipped'] += 1
            continue
        found = []
        for pattern in list(p.get('rules', [])) + list(p.get('referralMarketing', [])):
            names = expand(pattern)
            if names is None:
                stats['patterns_skipped'] += 1
                continue
            found += [n for n in names if usable(n)]
        found = [n for n in dict.fromkeys(found) if n not in global_names]
        if not found:
            stats['sites_skipped'] += 1
            continue
        sites.append({'name': name, 'hosts': hosts, 'remove': found, 'source': 'ClearURLs'})
        stats['sites_taken'] += 1
        stats['names_taken'] += len(found)
    stats['names_taken'] += len(set(global_names))
    return {'global_remove': list(dict.fromkeys(global_names)), 'sites': sites}, stats


def fetch(name):
    request = urllib.request.Request(BASE + name, headers={'User-Agent': 'url-trackbye-import'})
    with urllib.request.urlopen(request, timeout=40) as r:
        return r.read()


def main():
    """Show what a conversion would take over (without writing anything); tools/build_rules.py builds the real list."""
    raw = open(sys.argv[sys.argv.index('--file') + 1], 'rb').read() if '--file' in sys.argv else fetch('data.minify.json')
    rules, stats = convert(json.loads(raw))
    print('%d global names, %d sites (%d names in total); skipped %d providers and %d complex patterns.' % (
        len(rules['global_remove']), stats['sites_taken'], stats['names_taken'], stats['sites_skipped'], stats['patterns_skipped']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
