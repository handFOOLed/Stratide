"""Read-only forward accumulation and explicit admission blockers; no collection."""
from contextlib import closing
import datetime as dt
from pathlib import Path
import sqlite3

import eod_journal as j


def blockers(observation=None):
    entries = [
        ("historical_pit", "HISTORICAL_PIT_NOT_VERIFIED", "历史首次发布、修订与当时实收证据", "docs/M1_PR07_AUDIT.md", "#17"),
        ("historical_fees", "HISTORICAL_FEE_EFFECTIVE_DATES_MISSING", "2026-07-06 以前适用费用与取整的版本化来源", "docs/M1_PR07_AUDIT.md", "#17"),
        ("corporate_actions_2024_2025", "CORPORATE_ACTION_FACTS_MISSING", "2024/2025 事件公告、登记、除权与到账事实", "docs/M1_PR07_AUDIT.md", "#17"),
        ("corporate_action_2026", "FACTS_PARTIAL_PIT_TAX_SETTLEMENT_UNVERIFIED", "2026 事件历史 PIT、实际账户税务、到账与权益", "docs/M1_PR09.md", "#17"),
        ("opening", "OPENING_SOURCE_NOT_VERIFIED", "独立开盘权限、窗口内实收、单位/延迟与费用", "docs/M1_PR04B_OPENING_EVIDENCE.md", "#10"),
        ("action_feed", "COVERAGE_NOT_ATTESTED", "逐日当时取得的完整公司行为覆盖证据", "docs/M1_PR11.md", "#10/#17"),
        ("forward_paper", "FORWARD_OBSERVATION_NOT_PAPER_FILLS", "前向研究就绪、开盘/费用与实际模拟成交证据", "docs/M1_PR11.md", "#10"),
        ("real_fusion", "REAL_MARKET_DATA_EGRESS_DENIED", "Owner 对指定真实数据类别/接收方的另行显式授权", "docs/M2_PR20.md", "#76"),
    ]
    root = Path(__file__).resolve().parents[1]
    matrix = [dict(dependency=k,status="BLOCKED",reason=reason,required_evidence=required,
                   source=source,source_sha256=j.sha((root/source).read_bytes()),issue=issue)
              for k,reason,required,source,issue in entries]
    return dict(schema_version=1, engineering="SEPARATE_FROM_QUALIFICATION", historical_ex_post="RESEARCH_ONLY",
                historical_pit="BLOCKED", forward_paper="BLOCKED", live="BLOCKED", matrix=matrix,
                observation=observation, orders=0,fills=0,nav=None,
                independent_acceptance="NOT_PERFORMED_BY_THIS_DEVELOPER")


def operator_audit(path, observer):
    if path is None:
        return dict(state="NOT_VERIFIED",reason="OPERATOR_NOT_PROVIDED")
    path=Path(path).absolute()
    j.no_links(path)
    j.require(not any(Path(str(path)+s).exists() for s in ("-wal","-shm","-journal")), "OPERATOR_BUSY")
    before=j.sha(path.read_bytes())
    from eod_operator import Operator, POLICY
    with closing(sqlite3.connect(path.as_uri()+"?mode=ro",uri=True)) as db:
        db.execute("PRAGMA query_only=ON"); db.execute("BEGIN")
        row=db.execute("SELECT payload FROM events WHERE seq=0").fetchone()
        j.require(row, "OPERATOR_EMPTY")
        identity=j.loads(row[0])["data"]["identity"]
        j.require(identity["policy"] == POLICY, "OPERATOR_BINDING_CHANGED")
        verifier=Operator.__new__(Operator)
        verifier.identity=identity
        verifier.key=j.sha(j.canonical(identity))
        state=verifier.journal(db)
    j.require(before == j.sha(path.read_bytes()), "OPERATOR_CHANGED_DURING_READ")
    receipts=[e["data"] for e in state["entries"] if e["kind"] == "receipt"]
    observer_refs=[x["refs"]["observer"] for x in receipts if "observer" in x.get("refs",{})]
    # This audits only the observer association. Snapshot/Shadow/Fake are separate authorities.
    valid=bool(observer) and bool(observer_refs) and all(x["journal_head"] in observer["journal_chain"] for x in observer_refs)
    return dict(state="CHAIN_VERIFIED" if valid else "NOT_VERIFIED", journal_head=state["head"],
                database_sha256=before, events=len(state["entries"]), enabled=state["enabled"],
                journal_chain_verified=True, observer_prefix_refs_verified=valid, downstream_refs="NOT_VERIFIED_READ_ONLY_OBSERVER_SCOPE",
                receipts=[{k:x.get(k) for k in ("source_day","state","reason")} for x in receipts],
                credential_content_read=False, database_mutated=False)


