# make_shortcut.py - creates the Desktop shortcut (Arabic name + icon).
#
# WHY NOT WScript.Shell / .vbs:
#   WshShortcut.Save() converts the shortcut path through the SYSTEM ANSI
#   code page (GetACP(); 1252 on the dev machine). Characters that code page
#   cannot represent are replaced by "?", so the path WSH tries to write does
#   not exist and Save() fails with 0x80070003 - even when only the FOLDER
#   part of the path contains non-ASCII characters (our Desktop is
#   "...\OneDrive\المستندات\Desktop"). An Arabic "Description" is mangled the
#   same way, and WSH cannot even read such a shortcut back.
#
#   The COM interfaces used below (IShellLinkW + IPersistFile) keep UTF-16
#   file names end to end, so Arabic names, icon paths and descriptions all
#   work. Verified on this machine including Explorer readback.
#
# Standard library only, Python 3.8 compatible, Windows 7 safe.

import ctypes
import os
import shutil
import sys
import tempfile
import uuid
from ctypes import (
    POINTER,
    Structure,
    byref,
    c_int,
    c_long,
    c_ubyte,
    c_uint,
    c_ulong,
    c_ushort,
    c_void_p,
    c_wchar_p,
)

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from strings_ar import STRINGS

BASE_DIR = _APP_DIR
VBS_PATH = os.path.join(BASE_DIR, "launch_hidden.vbs")
ICON_PATH = os.path.join(BASE_DIR, "icon.ico")
SHORTCUT_NAME = STRINGS["app_title"] + ".lnk"

_CLSID_SHELLLINK = "{00021401-0000-0000-C000-000000000046}"
_IID_ISHELLLINKW = "{000214F9-0000-0000-C000-000000000046}"
_IID_IPERSISTFILE = "{0000010B-0000-0000-C000-000000000046}"
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2

# IShellLinkW vtable slots (0-2 are IUnknown).
_ISL_SET_DESCRIPTION = 7
_ISL_SET_WORKINGDIR = 9
_ISL_SET_ARGUMENTS = 11
_ISL_SET_ICONLOCATION = 17
_ISL_SET_PATH = 20
_IPF_SAVE = 6

_CSIDL_DESKTOPDIRECTORY = 0x0010


class _GUID(Structure):
    _fields_ = [
        ("Data1", c_ulong),
        ("Data2", c_ushort),
        ("Data3", c_ushort),
        ("Data4", c_ubyte * 8),
    ]


def _guid(text):
    g = _GUID()
    ctypes.memmove(byref(g), uuid.UUID(text).bytes_le, 16)
    return g


_ole32 = ctypes.WinDLL("ole32")
_ole32.CoInitializeEx.argtypes = [c_void_p, c_ulong]
_ole32.CoInitializeEx.restype = c_long
_ole32.CoCreateInstance.argtypes = [
    POINTER(_GUID),
    c_void_p,
    c_ulong,
    POINTER(_GUID),
    POINTER(c_void_p),
]
_ole32.CoCreateInstance.restype = c_long


def _method(pobj, index, restype, *argtypes):
    """Bind vtable slot `index` of a COM interface pointer."""
    vtable = ctypes.cast(pobj, POINTER(POINTER(c_void_p)))[0]
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtable[index])


