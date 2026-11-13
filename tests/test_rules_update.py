import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
import trackbye  # noqa: E402

GOOD = {'version': 20260101, 'built': '2026-01-01', 'exclude_hosts': ['bank.example'], 'global_remove': ['fbclid', 'newtracker'],
        'sites': [{'name': 'Shop', 'hosts': ['shop.example'], 'remove': ['aff_id']}]}


class Handler(http.server.BaseHTTPRequestHandler):
    body = json.dumps(GOOD).encode()
    status = 200

    def do_GET(self):
        if self.status != 200:
            self.send_response(self.status)
            self.end_headers()
            return
        if self.headers.get('If-None-Match') == '"v1"':
            self.send_response(304)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('ETag', '"v1"')
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, *args):
        pass


class Validation(unittest.TestCase):
    def test_good_list_is_accepted(self):
        self.assertEqual(trackbye.validate_rules(GOOD)['global_remove'], ['fbclid', 'newtracker'])

    def test_anything_but_plain_names_is_refused(self):
        for bad in ({'global_remove': ['a b']}, {'global_remove': ['x' * 80]}, {'global_remove': [1]}, {'global_remove': 'fbclid'},
                    {'sites': [{'hosts': ['Evil.COM/path'], 'remove': ['a']}]}, {'sites': [{'hosts': ['a.com'], 'remove': ['(.*)']}]},
                    {'sites': 'x'}, [], 'text'):
            with self.assertRaises(ValueError, msg=str(bad)):
                trackbye.validate_rules(bad)


class Update(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        cfg = os.path.join(self.tmp.name, 'trackbye')
        self.patches = [mock.patch.object(trackbye, 'CONFIG_DIR', cfg),
                        mock.patch.object(trackbye, 'RULES_DOWNLOADED', os.path.join(cfg, 'rules.downloaded.json')),
                        mock.patch.object(trackbye, 'RULES_META', os.path.join(cfg, 'rules.meta.json')),
                        mock.patch.object(trackbye, 'STATE_DIR', os.path.join(self.tmp.name, 'state')),
                        mock.patch.object(trackbye, 'EVENTS_PATH', os.path.join(self.tmp.name, 'state', 'events.jsonl'))]
        for p in self.patches:
            p.start()
        Handler.status = 200
        Handler.body = json.dumps(GOOD).encode()
        self.server = http.server.HTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = 'http://127.0.0.1:%d/rules.json' % self.server.server_port
        trackbye.save_config({'rules_url': self.url, 'rules_auto': True})

    def tearDown(self):
        self.server.shutdown()
        for p in self.patches:
            p.stop()
        self.tmp.cleanup()

    def test_download_is_used_instead_of_the_shipped_list(self):
        self.assertNotIn('newtracker', trackbye.builtin_rules()['global_remove'])
        self.assertEqual(trackbye.rules_update()[0], 'updated')
        rules = trackbye.builtin_rules()
        self.assertIn('newtracker', rules['global_remove'])
        self.assertEqual(trackbye.clean_url('https://shop.example/x?aff_id=1&b=2', rules), 'https://shop.example/x?b=2')
        self.assertEqual(trackbye.rules_info()['source'], 'downloaded')

    def test_second_call_is_a_cheap_not_modified(self):
        trackbye.rules_update()
        self.assertEqual(trackbye.rules_update()[0], 'unchanged')

    def test_manipulated_list_is_refused_and_the_old_one_stays(self):
        trackbye.rules_update()
        Handler.body = json.dumps({'global_remove': ['ok', 'rm -rf /']}).encode()
        status, message = trackbye.rules_update(force=True)
        self.assertEqual(status, 'error')
        self.assertIn('newtracker', trackbye.builtin_rules()['global_remove'])

    def test_missing_list_is_reported_and_the_shipped_one_is_used(self):
        Handler.status = 404
        status, message = trackbye.rules_update()
        self.assertEqual(status, 'error')
        self.assertIn('has been published', message)
        self.assertEqual(trackbye.rules_info()['source'], 'shipped')

    def test_only_https_or_localhost(self):
        trackbye.save_config({'rules_url': 'http://example.com/rules.json'})
        self.assertEqual(trackbye.rules_update()[0], 'error')

    def test_reset_goes_back_to_the_shipped_list(self):
        trackbye.rules_update()
        trackbye.rules_reset()
        self.assertEqual(trackbye.rules_info()['source'], 'shipped')

    def test_due_only_when_switched_on_and_older_than_a_day(self):
        self.assertTrue(trackbye.rules_due())
        trackbye.rules_update()
        self.assertFalse(trackbye.rules_due())
        trackbye.save_config({'rules_url': self.url, 'rules_auto': False})
        self.assertFalse(trackbye.rules_due())


if __name__ == '__main__':
    unittest.main()
