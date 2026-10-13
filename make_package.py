# make_package.py - builds the portable distribution zip.
#
# THROWAWAY BUILD TOOL - not part of the application. Lives in the repo root
# and is NOT copied into the package.
#
# What it produces: dist/kitchen_inventory_portable.zip containing a single
# flat folder's worth of files (everything that was in app/, at the zip
# ROOT), so extracting the zip gives one folder where start.bat can be
# double-clicked.
#
# Guarantees enforced here:
#   - an EMPTY data/ folder is included; no database ever is
#   - no *.db / -wal / -shm / kitchen_launcher.log / __pycache__ / tests /
#     .git content can leak in
#   - every member name inside the zip is ASCII-only (Windows 7 safety)
#   - runtime/ is included only when runtime/python.exe is present;
#     runtime/README.txt is always included when present
#
# Standard library only, Python 3.8 compatible. No new dependencies.

import hashlib
import os
import re
import sys
import zipfile

APP_DIR_NAME = "app"
DIST_DIR_NAME = "dist"
ZIP_NAME = "kitchen_inventory_portable.zip"
SHA_NAME = "kitchen_inventory_portable.sha256.txt"

# Windows 7 Explorer chokes near path length 260; the extraction folder
# (e.g. D:\kitchen_inventory\) counts too, so zip members stay far below.
MAX_MEMBER_LEN = 150

DATA_DIR_NAME = "data"

EXCLUDED_DIR_NAMES = frozenset((
    "__pycache__",
    "tests",
    "docs",
    "node_modules",
    "build_inputs",
    ".git",
    ".zwork",
    DIST_DIR_NAME,
    "data",
    "data_demo",
))

EXCLUDED_SUFFIXES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".db-journal",
    ".pyc",
    ".pyo",
    ".log",
)

EXCLUDED_FILE_NAMES = frozenset((
    "kitchen_launcher.log",
    "launcher.log",
    "report.txt",
    "make_package.py",
))

REQUIRED_FILES = (
    "start.bat",
    "start_demo.bat",
    "README_FIRST.txt",
    "create_shortcut.bat",
    "check_imports.py",
    "check.py",
    "RUN_CHECK.bat",
    "server.py",
    "launcher.py",
    "db.py",
    "calc.py",
    "seed_demo.py",
    "strings_ar.py",
    "routes_inventory.py",
    "routes_system.py",
    "http_kit.py",
    "make_shortcut.py",
    "launch_hidden.vbs",
    "www/index.html",
    "www/tokens.css",
    "www/base.css",
    "www/components.css",
    "www/screens.css",
    "www/strings.js",
    "www/api.js",
    "www/format.js",
    "www/dates.js",
    "www/ui.js",
    "www/uicheck.js",
    "www/screen-close.js",
    "www/screen-report.js",
    "www/screen-archive.js",
    "www/screen-products.js",
    "www/screen-backup.js",
    "www/app.js",
)

# The portable release is useless without these: refuse instead of
# shipping a zip the target PC cannot run.
REQUIRED_RUNTIME = (
    "runtime/python.exe",
    "runtime/pythonw.exe",
    "runtime/python38.dll",
    "runtime/python38._pth",
    "runtime/python38.zip",
    "runtime/_sqlite3.pyd",
    "runtime/sqlite3.dll",
    "runtime/browser/firefox.exe",
    "runtime/browser/distribution/policies.json",
)

# Any http(s) URL in www/ that is not our own loopback page would phone
# home (or just break) on the offline target PC.
EXTERNAL_URL_RE = re.compile(r"https?://(?!127\.0\.0\.1|localhost)[^\s\"'<>]+",
                             re.IGNORECASE)


class PackageError(Exception):
    """Raised when the package cannot be built correctly."""


def repo_root():
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    return os.path.join(repo_root(), APP_DIR_NAME)


def dist_dir():
    return os.path.join(repo_root(), DIST_DIR_NAME)


def zip_path():
    return os.path.join(dist_dir(), ZIP_NAME)


def is_excluded_dir(name):
    return name.lower() in EXCLUDED_DIR_NAMES


