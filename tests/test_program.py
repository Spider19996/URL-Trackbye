import json
import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, ROOT)
import trackbye  # noqa: E402


class ProgramParts(unittest.TestCase):
    def test_everything_tray_uses_exists(self):
        """tray.py calls trackbye functions by name; a missing one would only show up when the window opens."""
        source = open(os.path.join(ROOT, 'tray.py'), encoding='utf-8').read()
        for name in set(re.findall(r'\btb\.([A-Za-z_]\w*)', source)):
            self.assertTrue(hasattr(trackbye, name), 'trackbye has no ' + name)

    def test_native_host_answers_and_remembers_the_extension_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, XDG_STATE_HOME=tmp, XDG_CONFIG_HOME=tmp)
            proc = subprocess.Popen([os.path.join(ROOT, 'trackbye.py'), 'chrome-extension://x/'], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, env=env)

            def ask(msg):
                data = json.dumps(msg).encode()
                proc.stdin.write(struct.pack('=I', len(data)) + data)
                proc.stdin.flush()
                size = struct.unpack('=I', proc.stdout.read(4))[0]
                return json.loads(proc.stdout.read(size))

            self.assertTrue(ask({'type': 'hello', 'ext': '0.0.1'})['ok'])
            self.assertIn('sites', ask({'type': 'rules', 'ext': '0.0.1'})['rules'])
            self.assertEqual(ask({'type': 'clean', 'url': 'https://a.com/?utm_source=x&b=1'})['url'], 'https://a.com/?b=1')
            proc.stdin.close()
            self.assertEqual(proc.wait(timeout=10), 0)
            with open(os.path.join(tmp, 'trackbye', 'extension.json'), encoding='utf-8') as f:
                self.assertEqual(json.load(f)['version'], '0.0.1')


if __name__ == '__main__':
    unittest.main()
