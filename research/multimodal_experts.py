"""Versioned local numerical experts. No network, weights, execution or Agent queue.

Ratios are decimal strings per exchange session; timestamps are UTC milliseconds
rendered with Z. UNKNOWN_UNCALIBRATED is not a probability or confidence interval.
Only the trusted runner constructs identities, clocks, cost and authority.
"""
import datetime as dt
from decimal import Decimal, localcontext
import math
import re
import time

import eod_journal as j
import shadow as s

VERSION = "expert-result-v1"
POLICY = "multimodal-research-v1"
SCOPE = "multimodal_research_v1"
TARGET = "next_session_return_ratio"
WINDOW = 21
SAFE = dict(restriction="RESEARCH_ONLY", eligibility="ELIGIBILITY_DENIED",
            can_execute_forward_paper=False, live_allowed=False)
BASELINE = dict(model_id="naive-ewma", model_version="1")
ADAPTERS = {
    "local-test-shrinkage": dict(model_id="local-test-shrinkage", model_version="1"),
    "local-test-momentum": dict(model_id="local-test-momentum", model_version="1"),
    "external": dict(model_id="external", model_version="NOT_CONFIGURED"),
}
Q = Decimal("0.000000000001")


def digest(value):
    return j.sha(j.canonical(value))


def utc(ms):
    j.require(type(ms) is int and ms > 0, "EXPERT_TIME_INVALID")
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def timestamp(value):
    j.require(isinstance(value, str) and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", value),
              "EXPERT_TIMEZONE_INVALID")
    result = int(dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    j.require(utc(result) == value, "EXPERT_TIME_INVALID")
    return result


def number(value):
    j.require(isinstance(value, str) and len(value) <= 32
              and re.fullmatch(r"-?(0|[1-9][0-9]*)(\.[0-9]{1,12})?", value), "EXPERT_NUMBER_INVALID")
    result = Decimal(value)
    j.require(result.is_finite() and -1 <= result <= 1, "EXPERT_NUMBER_BOUND")
    return result


def decimal_text(value):
    with localcontext() as ctx:
        ctx.prec = 40
        value = Decimal(str(value)).quantize(Q)
    j.require(value.is_finite() and -1 <= value <= 1, "EXPERT_NUMBER_BOUND")
    return format(value, "f")


def closes(window):
    j.require(len(window) == WINDOW, "INSUFFICIENT_HISTORY")
    expected_bar = {"trade_day", "open_fen", "high_fen", "low_fen", "close_fen",
                    "volume_shares", "source_volume_unit", "price_semantics"}
    for row in window:
        bar = row["bar"]
        j.require(set(bar) == expected_bar and bar["price_semantics"] == "unadjusted_cny_fen"
                  and bar["source_volume_unit"] == "hand_100_shares", "WINDOW_UNITS_OR_LABEL_LEAK")
        j.require(all(type(bar[k]) is int and 0 < bar[k] <= 10**12 for k in
                      ("open_fen", "high_fen", "low_fen", "close_fen"))
                  and type(bar["volume_shares"]) is int and 0 <= bar["volume_shares"] <= 10**15
                  and bar["low_fen"] <= min(bar["open_fen"], bar["close_fen"])
                  <= max(bar["open_fen"], bar["close_fen"]) <= bar["high_fen"], "WINDOW_OHLCV_INVALID")
    values = [r["bar"]["close_fen"] for r in window]
    j.require(all(a < b for a, b in zip([r["bar"]["trade_day"] for r in window],
                                                      [r["bar"]["trade_day"] for r in window][1:])), "WINDOW_ORDER")
    j.require(all(abs(Decimal(b) / a - 1) <= 1 for a, b in zip(values, values[1:])), "RETURN_OUT_OF_BOUND")
    return values


def baseline(window):
    """Naive mean zero + EWMA second moment, lambda=.94, no fitting/labels."""
    values = closes(window)
    with localcontext() as ctx:
        ctx.prec = 40
        returns = [Decimal(b) / a - 1 for a, b in zip(values, values[1:])]
        mean, variance = returns[0], returns[0] ** 2
        for value in returns[1:]:
            mean = Decimal(".94") * mean + Decimal(".06") * value
            variance = Decimal(".94") * variance + Decimal(".06") * value ** 2
        return dict(expected_return_ratio=decimal_text(0), volatility_ratio=decimal_text(variance.sqrt()),
                    ewma_mean_ratio=decimal_text(mean))


class TimeSeriesAdapter:
    """Fixed local adapter registry, independent entry point from baseline.

    external is an explicit rejection boundary, not a vendor implementation.
    No dynamic module/executable, URL, remote configuration or model download.
    """
    def __init__(self, model_id):
        j.require(model_id in ADAPTERS, "TIMESERIES_MODEL_NOT_CONFIGURED")
        self.descriptor = ADAPTERS[model_id]

    def predict(self, window):
        j.require(self.descriptor["model_id"] != "external", "EXTERNAL_TIMESERIES_NOT_CONFIGURED")
        values = closes(window)
        returns = [b / a - 1.0 for a, b in zip(values, values[1:])]
        count = len(returns)
        mean = math.fsum(returns) / count
        if self.descriptor["model_id"] == "local-test-shrinkage":
            forecast = mean * count / (count + 20)
            volatility = math.sqrt(math.fsum((r - mean) ** 2 for r in returns) / (count - 1))
        else:
            forecast = math.fsum(returns[-5:]) / 10
            volatility = math.sqrt(math.fsum(r * r for r in returns) / count)
        j.require(math.isfinite(forecast) and math.isfinite(volatility), "EXPERT_NONFINITE")
        return dict(expected_return_ratio=decimal_text(forecast), volatility_ratio=decimal_text(volatility))


def recompute(window, descriptor):
    """Independent Decimal formulas check the bounded float adapter's output."""
    values = closes(window)
    with localcontext() as ctx:
        ctx.prec = 50
        ratios = [Decimal(values[i]) / values[i - 1] - 1 for i in range(1, len(values))]
        n = Decimal(len(ratios))
        if descriptor == BASELINE:
            weights = [Decimal(".94") ** (len(ratios) - 1)] + [
                Decimal(".06") * Decimal(".94") ** (len(ratios) - i - 1) for i in range(1, len(ratios))]
            return dict(expected_return_ratio=Decimal(0),
                        volatility_ratio=sum(w * r * r for w, r in zip(weights, ratios)).sqrt(),
                        ewma_mean_ratio=sum(w * r for w, r in zip(weights, ratios)))
        if descriptor == ADAPTERS["local-test-shrinkage"]:
            mean = sum(ratios) / n
            return dict(expected_return_ratio=sum(ratios) / (n + 20),
                        volatility_ratio=((sum(r * r for r in ratios) - sum(ratios) ** 2 / n) / (n - 1)).sqrt())
        j.require(descriptor == ADAPTERS["local-test-momentum"], "EXTERNAL_TIMESERIES_NOT_CONFIGURED")
        return dict(expected_return_ratio=sum(ratios[-5:]) / 10,
                    volatility_ratio=(sum(r * r for r in ratios) / n).sqrt())


def validate_metrics(result, window, descriptor):
    expected = recompute(window, descriptor)
    j.require(isinstance(result, dict) and set(result) == set(expected), "EXPERT_RESULT_FIELDS")
    for key, value in expected.items():
        actual = number(result[key])
        j.require((key != "volatility_ratio" or actual >= 0) and abs(actual - value) <= Q * 2,
                  "EXPERT_ARITHMETIC_MISMATCH")


def result(frozen, kind, at, *, adapter=None):
    started = time.perf_counter_ns()
    descriptor = BASELINE if kind == "baseline" else adapter.descriptor
    metrics = baseline(frozen["window"]) if kind == "baseline" else adapter.predict(frozen["window"])
    validate_metrics(metrics, frozen["window"], descriptor)
    elapsed = (time.perf_counter_ns() - started) // 1_000_000
    return dict(schema_version=1, contract=VERSION, expert_kind=kind, **descriptor,
                role="comparator" if kind == "baseline" else "temporal_evidence",
                task_id=frozen["task_id"], input_mode=frozen["input_mode"], instrument=frozen["instrument"],
                target=TARGET, horizon_sessions=1, input_snapshot_sha256=frozen["input_snapshot_sha256"],
                source_identity=frozen["source_identity_sha256"], as_of=utc(frozen["as_of"]),
                observed_at=utc(frozen["window"][-1]["observed_at"]), generated_at=utc(at),
                training_range=dict(first_day=frozen["window"][0]["bar"]["trade_day"],
                                    last_day=frozen["source_day"], samples=WINDOW),
                units="ratio_per_exchange_session", missing_policy="REJECT_NO_IMPUTATION",
                result=metrics, output_sha256=digest(metrics), uncertainty="UNKNOWN_UNCALIBRATED",
                evidence_refs=[frozen["input_snapshot_sha256"], frozen["window_sha256"]],
                quality="DETERMINISTIC_BASELINE" if kind == "baseline" else "LOCAL_TEST_EXPERT",
                limitations=["EXTERNAL_TIMESERIES_NOT_CONFIGURED", "NO_CALIBRATED_PROBABILITY",
                             "CORPORATE_ACTION_PIT_NOT_VERIFIED", "OPENING_SOURCE_BLOCKED"],
                cost=dict(billing="LOCAL_NO_BILLING", elapsed_ms=elapsed, input_tokens=None,
                          output_tokens=None, cloud_cost="UNKNOWN_NOT_BILLED"), authority=SAFE)


def validate_expert(value, frozen, kind):
    fields = {"schema_version", "contract", "expert_kind", "model_id", "model_version", "role", "task_id",
              "input_mode", "instrument", "target", "horizon_sessions", "input_snapshot_sha256", "source_identity",
              "as_of", "observed_at", "generated_at", "training_range", "units", "missing_policy", "result",
              "output_sha256", "uncertainty", "evidence_refs", "quality", "limitations", "cost", "authority"}
    j.require(isinstance(value, dict) and set(value) == fields and len(j.canonical(value)) <= 8192, "EXPERT_SCHEMA")
    descriptor = BASELINE if kind == "baseline" else frozen["plan"]["time_series"]
    for key, expected in dict(schema_version=1, contract=VERSION, expert_kind=kind, **descriptor,
            role="comparator" if kind == "baseline" else "temporal_evidence", task_id=frozen["task_id"],
            input_mode=frozen["input_mode"], instrument=frozen["instrument"], target=TARGET, horizon_sessions=1,
            input_snapshot_sha256=frozen["input_snapshot_sha256"], source_identity=frozen["source_identity_sha256"],
            as_of=utc(frozen["as_of"]), observed_at=utc(frozen["window"][-1]["observed_at"]),
            training_range=dict(first_day=frozen["window"][0]["bar"]["trade_day"], last_day=frozen["source_day"], samples=WINDOW),
            units="ratio_per_exchange_session", missing_policy="REJECT_NO_IMPUTATION",
            output_sha256=digest(value["result"]), uncertainty="UNKNOWN_UNCALIBRATED",
            evidence_refs=[frozen["input_snapshot_sha256"], frozen["window_sha256"]],
            quality="DETERMINISTIC_BASELINE" if kind == "baseline" else "LOCAL_TEST_EXPERT", authority=SAFE).items():
        j.require(value[key] == expected, "EXPERT_IDENTITY_OR_AUTHORITY")
    timestamp(value["as_of"])
    j.require(frozen["decision_at"] <= timestamp(value["generated_at"]) <= s.clock_ms(), "EXPERT_TIME_REGRESSION_OR_FUTURE")
    j.require(value["limitations"] == ["EXTERNAL_TIMESERIES_NOT_CONFIGURED", "NO_CALIBRATED_PROBABILITY",
              "CORPORATE_ACTION_PIT_NOT_VERIFIED", "OPENING_SOURCE_BLOCKED"], "EXPERT_QUALITY")
    cost = value["cost"]
    j.require(isinstance(cost, dict) and set(cost) == {"billing", "elapsed_ms", "input_tokens", "output_tokens", "cloud_cost"}
              and cost["billing"] == "LOCAL_NO_BILLING" and type(cost["elapsed_ms"]) is int
              and 0 <= cost["elapsed_ms"] <= 60000 and cost["input_tokens"] is None
              and cost["output_tokens"] is None and cost["cloud_cost"] == "UNKNOWN_NOT_BILLED", "EXPERT_COST")
    validate_metrics(value["result"], frozen["window"], descriptor)


def source_window(src, at, readiness_ref=None, *, replay=False):
    """Reuse #48 source/time/calendar rules; refuse revisions instead of warming
    up with retrospectively patched prices. Unadjusted is explicit, never PIT.
    """
    if readiness_ref is not None:
        import forward_readiness as r
        ready, window = r.window_readiness(src, at)
    else:
        ready, window = s.readiness(src, at)
    content = src["saved"]["content"]
    mode = content["data_mode"]
    j.require(mode in ("synthetic_test", "forward_observed_eod"), "HISTORICAL_REPLAY_EX_POST_ONLY")
    if len(window) < WINDOW:
        raise j.Rejected("INSUFFICIENT_FORWARD_HISTORY" if mode == "forward_observed_eod" else "INSUFFICIENT_HISTORY")
    j.require(not ready["blockers"], ready["blockers"][0] if ready["blockers"] else "WINDOW_BLOCKED")
    versions = content["versions"] if readiness_ref is None else [
        v for v in content["versions"] if v["bar"]["trade_day"] >= window[0]["bar"]["trade_day"]]
    j.require(not any(v["revision_of"] is not None or v["late_backfill"] for v in versions),
              "REVISED_OR_LATE_SOURCE_REJECTED")
    for row in window:
        key = row["bar"]["trade_day"]
        observed, received, available = [row[k] for k in ("observed_at", "received_at", "available_at")]
        j.require(0 < observed <= received <= available <= content["as_of_journal_event_at"] <= at
                  and all(j.day(t) == key for t in (observed, received, available)), "WINDOW_TIME_INVALID")
    closes(window)
    # PR33 alone is insufficient. Recompute the bound, on-day receipt rather
    # than replacing the old hard rejection with a caller's ready boolean.
    if mode == "forward_observed_eod" or readiness_ref is not None:
        j.require(readiness_ref is not None, "CORPORATE_ACTION_PIT_NOT_VERIFIED")
        import forward_readiness as r
        r.authorize(readiness_ref, src, at, current=not replay)
        ready["research_readiness_receipt"] = readiness_ref
    return ready, window


def experiment_key(spec):
    return digest(spec)


def validate_frozen(value):
    fields = {"schema_version", "policy", "task_id", "spec", "plan", "input_mode", "instrument", "source_day",
              "input_snapshot_sha256", "source_identity_sha256", "decision_at", "as_of", "snapshot_content",
              "latest_sync", "readiness", "window", "window_sha256", "authority"}
    j.require(isinstance(value, dict) and set(value) == fields and len(j.canonical(value)) <= 2 * 1024 * 1024,
              "FROZEN_SCHEMA")
    j.require(value["schema_version"] == 1 and value["policy"] == POLICY and value["authority"] == SAFE
              and value["task_id"] == experiment_key(value["spec"]), "FROZEN_IDENTITY")
    content = value["snapshot_content"]
    j.require(digest(content) == value["input_snapshot_sha256"] and value["input_mode"] == content["data_mode"]
              and value["instrument"] == content["instrument"] and value["source_day"] == content["last_valid_source_day"]
              and value["as_of"] == content["as_of_journal_event_at"], "FROZEN_SOURCE_SHA")
    identity = {key: content[key] for key in ("source", "instrument", "endpoint_version", "journal_genesis", "data_mode")}
    expected_spec = dict(
              source_identity_sha256=digest(identity), input_snapshot_sha256=digest(content),
              source_day=value["source_day"], target=TARGET, horizon_sessions=1, plan=value["plan"], policy=POLICY)
    receipt = value["readiness"].get("research_readiness_receipt")
    if receipt is not None:
        expected_spec["research_readiness_receipt"] = receipt
    j.require(value["source_identity_sha256"] == digest(identity) and value["spec"] == expected_spec,
              "FROZEN_SPEC_MISMATCH")
    ready, window = source_window(dict(saved=dict(content=content), attempt=value["latest_sync"]), value["decision_at"],
                                  receipt, replay=True)
    j.require(ready == value["readiness"] and window == value["window"]
              and digest(window) == value["window_sha256"], "FROZEN_WINDOW_MISMATCH")


def fusion_input(frozen, base, temporal):
    validate_frozen(frozen)
    validate_expert(base, frozen, "baseline")
    validate_expert(temporal, frozen, "time_series")
    different = base["result"]["expected_return_ratio"] != temporal["result"]["expected_return_ratio"]
    summary = dict(contract=SCOPE, task_id=frozen["task_id"], input_snapshot_sha256=frozen["input_snapshot_sha256"],
                   source_identity=frozen["source_identity_sha256"], source_day=frozen["source_day"],
                   instrument=frozen["instrument"], target=TARGET, horizon_sessions=1,
                   as_of=utc(frozen["as_of"]), baseline=base, time_series=temporal,
                   conflict="DIRECTION_DIFFERS_FROM_NAIVE" if different else "NO_NUMERIC_DISAGREEMENT",
                   quality_blockers=["EXTERNAL_TIMESERIES_NOT_CONFIGURED", "CORPORATE_ACTION_PIT_NOT_VERIFIED",
                                     "OPENING_SOURCE_BLOCKED"], uncertainty="UNKNOWN_UNCALIBRATED",
                   tradable_at="UNKNOWN_OPENING_SOURCE_BLOCKED", authority=SAFE)
    if "research_readiness_receipt" in frozen["readiness"]:
        summary["research_readiness_receipt"] = frozen["readiness"]["research_readiness_receipt"]
    j.require(len(j.canonical(summary)) <= 20000, "FUSION_INPUT_SIZE")
    day = frozen["source_day"]
    return dict(version=SCOPE + ":" + digest(summary), source_day=f"{day[:4]}-{day[4:6]}-{day[6:]}",
                mode=frozen["input_mode"], scopes=["owner_task", SCOPE], summary=summary, eod_eligible=False)


def walk_forward(content, descriptor):
    """Fixed, non-tuned synthetic prefix experiment; never an independent holdout."""
    j.require(content["data_mode"] == "synthetic_test", "WALK_FORWARD_SYNTHETIC_ONLY")
    days, gap = s.sequence(content, content["as_of_journal_event_at"])
    j.require(gap is None, "WALK_FORWARD_GAP")
    errors, rows, refusals = {"naive": [], "time_series": []}, [], 0
    adapter = TimeSeriesAdapter(descriptor["model_id"])
    for end in range(WINDOW, len(days)):
        prefix = days[end - WINDOW:end]
        # The later label is intentionally read only after both predictions.
        try:
            base, temporal = baseline(prefix), adapter.predict(prefix)
            validate_metrics(base, prefix, BASELINE)
            validate_metrics(temporal, prefix, descriptor)
        except j.Rejected:
            refusals += 1
            continue
        label = Decimal(days[end]["bar"]["close_fen"]) / prefix[-1]["bar"]["close_fen"] - 1
        row = dict(train_through=prefix[-1]["bar"]["trade_day"], revealed_day=days[end]["bar"]["trade_day"],
                   prefix_sha256=digest(prefix), naive=base["expected_return_ratio"],
                   time_series=temporal["expected_return_ratio"], revealed_return_ratio=decimal_text(label))
        rows.append(row)
        errors["naive"].append(abs(number(row["naive"]) - label))
        errors["time_series"].append(abs(number(row["time_series"]) - label))
    attempted = max(0, len(days) - WINDOW)
    return dict(status="SYNTHETIC_PREFIX_CHECK_NOT_INDEPENDENT" if rows else "INSUFFICIENT_EVIDENCE",
                attempted=attempted, evaluated=len(rows), refused=refusals,
                refusal_rate=decimal_text(Decimal(refusals) / attempted if attempted else 0),
                mean_absolute_error_ratio={key: decimal_text(sum(values) / len(values)) if values else None
                                           for key, values in errors.items()}, rows=rows,
                fusion_comparison="STRUCTURED_HYPOTHESES_ONLY_NO_PRICE_ACCURACY_SCORE",
                holdout="SYNTHETIC_EXPOSED_NOT_BLIND", authority=SAFE)
