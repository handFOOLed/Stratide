"""Sol self-test: kill the real CLI during report staging, then resume.

Uses only explicit synthetic inputs and fresh output directories. Existing
acceptance evidence is never changed. No production crash hook is enabled.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import time

NAMES = ("events.json", "daily.csv", "orders.csv", "fills.csv", "positions.csv", "report.json")
CONFIG = ["--initial-cash-fen", "1000000", "--max-order-fen", "500000",
          "--account-cap-fen", "800000", "--strategy-cap-fen", "500000",
          "--daily-loss-fen", "100000", "--drawdown-fen", "200000"]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def events(ledger):
    with sqlite3.connect(f"{(ledger / 'ledger.sqlite').as_uri()}?mode=ro", uri=True) as db:
        return db.execute("select seq,event_id,payload,digest from events order by seq").fetchall()


def equal_reports(left, right):
    return all((left / name).read_bytes() == (right / name).read_bytes() for name in NAMES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--input", type=Path, default=Path("samples/m0-pr03-synthetic.json"))
    args = parser.parse_args()
    root = args.output.resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()  # Never overwrite a previous self-test run.
    exe = str(args.exe.resolve())
    source = args.input.resolve()

    def command(data, ledger, report):
        return [exe, "paper-replay", str(data), str(ledger), str(report),
                "--sha256", sha(data), *CONFIG]

    def run(data, ledger, report, expected=0):
        result = subprocess.run(command(data, ledger, report), capture_output=True)
        assert result.returncode == expected, result.stderr.decode("utf-8", errors="replace")
        return result

    ledger, baseline, partial = root / "ledger", root / "baseline", root / "partial"
    run(source, ledger, baseline)
    before = events(ledger)
    db_hash = sha(ledger / "ledger.sqlite")
    partial.mkdir()
    shutil.copyfile(baseline / "events.json", partial / "events.json")
    (partial / "daily.csv").write_bytes(b"")
    run(source, ledger, partial)
    assert equal_reports(partial, baseline) and events(ledger) == before
    assert sha(ledger / "ledger.sqlite") == db_hash
    archived = list(root.glob(".partial.stratide-*.interrupted"))
    assert len(archived) == 1
    assert (archived[0] / "events.json").read_bytes() == (baseline / "events.json").read_bytes()
    assert (archived[0] / "daily.csv").read_bytes() == b""

    conflict = root / "conflict"
    shutil.copytree(baseline, conflict)
    (conflict / "daily.csv").write_bytes(b"different existing evidence\n")
    conflict_before = {name: sha(conflict / name) for name in NAMES}
    run(source, ledger, conflict, expected=2)
    assert {name: sha(conflict / name) for name in NAMES} == conflict_before
    assert events(ledger) == before

    # Pad only the synthetic source description to make the real filesystem
    # staging window observable. Prices, model and financial rules stay synthetic.
    data = json.loads(source.read_bytes())
    data["source"] += "/self-test-padding/" + "x" * 131072
    padded = root / "padded-synthetic.json"
    padded.write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
    padded_ledger, padded_report = root / "padded-ledger", root / "padded-baseline"
    run(padded, padded_ledger, padded_report)
    padded_events = events(padded_ledger)
    kill_result = None
    for attempt in range(5):
        killed_ledger = root / f"killed-ledger-{attempt}"
        killed_report = root / f"killed-report-{attempt}"
        process = subprocess.Popen(command(padded, killed_ledger, killed_report),
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            stages = list(root.glob(f".{killed_report.name}.stratide-*"))
            if any((stage / "events.json").exists() for stage in stages):
                process.kill()
                process.wait()
                if not killed_report.exists():
                    kill_result = (attempt, killed_ledger, killed_report, process.returncode, stages)
                break
        if process.poll() is None:
            process.kill()
            process.wait()
        if kill_result:
            break
    assert kill_result, "NOT VERIFIED: failed to interrupt the real staging window"
    attempt, killed_ledger, killed_report, killed_exit, stages = kill_result
    assert events(killed_ledger) == padded_events  # All economics committed before export.
    remnants = [{"path": str(stage), "files": {
        p.name: p.stat().st_size for p in stage.iterdir() if p.is_file()
    }} for stage in stages]
    run(padded, killed_ledger, killed_report)
    assert events(killed_ledger) == padded_events and equal_reports(killed_report, padded_report)
    run(padded, killed_ledger, killed_report)
    assert equal_reports(killed_report, padded_report)
    result = dict(
        classification="Sol self-test, synthetic_test only; not independent acceptance",
        legacy_partial_same_path="PASS; archived unchanged",
        conflict_preserved="PASS", real_cli_kill_attempt=attempt,
        killed_exit=killed_exit, staging_remnants=remnants,
        real_cli_same_path_resume="PASS; all events and six files equal baseline",
        fixture_sha256=sha(source), fixture_ledger_head=before[-1][3],
        fixture_reports={name: sha(baseline / name) for name in NAMES},
        padded_input_sha256=sha(padded), padded_ledger_head=padded_events[-1][3],
    )
    (root / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