def create_lnk(
    lnk_path, target, icon=None, arguments=None, working_dir=None,
    description=None,
):
    """Create or replace a .lnk file. Arabic paths are fully supported.

    Raises OSError carrying the HRESULT on any COM failure.
    """
    _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)  # result ignored

    link = c_void_p()
    hr = _ole32.CoCreateInstance(
        byref(_guid(_CLSID_SHELLLINK)),
        None,
        _CLSCTX_INPROC_SERVER,
        byref(_guid(_IID_ISHELLLINKW)),
        byref(link),
    )
    if hr != 0 or not link.value:
        raise OSError(
            "CoCreateInstance(ShellLink) failed, HRESULT=0x%08X"
            % (hr & 0xFFFFFFFF)
        )

    _method(link, _ISL_SET_PATH, c_long, c_wchar_p)(link, target)
    if icon:
        _method(link, _ISL_SET_ICONLOCATION, c_long, c_wchar_p, c_int)(
            link, icon, 0
        )
    if arguments:
        _method(link, _ISL_SET_ARGUMENTS, c_long, c_wchar_p)(link, arguments)
    if working_dir:
        _method(link, _ISL_SET_WORKINGDIR, c_long, c_wchar_p)(
            link, working_dir
        )
    if description:
        _method(link, _ISL_SET_DESCRIPTION, c_long, c_wchar_p)(
            link, description
        )

    persist = c_void_p()
    hr = _method(link, 0, c_long, POINTER(_GUID), POINTER(c_void_p))(
        link, byref(_guid(_IID_IPERSISTFILE)), byref(persist)
    )
    if hr != 0 or not persist.value:
        raise OSError(
            "QueryInterface(IPersistFile) failed, HRESULT=0x%08X"
            % (hr & 0xFFFFFFFF)
        )

    hr = _method(persist, _IPF_SAVE, c_long, c_wchar_p, c_int)(
        persist, lnk_path, 1  # fRemember = 1
    )
    if hr != 0:
        raise OSError(
            "IPersistFile.Save failed for %s, HRESULT=0x%08X"
            % (lnk_path, hr & 0xFFFFFFFF)
        )

    try:  # ask Explorer to refresh the desktop immediately
        shcn = ctypes.windll.shell32.SHChangeNotify
        shcn.argtypes = [c_ulong, c_uint, c_wchar_p, c_wchar_p]
        shcn(0x00000002, 0x0005, lnk_path, None)  # SHCNE_CREATE | SHCNF_PATHW
    except Exception:
        pass

    return os.path.isfile(lnk_path)


def create_lnk_with_fallback(lnk_path, **kwargs):
    """create_lnk(), falling back to stage-at-ASCII-path + move.

    The fallback exists in case the COM route is unavailable on some target
    machine; moving a finished .lnk keeps the Arabic name intact because
    Python's file APIs are Unicode-native.
    """
    try:
        return create_lnk(lnk_path, **kwargs)
    except OSError as exc:
        print("[WARN] COM shortcut creation failed (%s) - using fallback" % exc)
    fd, stage = tempfile.mkstemp(suffix=".lnk")
    os.close(fd)
    os.remove(stage)
    try:
        if not create_lnk(stage, **kwargs):
            return False
        shutil.move(stage, lnk_path)  # works across volumes too
        return os.path.isfile(lnk_path)
    finally:
        if os.path.isfile(stage):
            try:
                os.remove(stage)
            except OSError:
                pass


def desktop_folder():
    """Current user Desktop folder (follows OneDrive redirection)."""
    buf = ctypes.create_unicode_buffer(260)
    try:
        if (
            ctypes.windll.shell32.SHGetFolderPathW(
                None, _CSIDL_DESKTOPDIRECTORY, None, 0, buf
            )
            == 0
            and buf.value
        ):
            return buf.value
    except Exception:
        pass
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer"
            "\\User Shell Folders",
        ) as key:
            return os.path.expandvars(winreg.QueryValueEx(key, "Desktop")[0])
    except OSError:
        return os.path.join(os.path.expanduser("~"), "Desktop")


def wscript_exe():
    """wscript.exe path (exists on Windows 7 and newer)."""
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    p = os.path.join(system_root, "System32", "wscript.exe")
    if os.path.isfile(p):
        return p
    return "wscript.exe"


def main():
    if not os.path.isfile(VBS_PATH):
        print("[ERROR] launch_hidden.vbs not found next to make_shortcut.py")
        return 1
    if not os.path.isfile(ICON_PATH):
        print("[WARN] icon.ico not found - shortcut uses the default icon")

    desktop = desktop_folder()
    target_lnk = os.path.join(desktop, SHORTCUT_NAME)
    print("Desktop : " + desktop)
    print("Shortcut: " + SHORTCUT_NAME)

    ok = create_lnk_with_fallback(
        target_lnk,
        target=wscript_exe(),
        arguments='"' + VBS_PATH + '"',
        working_dir=BASE_DIR,
        icon=ICON_PATH,
        description=STRINGS["app_title"],
    )
    if not ok:
        print("[ERROR] could not create the shortcut")
        return 1

    size = os.path.getsize(target_lnk)
    print("[OK] Shortcut created (%d bytes)" % size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