def accumulate(content, calendar, through, audit_day=None):
    j.date(through)
    audit_day=audit_day or dt.datetime.now(j.ZONE).strftime("%Y%m%d")
    j.require(through <= audit_day,"AUDIT_FUTURE_DAY")
    start = j.day(content["as_of_journal_event_at"]) if not content["coverage"] else content["coverage"][0]["source_day"]
    j.require(start <= through, "AUDIT_RANGE")
    versions=content["versions"]
    rows=[]
    for delta in range((j.date(through)-j.date(start)).days+1):
        day=(j.date(start)+dt.timedelta(days=delta)).strftime("%Y%m%d")
        v=[x for x in versions if x["bar"]["trade_day"] == day]
        attempts=[x for x in content["attempts"] if x["trade_day"] == day]
        opened=calendar.get(day)
        conflict=any(x["revision_of"] is not None for x in v) or "CALENDAR_CONFLICT" in content["blockers"]
        if opened is None:
            state, reason="NOT_VERIFIED", "CALENDAR_UNKNOWN"
        elif not opened:
            state, reason="CLOSED", None
        elif conflict:
            state, reason="BLOCKED", "REVISED_OR_CONFLICTING_EVIDENCE"
        elif any(not x["late_backfill"] and x["duplicate_of"] is None for x in v):
            state, reason="ON_TIME", None
        elif v:
            state, reason="LATE_BACKFILL", "NOT_ON_DAY_OBSERVATION"
        elif day in content.get("pending_days",[]):
            state, reason="BLOCKED", "PENDING_COLLECTION"
        elif attempts:
            state, reason="BLOCKED", "COLLECTION_FAILED_OR_INCOMPLETE"
        elif day == audit_day:
            state, reason="NOT_VERIFIED", "CURRENT_DAY_NOT_CLOSED_BY_THIS_READ_ONLY_AUDIT"
        else:
            state, reason="MISSED", "KNOWN_OPEN_DAY_WITHOUT_ON_DAY_COLLECTION"
        rows.append(dict(source_day=day,state=state,reason=reason,attempts=len(attempts),
                         acquired_at=[x["available_at"] for x in v],
                         late_backfill=sum(x["late_backfill"] for x in v)))
    actual_mode=content["data_mode"] == "forward_observed_eod"
    on_time=sum(r["state"] == "ON_TIME" for r in rows)
    run=longest=0
    for row in rows:
        if row["state"] == "CLOSED": continue
        run = run+1 if row["state"] == "ON_TIME" else 0
        longest=max(longest,run)
    return dict(data_mode=content["data_mode"], through=through,days=rows,on_time_days=on_time,
                longest_consecutive_known_open_days=longest,
                cumulative_continuity="EOD_CONTINUITY_VERIFIED" if actual_mode and longest >= 2 else "NOT_VERIFIED",
                current_continuity="GAPS_OR_UNVERIFIED" if any(x["state"] not in ("ON_TIME","CLOSED") for x in rows) else "COVERED_IN_AUDITED_RANGE",
                raw_sha256=content["raw_sha256"],journal_head=content["journal_head"],
                events=content["event_count"],opening_source="BLOCKED",orders=0,fills=0,nav=None,
                physical_restart="NOT_VERIFIED",new_observed_days_created=0)


def audit(observer, through, out, operator=None, v1_root=None, v2_root=None):
    from risk_evaluation import new_directory, write, SAFE
    j.require(through is not None,"AUDIT_THROUGH_REQUIRED")
    content,before=(j.read_observer(observer) if observer else (None,None))
    if content:
        # The original reader verifies all events; retain unfinished run dates for
        # accurate per-day BLOCKED status after a collector crash.
        with closing(sqlite3.connect(Path(observer).absolute().as_uri()+"?mode=ro",uri=True)) as db:
            db.execute("PRAGMA query_only=ON");db.execute("BEGIN")
            pending={}
            for (payload,) in db.execute("SELECT payload FROM events ORDER BY seq"):
                event=j.loads(payload)
                if event["event"]=="collection_started":pending[event["run_id"]]=event["trade_day"]
                elif event["event"] in ("collection_finished","interrupted"):pending.pop(event["run_id"],None)
        content["pending_days"]=sorted(set(pending.values()))
        # Local journal's accepted raw calendar; V2 adds known days, never weekdays.
        calendar={x["source_day"]:x["state"] != "market_closed" for x in content["coverage"] if x["state"] != "calendar_unknown"}
        if v1_root and v2_root:
            from multistock_data import Dataset
            with Dataset(v1_root,v2_root) as ds:
                exchange="SSE" if content["instrument"].endswith(".SH") else "SZSE"
                for (e,day),opened in ds.calendar.items():
                    if e != exchange or day > through: continue
                    if day in calendar:
                        j.require(calendar[day] == (opened == "1"),"AUDIT_CALENDAR_CONFLICT")
                    calendar[day]=opened == "1"
        obs=accumulate(content,calendar,through)
    else:
        obs=dict(state="NOT_VERIFIED",reason="ORIGINAL_OBSERVER_UNAVAILABLE",new_observed_days_created=0)
    op=operator_audit(operator,content)
    if observer:
        j.require(before == j.sha(Path(observer).read_bytes()),"SOURCE_CHANGED_DURING_READ")
    report=dict(schema_version=1,observation=obs,operator=op,admission=blockers(obs),
                observer_database_sha256=before,observer_bytes_unchanged=True,new_http_calls=0,
                key_content_read=False,**SAFE)
    path=new_directory(out)
    write(path/"audit.json",report)
    digest=j.sha((path/"audit.json").read_bytes())
    write(path/"audit-seal.json",dict(report_sha256=digest))
    return dict(state="AUDITED",report_sha256=digest, observation={k:obs.get(k) for k in
                ("data_mode","on_time_days","longest_consecutive_known_open_days","cumulative_continuity","current_continuity")},
                operator_state=op["state"],admission="BLOCKED",new_http_calls=0,key_content_read=False,**SAFE)
