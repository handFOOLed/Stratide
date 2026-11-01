"""Offline, operator-reviewed action feed evidence. No HTTP, secrets or accounts.

The publisher's complete-coverage contract is a separate trust input. An empty
event array is never a coverage contract. Acquisition is stamped by the caller's
trusted local collector, never imported from a user-supplied historical date.
PR38 owns document/literal checks; PR40's gross CNY units/date ordering are used
only as constraints, never as authority to book a real dividend or adjust price.
"""
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
import re

import corporate_actions as ca
import eod_journal as j

VERSION = "forward-action-evidence-v1"
COMPLETE = "all_price_affecting_corporate_actions"
MAX_RECORDS = 256


def keys(value, fields, code):
    ca.keys(value, fields, code)


def text(value, code, limit=500):
    return ca.string(value, code, limit)


def stamp(value):
    j.require(type(value) is int and value > 0, "EVIDENCE_TIMESTAMP")
    j.day(value)
    return value


@dataclass(frozen=True)
class SourceContract:
    schema_version: int
    source_id: str
    kind: str
    version: str
    publisher_url: str | None
    permission_basis: str
    completeness_scope: str
    completeness_quote: str
    document_sha256: str
    review_method: str

    @classmethod
    def parse(cls, value, document, mode):
        keys(value, cls.__dataclass_fields__, "ACTION_CONTRACT_SCHEMA")
        j.require(type(value["schema_version"]) is int and value["schema_version"] == 1,
                  "ACTION_CONTRACT_VERSION")
        ca.identifier(value["source_id"])
        text(value["version"], "ACTION_CONTRACT_VERSION")
        j.require(value["kind"] == ("synthetic_test" if mode == "synthetic_test" else "official_event_feed"),
                  "ACTION_SOURCE_MODE_MISMATCH")
        ca.public_url(value["publisher_url"], "synthetic_test" if mode == "synthetic_test" else "public_document")
        j.require(mode == "synthetic_test" or value["publisher_url"] is not None, "OFFICIAL_SOURCE_REQUIRED")
        text(value["permission_basis"], "ACTION_PERMISSION_REQUIRED")
        j.require(value["completeness_scope"] == COMPLETE
                  and value["review_method"] == "operator_manual_document_text_crosscheck",
                  "COVERAGE_NOT_ATTESTED")
        text(value["completeness_quote"], "COVERAGE_NOT_ATTESTED", 1500)
        j.require(j.sha(document) == ca.digest(value["document_sha256"]), "ACTION_CONTRACT_DOCUMENT_SHA")
        j.require(ca.compact(value["completeness_quote"]) in ca.compact(document.decode("utf-8")),
                  "COVERAGE_QUOTE_NOT_IN_SOURCE")
        return cls(**value)


def load_contract(path, mode):
    path = Path(path).absolute()
    manifest = j.loads(ca.read_file(path))
    j.require(type(manifest) is dict and "document_path" in manifest, "ACTION_CONTRACT_SCHEMA")
    value = {k: v for k, v in manifest.items() if k != "document_path"}
    document = ca.read_file(ca.relative_file(path.parent, manifest["document_path"]))
    contract = SourceContract.parse(value, document, mode)
    return asdict(contract), document


def event_facts(value, instrument):
    keys(value, ca.FIELDS, "ACTION_FACTS_SCHEMA")
    j.require(value["symbol"] == instrument, "ACTION_INSTRUMENT_CONFLICT")
    for field, fact in value.items():
        if fact is None:
            continue
        text(fact, "ACTION_FACT_VALUE")
        if field in ca.ENUMS:
            j.require(fact in ca.ENUMS[field], "ACTION_UNIT_OR_CURRENCY")
        if field in ca.DATE_FIELDS:
            ca.date(fact)
        if field in ca.NUM_FIELDS:
            j.require(re.fullmatch(r"(?:0|[1-9]\d{0,8})(?:\.\d{1,8})?", fact)
                      and Decimal(fact) >= 0, "ACTION_AMOUNT_INVALID")
        if field == "actual_account_cash_received_at":
            ca.timestamp(fact)
    for before, after in (("record_date", "ex_date"), ("ex_date", "scheduled_pay_date"),
                          ("stock_listing_date", "sellable_date")):
        if value[before] and value[after]:
            j.require(ca.date(value[before]) <= ca.date(value[after]), "ACTION_DATE_CONFLICT")
    return value


