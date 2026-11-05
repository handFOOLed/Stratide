"""Setup helper: store the Tushare token in the current Windows user's
Credential Manager. The secret is read from stdin only and is never printed.

Target format is identical to research/historical_warehouse.credential and
research/eod_operator.credential in installed mode:
    Stratide/<sha256(casefold(resolved state root))>/tushare-daily-trade-cal-v1
"""
import ctypes as ct
from ctypes import wintypes as w
import hashlib
import json
import os
from pathlib import Path
import sys

SUFFIX = "/tushare-daily-trade-cal-v1"


class Credential(ct.Structure):
    _fields_ = [("Flags", w.DWORD), ("Type", w.DWORD), ("TargetName", w.LPWSTR),
                ("Comment", w.LPWSTR), ("LastWritten", w.FILETIME),
                ("CredentialBlobSize", w.DWORD), ("CredentialBlob", ct.POINTER(ct.c_ubyte)),
                ("Persist", w.DWORD), ("AttributeCount", w.DWORD), ("Attributes", ct.c_void_p),
                ("TargetAlias", w.LPWSTR), ("UserName", w.LPWSTR)]


def api():
    dll = ct.WinDLL("Advapi32.dll", use_last_error=True)
    dll.CredReadW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD, ct.POINTER(ct.POINTER(Credential))]
    dll.CredReadW.restype = w.BOOL
    dll.CredWriteW.argtypes = [ct.POINTER(Credential), w.DWORD]
    dll.CredWriteW.restype = w.BOOL
    dll.CredDeleteW.argtypes = [w.LPCWSTR, w.DWORD, w.DWORD]
    dll.CredDeleteW.restype = w.BOOL
    dll.CredFree.argtypes = [ct.c_void_p]
    dll.CredFree.restype = None
    return dll


def target():
    root = Path(os.environ["STRATIDE_STATE_ROOT"]).resolve()
    digest = hashlib.sha256(str(root).casefold().encode()).hexdigest()
    return "Stratide/" + digest + SUFFIX


def check(dll):
    entry = ct.POINTER(Credential)()
    if not dll.CredReadW(target(), 1, 0, ct.byref(entry)):
        return dict(state="MISSING", configured=False)
    try:
        size = entry.contents.CredentialBlobSize
        present = 0 < size <= 5120
    finally:
        dll.CredFree(entry)
    return dict(state="CONFIGURED" if present else "MISSING", configured=present)


def write(dll, raw):
    token = raw.decode("utf-8").strip()
    if not (0 < len(token) <= 1024) or any(ord(c) < 32 or ord(c) == 127 for c in token):
        return dict(state="INVALID", error="TOKEN_FORMAT")
    encoded = token.encode("utf-16-le")
    blob = (ct.c_ubyte * len(encoded)).from_buffer_copy(encoded)
    entry = Credential(Type=1, TargetName=target(), CredentialBlobSize=len(encoded),
                       CredentialBlob=blob, Persist=2, UserName="Stratide Tushare EOD")
    if not dll.CredWriteW(ct.byref(entry), 0):
        return dict(state="ERROR", error="CREDENTIAL_WRITE_FAILED")
    return dict(state="CONFIGURED", configured=True)


def main():
    if os.name != "nt":
        print(json.dumps(dict(state="ERROR", error="WINDOWS_ONLY")))
        return 2
    if not os.environ.get("STRATIDE_STATE_ROOT"):
        print(json.dumps(dict(state="ERROR", error="STATE_ROOT_REQUIRED")))
        return 2
    action = sys.argv[1] if len(sys.argv) > 1 else "check"
    dll = api()
    if action == "check":
        result = check(dll)
    elif action == "write":
        result = write(dll, sys.stdin.buffer.read(4096))
    elif action == "delete":
        dll.CredDeleteW(target(), 1, 0)
        result = dict(state="DELETED")
    else:
        result = dict(state="ERROR", error="UNKNOWN_ACTION")
    print(json.dumps(result))
    return 0 if result["state"] in ("CONFIGURED", "MISSING", "DELETED") else 2


if __name__ == "__main__":
    raise SystemExit(main())
