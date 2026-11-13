import os
import subprocess
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')


class InstallScript(unittest.TestCase):
    def run_in(self, home, *args):
        env = {k: v for k, v in os.environ.items() if not k.startswith(('XDG_', 'QT_'))}
        env.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, '.config'), XDG_STATE_HOME=os.path.join(home, '.local', 'state'))
        return subprocess.run(['sh', os.path.join(ROOT, 'install.sh'), *args], env=env, capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=60)

    def test_install_and_uninstall_leave_nothing_behind(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, '.config', 'vivaldi'))      # a "found" Chrome-like browser
            os.makedirs(os.path.join(home, '.mozilla', 'firefox'))     # a "found" Firefox
            done = self.run_in(home, '--autostart', '--native', '--link')
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            expected = [
                '.local/share/applications/trackbye-app.desktop',
                '.config/autostart/trackbye.desktop',
                '.local/bin/trackbye',
                '.config/vivaldi/NativeMessagingHosts/de.trackbye.host.json',
                '.mozilla/native-messaging-hosts/de.trackbye.host.json',
            ]
            for path in expected:
                self.assertTrue(os.path.lexists(os.path.join(home, path)), 'missing ' + path)
            with open(os.path.join(home, '.config/autostart/trackbye.desktop'), encoding='utf-8') as f:
                self.assertIn('--background', f.read())
            gone = self.run_in(home, '--uninstall')
            self.assertEqual(gone.returncode, 0, gone.stdout + gone.stderr)
            for path in expected:
                self.assertFalse(os.path.lexists(os.path.join(home, path)), 'left behind: ' + path)

    def test_unknown_option_is_refused(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(self.run_in(home, '--nonsense').returncode, 2)


if __name__ == '__main__':
    unittest.main()
