"""Offline corporate-action source evidence, never a financial ledger or PIT certifier.

V1 consumes a trusted operator's manifest and manually checked document transcript.
Hashes and quote checks prove local consistency, not authenticity of an arbitrary
PDF/transcript. No network, Provider, SQLite connection or trading entry point.
"""
import argparse
import datetime as dt
from decimal import Decimal
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from urllib.parse import urlsplit
import uuid

from .eod_journal import Rejected, ZONE, canonical, loads, no_links, require, sha

ROOT = Path(__file__).resolve().parents[1]
VERSION = "corporate-action-evidence-v1"
MAX_FILE = 4_000_000
HISTORY_NAMES = ("daily", "calendar", "limits", "suspensions", "extraction")
FIELDS = ("symbol", "event_id", "event_type", "announcement_date", "record_date",
          "ex_date", "scheduled_pay_date", "cash_amount", "cash_unit", "currency",
          "tax_basis", "tax_terms", "net_cash_amount", "stock_dividend_ratio",
          "capitalization_ratio", "rights_ratio", "stock_listing_date", "sellable_date",
          "actual_account_cash_received_at")
DATE_FIELDS = {"announcement_date", "record_date", "ex_date", "scheduled_pay_date",
               "stock_listing_date", "sellable_date"}
NUM_FIELDS = {"cash_amount", "net_cash_amount", "stock_dividend_ratio",
              "capitalization_ratio", "rights_ratio"}
ENUMS = {
    "symbol": {"600000.SH"}, "event_type": {"CASH_DIVIDEND", "SHARE_CHANGE"},
    "cash_unit": {"CNY_PER_SHARE", "CNY_PER_10_SHARES"}, "currency": {"CNY"},
    "tax_basis": {"GROSS", "NET"},
}
NEXT = {
    "PIT_NOT_VERIFIED": "历史决策时刻可得的逐版本原始记录及独立 PIT 核验；公告日期不能替代本机实收。",
    "ACCOUNTING_NOT_IMPLEMENTED": "另行授权共享 v3 ledger 的登记日权益、应收/到账、税务与股份事件及统一 NAV/报告。",
    "SOURCE_MISSING": "发行人/交易所/巨潮原始实施公告、精确字节和经人工核对的逐页文本。",
    "SOURCE_CONFLICT": "保留全部版本并核实更正关系与生效事实；V1 不自动选取有利版本。",
    "HISTORY_MISSING": "原 daily/calendar/limits/suspensions/extraction 五文件及既有 SHA。",
    "INITIAL_DISCLOSURE_NOT_OBTAINED": "同一事件的官方首次预案/披露原文及版本关系；搜索摘要不算原文。",
    "REVISION_HISTORY_NOT_VERIFIED": "可核实的历史修订全史与逐版本可得时刻；当前看到的公告不能证明未有更正。",
}


def keys(value, expected, code):
    require(type(value) is dict and set(value) == set(expected), code)


def string(value, code, limit=200):
    require(type(value) is str and 0 < len(value) <= limit and not any(ord(c) < 32 for c in value), code)
    return value


def identifier(value):
    require(type(value) is str and re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value), "IDENTIFIER_INVALID")
    return value


def digest(value):
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "SHA_INVALID")
    return value


def date(value):
    require(type(value) is str and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value), "DATE_INVALID")
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise Rejected("DATE_INVALID") from None


def timestamp(value):
    require(type(value) is str and len(value) <= 40, "TIMESTAMP_INVALID")
    try:
        result = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        require(result.tzinfo is not None, "TIMEZONE_REQUIRED")
        return result.astimezone(dt.timezone.utc)
    except ValueError:
        raise Rejected("TIMESTAMP_INVALID") from None


def utc(value):
    return value.isoformat().replace("+00:00", "Z")


def read_file(path, expected=None):
    path = Path(path).absolute()
    no_links(path)
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_FILE, "SOURCE_SIZE_OR_TYPE")
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE + 1)
    require(len(data) == info.st_size, "SOURCE_SIZE_CHANGED")
    if expected is not None:
        require(sha(data) == digest(expected), "SOURCE_SHA_MISMATCH")
    return data


def relative_file(root, name):
    require(type(name) is str and "\\" not in name and ":" not in name, "SOURCE_PATH_INVALID")
    rel = Path(name)
    require(not rel.is_absolute() and rel.parts and all(p not in (".", "..") for p in rel.parts),
            "SOURCE_PATH_INVALID")
    path = root / rel
    no_links(path)
    require(path.absolute().is_relative_to(root.absolute()), "SOURCE_PATH_INVALID")
    return path


