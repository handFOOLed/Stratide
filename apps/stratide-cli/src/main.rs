#![recursion_limit = "256"]
mod forward;
mod paper;
mod replay;
use std::{collections::BTreeMap, env, process::ExitCode};
use stratide_contracts::*;
use stratide_risk::{FreezeReason, RiskDecision, RiskKernel, RiskScope};

fn main() -> ExitCode {
    match run(env::args().skip(1).collect()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("错误：{error}");
            ExitCode::from(2)
        }
    }
}

fn run(args: Vec<String>) -> Result<(), String> {
    match args.first().map(String::as_str).unwrap_or("help") {
        "status" => {
            println!(
                "Stratide M0-PR03 — paper-only；使用 paper-replay / paper-report / paper-status"
            )
        }
        "risk-demo" => demo(&args[1..])?,
        command if command.starts_with("forward-") => forward::run(&args)?,
        "paper-replay" | "paper-report" => replay::run(&args)?,
        command if command.starts_with("paper-") => paper::run(command, &args[1..])?,
        "help" | "--help" | "-h" => println!(
            "stratide-cli status\nstratide-cli risk-demo\n\
  --initial-cash-fen <正整数分> --max-order-fen <分>\n\
  --account-cap-fen <分> --strategy-cap-fen <分>\n\
  --daily-loss-fen <正整数分> --drawdown-fen <正整数分>\n\n\
所有资金与风险参数均需显式传入；risk-demo 仅审查。
\
paper-create <目录> <上述全部六项参数>
\
paper-submit-synthetic <目录>
\
paper-match-synthetic <目录>
\
paper-status <目录>
\
paper-apply <目录> <唯一事件ID> <可信命令JSON文件>
paper-replay <输入JSON> <账本目录> <报表目录> --sha256 <输入文件SHA256> <上述全部六项参数>
paper-report <输入JSON> <账本目录> <报表目录> --sha256 <输入文件SHA256>
\
Paper 演示使用 synthetic_test 人工行情/费率，绝非真实市场数据。
forward-init <新目录> <观察配置JSON>
forward-source-check <目录>
forward-collect-once <目录> [--trade-day YYYYMMDD]
forward-eod-step <目录> <报告根目录>
forward-eod-at <目录> <交易日> <UTC epoch毫秒>
forward-status <目录>
forward-report <目录> <新报告目录>
Forward 仅 observe-only；不创建资金账本、不产生策略提案或成交。"
        ),
        other => return Err(format!("未知命令 {other}；使用 --help 查看用法")),
    }
    Ok(())
}

fn config(args: &[String]) -> Result<PaperAccountConfig, String> {
    let names = [
        "--initial-cash-fen",
        "--max-order-fen",
        "--account-cap-fen",
        "--strategy-cap-fen",
        "--daily-loss-fen",
        "--drawdown-fen",
    ];
    let (pairs, remainder) = args.as_chunks::<2>();
    if !remainder.is_empty() {
        return Err("每个参数必须有整数分值；参见 --help".into());
    }
    let mut values = BTreeMap::new();
    for pair in pairs {
        if !names.contains(&pair[0].as_str()) || values.contains_key(pair[0].as_str()) {
            return Err(format!("未知或重复参数 {}", pair[0]));
        }
        let value = pair[1]
            .parse::<i64>()
            .map_err(|_| format!("{} 必须是 i64 整数分", pair[0]))?;
        values.insert(
            pair[0].as_str(),
            Cny::from_fen(value).map_err(|e| e.to_string())?,
        );
    }
    let get = |name: &str| {
        values
            .get(name)
            .copied()
            .ok_or_else(|| format!("必须显式指定 {name}；不提供默认本金或风险参数"))
    };
    let initial = get("--initial-cash-fen")?;
    let limits = RiskLimits {
        max_order_commitment: get("--max-order-fen")?,
        max_exposure: get("--account-cap-fen")?,
        daily_loss: get("--daily-loss-fen")?,
        drawdown: get("--drawdown-fen")?,
    };
    let config = PaperAccountConfig {
        account_id: "synthetic-account".into(),
        authorized_principal: initial,
        initial_capital: initial,
        deployment: DeploymentIdentity {
            group_id: "synthetic-group".into(),
            strategy_id: "synthetic-strategy".into(),
            frozen_version: "synthetic-v1".into(),
            deployment_id: "synthetic-demo".into(),
        },
        account_limits: limits,
        strategy_limits: RiskLimits {
            max_exposure: get("--strategy-cap-fen")?,
            ..limits
        },
        max_snapshot_age_ms: 60_000,
        max_mark_age_ms: 60_000,
    };
    config.validate()?;
    Ok(config)
}

