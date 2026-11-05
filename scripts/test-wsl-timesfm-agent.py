"""Directed real-WSL TimesFM test through the installed-state Agent chain.

Requires an isolated STRATIDE_STATE_ROOT, release binaries in STRATIDE_BIN_DIR,
and STRATIDE_WSL_DISTRIBUTION/WORKSPACE/PYTHON/MODEL pointing at the Owner's
existing WSL2 venv/model. Uses synthetic numeric input only: no Tushare,
DeepSeek, market data or Paper ledger is touched.
"""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "research/timesfm_cpu"))
import cli


def run(command):
    result = subprocess.run([str(part) for part in command], capture_output=True)
    if result.returncode != 0:
        raise SystemExit(json.dumps(dict(state="FAILED", step="subprocess", command=command[1:],
                                         stdout=result.stdout.decode(errors="replace")[-1200:],
                                         stderr=result.stderr.decode(errors="replace")[-1200:])))
    return result


def main():
    state = Path(os.environ["STRATIDE_STATE_ROOT"])
    binaries = Path(os.environ["STRATIDE_BIN_DIR"])
    agent = state / "agent"
    agent.mkdir(parents=True, exist_ok=True)
    if not (agent / "settings.json").is_file():
        run([binaries / "stratided.exe", "--agent-init-fake", agent])
    binding = state / "state" / "risk-portfolio" / "agent-binding.json"
    if not binding.is_file():
        run([binaries / "risk-portfolio-agent.exe", "init", "--agent-dir", agent])
    cli.bridge("enable")
    descriptor = cli.bridge("descriptor")
    manifest = cli.model_manifest()
    name = "wsl-real-" + str(int(time.time()))
    plan = dict(batch=name, frozen=cli.frozen(descriptor, 1),
                manifest_sha256=manifest["manifest_sha256"],
                code_sha256=descriptor["code_sha256"], max_context=256,
                batch_size=1, threads=2)
    cli.bridge("project", plan)
    path = cli.batch_path(name)
    path.mkdir(parents=True, exist_ok=True)
    (path / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
    started = time.monotonic()
    first = cli.once(name)
    first_seconds = time.monotonic() - started
    verified = cli.verify(name)
    bundle = verified.get("result", {}).get("research", {}).get("risk_portfolio", {})
    receipt = bundle.get("receipt", {})
    started = time.monotonic()
    second = cli.once(name)
    second_seconds = time.monotonic() - started
    with sqlite3.connect(str(agent / "agent.sqlite")) as db:
        tasks = db.execute("SELECT COUNT(*) FROM tasks WHERE trigger_key=?",
                           ("timesfm-cpu-v1:" + name,)).fetchone()[0]
        calls = db.execute("SELECT COUNT(*) FROM calls WHERE task_id IN "
                           "(SELECT id FROM tasks WHERE trigger_key=?)",
                           ("timesfm-cpu-v1:" + name,)).fetchone()[0]
    result = dict(
        state="PASS",
        batch=name,
        first_state=first.get("state"),
        first_seconds=round(first_seconds, 3),
        second_state=second.get("state"),
        same_task=first.get("id") == second.get("id"),
        second_seconds=round(second_seconds, 3),
        agent_tasks=tasks,
        paid_calls=calls,
        verified=verified.get("verified"),
        model_revision=manifest["model_revision"],
        manifest_sha256=manifest["manifest_sha256"],
        weight_sha256=manifest["weight_sha256"],
        source=manifest["source"],
        receipt=dict(billing=receipt.get("billing"), request_sha256=receipt.get("request_sha256"),
                     manifest_sha256=receipt.get("manifest_sha256"),
                     code_sha256=receipt.get("code_sha256"),
                     model_revision=receipt.get("model_revision"),
                     weight_sha256=receipt.get("weight_sha256")),
        isolation=receipt.get("isolation"),
        metrics=receipt.get("metrics"),
        paper_allowed=verified.get("paper_allowed"),
        live_allowed=verified.get("live_allowed"),
    )
    assert result["first_state"] == "completed", result
    assert result["second_state"] == "completed" and result["same_task"], result
    assert result["agent_tasks"] == 1 and result["paid_calls"] == 0, result
    assert result["verified"] is True and result["paper_allowed"] is False
    assert result["live_allowed"] is False and result["source"] == "WSL2_TIMESFM_CPU", result
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