def public_url(value, kind):
    if value is None:
        return None
    string(value, "PUBLIC_URL_INVALID", 500)
    u = urlsplit(value)
    hosts = {"static.cninfo.com.cn", "www.cninfo.com.cn", "www.sse.com.cn", "static.sse.com.cn",
             "www.spdb.com.cn", "news.spdb.com.cn"}
    require(u.scheme == "https" and u.hostname in hosts and not u.username and not u.password
            and u.port in (None, 443) and not u.query and not u.fragment, "PUBLIC_URL_INVALID")
    require(kind == "public_document", "SYNTHETIC_PUBLIC_URL_DENIED")
    return value


def compact(text):
    return "".join(text.split())


def check_fact(field, value, quote):
    """Check literal support; semantic column/identity mapping remains manual review."""
    if field in ENUMS:
        require(value in ENUMS[field], "FACT_ENUM_INVALID")
    if field in DATE_FIELDS:
        d = date(value)
        forms = (value, f"{d.year}/{d.month}/{d.day}", f"{d.year}年{d.month}月{d.day}日")
        require(any(s in quote for s in forms), "FACT_QUOTE_VALUE_MISMATCH")
    elif field in NUM_FIELDS:
        require(type(value) is str and re.fullmatch(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,8})?", value),
                "FACT_DECIMAL_INVALID")
        require(Decimal(value) >= 0 and re.search(r"(?<![\d.])" + re.escape(value) + r"(?![\d.])", quote),
                "FACT_QUOTE_VALUE_MISMATCH")
    elif field == "actual_account_cash_received_at":
        timestamp(value)
        require(value in quote, "FACT_QUOTE_VALUE_MISMATCH")
    else:
        tokens = {"symbol": "600000", "event_type": "现金红利" if value == "CASH_DIVIDEND" else "股",
                  "cash_unit": "每股" if value == "CNY_PER_SHARE" else "每10股",
                  "currency": "人民币", "tax_basis": "含税" if value == "GROSS" else "扣税后"}
        require(compact(tokens.get(field, value)) in quote, "FACT_QUOTE_VALUE_MISMATCH")


def history(spec, root, files):
    if spec is None:
        return None
    keys(spec, ("directory", "sha256"), "HISTORY_SCHEMA")
    keys(spec["sha256"], HISTORY_NAMES, "HISTORY_SHA_SCHEMA")
    require(type(spec["directory"]) is str, "HISTORY_PATH_INVALID")
    directory = Path(spec["directory"])
    directory = directory if directory.is_absolute() else relative_file(root, spec["directory"])
    no_links(directory)
    raw = {n: read_file(directory / (n + ".json"), spec["sha256"][n]) for n in HISTORY_NAMES}
    # Reuse the existing adapter's exact decimal/row semantics, never fetch/prepare.
    import importlib.util
    module_spec = importlib.util.spec_from_file_location("ca_historical", ROOT / "scripts/historical-data.py")
    adapter = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(adapter)
    daily_rows = adapter.rows(directory / "daily.json")
    daily = adapter.index(daily_rows, "trade_date", "20240101", "20261028")
    calendar = adapter.rows(directory / "calendar.json")
    extraction = loads(raw["extraction"])
    require(extraction["params"] == dict(ts_code="600000.SH", exchange="SSE",
                                        start_date="20240101", end_date="20261028"), "HISTORY_QUERY_MISMATCH")
    extracted_at = utc(timestamp(extraction["extracted_at_utc"]))
    discontinuities = []
    previous = None
    for day in sorted(daily):
        row = daily[day]
        close = adapter.exact(row["close"], 100)
        pre = adapter.exact(row["pre_close"], 100)
        if previous is not None and pre != previous:
            discontinuities.append(day)
        previous = close
    before = daily.get("20260715")
    current = daily.get("20260716")
    observed_delta = None
    if before and current:
        observed_delta = adapter.exact(before["close"], 100) - adapter.exact(current["pre_close"], 100)
    # Double-read bytes actually consumed by the adapter; do not open any database.
    for name in HISTORY_NAMES:
        require(read_file(directory / (name + ".json")) == raw[name], "HISTORY_CHANGED_DURING_READ")
        files[f"history/{name}.json"] = raw[name]
    return dict(raw_sha256={n: sha(raw[n]) for n in HISTORY_NAMES}, extracted_at=extracted_at,
                daily_rows=len(daily_rows), calendar_rows=len(calendar), discontinuities=discontinuities,
                breakpoint_present="20260716" in discontinuities,
                # Kept only inside ignored bundle; never emitted by public_summary.
                observed_close_minus_pre_close_fen=observed_delta,
                fee_model_version="paper-cost-assumption-20260706-v1", fee_valid_from="2026-07-06",
                fee_valid_through="2026-12-31", original_supported_sessions=68,
                original_supported_start="2026-07-17", original_supported_end="2026-10-28",
                history_quality_recertified=False)


