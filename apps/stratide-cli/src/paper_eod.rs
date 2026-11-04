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
    let command = &args[0];
    let at = now()?;
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
    if args.len() != 4 {
        return Err("paper-eod-intent/confirm <原账本> <唯一事件ID> <本机可信输入JSON>".into());
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
    let (raw, sha) = input(&args[3])?;
    let id = &args[2];
    if command == "paper-eod-intent" {
        let mut v: Intent = serde_json::from_slice(&raw).map_err(|e| e.to_string())?;
        let history = ledger.history()?;
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
        let at = history
            .iter()
            .find_map(|e| {
                if e.event_id == format!("{id}:observe") {
                    Some(e.state.snapshot.as_of)
                } else {
                    None
                }
            })
            .unwrap_or(at);
        let (day, hour) = stratide_ledger::paper_eod::shanghai_day(at)?;
        if hour < 16 || stratide_ledger::paper_eod::shanghai_day(now()?)?.0 != day {
            return Err("PAPER_INTENT_REQUIRES_CURRENT_EOD".into());
        }
        v.proposal.decision_at = at;
        ledger.execute(
            &format!("{id}:observe"),
            Command::Observe {
                now: at,
                day,
                marks: v.marks,
                external_flow_fen: 0,
            },
        )?;
        ledger.execute(
            &format!("{id}:submit"),
            Command::Submit {
                proposal: v.proposal,
                now: at,
                day,
                rules: Some(v.rules),
                fees: Some(v.fees),
            },
        )?;
        ledger.execute(
            &format!("{id}:freeze"),
            Command::FreezePaperIntentsV1 {
                now: at,
                target_day: v.target_day,
                decision_source_sha256: sha,
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
    println!("{}",serde_json::to_string(&serde_json::json!({"label":"EX_POST_OPEN_ASSUMPTION","ledger_head":l.head(),"state":l.state(),"opening_observed":"NOT_VERIFIED","live_allowed":false})).map_err(|e|e.to_string())?);
    Ok(())
}
