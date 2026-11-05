"""Create the default simulated account once, without asking the Owner.

The trusted ledger stays the only financial authority: this script writes one
Genesis record into a new ledger file and a path-only binding. It never trades,
never contacts a provider and never overwrites an existing ledger.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research"))
import stratide_paths as paths

FEN = 100
DEFAULTS = dict(
    authorized_principal=100_000 * FEN,
    initial_capital=100_000 * FEN,
    account_limits=dict(max_order_commitment=20_000 * FEN, max_exposure=40_000 * FEN,
                        daily_loss=2_000 * FEN, drawdown=10_000 * FEN),
    strategy_limits=dict(max_order_commitment=20_000 * FEN, max_exposure=40_000 * FEN,
                         daily_loss=2_000 * FEN, drawdown=10_000 * FEN),
    max_snapshot_age_ms=8 * 3600 * 1000,
    max_mark_age_ms=8 * 3600 * 1000,
)
DEPLOYMENT = dict(strategy_id="stratide-paper", group_id="main",
                  deployment_id="paper-main-v1", frozen_version="fixed-ticket-paper-v1")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def shanghai_now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))


def main():
    root = paths.common_root()
    state = root / "state/paper-portfolio"
    state.mkdir(parents=True, exist_ok=True)
    binding = state / "binding.json"
    ledger = state / "paper.sqlite"
    if binding.is_file() and ledger.is_file():
        print(json.dumps(dict(state="EXISTS", ledger=str(ledger))))
        return 0
    settings = root / "paper-account.json"
    config = dict(DEFAULTS, account_id="stratide-paper", deployment=DEPLOYMENT)
    if settings.is_file():
        overrides = json.loads(settings.read_text(encoding="utf-8"))
        for key in ("authorized_principal", "initial_capital", "account_limits",
                    "strategy_limits", "max_snapshot_age_ms", "max_mark_age_ms"):
            if key in overrides:
                config[key] = overrides[key]
    settings.write_text(json.dumps({k: config[k] for k in (
        "authorized_principal", "initial_capital", "account_limits",
        "strategy_limits", "max_snapshot_age_ms", "max_mark_age_ms")},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    now = shanghai_now()
    genesis = dict(
        config=config,
        # The merged ledger only supports synthetic_test and historical_replay.
        # This account is a paper hypothesis over collected daily bars; every UI
        # surface keeps it labelled simulated and not a forward observation.
        provenance=dict(mode="historical_replay", source_version="paper-eod-assumption-v1:stratide-forward-collect",
                        dataset_hash=hashlib.sha256(canonical(config)).hexdigest(),
                        timezone="Asia/Shanghai", price_semantics="unadjusted_cny_fen"),
        at=int(now.timestamp() * 1000),
        day=int(now.strftime("%Y%m%d")),
    )
    result = subprocess.run(
        [str(paths.executable("stratide-cli")), "paper-portfolio", str(ledger), "init"],
        input=canonical(genesis), capture_output=True, timeout=120)
    if result.returncode != 0:
        raise SystemExit("PAPER_ACCOUNT_INIT_FAILED " + result.stdout.decode(errors="replace")[-400:])
    binding.write_text(json.dumps(dict(ledger=str(ledger))), encoding="utf-8")
    print(json.dumps(dict(state="CREATED", ledger=str(ledger),
                          authorized_principal=config["authorized_principal"])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
