use stratide_forward::{source_check, Config, Journal};

pub fn run(args: &[String]) -> Result<(), String> {
    match args.iter().map(String::as_str).collect::<Vec<_>>().as_slice() {
        ["forward-init", path, config] => {
            let config: Config = serde_json::from_slice(&std::fs::read(config).map_err(|e| e.to_string())?).map_err(|e| e.to_string())?;
            let journal = Journal::create(path, config)?;
            println!("{}", serde_json::to_string_pretty(&journal.status()?).map_err(|e| e.to_string())?);
        },
        ["forward-status", path] => {
            let journal = Journal::open(path)?;
            println!("{}", serde_json::to_string_pretty(&journal.status()?).map_err(|e| e.to_string())?);
        },
        ["forward-source-check", path] => {
            let journal = Journal::open(path)?;
            let probes = source_check(journal.config())?;
            println!("{}", serde_json::to_string_pretty(&probes).map_err(|e| e.to_string())?);
            if probes.iter().any(|p| p.status != "access_ok_not_license_verification") {
                return Err("BLOCKED：真实 HTTP 探测未全部成功；无原始数据持久保存".into());
            }
        },
        ["forward-collect-once", path] => collect(path, None)?,
        ["forward-collect-once", path, "--trade-day", day] => collect(path, Some(day))?,
        ["forward-eod-at", path, day, at] => {
            let journal = Journal::open(path)?;
            let at = at.parse::<i64>().map_err(|_| "as-of 必须是 UTC epoch 毫秒整数")?;
            let view = journal.eod_as_of(day, at)?;
            println!("{}", serde_json::to_string_pretty(&serde_json::json!({"as_of": at, "journal_head": journal.head(), "view": view, "clock_uncertainty": journal.clock_uncertainty(), "available_at_semantics": stratide_forward::AVAILABILITY_SEMANTICS, "purpose": "read_only_eod_audit_not_execution_evidence"})).map_err(|e| e.to_string())?);
        },
        ["forward-eod-step", path, reports] => {
            let mut journal = Journal::open(path)?;
            let result = journal.eod_step();
            // Publish even blocked/recovered diagnostics; report failure never hides them.
            std::fs::create_dir_all(reports).map_err(|e| e.to_string())?;
            let destination = std::path::Path::new(reports).join(journal.head());
            journal.report(&destination)?;
            let step = result?;
            println!("{}", serde_json::to_string_pretty(&serde_json::json!({"step": step, "head": journal.head(), "report_directory": destination})).map_err(|e| e.to_string())?);
            if !step.ready && step.status != "waiting_eod_publication_window" {
                return Err("EOD 未形成当日有效观察；已保留报告。重试需显式 forward-collect-once".into());
            }
        },
        ["forward-report", path, destination] => {
            let journal = Journal::open(path)?;
            journal.report(destination)?;
            println!("已导出 observe-only 报告；HEAD={}；没有策略提案或模拟成交", journal.head());
        },
        _ => return Err("用法：forward-init <新目录> <配置JSON> | forward-source-check <目录> | forward-collect-once <目录> [--trade-day YYYYMMDD] | forward-eod-step <目录> <报告根目录> | forward-eod-at <目录> <交易日> <UTC epoch毫秒> | forward-status <目录> | forward-report <目录> <新报告目录>".into()),
    }
    Ok(())
}
fn collect(path: &str, day: Option<&str>) -> Result<(), String> {
    let mut journal = Journal::open(path)?;
    let status = journal.collect_once(day)?;
    println!("observe-only: {status}; HEAD={}", journal.head());
    if !matches!(status.as_str(), "valid_eod" | "market_closed") {
        return Err(format!("采集没有形成有效前向日线：{status}；诊断已追加"));
    }
    Ok(())
}
