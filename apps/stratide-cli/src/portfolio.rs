//! Local trusted runner boundary. Never accepts a caller-supplied wall clock.
use std::io::{self, Read};
use stratide_contracts::Timestamp;
use stratide_ledger::{portfolio::*, Command, Ledger};

pub fn run(args: &[String]) -> Result<(), String> {
    let now = Timestamp(
        i64::try_from(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_millis(),
        )
        .map_err(|e| e.to_string())?,
    );
    run_at(args, now)
}

fn run_at(args: &[String], now: Timestamp) -> Result<(), String> {
    if args.len() != 3 {
        return Err("paper-portfolio <原Paper账本> status|configure|pause|resume|freeze|confirm|recover；JSON经stdin".into());
    }
    let action = args[2].as_str();
    let mut ledger = if action == "status" {
        Ledger::read(&args[1])?
    } else {
        Ledger::open(&args[1])?
    };
    if action != "status" {
        let mut raw = String::new();
        io::stdin()
            .take(4 * 1024 * 1024 + 1)
            .read_to_string(&mut raw)
            .map_err(|e| e.to_string())?;
        if raw.len() > 4 * 1024 * 1024 {
            return Err("PORTFOLIO_INPUT_SIZE".into());
        }
        let (id, mut cmd) = match action {
            "configure" => (
                "portfolio:policy".into(),
                Command::ConfigurePortfolioV1 {
                    now,
                    policy: serde_json::from_str(&raw).map_err(|e| e.to_string())?,
                },
            ),
            "pause" | "resume" => (
                format!("portfolio:{action}:{}", ledger.head()),
                Command::PausePortfolioV1 {
                    now,
                    automatic: action == "resume",
                },
            ),
            "freeze" => {
                let mut decision: Decision =
                    serde_json::from_str(&raw).map_err(|e| e.to_string())?;
                decision.now = now;
                (
                    format!("portfolio:decision:{}", decision.day.0),
                    Command::FreezePortfolioV1 { decision },
                )
            }
            "recover" => {
                let mut valuation: Confirmation =
                    serde_json::from_str(&raw).map_err(|e| e.to_string())?;
                valuation.now = now;
                (
                    format!("portfolio:valuation-recovery:{}", valuation.day.0),
                    Command::RecoverPortfolioValuationV1 { valuation },
                )
            }
            "confirm" => {
                let mut confirmation: Confirmation =
                    serde_json::from_str(&raw).map_err(|e| e.to_string())?;
                confirmation.now = now;
                (
                    format!("portfolio:confirm:{}", confirmation.day.0),
                    Command::ConfirmPortfolioV1 { confirmation },
                )
            }
            _ => return Err("PORTFOLIO_ACTION_INVALID".into()),
        };
        if let Command::ConfigurePortfolioV1 { policy, .. } = &cmd {
            if policy.capacity_scope != Some(CapacityScope::Batch)
                && ledger.state().portfolio.is_none()
            {
                return Err("OWNER_BATCH_CAPACITY_SCOPE_REQUIRED".into());
            }
        }
        // Identical retries bind to the original wall clock, never a new day.
        if let Some(old) = ledger
            .history()?
            .into_iter()
            .find(|e| e.event_id == id)
            .and_then(|e| e.command)
        {
            match (&mut cmd, old) {
                (
                    Command::ConfigurePortfolioV1 { now, .. },
                    Command::ConfigurePortfolioV1 { now: at, .. },
                ) => *now = at,
                (
                    Command::FreezePortfolioV1 { decision },
                    Command::FreezePortfolioV1 { decision: prior },
                ) => decision.now = prior.now,
                (
                    Command::ConfirmPortfolioV1 { confirmation },
                    Command::ConfirmPortfolioV1 {
                        confirmation: prior,
                    },
                ) => confirmation.now = prior.now,
                (
                    Command::RecoverPortfolioValuationV1 { valuation },
                    Command::RecoverPortfolioValuationV1 { valuation: prior },
                ) => valuation.now = prior.now,
                _ => return Err("PORTFOLIO_EVENT_ID_CONFLICT".into()),
            }
        }
        ledger.execute(&id, cmd)?;
    }
    println!("{}",serde_json::to_string(&serde_json::json!({"ledger_head":ledger.head(),"state":ledger.state(),
        "opening_observed":"NOT_VERIFIED","historical_pit":"NOT_VERIFIED","real_tradability":"NOT_VERIFIED","live_allowed":false})).map_err(|e|e.to_string())?);
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn runner_child() {
        let Ok(args) = std::env::var("STRATIDE_PORTFOLIO_TEST_ARGS") else {
            return;
        };
        let args: Vec<String> = serde_json::from_str(&args).unwrap();
        let now = Timestamp(
            std::env::var("STRATIDE_PORTFOLIO_TEST_AT")
                .unwrap()
                .parse()
                .unwrap(),
        );
        if args[2] == "init" {
            let genesis: stratide_ledger::Genesis = serde_json::from_reader(io::stdin()).unwrap();
            Ledger::create(&args[1], genesis).unwrap();
        } else {
            run_at(&args, now).unwrap();
        }
    }
}
