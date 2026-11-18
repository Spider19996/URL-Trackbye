import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


class ConcurrentLogging(unittest.TestCase):
    """The browser starts one helper per message, the clipboard helper runs at the same time: they all write the same
    log files. This used to fail with "No such file or directory: log.jsonl.tmp" and lost entries."""

    def test_many_programs_log_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, HOME=tmp, XDG_STATE_HOME=os.path.join(tmp, 's'), XDG_CONFIG_HOME=os.path.join(tmp, 'c'))
            code = ("import sys; sys.path.insert(0, %r); import trackbye as tb\n"
                    "n = sys.argv[1]\n"
                    "for i in range(25):\n"
                    "    tb.log_event('clipboard', 'https://a.com/%%s/%%d?utm_source=x&id=1' %% (n, i), 'https://a.com/%%s/%%d?id=1' %% (n, i))\n"
                    "    tb.diag('info', 'message %%s %%d' %% (n, i))\n") % ROOT
            procs = [subprocess.Popen([sys.executable, '-c', code, str(k)], env=env, stderr=subprocess.PIPE) for k in range(8)]
            errors = b''.join(p.communicate()[1] for p in procs)
            self.assertEqual(errors, b'', errors.decode())
            state = os.path.join(tmp, 's', 'trackbye')
            with open(os.path.join(state, 'log.jsonl'), encoding='utf-8') as f:
                log = [json.loads(line) for line in f]
            with open(os.path.join(state, 'events.jsonl'), encoding='utf-8') as f:
                events = [json.loads(line) for line in f]
            self.assertEqual(len(log), 8 * 25)       # nothing lost
            self.assertEqual(sum(e['count'] for e in events), 8 * 25)
            self.assertEqual([f for f in os.listdir(state) if f.endswith('.tmp')], [])  # no leftovers


if __name__ == '__main__':
    unittest.main()
