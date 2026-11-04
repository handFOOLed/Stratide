"""Stopped local data backup/verify/restore. Never restores over existing data."""
import argparse
from contextlib import ExitStack, closing
import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research/timesfm_cpu"))
from runtime import lock
from model import Rejected


def require(ok,code):
    if not ok: raise ValueError(code)


def sha(path):
    with path.open("rb") as f: return hashlib.file_digest(f,"sha256").hexdigest()


def ordinary(path):
    require(not path.is_symlink() and not (hasattr(path,"is_junction") and path.is_junction()),"BACKUP_LINK_DENIED")


def files(root):
    result=[]
    for p in sorted(root.rglob("*")):
        ordinary(p)
        if p.is_file():result.append(p)
    return result


def create(config,out,stopped):
    require(stopped,"STOP_WRITERS_FIRST")
    cfg=json.loads(config.read_bytes())
    require(cfg["schema_version"]==1 and 0<len(cfg["sources"])<=12,"BACKUP_CONFIG")
    require(not out.exists(),"BACKUP_DESTINATION_EXISTS")
    roots=[]
    names=set()
    for source in cfg["sources"]:
        name=source["name"]
        require(name.isascii() and name.replace("-","").replace("_","").isalnum() and name not in names,"BACKUP_SOURCE_NAME")
        names.add(name)
        root=Path(source["path"]).absolute()
        ordinary(root)
        require(root.is_dir() and not out.absolute().is_relative_to(root),"BACKUP_SOURCE_OR_DESTINATION")
        roots.append((name,root))
    out.mkdir(parents=True)
    if os.name!="nt":out.chmod(0o700)
    manifest=dict(schema_version=1,created_at=dt.datetime.now(dt.timezone.utc).isoformat(),
        state="LOCAL_STOPPED_BACKUP",secrets="EXCLUDED_PRESERVE_ORIGINAL_CREDENTIALS",files=[],excluded=[],
        recovery="RESTORE_TO_NEW_DIRECTORY_ONLY_NO_AUTORUN")
    with ExitStack() as stack:
        # Same OS file locks as the existing Worker/Rust writer. Copying a
        # live journal tree is deliberately unsupported; SQLite uses its backup API.
        for _,root in roots:
            for p in files(root):
                if p.suffix==".lock":stack.enter_context(lock(p))
        for name,root in roots:
            candidates=files(root)
            versions={p:(p.stat().st_size,p.stat().st_mtime_ns) for p in candidates}
            for p in candidates:
                rel=p.relative_to(root)
                lower=p.name.lower()
                if p.suffix==".lock" or lower.endswith(("-wal","-shm","-journal")) or lower in ("owner-token","process.json") or "token" in lower or "api-key" in lower or lower.startswith(".env"):
                    manifest["excluded"].append(str(PurePosixPath(name,*rel.parts)));continue
                target=out/name/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                if p.suffix in (".sqlite",".db",".sqlite3"):
                    with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True)) as source, closing(sqlite3.connect(target)) as dest:
                        source.backup(dest)
                        require(dest.execute("PRAGMA integrity_check").fetchone()[0]=="ok","BACKUP_SQLITE_INTEGRITY")
                else:shutil.copyfile(p,target)
                manifest["files"].append(dict(path=str(PurePosixPath(name,*rel.parts)),size=target.stat().st_size,sha256=sha(target)))
            require(candidates==files(root) and all(p.exists() and (p.stat().st_size,p.stat().st_mtime_ns)==v for p,v in versions.items()),"BACKUP_SOURCE_CHANGED_STOP_WRITERS")
    (out/"manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return verify(out)


def verify(bundle):
    ordinary(bundle)
    manifest=json.loads((bundle/"manifest.json").read_bytes())
    require(manifest["schema_version"]==1 and manifest["recovery"]=="RESTORE_TO_NEW_DIRECTORY_ONLY_NO_AUTORUN","BACKUP_MANIFEST_VERSION")
    seen=set()
    for row in manifest["files"]:
        rel=PurePosixPath(row["path"])
        require(not rel.is_absolute() and ".." not in rel.parts and "\\" not in row["path"] and ":" not in row["path"] and str(rel) not in seen,"BACKUP_MANIFEST_PATH")
        seen.add(str(rel))
        p=bundle.joinpath(*rel.parts)
        for parent in [p,*p.parents]:
            ordinary(parent)
            if parent==bundle:break
        require(p.is_file() and p.stat().st_size==row["size"] and sha(p)==row["sha256"],"BACKUP_HASH_MISMATCH")
        if p.suffix in (".sqlite",".db",".sqlite3"):
            with closing(sqlite3.connect(p.as_uri()+"?mode=ro",uri=True)) as db:
                require(db.execute("PRAGMA integrity_check").fetchone()[0]=="ok","BACKUP_SQLITE_INTEGRITY")
    require({str(PurePosixPath(*p.relative_to(bundle).parts)) for p in files(bundle) if p!=bundle/"manifest.json"}==seen,"BACKUP_MANIFEST_FILES")
    return dict(state="VERIFIED_LOCAL_BACKUP",files=len(seen),manifest_sha256=sha(bundle/"manifest.json"),autorun=False)


def restore(bundle,out,apply):
    result=verify(bundle)
    require(not out.exists() and not out.absolute().is_relative_to(bundle.absolute()),"RESTORE_CONFLICT_NEW_DESTINATION_REQUIRED")
    if apply:
        out.mkdir(parents=True)
        if os.name!="nt":out.chmod(0o700)
        manifest=json.loads((bundle/"manifest.json").read_bytes())
        for row in manifest["files"]:
            rel=PurePosixPath(row["path"])
            target=out.joinpath(*rel.parts)
            target.parent.mkdir(parents=True,exist_ok=True)
            with bundle.joinpath(*rel.parts).open("rb") as source,target.open("xb") as dest:shutil.copyfileobj(source,dest)
        # Preserve inspection provenance; restore never launches/replays tasks.
        shutil.copyfile(bundle/"manifest.json",out/"manifest.json")
        verify(out)
    return dict(result,restore="RESTORED_INACTIVE_NEW_DIRECTORY" if apply else "DRY_RUN",credentials="RECONNECT_EXISTING_LOCAL_CREDENTIALS_EXPLICITLY",autorun=False)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=["create","verify","restore"])
    p.add_argument("--config",type=Path)
    p.add_argument("--bundle",type=Path)
    p.add_argument("--out",type=Path)
    p.add_argument("--stopped",action="store_true")
    p.add_argument("--apply",action="store_true",help="restore only; default is dry-run")
    a=p.parse_args()
    try:
        if a.command=="create":require(a.config is not None and a.out is not None,"BACKUP_ARGUMENTS");result=create(a.config,a.out.absolute(),a.stopped)
        elif a.command=="verify":require(a.bundle is not None,"BACKUP_ARGUMENTS");result=verify(a.bundle.absolute())
        else:require(a.bundle is not None and a.out is not None,"BACKUP_ARGUMENTS");result=restore(a.bundle.absolute(),a.out.absolute(),a.apply)
        print(json.dumps(result));return 0
    except (OSError,ValueError,sqlite3.Error,Rejected) as e:
        print(json.dumps(dict(state="BLOCKED",reason=str(e),autorun=False)));return 2

if __name__=="__main__":raise SystemExit(main())