def evaluate(manifest, root):
    keys(manifest, ("schema_version", "evidence_kind", "symbol", "breakpoint", "decision_at",
                    "documents", "events", "historical_source"), "MANIFEST_SCHEMA")
    require(type(manifest["schema_version"]) is int and manifest["schema_version"] == 1, "MANIFEST_VERSION")
    kind = manifest["evidence_kind"]
    require(kind in ("synthetic_test", "public_document"), "EVIDENCE_KIND")
    require(manifest["symbol"] == "600000.SH" and manifest["breakpoint"] == "2026-07-16", "V1_SCOPE")
    decision = timestamp(manifest["decision_at"])
    require(decision.astimezone(ZONE).date() == date("2026-07-16"), "DECISION_SCOPE")
    require(type(manifest["documents"]) is list and len(manifest["documents"]) <= 8, "DOCUMENT_LIMIT")
    require(type(manifest["events"]) is list and len(manifest["events"]) <= 8, "EVENT_LIMIT")
    frozen = {}
    docs, texts, acquisition, seen = {}, {}, {}, {}
    normalized_docs = []
    for source in manifest["documents"]:
        keys(source, ("id", "role", "version", "supersedes", "document_id", "path", "sha256",
                      "text_path", "text_sha256", "public_url", "obtained_at", "disclosed_on",
                      "published_at", "disclosure_basis", "review_method"), "DOCUMENT_SCHEMA")
        name = identifier(source["id"])
        if name in seen:
            require(source == seen[name], "DOCUMENT_ID_CONFLICT")
            continue
        seen[name] = source
        require(source["role"] in ("initial", "implementation", "correction"), "DOCUMENT_ROLE")
        string(source["version"], "DOCUMENT_VERSION")
        if source["supersedes"] is not None:
            identifier(source["supersedes"])
        if source["document_id"] is not None:
            string(source["document_id"], "DOCUMENT_ID")
        require(source["disclosure_basis"] in ("document_signed_date", "publisher_listing_date", "unverified"),
                "DISCLOSURE_BASIS")
        require(source["review_method"] == "operator_manual_document_text_crosscheck", "REVIEW_METHOD")
        obtained = timestamp(source["obtained_at"])
        require(obtained <= dt.datetime.now(dt.timezone.utc), "ACQUISITION_IN_FUTURE")
        if source["disclosed_on"] is not None:
            require(date(source["disclosed_on"]) <= obtained.astimezone(ZONE).date(), "DISCLOSURE_AFTER_ACQUISITION")
        if source["published_at"] is not None:
            require(timestamp(source["published_at"]) <= obtained, "DISCLOSURE_AFTER_ACQUISITION")
        url = public_url(source["public_url"], kind)
        raw_path = relative_file(root, source["path"])
        suffix = raw_path.suffix.lower()
        require(suffix in (".pdf", ".txt", ".html"), "DOCUMENT_TYPE")
        raw = read_file(raw_path, source["sha256"])
        if suffix == ".pdf":
            require(raw.startswith(b"%PDF-"), "DOCUMENT_NOT_PDF")
        text = read_file(relative_file(root, source["text_path"]), source["text_sha256"])
        pages = text.decode("utf-8").split("\f")
        require(len(pages) <= 100, "DOCUMENT_PAGE_LIMIT")
        path = "documents/" + sha(raw) + suffix
        text_path = "documents/" + sha(text) + ".txt"
        frozen[path], frozen[text_path] = raw, text
        doc = {k: source[k] for k in ("id", "role", "version", "supersedes", "document_id",
                                      "sha256", "text_sha256", "disclosed_on", "published_at",
                                      "disclosure_basis", "review_method")}
        doc.update(public_url=url, size_bytes=len(raw), text_size_bytes=len(text),
                   transcript_assurance="operator_attested_not_automatic_pdf_semantic_verification")
        docs[name], texts[name], acquisition[name] = doc, pages, utc(obtained)
        normalized_docs.append({**source, "path": path, "text_path": text_path, "obtained_at": utc(obtained)})
    for name, doc in docs.items():
        ancestor = doc["supersedes"]
        visited = {name}
        while ancestor is not None:
            require(ancestor in docs and ancestor not in visited, "REVISION_RELATION_INVALID")
            visited.add(ancestor)
            ancestor = docs[ancestor]["supersedes"]
    events = []
    for event in manifest["events"]:
        keys(event, ("source_id", "facts", "references"), "EVENT_SCHEMA")
        source_id = event["source_id"]
        require(source_id in docs, "EVENT_SOURCE_MISSING")
        keys(event["facts"], FIELDS, "FACTS_SCHEMA")
        require(type(event["references"]) is dict and set(event["references"]) <= set(FIELDS), "REFERENCES_SCHEMA")
        for field, value in event["facts"].items():
            if value is None:
                require(field not in event["references"], "NULL_FACT_HAS_REFERENCE")
                continue
            string(value, "FACT_VALUE_INVALID", 500)
            require(field in event["references"], "FACT_REFERENCE_MISSING")
            ref = event["references"][field]
            keys(ref, ("page", "quote"), "REFERENCE_SCHEMA")
            require(type(ref["page"]) is int and 1 <= ref["page"] <= len(texts[source_id]), "REFERENCE_PAGE")
            require(type(ref["quote"]) is str and 0 < len(ref["quote"]) <= 1500, "REFERENCE_QUOTE")
            quote = compact(ref["quote"])
            require(quote in compact(texts[source_id][ref["page"] - 1]), "QUOTE_NOT_IN_SOURCE")
            check_fact(field, value, quote)
        facts = event["facts"]
        if facts["record_date"] and facts["ex_date"]:
            require(date(facts["record_date"]) <= date(facts["ex_date"]), "EVENT_DATE_ORDER")
        if facts["scheduled_pay_date"] and facts["ex_date"]:
            require(date(facts["ex_date"]) <= date(facts["scheduled_pay_date"]), "EVENT_DATE_ORDER")
        events.append(event)
    # Exact repeated announcements/claims do not increase evidence. Preserve every
    # distinct document/version, but never silently pick a winner on disagreement.
    events = sorted({canonical(e): e for e in events}.values(), key=canonical)
    blockers = {"PIT_NOT_VERIFIED", "ACCOUNTING_NOT_IMPLEMENTED", "REVISION_HISTORY_NOT_VERIFIED"}
    if not any(d["role"] == "initial" for d in docs.values()):
        blockers.add("INITIAL_DISCLOSURE_NOT_OBTAINED")
    conflicts = set()
    for field in FIELDS:
        values = {e["facts"][field] for e in events if e["facts"][field] is not None}
        if len(values) > 1:
            conflicts.add(field)
    if conflicts:
        blockers.add("SOURCE_CONFLICT")
    eligible_sources = [e for e in events if docs[e["source_id"]]["role"] in ("implementation", "correction")
                        and (kind == "synthetic_test" or docs[e["source_id"]]["public_url"])]
    if not eligible_sources:
        blockers.add("SOURCE_MISSING")
    coverage = {}
    for field in FIELDS:
        values = sorted({e["facts"][field] for e in eligible_sources if e["facts"][field] is not None})
        coverage[field] = "CONFLICT" if field in conflicts else "VERIFIED_LITERAL" if values else "MISSING"
        if not values:
            blockers.add("FACT_MISSING:" + field)
    for name, doc in docs.items():
        if doc["disclosed_on"] is None:
            blockers.add("DISCLOSURE_DATE_MISSING:" + name)
        elif date(doc["disclosed_on"]) > decision.astimezone(ZONE).date():
            blockers.add("DISCLOSED_AFTER_DECISION:" + name)
        if doc["published_at"] is None:
            blockers.add("DISCLOSURE_TIME_NOT_VERIFIED:" + name)
        elif timestamp(doc["published_at"]) > decision:
            blockers.add("DISCLOSED_AFTER_DECISION:" + name)
        if timestamp(acquisition[name]) > decision:
            blockers.add("ACQUIRED_AFTER_DECISION:" + name)
    baseline = history(manifest["historical_source"], root, frozen)
    if baseline is None:
        blockers.add("HISTORY_MISSING")
    fact_status = ("SOURCE_CONFLICT" if conflicts else "DATA_BLOCKED" if not eligible_sources
                   else "FACTS_PARTIAL" if any(v != "VERIFIED_LITERAL" for v in coverage.values())
                   else "SYNTHETIC_PASS" if kind == "synthetic_test" else "VERIFIED")
    status = ("DATA_BLOCKED" if fact_status in ("SOURCE_CONFLICT", "DATA_BLOCKED") else
              "PARTIAL" if fact_status == "FACTS_PARTIAL" else "FOUND_VERIFIABLE_EVENT")
    dates = {e["facts"]["ex_date"] for e in eligible_sources if e["facts"]["ex_date"]}
    consistency = "SOURCE_CONFLICT" if conflicts else "NOT_CHECKED"
    if not conflicts and dates and baseline and baseline["breakpoint_present"]:
        consistency = "DATE_MATCH" if dates == {manifest["breakpoint"]} else "DATE_MISMATCH"
        if consistency == "DATE_MISMATCH":
            blockers.add("EVENT_BREAKPOINT_DATE_MISMATCH")
    amount_match = None
    if baseline and not conflicts:
        # This comparison consumes sourced amounts only. Never derive an event
        # amount from the market-price delta or emit raw prices to public output.
        matches = []
        for e in eligible_sources:
            f = e["facts"]
            if (f["event_type"] == "CASH_DIVIDEND" and f["cash_amount"] is not None
                    and f["cash_unit"] in ENUMS["cash_unit"] and f["currency"] == "CNY"
                    and f["tax_basis"] == "GROSS" and f["ex_date"] == manifest["breakpoint"]):
                fen = Decimal(f["cash_amount"]) * (100 if f["cash_unit"] == "CNY_PER_SHARE" else 10)
                if baseline["observed_close_minus_pre_close_fen"] is not None:
                    matches.append(fen == baseline["observed_close_minus_pre_close_fen"])
        amount_match = all(matches) if matches else None
        if amount_match is False:
            blockers.add("SOURCED_CASH_PRICE_DELTA_MISMATCH")
    content = dict(schema_version=1, parser_version=VERSION, evidence_kind=kind, symbol="600000.SH",
                   breakpoint="2026-07-16", decision_at=utc(decision),
                   documents=sorted(docs.values(), key=lambda d: d["id"]), events=events,
                   baseline=baseline, status=status, event_fact_status=fact_status,
                   historical_pit_status="NOT_VERIFIED", accounting_support_status="NOT_IMPLEMENTED",
                   historical_replay_eligible=False, eligibility="ELIGIBILITY_DENIED", opening_source="BLOCKED",
                   field_coverage=coverage, conflicting_fields=sorted(conflicts),
                   consistency=dict(event_ex_date_vs_breakpoint=consistency,
                                    sourced_cash_vs_price_delta_match=amount_match,
                                    event_within_existing_fee_model=True if dates == {"2026-07-16"} else None,
                                    prices_are_not_event_evidence=True, fee_history_recertified=False),
                   blockers=sorted(blockers),
                   next_required_evidence=[dict(blocker=b, required=NEXT.get(b,
                       "取得该字段的明确原文、适用身份/实际账户证据或历史逐版本实收；保留 null，不从价格补造。"))
                                          for b in sorted(blockers)],
                   missing_accounting_primitives=["record_date_entitlements", "dividend_receivable_and_settlement",
                       "tax_identity_holding_period_and_deferred_liability", "corporate_action_shares_and_sellable_date",
                       "single_ledger_nav_risk_and_report_reconciliation", "idempotent_event_versions"],
                   verification_scope="trusted_operator_manifest_and_manual_transcript; not_independent_acceptance")
    normalized = {**manifest, "documents": sorted(normalized_docs, key=lambda d: d["id"]), "events": events}
    if manifest["historical_source"] is not None:
        normalized["historical_source"] = {**manifest["historical_source"], "directory": "history"}
    return content, normalized, frozen, acquisition


