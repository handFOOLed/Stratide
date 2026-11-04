//! Trusted local Owner entry, no network or broker. Wall-clock intent receipt.
use serde::Deserialize;
use sha2::{Digest, Sha256};
use stratide_contracts::*;
use stratide_ledger::{Command, DailyBar, DataMode, FeeSchedule, Genesis, Ledger, Provenance};

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Intent {
    proposal: OrderProposal,
    rules: TradingRules,
    fees: FeeSchedule,
    marks: Vec<PositionMark>,
    target_day: TradingDay,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct OpenSource {
    bar: DailyBar,
    rules: TradingRules,
    source_received_at: Timestamp,
    corporate_actions_verified: bool,
}

fn now() -> Result<Timestamp, String> {
    Ok(Timestamp(
        i64::try_from(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_millis(),
        )
        .map_err(|e| e.to_string())?,
    ))
}
fn input(path: &str) -> Result<(Vec<u8>, String), String> {
    let raw = std::fs::read(path).map_err(|e| e.to_string())?;
    if raw.len() > 2 * 1024 * 1024 {
        return Err("PAPER_INPUT_SIZE".into());
    }
    let sha = format!("{:x}", Sha256::digest(&raw));
    Ok((raw, sha))
}
pub fn run(args: &[String]) -> Result<(), String> {
    run_at(args, now()?)
}
fn run_at(args: &[String], at: Timestamp) -> Result<(), String> {
    let command = &args[0];
    let (day, _) = stratide_ledger::paper_eod::shanghai_day(at)?;
    if command == "paper-eod-init" {
        if args.len() != 4 {
            return Err(
                "paper-eod-init <新账本目录> <Owner六项风险/资金与身份配置JSON> <来源版本ID>"
                    .into(),
            );
        }
        let (raw, sha) = input(&args[2])?;
        let config: PaperAccountConfig = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
        let ledger = Ledger::create(
            &args[1],
            Genesis {
                config,
                at,
                day,
                provenance: Provenance {
                    mode: DataMode::HistoricalReplay,
                    source_version: format!("paper-eod-assumption-v1:{}", args[3]),
                    dataset_hash: sha,
                    timezone: "Asia/Shanghai".into(),
                    price_semantics: "unadjusted_cny_fen".into(),
                },
            },
        )?;
        return show(&ledger);
    }
    if args.len() != if command == "paper-eod-expire" { 3 } else { 4 } {
        return Err("paper-eod-intent/confirm <原账本> <唯一事件ID> <本机可信输入JSON>；paper-eod-expire <原账本> <唯一事件ID>".into());
    }
    let mut ledger = Ledger::open(&args[1])?;
    if !ledger
        .state()
        .provenance
        .source_version
        .starts_with("paper-eod-assumption-v1")
    {
        return Err("CURRENT_PAPER_LEDGER_REQUIRED".into());
    }
    let id = &args[2];
    if command == "paper-eod-expire" {
        if let Some(entry) = ledger.history()?.iter().find(|e| e.event_id == *id) {
            if !matches!(entry.command, Some(Command::ExpirePaperIntentsV1 { .. })) {
                return Err("PAPER_EXPIRY_ID_CONFLICT".into());
            }
        } else {
            ledger.execute(id, Command::ExpirePaperIntentsV1 { now: at })?;
        }
        return show(&ledger);
    }
    let (raw, sha) = input(&args[3])?;
    if command == "paper-eod-intent" {
        let mut v: Intent = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
        let history = ledger.history()?;
        if let Some(entry) = history.iter().find(|e| e.event_id == *id) {
            if !matches!(&entry.command,Some(Command::SubmitPaperIntentV1{intent}) if intent.decision_source_sha256==sha)
            {
                return Err("PAPER_INTENT_ID_CONFLICT".into());
            }
            return show(&ledger);
        }
        // R1 completed legacy intents remain auditable/idempotent. Incomplete
        // legacy submissions are never replayed into another decision day.
        if let Some(entry) = history
            .iter()
            .find(|e| e.event_id == format!("{id}:freeze"))
        {
            if !matches!(&entry.command,Some(Command::FreezePaperIntentsV1{decision_source_sha256,..}) if decision_source_sha256==&sha)
            {
                return Err("PAPER_INTENT_ID_CONFLICT".into());
            }
            return show(&ledger);
        }
        if history
            .iter()
            .any(|e| e.event_id == format!("{id}:observe") || e.event_id == format!("{id}:submit"))
        {
            return Err("PAPER_LEGACY_PARTIAL_INTENT_USE_EXPIRE_THEN_FRESH_ID".into());
        }
        v.proposal.decision_at = at;
        ledger.execute(
            id,
            Command::SubmitPaperIntentV1 {
                intent: stratide_ledger::paper_eod::PaperIntent {
                    now: at,
                    target_day: v.target_day,
                    decision_source_sha256: sha,
                    proposal: v.proposal,
                    rules: v.rules,
                    fees: v.fees,
                    marks: v.marks,
                },
            },
        )?;
    } else {
        let v: OpenSource = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
        if let Some(entry) = ledger.history()?.iter().find(|e| e.event_id == *id) {
            if !matches!(&entry.command,Some(Command::ExPostOpenAssumptionV1{source_sha256,..}) if source_sha256==&sha)
            {
                return Err("PAPER_OPEN_ID_CONFLICT".into());
            }
            return show(&ledger);
        }
        if let Some(pending) = ledger
            .state()
            .paper_eod
            .as_ref()
            .and_then(|b| b.pending.as_ref())
        {
            if at >= stratide_ledger::paper_eod::confirmation_deadline(pending.target_day)? {
                return Err("PAPER_CONFIRMATION_WINDOW_CLOSED_USE_EXPIRE".into());
            }
        }
        ledger.execute(
            id,
            Command::ExPostOpenAssumptionV1 {
                now: at,
                bar: v.bar,
                rules: v.rules,
                source_sha256: sha,
                source_received_at: v.source_received_at,
                corporate_actions_verified: v.corporate_actions_verified,
            },
        )?;
    }
    show(&ledger)
}
fn show(l: &Ledger) -> Result<(), String> {
    let history = l.history()?;
    let label = match &history.last().expect("ledger genesis").command {
        Some(Command::ExpirePaperIntentsV1 { .. }) => "NO_FILL",
        Some(Command::SubmitPaperIntentV1 { .. }) => {
            if l.state().orders.last().expect("intent order").active() {
                "PAPER_INTENTS_FROZEN"
            } else {
                "PAPER_INTENT_REJECTED"
            }
        }
        _ => "EX_POST_OPEN_ASSUMPTION",
    };
    println!("{}",serde_json::to_string(&serde_json::json!({"label":label,"ledger_head":l.head(),"state":l.state(),"source_attestation":"OWNER_DECLARED_NOT_PROVIDER_VERIFIED","opening_observed":"NOT_VERIFIED","live_allowed":false})).map_err(|e|e.to_string())?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use stratide_ledger::synthetic as f;
    #[test]
    fn cli_intent_is_one_event_and_retries_after_restart_ignore_new_wall_clock() {
        let t = tempfile::tempdir().unwrap();
        let path = t.path().join("paper");
        let report: serde_json::Value = serde_json::from_slice(
            &std::fs::read(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/../../docs/evidence/m0-pr03/sample-report/report.json"
            ))
            .unwrap(),
        )
        .unwrap();
        let cfg: PaperAccountConfig = serde_json::from_value(report["config"].clone()).unwrap();
        let at = Timestamp(f::T0 + 3_600_000);
        let mut g = f::genesis(cfg);
        g.at = at;
        g.provenance.mode = DataMode::HistoricalReplay;
        g.provenance.source_version = "paper-eod-assumption-v1:synthetic_test".into();
        let l = Ledger::create(&path, g).unwrap();
        let head = l.head().to_string();
        let mut p = f::proposal(&l.state().config, 1);
        drop(l);
        p.limit_price = Cny::from_fen(1020).unwrap();
        p.data_available_at = at;
        p.earliest_execution_at = Timestamp(at.0 + 1);
        let mut v = serde_json::json!({"proposal":p,"rules":f::rules(TradingDay(20261028),at),"fees":f::fees(),"marks":[],"target_day":20261028});
        let file = t.path().join("intent.json");
        std::fs::write(&file, v.to_string()).unwrap();
        let args = vec![
            "paper-eod-intent".into(),
            path.to_str().unwrap().into(),
            "decision".into(),
            file.to_str().unwrap().into(),
        ];
        assert!(run_at(&args, at).is_err());
        assert_eq!(Ledger::read(&path).unwrap().head(), head);
        v["target_day"] = serde_json::json!(20261029);
        std::fs::write(&file, v.to_string()).unwrap();
        run_at(&args, at).unwrap();
        let l = Ledger::read(&path).unwrap();
        let accepted = l.head().to_string();
        assert_eq!(l.history().unwrap().len(), 2);
        assert_eq!(l.state().snapshot.pending_orders.len(), 1);
        drop(l);
        run_at(&args, Timestamp(at.0 + 2 * f::DAY)).unwrap();
        assert_eq!(Ledger::read(&path).unwrap().head(), accepted);
        v["proposal"]["quantity"] = serde_json::json!(200);
        std::fs::write(&file, v.to_string()).unwrap();
        assert!(run_at(&args, Timestamp(at.0 + 2 * f::DAY)).is_err());
        let expiry = vec![
            "paper-eod-expire".into(),
            path.to_str().unwrap().into(),
            "missing-session".into(),
        ];
        let cutoff =
            stratide_ledger::paper_eod::confirmation_deadline(TradingDay(20261029)).unwrap();
        run_at(&expiry, cutoff).unwrap();
        run_at(&expiry, Timestamp(cutoff.0 + f::DAY)).unwrap();
        let l = Ledger::read(&path).unwrap();
        assert!(l.state().fills.is_empty());
        assert!(l.state().snapshot.pending_orders.is_empty());
        assert_eq!(l.state().snapshot.cash.fen(), 1_000_000);
        assert_eq!(l.state().paper_eod.as_ref().unwrap().no_fills.len(), 1);
    }
}
