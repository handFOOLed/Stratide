"""Sol self-test on FROZEN REAL local history. Never uploads market rows.

Replays in fresh directories; checks reports, raw hashes, accounting and actual
process kill/resume. Mutated future-price probes are separately labelled tests.
Requires all six Owner-approved capital/risk flags explicitly after --.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import time

NAMES = ("events.json", "daily.csv", "orders.csv", "fills.csv", "positions.csv", "report.json")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def journal(path):
    with sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, timeout=0.1) as db:
        return db.execute("select seq,event_id,payload,digest from events order by seq").fetchall()


def verify_accounting(report):
    cash = report["initial_nav_fen"]
    shares = 0
    total_fee = 0
    ids = set()
    for f in report["fills"]:
        assert f["event_id"] not in ids
        ids.add(f["event_id"])
        assert f["quantity"] > 0 and f["quantity"] % 100 == 0
        assert "opening_evidence" not in f
        assert f["historical_execution"].startswith("historical_ex_post_execution_assumption")
        order = next(o for o in report["orders"] if o["proposal"]["proposal_id"] == f["order_id"])
        assert order["proposal"]["decision_at"] < f["evidence"]["opens_at"]
        assert order["accepted_on"] < f["day"]
        gross = f["quantity"] * f["price"]
        rates = report["fee_assumption"]
        commission = max((gross*rates["commission_ppm"]+999999)//1000000, rates["minimum_commission_fen"])
        transfer = (gross*rates["transfer_ppm"]+999999)//1000000
        tax = (gross*rates["sell_tax_ppm"]+999999)//1000000 if f["side"] == "Sell" else 0
        assert f["fees"] == dict(commission=commission, transfer=transfer, tax=tax)
        fee = commission+transfer+tax
        cash += (-gross if f["side"] == "Buy" else gross) - fee
        shares += f["quantity"] if f["side"] == "Buy" else -f["quantity"]
        assert cash >= 0 and shares >= 0
        total_fee += fee
    assert cash == report["ending_cash_fen"]
    assert shares == report["ending_held_shares"]
    assert total_fee == report["total_fee_fen"]
    assert report["ending_nav_fen"]-report["initial_nav_fen"] == report["realized_pnl_fen"]+report["unrealized_pnl_fen"]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--exe", type=Path, required=True)
    p.add_argument("--input", type=Path, required=True)
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("config", nargs=argparse.REMAINDER)
    a = p.parse_args()
    config = a.config[1:] if a.config[:1] == ["--"] else a.config
    assert len(config) == 12, "six explicit capital/risk flags required"
    a.output.mkdir(parents=True)
    source = json.loads(a.input.read_bytes())
    assert source["mode"] == "historical_replay" and source["schema_version"] == 2
    manifest = source["historical"]["source_manifest"]
    for name, expected in manifest["raw_sha256"].items():
        assert sha(a.source_dir / f"{name}.json") == expected
    exe = str(a.exe.resolve())

    def command(name, input_path=a.input):
        return [exe, "paper-replay", str(input_path.resolve()), str((a.output/name/"ledger").resolve()),
                str((a.output/name/"report").resolve()), "--sha256", sha(input_path), *config]

    def run(name, input_path=a.input):
        result = subprocess.run(command(name, input_path), capture_output=True, timeout=60)
        assert result.returncode == 0, result.stderr.decode("utf-8", errors="replace")
        return json.loads((a.output/name/"report/report.json").read_bytes())

    baseline = run("a")
    verify_accounting(baseline)
    run("b")
    for file in NAMES:
        assert (a.output/"a/report"/file).read_bytes() == (a.output/"b/report"/file).read_bytes()
    before = journal(a.output/"a/ledger/ledger.sqlite")
    run("a")
    assert journal(a.output/"a/ledger/ledger.sqlite") == before

    # The ledger holds SQLite EXCLUSIVE locking. Do not open a concurrent SQL
    # reader (it can interfere with first initialization). Observe the raw file
    # for a written event marker, kill, then let the CLI recover any hot journal
    # BEFORE inspecting the committed prefix via read-only SQL.
    first = next((x for x in baseline["events"] if x["new_fills"]), baseline["events"][len(baseline["events"])//2])
    needle = first["event_id"].encode()
    process = subprocess.Popen(command("interrupted"), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stopped = False
    deadline = time.monotonic()+30
    while process.poll() is None and time.monotonic() < deadline:
        try:
            raw = (a.output/"interrupted/ledger/ledger.sqlite").read_bytes()
            if needle in raw:
                process.kill()
                stopped = True
                break
        except OSError:
            pass
        time.sleep(0.005)
    process.communicate(timeout=10)
    assert stopped, "did not stop the child during a partial run"
    recovery = subprocess.run([exe, "paper-status", str((a.output/"interrupted/ledger").resolve())], capture_output=True, timeout=30)
    assert recovery.returncode == 0, "CLI failed to recover interrupted ledger; preserve all evidence"
    committed = journal(a.output/"interrupted/ledger/ledger.sqlite")
    assert 1 < len(committed) < len(before), "did not establish a committed mid-ledger prefix"
    run("interrupted")
    recovered = journal(a.output/"interrupted/ledger/ledger.sqlite")
    assert recovered[:len(committed)] == committed and recovered == before
    for file in NAMES:
        assert (a.output/"a/report"/file).read_bytes() == (a.output/"interrupted/report"/file).read_bytes()

    # A separate synthetic mutation of the real frozen input, never attributed as
    # another market observation. Change the first fill day's OHLC only. Compare
    # frozen T-day proposals (hash metadata correctly differs between inputs).
    changed = json.loads(a.input.read_bytes())
    target = baseline["fills"][0]["day"] if baseline["fills"] else baseline["daily"][-1]["day"]
    session = next(s for s in changed["sessions"] if s["day"] == target)
    tick = -1 if session["open_fen"]-session["low_fen"] > 2 else 1
    session["open_fen"] += tick
    session["low_fen"] = min(session["low_fen"], session["open_fen"])-1
    session["high_fen"] = max(session["high_fen"], session["open_fen"])+1
    session["close_fen"] += tick
    changed["source_version"] += "/synthetic_future_mutation_probe_not_market_evidence"
    probe = a.output/"mutated-fixture.json"
    probe.write_text(json.dumps(changed, ensure_ascii=False), encoding="utf-8")
    mutated = run("mutated-probe", probe)
    original_proposals = [o["proposal"] for o in baseline["orders"] if o["accepted_on"] < target]
    changed_proposals = [o["proposal"] for o in mutated["orders"] if o["accepted_on"] < target]
    assert original_proposals == changed_proposals
    if baseline["fills"]:
        assert baseline["fills"][0]["price"] != mutated["fills"][0]["price"]
    result = dict(kind="Sol_self_test_not_independent_acceptance", mode="historical_replay",
                  input_sha256=sha(a.input), first_day=baseline["first_day"], last_day=baseline["last_day"],
                  daily_rows=len(baseline["daily"]), orders=len(baseline["orders"]), fills=len(baseline["fills"]),
                  initial_nav_fen=baseline["initial_nav_fen"], ending_nav_fen=baseline["ending_nav_fen"],
                  ending_cash_fen=baseline["ending_cash_fen"], fees_fen=baseline["total_fee_fen"],
                  realized_pnl_fen=baseline["realized_pnl_fen"], unrealized_pnl_fen=baseline["unrealized_pnl_fen"],
                  ending_shares=baseline["ending_held_shares"],
                  identical_six_reports=True, duplicate_events_added=0, killed_after_committed_events=len(committed),
                  resumed_events_equal=True, future_mutation_keeps_prior_proposals=True,
                  financial_conservation=True, raw_hashes_verified=True)
    (a.output/"summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