fn demo(args: &[String]) -> Result<(), String> {
    let config = config(args)?;
    let initial = config.initial_capital;
    let now = Timestamp(1_793_152_800_000); // fixed synthetic input, not wall-clock observation
    let day = TradingDay(20261028);
    let snapshot = config.initialize(now, day)?;
    let before = snapshot.clone();
    let mut kernel = RiskKernel::new(config.clone())?;
    let initial_equity = kernel
        .observe_account(&snapshot, now, day)
        .map_err(|error| error.to_string())?;
    let mut p = OrderProposal {
        proposal_id: ProposalId(1),
        account_id: config.account_id,
        deployment: config.deployment,
        instrument: Instrument {
            market: Market::Shanghai,
            code: "600000".into(),
        },
        side: Side::Buy,
        quantity: 100,
        limit_price: Cny::from_fen(1_000).map_err(|e| e.to_string())?,
        decision_at: now,
        data_available_at: now,
        earliest_execution_at: Timestamp(now.0 + 1),
        expires_at: Timestamp(now.0 + 60_000),
    };
    let mut c = ReviewContext {
        now,
        trading_day: day,
        rules: Some(TradingRules {
            instrument: p.instrument.clone(),
            trading_day: day,
            available_at: now,
            source: "synthetic_test/rules-v1 (非交易所规则验证)".into(),
            tradable: true,
            settlement: SettlementRule::TPlusOne,
            buy_lot: 100,
            sell_lot: 100,
            allow_odd_lot_liquidation: true,
            tick_size: Cny::from_fen(1).map_err(|e| e.to_string())?,
            min_price: Cny::from_fen(900).map_err(|e| e.to_string())?,
            max_price: Cny::from_fen(1_100).map_err(|e| e.to_string())?,
        }),
        cost: None,
    };
    c.cost = Some(CostEstimate {
        proposal: p.clone(),
        rules: c.rules.clone().unwrap(),
        valid_until: p.expires_at,
        proposal_id: p.proposal_id,
        maximum_fee: Cny::from_fen(500).map_err(|e| e.to_string())?,
        source: "synthetic_test/cost-bound-v1 (非真实费率)".into(),
    });
    println!("模式：synthetic_test；固定人工价格/规则/费用；无行情抓取、无成交、无磁盘账本");
    println!(
        "显式本金：{initial}；初始 NAV：{}；持仓：0 股",
        initial_equity
    );
    let first = kernel.review(&snapshot, &p, &c);
    let repeated = kernel.review(&snapshot, &p, &c);
    if first != repeated {
        return Err("相同输入的审查结果不一致".into());
    }
    show("买入申请", &first);
    println!("重复审查：结果一致");

    p.proposal_id = ProposalId(2);
    c.cost.as_mut().unwrap().proposal_id = p.proposal_id;
    p.quantity = (initial.fen() / 100_000 + 1) * 100;
    c.cost.as_mut().unwrap().proposal = p.clone();
    show("超现金买入", &kernel.review(&snapshot, &p, &c));
    p.proposal_id = ProposalId(3);
    c.cost.as_mut().unwrap().proposal_id = p.proposal_id;
    p.side = Side::Sell;
    p.quantity = 100;
    c.cost.as_mut().unwrap().proposal = p.clone();
    show("无持仓卖出", &kernel.review(&snapshot, &p, &c));
    kernel.freeze(RiskScope::Account, FreezeReason::Manual);
    p.proposal_id = ProposalId(4);
    c.cost.as_mut().unwrap().proposal_id = p.proposal_id;
    p.side = Side::Buy;
    c.cost.as_mut().unwrap().proposal = p.clone();
    show("冻结后买入", &kernel.review(&snapshot, &p, &c));
    if snapshot != before {
        return Err("审查意外改变了账户状态".into());
    }
    println!(
        "审查后现金：{}；持仓：0 股；未完成委托：0；审查未改变资金或仓位",
        snapshot.cash
    );
    Ok(())
}

fn show(label: &str, decision: &RiskDecision) {
    match decision {
        RiskDecision::Accepted(a) => println!(
            "{label} #{}：接受提案；不是成交；最大现金支出 {}",
            a.proposal().proposal_id.0,
            a.maximum_cash_debit()
        ),
        RiskDecision::Rejected {
            proposal_id,
            reason,
        } => println!("{label} #{}：拒绝：{reason}", proposal_id.0),
    }
}