def public_summary(envelope):
    c = envelope["content"]
    result = {k: c[k] for k in ("schema_version", "parser_version", "evidence_kind", "symbol", "breakpoint",
              "decision_at", "status", "event_fact_status", "historical_pit_status", "accounting_support_status",
              "historical_replay_eligible", "eligibility", "opening_source", "field_coverage", "conflicting_fields",
              "consistency", "blockers", "next_required_evidence", "missing_accounting_primitives", "verification_scope")}
    result.update(bundle_sha256=envelope["bundle_sha256"], verified_at=envelope["verified_at"],
                  documents=c["documents"], obtained_at=envelope["obtained_at"],
                  events=[dict(source_id=e["source_id"], facts=e["facts"]) for e in c["events"]])
    if c["baseline"]:
        result["historical_baseline"] = {k: v for k, v in c["baseline"].items()
                                         if k != "observed_close_minus_pre_close_fen"}
    else:
        result["historical_baseline"] = None
    return result


def status(bundle):
    bundle = Path(bundle).absolute()
    no_links(bundle)
    envelope = loads(read_file(bundle / "bundle.json"))
    keys(envelope, ("bundle_sha256", "content", "verified_at", "obtained_at", "verification_sha256"), "BUNDLE_SCHEMA")
    digest(envelope["bundle_sha256"])
    require(sha(canonical({k: v for k, v in envelope.items() if k != "verification_sha256"}))
            == envelope["verification_sha256"], "BUNDLE_VERIFICATION_SHA_MISMATCH")
    verified = timestamp(envelope["verified_at"])
    manifest = loads(read_file(bundle / "manifest.json"))
    content, _, _, obtained = evaluate(manifest, bundle)
    require(content == envelope["content"] and sha(canonical(content)) == envelope["bundle_sha256"],
            "BUNDLE_CONTENT_MISMATCH")
    require(obtained == envelope["obtained_at"] and all(timestamp(t) <= verified for t in obtained.values()),
            "BUNDLE_ACQUISITION_MISMATCH")
    return public_summary(envelope)


