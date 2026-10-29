"""Developer offline recheck of a forward journal; never fetches or writes it.

Output contains only counts, timestamps and hashes, never market values or raw bodies.
This is not independent acceptance, source certification or new forward observation.
"""
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from email.utils import parsedate_to_datetime
from pathlib import Path


def sha(data):
    return hashlib.sha256(data).hexdigest()


def day(ms):
    return datetime.fromtimestamp(ms / 1000, timezone(timedelta(hours=8))).strftime("%Y%m%d")


def verify(path):
    path = Path(path).resolve(strict=True)
    before = sha(path.read_bytes())
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        db.execute("PRAGMA query_only=ON")
        db.execute("BEGIN")
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1041
        rows = db.execute("SELECT seq,payload,digest FROM events ORDER BY seq").fetchall()
        checkpoints = db.execute("SELECT seq,digest FROM checkpoint").fetchall()
        assert len(checkpoints) == 1 and rows
        previous = ""
        starts = {}
        raw_count = bars = calendars = 0
        forward_days = set()
        availability = []
        config = json.loads(rows[0][1])["config"]
        exchange = "SSE" if config["instrument"].endswith(".SH") else "SZSE"
        for index, (seq, payload, digest) in enumerate(rows):
            assert seq == index
            encoded = json.dumps([1, "forward_observation", previous, seq, payload],
                                 ensure_ascii=False, separators=(",", ":")).encode()
            assert sha(encoded) == digest
            previous = digest
            event = json.loads(payload)
            kind = event["event"]
            if kind == "collection_started":
                assert event["run_id"] not in starts
                starts[event["run_id"]] = event
            elif kind == "interrupted":
                assert starts.pop(event["run_id"], None) is not None
            elif kind == "collection_finished":
                started = starts.pop(event["run_id"])
                out = event["outcome"]
                decoded = {}
                for raw in out["raw"]:
                    body = bytes(raw["body"])
                    assert sha(body) == raw["sha256"]
                    raw_count += 1
                    assert started["observed_at"] <= raw["received_at"] <= event["finished_at"]
                    response = json.loads(body, parse_float=Decimal)
                    assert response["code"] == 0 and raw["http_status"] == 200
                    fields = response["data"]["fields"]
                    assert len(fields) == len(set(fields))
                    decoded[raw["api"]] = [dict(zip(fields, row, strict=True))
                                           for row in response["data"]["items"]]
                    if out["status"] == "valid_eod":
                        stamp = parsedate_to_datetime(raw["server_date"]).timestamp() * 1000
                        assert abs(stamp - raw["received_at"]) <= 300_000
                        assert raw["received_at"] <= out["available_at"]
                if out["calendar"]:
                    cal = decoded["trade_cal"]
                    assert all(r["exchange"] == exchange for r in cal)
                    assert sorted((r["cal_date"], bool(int(r["is_open"]))) for r in cal) == sorted(
                        (r["day"], r["is_open"]) for r in out["calendar"])
                    calendars += 1
                if out["bar"] is not None:
                    bar = out["bar"]
                    daily = decoded["daily"]
                    assert len(daily) == 1
                    raw_bar = daily[0]
                    assert raw_bar["ts_code"] == config["instrument"]
                    assert raw_bar["trade_date"] == bar["trade_day"] == started["trade_day"]
                    for field in ("open", "high", "low", "close"):
                        exact = Decimal(str(raw_bar[field])) * 100
                        assert exact == exact.to_integral_value() == bar[field + "_fen"]
                    volume = Decimal(str(raw_bar["vol"])) * 100
                    assert volume == volume.to_integral_value() == bar["volume_shares"]
                    assert bar["price_semantics"] == "unadjusted_cny_fen"
                    assert bar["source_volume_unit"] == "hand_100_shares"
                    assert started["observed_at"] <= out["available_at"] <= event["finished_at"]
                    late = (bar["trade_day"] < day(started["observed_at"])
                            or bar["trade_day"] < day(event["finished_at"]))
                    assert out["late_backfill"] == late
                    availability.append(out["available_at"])
                    bars += 1
                    if out["status"] == "valid_eod" and not late:
                        forward_days.add(bar["trade_day"])
        assert checkpoints[0] == (rows[-1][0], previous)
    after = sha(path.read_bytes())
    assert before == after, "concurrent change or unexpected mutation; do not certify this run"
    return dict(verification_kind="developer_full_readonly_offline_recheck_not_independent_acceptance",
                sqlite_open_mode="ro + query_only + read_transaction", integrity_check="ok",
                journal_schema=1041, events=len(rows), checkpoint_count=1, head=previous,
                event_chain_and_checkpoint_recomputed=True, raw_sha256_recomputed=raw_count,
                normalized_bars_recomputed=bars, calendars_recomputed=calendars,
                actual_valid_forward_days=len(forward_days), pending_runs=len(starts),
                available_at_epoch_ms=availability, database_sha256_before=before,
                database_sha256_after=after, original_bytes_unchanged=True,
                new_http_calls=0, raw_market_data_uploaded=False,
                available_at_semantics="validated_in_process_precommit_not_exact_commit_visibility")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify-forward-readonly.py <existing forward.sqlite>")
    print(json.dumps(verify(sys.argv[1]), ensure_ascii=False, indent=2))
