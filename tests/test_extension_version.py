import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'tools'))
import extension_version  # noqa: E402


class ExtensionVersion(unittest.TestCase):
    def test_version_changes_exactly_when_the_extension_changes(self):
        self.assertIsNone(extension_version.problem())


if __name__ == '__main__':
    unittest.main()
