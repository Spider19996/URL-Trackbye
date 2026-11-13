import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'tools'))
sys.path.insert(0, ROOT)
import import_clearurls as ic  # noqa: E402
import trackbye  # noqa: E402

SAMPLE = {'providers': {
    'globalRules': {'urlPattern': '.*', 'rules': ['(?:%3F)?fbclid', '(?:%3F)?mc_(?:eid|cid|tc)', '(?:%3F)?utm(?:_[a-z_]*)?', 'a'],
                    'referralMarketing': ['(?:%3F)?ref_?']},
    'shop': {'urlPattern': r'^https?:\/\/(?:[a-z0-9-]+\.)*?shop(?:\.[a-z]{2,}){1,}', 'rules': ['trk_id', 'th', 'p[fd]_rd_[a-z]*']},
    'two': {'urlPattern': r'^https?:\/\/(?:[a-z0-9-]+\.)*?(one\.org|two\.net)', 'rules': ['visit_token']},
    'guarded': {'urlPattern': r'^https?:\/\/(?:[a-z0-9-]+\.)*?guarded\.com', 'rules': ['spy_id'], 'exceptions': [r'^https?:\/\/guarded\.com\/login']},
    'blocked': {'urlPattern': r'^https?:\/\/(?:[a-z0-9-]+\.)*?blocked\.com', 'rules': ['x_id'], 'completeProvider': True},
    'pathy': {'urlPattern': r'^https?:\/\/(?:[a-z0-9-]+\.)*?pathy\.com\/app', 'rules': ['p_id']},
}}


class Importer(unittest.TestCase):
    def test_only_safe_patterns_are_taken(self):
        rules, stats = ic.convert(SAMPLE)
        self.assertEqual(rules['global_remove'], ['fbclid', 'mc_eid', 'mc_cid', 'mc_tc'])  # no regex, no 1-letter, no ref
        names = {s['name']: s for s in rules['sites']}
        self.assertEqual(sorted(names), ['shop', 'two'])  # exceptions, complete-provider and path-scoped ones are skipped
        self.assertEqual(names['shop']['remove'], ['trk_id'])  # th is functional, the regex is skipped
        self.assertIn('shop.de', names['shop']['hosts'])
        self.assertEqual(names['two']['hosts'], ['one.org', 'two.net'])
        self.assertTrue(all(s['source'] == 'ClearURLs' for s in rules['sites']))

    def test_expand(self):
        self.assertEqual(ic.expand('(?:%3F)?gclid'), ['gclid'])
        self.assertEqual(ic.expand('fb_(?:source|ref)'), ['fb_source', 'fb_ref'])
        self.assertIsNone(ic.expand('utm(?:_[a-z_]*)?'))
        self.assertIsNone(ic.expand('wt_?z?mc'))


class ShippedRules(unittest.TestCase):
    def built(self):
        import build_rules
        doc, _ = build_rules.build(trackbye.shipped_rules(), SAMPLE, 'abc', today='2026-11-13')
        return doc

    def test_things_a_page_needs_survive(self):
        rules = self.built()
        keep = ['https://www.amazon.de/dp/B0?th=1&psc=1', 'https://www.youtube.com/watch?v=a&t=5&list=PL1',
                'https://www.google.com/search?q=hallo', 'https://github.com/o/r/tree/main?ref=dev', 'https://example.com/a?page=2&sort=asc']
        for url in keep:
            self.assertEqual(trackbye.clean_url(url, rules), url, url)

    def test_the_converted_names_clean(self):
        self.assertEqual(trackbye.clean_url('https://example.com/a?id=1&mc_tc=y&fbclid=z', self.built()), 'https://example.com/a?id=1')

    def test_the_built_list_is_valid_and_carries_its_sources(self):
        doc = self.built()
        self.assertEqual(trackbye.validate_rules(doc)['version'], 20261113)
        self.assertEqual([s['license'] for s in doc['sources']], ['GPL-3.0-or-later', 'LGPL-3.0'])

    def test_attribution_and_workflow_are_in_the_repository(self):
        for name in ('NOTICE.md', 'COPYING.LESSER', '.github/workflows/rules.yml'):
            self.assertTrue(os.path.exists(os.path.join(ROOT, name)), name)
        self.assertFalse(os.path.exists(os.path.join(ROOT, 'rules.clearurls.json')), 'the converted list is built outside the program')


if __name__ == '__main__':
    unittest.main()
