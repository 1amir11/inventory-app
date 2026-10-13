# test_package.py - tests for make_package.py guarantees: empty data/,
# no database leaks, ASCII names, required files + runtime present, no
# external URLs, path lengths, refusal rules, sha256 sidecar.
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


def make_tree(tmp, with_runtime=True):
    """Copy app/ to tmp/app minus DBs/caches; optionally stub the runtime
    (empty files with the required names - only presence is checked)."""
    clean = os.path.join(tmp, "app")
    shutil.copytree(os.path.join(_ROOT_DIR, "app"), clean,
                    ignore=shutil.ignore_patterns("*.db", "*.db-*",
                                                  "__pycache__"))
    if with_runtime:
        for name in make_package.REQUIRED_RUNTIME:
            full = os.path.join(clean, *name.split("/"))
            parent = os.path.dirname(full)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            if not os.path.isfile(full):
                with open(full, "wb") as handle:
                    handle.write(b"stub")
    return clean


class TestPackageRules(unittest.TestCase):

    def test_dev_databases_detected(self):
        # Plant a database in a TEMP copy: the build must refuse, and the
        # real repo tree is never assumed to contain one.
        tmp = tempfile.mkdtemp(prefix="kitchen_pkg_refuse_")
        try:
            clean = make_tree(tmp)
            planted = os.path.join(clean, "data", "kitchen.db")
            if not os.path.isdir(os.path.dirname(planted)):
                os.makedirs(os.path.dirname(planted))
            with open(planted, "wb") as handle:
                handle.write(b"fake")
            found = make_package.find_dev_databases(clean)
            self.assertTrue(any(f.endswith(".db") for f in found))
            with self.assertRaises(make_package.PackageError):
                make_package.build(os.path.join(tmp, "out.zip"),
                                   verbose=False, root=clean)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_missing_runtime_refused(self):
        tmp = tempfile.mkdtemp(prefix="kitchen_pkg_nort_")
        try:
            clean = make_tree(tmp, with_runtime=False)
            # Remove the real (git-ignored) runtime so presence is stub-only.
            shutil.rmtree(os.path.join(clean, "runtime"), ignore_errors=True)
            with self.assertRaises(make_package.PackageError):
                make_package.build(os.path.join(tmp, "out.zip"),
                                   verbose=False, root=clean)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_long_path_refused(self):
        with self.assertRaises(make_package.PackageError):
            make_package.check_member_lengths(["ok.txt", "x" * 151])
        self.assertEqual(make_package.check_member_lengths(["ok.txt"]), 6)

    def test_external_url_refused(self):
        tmp = tempfile.mkdtemp(prefix="kitchen_pkg_url_")
        try:
            page = os.path.join(tmp, "x.js")
            with open(page, "w", encoding="utf-8") as handle:
                handle.write('var u = "https://example.com/y.js";')
            with self.assertRaises(make_package.PackageError):
                make_package.check_no_external_urls(
                    [(page, "www/x.js")])
            local = os.path.join(tmp, "y.js")
            with open(local, "w", encoding="utf-8") as handle:
                handle.write('var u = "http://127.0.0.1:8001/";')
            self.assertTrue(make_package.check_no_external_urls(
                [(local, "www/y.js")]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_exclusion_helpers(self):
        self.assertTrue(make_package.is_excluded_file("kitchen.db"))
        self.assertTrue(make_package.is_excluded_file("kitchen_launcher.log"))
        self.assertFalse(make_package.is_excluded_file("server.py"))
        self.assertTrue(make_package.is_excluded_dir("data"))
        self.assertTrue(make_package.is_excluded_dir("data_demo"))
        self.assertTrue(make_package.is_excluded_dir("docs"))
        with self.assertRaises(make_package.PackageError):
            make_package.check_ascii(["ok.txt", "ملف.txt"])
        with self.assertRaises(make_package.PackageError):
            make_package.check_required(["server.py"])

    def test_build_from_clean_tree(self):
        tmp = tempfile.mkdtemp(prefix="kitchen_pkg_")
        try:
            clean = make_tree(tmp)
            out = os.path.join(tmp, "out.zip")
            _path, members = make_package.build(out, verbose=False,
                                               root=clean)
            self.assertIn("data/", members)
            for name in make_package.REQUIRED_FILES:
                self.assertIn(name, members)
            for name in make_package.REQUIRED_RUNTIME:
                self.assertIn(name, members)
            for name in members:
                self.assertTrue(all(ord(ch) < 128 for ch in name), name)
                self.assertFalse(name.endswith(".db"), name)
                self.assertLessEqual(len(name), 150, name)
            self.assertFalse(any(n.startswith("docs/") for n in members))
            self.assertFalse(any(n.startswith("tests/") for n in members))
            with zipfile.ZipFile(out) as archive:
                self.assertIn("data/", archive.namelist())
                info = archive.getinfo("data/")
                self.assertEqual(info.file_size, 0)
            sha_file = os.path.splitext(out)[0] + ".sha256.txt"
            self.assertTrue(os.path.isfile(sha_file))
            with open(sha_file, encoding="ascii") as handle:
                line = handle.read().strip()
            digest, _, fname = line.partition("  ")
            self.assertEqual(len(digest), 64)
            self.assertTrue(all(c in "0123456789abcdef" for c in digest))
            self.assertEqual(fname, "kitchen_inventory_portable.zip")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