def write_frozen(path, data):
    no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def audit(manifest_path, out):
    manifest_path, out = Path(manifest_path).absolute(), Path(out).absolute()
    no_links(out)
    out = out.resolve()
    require(out.is_relative_to(ROOT / "state") and out != ROOT / "state", "OUTPUT_MUST_BE_NEW_STATE_DIRECTORY")
    ignored = subprocess.run(["git", "check-ignore", "--quiet", "--", str(out / "bundle.json")], cwd=ROOT)
    require(ignored.returncode == 0, "OUTPUT_MUST_BE_GITIGNORED")
    manifest = loads(read_file(manifest_path))
    content, normalized, files, acquisition = evaluate(manifest, manifest_path.parent)
    require(not manifest_path.is_relative_to(out), "OUTPUT_SOURCE_OVERLAP")
    key = sha(canonical(content))
    if out.exists():
        saved = status(out)
        require(saved["bundle_sha256"] == key, "IMMUTABLE_BUNDLE_USE_NEW_OUTPUT")
        return saved
    envelope = dict(bundle_sha256=key, content=content, verified_at=utc(dt.datetime.now(dt.timezone.utc)),
                    obtained_at=acquisition)
    envelope["verification_sha256"] = sha(canonical(envelope))
    stage = out.with_name("." + out.name + ".tmp-" + uuid.uuid4().hex)
    stage.mkdir(parents=True, exist_ok=False)
    # On interruption an unpublished sibling may remain. It is never status/read
    # success; retry uses a fresh sibling and does not overwrite existing evidence.
    for name, data in sorted(files.items()):
        write_frozen(stage / name, data)
    write_frozen(stage / "manifest.json", canonical(normalized))
    write_frozen(stage / "bundle.json", canonical(envelope))
    status(stage)
    require(not out.exists(), "OUTPUT_EXISTS")
    os.rename(stage, out)
    return status(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    a = commands.add_parser("audit", help="离线验证可信本机清单，原子发布新的 ignored 证据包")
    a.add_argument("--source-manifest", type=Path, required=True)
    a.add_argument("--out", type=Path, required=True)
    s = commands.add_parser("status", help="从包内冻结文档重算，只读、无网络")
    s.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.source_manifest, args.out) if args.command == "audit" else status(args.bundle)
        print(canonical(result).decode("utf-8"))
        # Exit 0 means the source audit is complete, never PIT/replay permission.
        return 0 if result["status"] == "FOUND_VERIFIABLE_EVENT" else 1 if result["status"] == "PARTIAL" else 2
    except (ValueError, OSError, KeyError, TypeError, UnicodeError, OverflowError):
        # Only fixed error codes may leave the process; OS/provider text can leak paths.
        error = sys.exception()
        code = str(error) if isinstance(error, Rejected) else "SOURCE_IO_OR_FORMAT_ERROR"
        print(canonical(dict(status="DATA_BLOCKED", error_code=code, historical_pit_status="NOT_VERIFIED",
                             accounting_support_status="NOT_IMPLEMENTED", historical_replay_eligible=False,
                             eligibility="ELIGIBILITY_DENIED", opening_source="BLOCKED")).decode("utf-8"))
        return 2


if __name__ == "__main__":
    sys.exit(main())