@dataclass(frozen=True)
class Coverage:
    schema_version: int
    source_id: str
    source_version: str
    instrument: str
    as_of_day: str
    covered_from: str
    covered_through: str
    complete_scope: str | None
    publisher_generated_at: int | None
    revision: str
    supersedes: str | None
    events: list

    @classmethod
    def parse(cls, value, contract, instrument):
        keys(value, cls.__dataclass_fields__, "ACTION_PAYLOAD_SCHEMA")
        j.require(type(value["schema_version"]) is int and value["schema_version"] == 1,
                  "ACTION_PAYLOAD_VERSION")
        j.require(value["source_id"] == contract.source_id and value["source_version"] == contract.version,
                  "ACTION_SOURCE_IDENTITY")
        j.require(value["instrument"] == instrument, "ACTION_INSTRUMENT_CONFLICT")
        for name in ("as_of_day", "covered_from", "covered_through"):
            j.date(value[name])
        j.require(value["covered_from"] <= value["covered_through"] <= value["as_of_day"],
                  "ACTION_COVERAGE_DATE_CONFLICT")
        j.require(value["complete_scope"] in (None, COMPLETE), "COVERAGE_NOT_ATTESTED")
        if value["publisher_generated_at"] is not None:
            stamp(value["publisher_generated_at"])
        text(value["revision"], "ACTION_REVISION")
        if value["supersedes"] is not None:
            text(value["supersedes"], "ACTION_REVISION")
            j.require(value["supersedes"] != value["revision"], "ACTION_REVISION_CYCLE")
        j.require(type(value["events"]) is list and len(value["events"]) <= 64, "ACTION_EVENT_LIMIT")
        ids = []
        for event in value["events"]:
            event_facts(event, instrument)
            ids.append(event["event_id"])
        j.require(len(set(ids)) == len(ids), "ACTION_EVENT_CONFLICT")
        return cls(**value)


@dataclass(frozen=True)
class DayEvidence:
    source_day: str
    return_from: str
    status: str
    evidence_sha256: list
    blockers: list


def coverage_for(day, previous, captures, at):
    """Positive on-day coverage of every calendar date crossed by this return.

    The collector's actual acquisition is authoritative locally. Provider times
    remain assertions; hashing them does not authenticate a provider's clock.
    Corrections/conflicts are retained and never silently selected away.
    """
    candidates = [r for r in captures if r["payload"]["as_of_day"] == day]
    blockers = []
    if not captures:
        blockers.append("ACTION_FEED_UNAVAILABLE")
    if not candidates:
        blockers.append("COVERAGE_NOT_ATTESTED")
    hashes, incomplete, proven = [], [], False
    for record in candidates:
        hashes.append(record["sha256"])
        payload, acquired = record["payload"], record["acquired_at"]
        if not (payload["covered_from"] <= previous <= day <= payload["covered_through"]
                and payload["complete_scope"] == COMPLETE):
            incomplete.append("COVERAGE_NOT_ATTESTED")
            complete = False
        else:
            complete = True
        if not (j.day(acquired) == day and acquired <= at):
            incomplete.append("PIT_NOT_PROVEN")
            complete = False
        generated = payload["publisher_generated_at"]
        if generated is not None and (generated > acquired or j.day(generated) > day):
            blockers.append("ACTION_FUTURE_PUBLICATION")
        if payload["supersedes"] is not None:
            blockers.append("ACTION_SOURCE_REVISED")
        if payload["events"]:
            for event in payload["events"]:
                if any(event[k] is None for k in ("event_id", "event_type", "ex_date", "record_date")):
                    blockers.append("EVENT_FACT_PARTIAL")
                if event["event_type"] == "CASH_DIVIDEND" and any(event[k] is None for k in
                        ("cash_amount", "cash_unit", "currency", "tax_basis")):
                    blockers.append("EVENT_FACT_PARTIAL")
            # No actual-event adjustment engine is authorized in this module.
            blockers.append("PRICE_SEMANTICS_UNSAFE")
        elif complete:
            proven = True
    # A new timestamp/response version is new evidence, not a contradictory
    # issuer fact. A prior incomplete empty response did not assert no events.
    facts = {j.sha(j.canonical(sorted(r["payload"]["events"], key=j.canonical))) for r in candidates
             if r["payload"]["complete_scope"] == COMPLETE or r["payload"]["events"]}
    if len(facts) > 1:
        blockers.append("ACTION_SOURCE_CONFLICT")
    if not proven:
        blockers.extend(incomplete)
    blockers = sorted(set(blockers))
    status = "NO_ACTION_WITH_VERIFIED_COVERAGE" if candidates and not blockers else "UNKNOWN"
    if "PRICE_SEMANTICS_UNSAFE" in blockers:
        status = "EVENT_FACT_PARTIAL" if "EVENT_FACT_PARTIAL" in blockers else "PRICE_SEMANTICS_UNSAFE"
    return asdict(DayEvidence(day, previous, status, hashes, blockers))