def is_excluded_file(name):
    lowered = name.lower()
    if lowered in EXCLUDED_FILE_NAMES:
        return True
    if lowered.endswith(".exe") and (
            "setup" in lowered or "install" in lowered):
        return True
    for suffix in EXCLUDED_SUFFIXES:
        if lowered.endswith(suffix):
            return True
    if lowered.endswith("-wal") or lowered.endswith("-shm"):
        return True
    return False


def is_database_file(name):
    lowered = name.lower()
    if lowered.endswith(".db"):
        return True
    if lowered.endswith(".db-wal"):
        return True
    if lowered.endswith(".db-shm"):
        return True
    if lowered.endswith(".db-journal"):
        return True
    if lowered.endswith("-wal") or lowered.endswith("-shm"):
        return True
    return False


def find_dev_databases(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            if d.lower() in ("data", "data_demo"):
                keep.append(d)
            elif not is_excluded_dir(d):
                keep.append(d)
        dirnames[:] = keep
        for fn in filenames:
            if is_database_file(fn):
                full = os.path.join(dirpath, fn)
                found.append(os.path.relpath(full, root))
    return sorted(found)


def iter_app_files(root=None):
    root = root or app_dir()
    if not os.path.isdir(root):
        raise PackageError("app folder not found: " + root)
    for entry in sorted(os.listdir(root)):
        full = os.path.join(root, entry)
        lowered = entry.lower()
        if os.path.isdir(full):
            if lowered in ("data", "data_demo"):
                continue
            if lowered == "runtime":
                runtime_python = os.path.join(full, "python.exe")
                if os.path.isfile(runtime_python):
                    for walked in _walk_dir(full, entry):
                        yield walked
                else:
                    readme = os.path.join(full, "README.txt")
                    if os.path.isfile(readme):
                        yield readme, entry + "/README.txt"
                    browser_policies = os.path.join(
                        full, "browser", "distribution", "policies.json")
                    if os.path.isfile(browser_policies):
                        yield (browser_policies,
                               entry + "/browser/distribution/policies.json")
                continue
            if is_excluded_dir(entry):
                continue
            for walked in _walk_dir(full, entry):
                yield walked
        else:
            if is_excluded_file(entry):
                continue
            yield full, entry


def _walk_dir(full_dir, archive_prefix):
    for entry in sorted(os.listdir(full_dir)):
        full = os.path.join(full_dir, entry)
        archive_name = archive_prefix + "/" + entry
        if os.path.isdir(full):
            if is_excluded_dir(entry):
                continue
            for walked in _walk_dir(full, archive_name):
                yield walked
        else:
            if is_excluded_file(entry):
                continue
            yield full, archive_name


def check_ascii(names):
    bad = [name for name in names if any(ord(ch) > 127 for ch in name)]
    if bad:
        raise PackageError(
            "non-ASCII file name(s) inside the package are not allowed: "
            + ", ".join(repr(b) for b in bad))
    return True


def check_required(members):
    missing = [name for name in REQUIRED_FILES if name not in members]
    if missing:
        raise PackageError(
            "required file(s) missing from the package: "
            + ", ".join(missing))
    missing_rt = [name for name in REQUIRED_RUNTIME if name not in members]
    if missing_rt:
        raise PackageError(
            "required runtime file(s) missing (stage Python 3.8 + Firefox"
            " into app/runtime/ first): " + ", ".join(missing_rt))
    return True


def check_no_databases(members):
    offenders = [
        name for name in members
        if is_excluded_file(os.path.basename(name))
        and is_database_file(os.path.basename(name))
    ]
    if offenders:
        raise PackageError(
            "database/dev files must not be packaged: "
            + ", ".join(offenders))
    return True


def check_member_lengths(members):
    """Refuse members longer than MAX_MEMBER_LEN (Win7 Explorer 260 limit
    counts the extraction folder too). Returns the longest length."""
    longest = 0
    for name in members:
        if len(name) > longest:
            longest = len(name)
    too_long = [name for name in members if len(name) > MAX_MEMBER_LEN]
    if too_long:
        raise PackageError(
            "member path(s) longer than %d characters: " % MAX_MEMBER_LEN
            + ", ".join(too_long))
    return longest


def check_no_external_urls(planned):
    """Refuse when a www file references an external URL. Our own loopback
    addresses are fine; anything else would break offline."""
    offenders = []
    for full, archive_name in planned:
        if not archive_name.startswith("www/"):
            continue
        try:
            with open(full, "rb") as handle:
                text = handle.read().decode("utf-8", "replace")
        except OSError:
            continue
        hits = EXTERNAL_URL_RE.findall(text)
        if hits:
            offenders.append("%s (%s)" % (archive_name, hits[0]))
    if offenders:
        raise PackageError(
            "www file(s) reference external URL(s), forbidden offline: "
            + ", ".join(offenders))
    return True


def sha256_of(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(zip_file=None, verbose=True, root=None):
    root = root or app_dir()
    if not os.path.isdir(root):
        raise PackageError("app folder not found: " + root)
    dbs = find_dev_databases(root)
    if dbs:
        raise PackageError(
            "refusing to build: dev database file(s) found under app/: "
            + ", ".join(dbs)
            + " (move or delete them; the package ships an EMPTY data/)")
    zip_file = zip_file or zip_path()
    planned = list(iter_app_files(root))
    members = [archive_name for _full, archive_name in planned]

    # An empty data/ folder: recorded as a directory entry so it survives
    # extraction (zip has no concept of an empty directory otherwise).
    data_entry = DATA_DIR_NAME + "/"
    members.append(data_entry)

    # Checks run BEFORE anything is written, so a bad build leaves no zip.
    check_ascii(members)
    check_no_databases(members)
    check_required(members)
    check_no_external_urls(planned)
    longest = check_member_lengths(members)

    parent = os.path.dirname(os.path.abspath(zip_file))
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    if os.path.isfile(zip_file):
        os.remove(zip_file)

    # No zip64 (stays far below 4 GB), deterministic order, fixed
    # timestamps for reproducible builds, forward slashes, no encryption.
    total_raw = 0
    with zipfile.ZipFile(zip_file, "w", zipfile.ZIP_DEFLATED, False) as archive:
        info = zipfile.ZipInfo(data_entry)
        info.date_time = (1980, 1, 1, 0, 0, 0)
        info.external_attr = 0x10
        archive.writestr(info, b"")
        for full, archive_name in planned:
            info = zipfile.ZipInfo(archive_name)
            info.date_time = (1980, 1, 1, 0, 0, 0)
            info.external_attr = 0x20
            info.compress_type = zipfile.ZIP_DEFLATED
            with open(full, "rb") as handle:
                raw = handle.read()
            total_raw += len(raw)
            archive.writestr(info, raw)

    digest = sha256_of(zip_file)
    sha_file = os.path.splitext(zip_file)[0] + ".sha256.txt"
    with open(sha_file, "w", encoding="ascii", newline="\n") as handle:
        handle.write("%s  %s\n" % (digest, ZIP_NAME))

    if verbose:
        _print_manifest(zip_file, sorted(members), total_raw, longest,
                        digest, sha_file)

    return zip_file, sorted(members)


def _print_manifest(zip_file, members, total_raw, longest, digest, sha_file):
    print("Package built : " + zip_file)
    try:
        size = os.path.getsize(zip_file)
        print("Size          : %d bytes (%.1f MB)"
              % (size, size / 1048576.0))
    except OSError:
        pass
    print("Uncompressed  : %d bytes (%.1f MB)"
          % (total_raw, total_raw / 1048576.0))
    print("Members       : %d" % len(members))
    print("Longest path  : %d characters (limit %d)"
          % (longest, MAX_MEMBER_LEN))
    print("SHA256        : " + digest)
    print("SHA file      : " + sha_file)
    print("")
    for name in members:
        if name.startswith("runtime/"):
            continue
        print("   " + name)
    print("   ... plus %d runtime/ files (Python + Firefox)"
          % len([n for n in members if n.startswith("runtime/")]))
    print("")
    print("runtime/python.exe is INCLUDED - the package is self-contained.")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    target = None
    for arg in argv:
        if arg in ("-h", "--help"):
            print("Usage: python make_package.py [OUTPUT_ZIP]")
            print("")
            print("Builds the portable distribution, by default to")
            print("   " + zip_path())
            sys.exit(0)
        elif not arg.startswith("-"):
            target = arg
        else:
            print("Unknown option: %s (try --help)" % arg)
            sys.exit(2)
    try:
        build(target)
    except PackageError as exc:
        print("PACKAGE FAILED: %s" % exc)
        return 1
    print("Done. Copy the zip to the target PC and extract it there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
