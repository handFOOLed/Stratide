"""Offline counterexamples for Issue #61; all market rows here are synthetic."""
import contextlib
import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sqlite3
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import multistock_research as m


def make_fixture(root):
    h = m.data.sidecar
    a = dt.date(2021, 11, 1)
    dates = [(a + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(126)
             if (a + dt.timedelta(days=i)).weekday() < 5]
    codes = ["600000.SH", "600001.SH", "000001.SZ", "000002.SZ", "600002.SH",
             "600003.SH", "920001.BJ", "689001.SH"]
    w, s = h.v1.Warehouse(root / "v1"), h.Sidecar(root / "v2")

    def attempt(store, db, api, date):
        run = db.execute("INSERT INTO runs(kind,started,status,config,config_sha) VALUES('fixture',?,'DONE','{}',?)",
                         (h.now(), h.sha(b"{}"))).lastrowid
        aid = db.execute("""INSERT INTO attempts(run_id,api,params,fields,credential_source,
            permission_source,started,ended,status,may_have_sent,response_sha)
            VALUES(?,?,?,?,?,?,?,?,'OK',0,?)""",
            (run, api, h.canonical(dict(trade_date=date)).decode(), "synthetic", "NONE",
             "SYNTHETIC_NOT_MARKET", "2026-11-01T00:00:00+00:00", "2026-11-01T00:00:01+00:00", h.sha((api+date).encode()))).lastrowid
        store.seal_attempt(db, aid)
        return aid

    objects = dict(stock_basic=[dict(ts_code=c, exchange={"SH":"SSE", "SZ":"SZSE", "BJ":"BSE"}[c[-2:]],
        list_date="20200101", delist_date=dates[72] if c==codes[1] else None,
        list_status="D" if c==codes[1] else "L") for c in codes],
        trade_cal=[dict(exchange=e, cal_date=d, is_open="1", pretrade_date=dates[i-1] if i else None)
                   for e in ("SSE", "SZSE") for i,d in enumerate(dates)])
    with w.write() as db:
        for api, rows in objects.items():
            aid = attempt(w, db, api, dates[0])
            w.publish_objects(db, api, rows, aid)
        for i, d in enumerate(dates):
            rows = []
            for j, c in enumerate(codes):
                if (c==codes[1] and i>=72) or (c==codes[4] and i<20) or (c==codes[3] and i==65):
                    continue
                p = m.D(10) + m.D(i*(j+1))/100 + m.D((i%7)*(j%3))/100
                # Later corporate action changes only its own and following factors/prices.
                factor = m.D(2) if c==codes[0] and i>=70 else m.D(1)
                p /= factor
                rows.append(dict(ts_code=c, trade_date=d, open=str(p), high=str(p+m.D('.2')),
                    low=str(p-m.D('.2')), close=str(p+m.D('.05')), pre_close=str(p), vol="100000", amount="20000"))
            aid = attempt(w, db, "daily", d)
            w.publish_day(db, d, rows, [aid], "COMPLETE", "SYNTHETIC")
    with s.write() as db:
        s.install_metadata(db, objects, dict(source="synthetic_fixture_not_market",
            source_contract_sha=h.sha(h.canonical(h.v1.CONTRACT))))
        for i,d in enumerate(dates):
            for api in h.FIELDS:
                rows=[]
                for j,c in enumerate(codes):
                    if api=="suspend_d":
                        if c==codes[2] and i==66:
                            rows.append(dict(ts_code=c,trade_date=d,suspend_type="S",suspend_timing=None,
                                             security_kind=h.security_kind(c)))
                        continue
                    r = dict(ts_code=c,trade_date=d,security_kind=h.security_kind(c),quality_flags=[])
                    if api=="adj_factor":
                        r["adj_factor"] = None if c==codes[3] and i==67 else ("2" if c==codes[0] and i>=70 else "1")
                    elif api=="daily_basic":
                        r.update(pe=None, pb="1.234567890123456789", turnover_rate="1.25")
                    else:
                        r.update(up_limit="1000",down_limit=".01",asset_type="STK",
                                 exchange="SZSE" if c==codes[0] and i==66 else {"SH":"SSE","SZ":"SZSE","BJ":"BSE"}[c[-2:]])
                    rows.append(r)
                aid=attempt(s,db,api,d)
                s.publish(db,api,d,rows,[aid],"COMPLETE","SYNTHETIC")
    return dates, codes


class Suite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent=ROOT/"state"/"multistock-research-tests"
        parent.mkdir(parents=True,exist_ok=True)
        cls.temp=tempfile.TemporaryDirectory(dir=parent)
        cls.root=Path(cls.temp.name)
        cls.dates, cls.codes=make_fixture(cls.root)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def dataset(self):
        return m.data.Dataset(self.root/"v1",self.root/"v2",self.dates[0],self.dates[-1])

    def config(self):
        c=m.default_config(self.dates[0],self.dates[-1])
        c["windows"]=[dict(name="development",role="development",start=self.dates[0],end=self.dates[29]),
            dict(name="validation",role="validation",start=self.dates[30],end=self.dates[49]),
            dict(name="late",role="evaluation",start=self.dates[50],end=self.dates[-1],train_end=self.dates[49])]
        return c

    def test_frozen_end_to_end_is_deterministic_and_readonly(self):
        before=m.data.file_receipts([self.root/"v1",self.root/"v2"])
        with mock.patch.object(m.data.sidecar.v1,"credential",side_effect=AssertionError("TOKEN_READ")), \
             mock.patch.object(m.data.sidecar.v1.TushareHTTP,"__call__",side_effect=AssertionError("HTTP")):
            outputs=[]
            for name in ("a","b"):
                outputs.append(m.run(self.dataset(), self.config(), ROOT/"state"/"multistock-research"/self.root.name/name))
        self.assertEqual(outputs[0]["output_sha"],outputs[1]["output_sha"])
        self.assertEqual(outputs[0]["results"],outputs[1]["results"])
        self.assertEqual(before,m.data.file_receipts([self.root/"v1",self.root/"v2"]))
        r=outputs[0]["results"]
        self.assertEqual(len(r["full_period"]),18)
        self.assertGreater(r["coverage"]["daily_rows"],500)
        self.assertEqual(r["source_origin"],"SYNTHETIC")
        self.assertFalse(r["paper_allowed"])
        self.assertEqual(r["full_period"]["cash/base"]["total_return"],"0")
        out=ROOT/"state"/"multistock-research"/self.root.name/"a"
        self.assertTrue(m.verify(out)["verified"])
        for record in map(json.loads,(out/"daily.jsonl").read_text().splitlines()):
            if any(b["assumed_exposure_changes"] for b in record["full"].values()):
                self.assertLess(record["signal_date"],record["trade_date"])
            for name,books in record["walk_forward"].items():
                if any(b["assumed_exposure_changes"] for b in books.values()):
                    self.assertLess(record["walk_forward_signal_dates"][name],record["trade_date"])
        fold=r["walk_forward"]["late"]
        self.assertEqual(fold["embargo_dates"],[self.dates[50]])
        self.assertEqual(fold["results"]["cash/base"]["start"],self.dates[51])

    def test_nulls_events_identity_and_decimal_are_not_invented(self):
        with self.dataset() as ds:
            day=ds.read_day(self.dates[66])
            rows={r["ts_code"]:r for r in day["rows"]}
            self.assertIn("SOURCE_EXCHANGE_CONFLICT",rows[self.codes[0]]["quality"])
            self.assertEqual(rows[self.codes[3]]["tradability"],"UNKNOWN")
            self.assertEqual(rows[self.codes[2]]["suspension_events"][0]["suspend_type"],"S")
            self.assertEqual(rows[self.codes[0]]["daily_basic"]["pb"],"1.234567890123456789")
            self.assertIn("BSE_CALENDAR_NOT_VERIFIED",rows[self.codes[6]]["quality"])
            self.assertIsNone({r["ts_code"]:r for r in ds.read_day(self.dates[67])["rows"]}[self.codes[3]]["factor"])
            self.assertIn(self.codes[1],{r["ts_code"] for r in ds.read_day(self.dates[0])["rows"]})

    def test_signal_prefix_does_not_use_tomorrow_or_future_factor(self):
        config=self.config()
        with self.dataset() as ds:
            days=[ds.read_day(d) for d in self.dates]
        a=m.Features(config)
        b=m.Features(config)
        prefix=[]
        for i,day in enumerate(days[:69]):
            a.update(day,i)
            b.update(copy.deepcopy(day),i)
            prefix.append(m.targets(a,config))
        changed=copy.deepcopy(days[69])
        changed["rows"][0]["daily"]["close"]="999999"
        changed["rows"][0]["factor"]="999"
        a.update(days[69],69)
        b.update(changed,69)
        self.assertEqual(prefix[-1],m.targets_from_history(days[:69],config))
        self.assertNotEqual(m.targets(a,config),m.targets(b,config))

    def test_constraints_and_directional_costs(self):
        with self.dataset() as ds:
            day=ds.read_day(self.dates[66])
        rows={r["ts_code"]:r for r in day["rows"]}
        self.assertEqual(m.execution_block(rows[self.codes[0]],"buy"),"SOURCE_EXCHANGE_CONFLICT")
        self.assertEqual(m.execution_block(rows[self.codes[2]],"sell"),"SUSPENSION_EVENT")
        bad=copy.deepcopy(rows[self.codes[3]])
        bad["limit"]["up_limit"]=bad["daily"]["open"]
        self.assertEqual(m.execution_block(bad,"buy"),"UP_LIMIT_REFERENCE")
        bad["limit"]=None
        self.assertEqual(m.execution_block(bad,"sell"),"LIMIT_UNKNOWN")
        self.assertGreater(m.cost_rate(m.default_config()["cost_scenarios"][2],"sell","20211101"),
                           m.cost_rate(m.default_config()["cost_scenarios"][1],"buy","20211101"))

    def test_warmup_gaps_and_all_cash(self):
        f=m.Features(self.config())
        with self.dataset() as ds:
            for i,d in enumerate(self.dates[:69]):
                f.update(ds.read_day(d),i)
                if i<60:self.assertTrue(all(not v for v in m.targets(f,self.config()).values()))
        self.assertNotIn(self.codes[3],f.eligible())
        self.assertNotIn(self.codes[6],f.eligible())
        self.assertNotIn(self.codes[7],f.eligible())

    def test_writer_wal_foreign_schema_and_output_boundary(self):
        h=m.data.sidecar
        with h.v1.writer_lock(self.root/"v1"):
            with self.assertRaisesRegex(h.Error,"BUSY"):
                with self.dataset():pass
        wal=self.root/"v1"/"warehouse.sqlite-wal"
        wal.write_bytes(b"pending")
        try:
            with self.assertRaisesRegex(h.Error,"RECOVERY"):
                with self.dataset():pass
        finally:wal.unlink()
        with self.assertRaisesRegex(h.Error,"OUTPUT"):
            m.run(self.dataset(),self.config(),self.root/"v1"/"research")

    def test_revision_new_plan_does_not_rewrite_old_version(self):
        revision=self.root/"revision"
        shutil.copytree(self.root/"v1",revision/"v1")
        shutil.copytree(self.root/"v2",revision/"v2")
        h=m.data.sidecar
        def ds(bound=None):
            return m.data.Dataset(revision/"v1",revision/"v2",self.dates[0],self.dates[-1],bound)
        with ds() as old:
            old_sha,old_bound=old.source_sha,old.version_bounds[0]
            original=old.read_day(self.dates[68])
        w=h.v1.Warehouse(revision/"v1")
        with w.write() as db:
            aid=db.execute("SELECT MAX(id) FROM attempts WHERE api='daily'").fetchone()[0]
            rows=[{k:v for k,v in r["daily"].items() if k!="_row_sha"} for r in original["rows"]]
            rows[0]["close"]="500"
            rows[0]["high"]="501"
            w.publish_day(db,self.dates[68],rows,[aid],"COMPLETE","SYNTHETIC_REVISION")
        with ds(old_bound) as frozen:
            self.assertEqual(frozen.source_sha,old_sha)
            self.assertEqual(frozen.read_day(self.dates[68]),original)
        with ds() as revised:
            self.assertNotEqual(revised.source_sha,old_sha)
            self.assertNotEqual(revised.read_day(self.dates[68]),original)

    def test_cost_cash_limit_missing_marks_and_no_same_day_sale(self):
        config=self.config()
        with self.dataset() as ds:
            day=ds.read_day(self.dates[64],(self.codes[0],))
        code=self.codes[0]
        books=[m.Portfolio(s,config) for s in config["cost_scenarios"]]
        for book in books:
            r=book.step(day,64,{code:"1"})
            self.assertGreaterEqual(book.cash,m.D('-1e-28'))
            self.assertEqual(r["assumed_exposure_changes"],1)
        self.assertGreater(books[0].value(),books[1].value())
        self.assertGreater(books[1].value(),books[2].value())
        book=books[1]
        same=book.step(day,64,{})
        self.assertEqual(same["rejected"].get("T_PLUS_1_ASSUMPTION"),1)
        missing=dict(day,trade_date=self.dates[65],rows=[])
        stale=book.step(missing,65,{})
        self.assertEqual(stale["stale_marks"],1)
        self.assertEqual(stale["rejected"].get("DAILY_MISSING"),1)
        self.assertLess(m.D(stale["terminal_zero_stale_index"]),m.D(stale["index"]))

    def test_next_open_gate_does_not_read_next_close_or_volume(self):
        with self.dataset() as ds:
            day=ds.read_day(self.dates[64],(self.codes[0],))
        row=day["rows"][0]
        original=m.execution_block(row,"buy")
        changed=copy.deepcopy(row)
        changed["daily"]["close"]="999999999"
        changed["daily"]["vol"]="0"
        self.assertEqual(m.execution_block(changed,"buy"),original)

    def test_adjustment_neutrality_no_cash_dividend_double_count(self):
        with self.dataset() as ds:
            first=ds.read_day(self.dates[64],(self.codes[0],))
        row=first["rows"][0]
        row["daily"]["open"]=row["daily"]["close"]="10"
        row["factor"]="1"
        book=m.Portfolio(self.config()["cost_scenarios"][0],self.config())
        before=book.step(first,64,{self.codes[0]:"1"})
        second=copy.deepcopy(first)
        second["trade_date"]=self.dates[65]
        second["rows"][0]["daily"]["open"]=second["rows"][0]["daily"]["close"]="5"
        second["rows"][0]["factor"]="2"
        after=book.step(second,65,None)
        self.assertEqual(m.D(before["index"]),m.D(1))
        self.assertEqual(m.D(after["index"]),m.D(1))
        self.assertEqual(m.D(after["daily_return"]),m.D(0))
        self.assertEqual(book.cash,m.D(0))

    def test_unknown_sources_and_foreign_schema_rejected_without_writes(self):
        fake=self.root/"foreign"
        fake.mkdir()
        (fake/"writer.lock").write_bytes(b"0")
        with sqlite3.connect(fake/"warehouse.sqlite") as db:
            db.execute("create table money(amount text)")
        before=m.data.file_receipts([fake])
        with self.assertRaisesRegex(m.Error,"SCHEMA"):
            with m.data.Dataset(fake,self.root/"v2",self.dates[0],self.dates[-1]):pass
        self.assertEqual(before,m.data.file_receipts([fake]))

    def test_cli_readonly_commands_and_artifact_tamper(self):
        out=ROOT/"state"/"multistock-research"/self.root.name/"cli-source"
        m.run(self.dataset(),self.config(),out)
        before=m.data.file_receipts([self.root/"v1",self.root/"v2"])
        base=[sys.executable,"-I","-B",str(ROOT/"scripts/multistock-research.py")]
        for command in ("report","verify"):
            completed=subprocess.run(base+[command,"--out",str(out)],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        for command in ("inspect","query"):
            completed=subprocess.run(base+[command,"--v1-root",str(self.root/"v1"),"--v2-root",str(self.root/"v2"),
                "--start",self.dates[0],"--end",self.dates[-1],"--date",self.dates[64],"--symbols",self.codes[0]],capture_output=True,text=True)
            self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)
        self.assertEqual(before,m.data.file_receipts([self.root/"v1",self.root/"v2"]))
        with (out/"results.json").open("ab") as f:f.write(b" ")
        with self.assertRaisesRegex(m.Error,"OUTPUT_HASH"):
            m.verify(out)


if __name__=="__main__":
    unittest.main(verbosity=2)
