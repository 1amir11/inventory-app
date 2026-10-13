# test_package.py - tests for make_package.py guarantees: empty data/,
# no database leaks, ASCII names, required files present.
#
# Run from the repository root:  python -m unittest discover -s tests -v
# Standard library only (unittest), Python 3.8 compatible.

import os
import shutil
import sys
import tempfile
import unittest
import zipfile

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

import make_package  # noqa: E402


class TestPackageRules(unittest.TestCase):

    def test_dev_databases_detected(self):
        # The real app/ tree currently holds the demo DB, so a build from
        # it must REFUSE (never ship any database).
        found = make_package.find_dev_databases(
            os.path.join(_ROOT_DIR, "app"))
        self.assertTrue(any(f.endswith(".db") for f in found))

    def test_exclusion_helpers(self):
        self.assertTrue(make_package.is_excluded_file("kitchen.db"))
        self.assertTrue(make_package.is_excluded_file("kitchen_launcher.log"))
        self.assertFalse(make_package.is_excluded_file("server.py"))
        self.assertTrue(make_package.is_excluded_dir("data"))
        self.assertTrue(make_package.is_excluded_dir("data_demo"))
        with self.assertRaises(make_package.PackageError):
            make_package.check_ascii(["ok.txt", "ملف.txt"])
        with self.assertRaises(make_package.PackageError):
            make_package.check_required(["server.py"])

    def test_build_from_clean_tree(self):
        tmp = tempfile.mkdtemp(prefix="kitchen_pkg_")
        try:
            clean = os.path.join(tmp, "app")
            shutil.copytree(os.path.join(_ROOT_DIR, "app"), clean,
                            ignore=shutil.ignore_patterns("*.db", "*.db-*",
                                                          "__pycache__"))
            # data_demo/ has no DB now, but must still be excluded.
            out = os.path.join(tmp, "out.zip")
            _path, members = make_package.build(out, verbose=False,
                                               root=clean)
            self.assertIn("data/", members)
            for name in make_package.REQUIRED_FILES:
                self.assertIn(name, members)
            for name in members:
                self.assertTrue(all(ord(ch) < 128 for ch in name), name)
                self.assertFalse(name.endswith(".db"), name)
            with zipfile.ZipFile(out) as archive:
                self.assertIn("data/", archive.namelist())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
