"""Synthetic backup/restore counterproofs; no Owner data or credentials."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("local_backup",ROOT/"scripts/local-backup.py")
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)

class Tests(unittest.TestCase):
    def setup_bundle(self,t):
        root=Path(t);source=root/"source";source.mkdir()
        (source/"journal.jsonl").write_text('{"synthetic_test":true}\n')
        (source/"owner-token").write_text("SYNTHETIC_TEST_SECRET_NOT_A_REAL_TOKEN")
        with closing(sqlite3.connect(source/"agent.sqlite")) as db:db.execute("CREATE TABLE evidence(id INTEGER PRIMARY KEY,value TEXT)");db.execute("INSERT INTO evidence VALUES(1,'synthetic_test')");db.commit()
        config=root/"config.json";config.write_text(json.dumps(dict(schema_version=1,sources=[dict(name="test",path=str(source))])))
        bundle=root/"bundle";self.assertEqual(b.create(config,bundle,True)["state"],"VERIFIED_LOCAL_BACKUP")
        return source,bundle

    def test_snapshot_integrity_dry_run_and_restore_never_overwrite_or_autorun(self):
        with tempfile.TemporaryDirectory() as t:
            source,bundle=self.setup_bundle(t);target=Path(t)/"restored"
            self.assertFalse((bundle/"test/owner-token").exists());self.assertTrue((source/"owner-token").is_file())
            self.assertEqual(b.restore(bundle,target,False)["restore"],"DRY_RUN");self.assertFalse(target.exists())
            result=b.restore(bundle,target,True);self.assertFalse(result["autorun"])
            self.assertEqual((source/"journal.jsonl").read_bytes(),(target/"test/journal.jsonl").read_bytes())
            with self.assertRaisesRegex(ValueError,"RESTORE_CONFLICT"):b.restore(bundle,target,True)

    def test_changed_bytes_or_escaping_manifest_cannot_restore(self):
        with tempfile.TemporaryDirectory() as t:
            _,bundle=self.setup_bundle(t);file=bundle/"test/journal.jsonl";original=file.read_bytes();file.write_text("tampered")
            with self.assertRaisesRegex(ValueError,"HASH_MISMATCH"):b.verify(bundle)
            file.write_bytes(original);path=bundle/"manifest.json";manifest=json.loads(path.read_bytes());manifest["files"][0]["path"]="../escape"
            path.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError,"MANIFEST_PATH"):b.restore(bundle,Path(t)/"restored",True)
            self.assertFalse((Path(t)/"restored").exists())

if __name__=="__main__":unittest.main()
