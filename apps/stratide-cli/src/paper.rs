use stratide_contracts::{Timestamp, TradingDay};
use stratide_ledger::{synthetic as fixture, Command, DataMode, Ledger};

pub fn run(command: &str, args: &[String]) -> Result<(), String> {
    let path = args.first().ok_or("必须指定独立 paper 账本目录")?;
    if command == "paper-create" {
        let config = super::config(&args[1..])?;
        let ledger = Ledger::create(path, fixture::genesis(config))?;
        return show(&ledger);
    }
    let expected = if command == "paper-apply" { 3 } else { 1 };
    if args.len() != expected {
        return Err("参数数量错误；参见 --help".into());
    }
    let mut ledger = Ledger::open(path)?;
    match command {
        "paper-status" => {}
        "paper-submit-synthetic" | "paper-match-synthetic" => {
            if ledger.state().provenance.mode != DataMode::SyntheticTest {
                return Err("人工演示不可写入历史回放账本".into());
            }
            let (id, action) = if command == "paper-submit-synthetic" {
                (
                    "synthetic-order-1",
                    fixture::submit(
                        fixture::proposal(&ledger.state().config, 1),
                        TradingDay(20261028),
                        Timestamp(fixture::T0),
                    ),
                )
            } else {
                (
                    "synthetic-session-20261029",
                    fixture::session(fixture::bar(TradingDay(20261029), 1)),
                )
            };
            ledger.execute(id, action)?;
        }
        "paper-apply" => {
            let input = std::fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
            let action: Command = serde_json::from_str(&input).map_err(|e| e.to_string())?;
            ledger.execute(&args[1], action)?;
        }
        _ => return Err(format!("未知 Paper 命令：{command}")),
    }
    show(&ledger)
}

fn show(ledger: &Ledger) -> Result<(), String> {
    println!(
        "{}",
        serde_json::to_string_pretty(ledger.state()).map_err(|e| e.to_string())?
    );
    Ok(())
}
