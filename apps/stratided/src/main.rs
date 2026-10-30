use std::{fs::OpenOptions, io::Write, path::PathBuf};
use stratide_research::{config::Settings, Agent};
use stratided::{bind_local, handle_with_agent, App, Assets, Config};

fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().is_some_and(|s| s == "--agent-init-fake") && args.len() == 2 {
        let dir = PathBuf::from(&args[1]);
        std::fs::create_dir_all(&dir).map_err(|_| "无法创建 Agent 目录")?;
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(dir.join("settings.json"))
            .map_err(|_| "配置已存在或无法写入；不会覆盖 Owner 设置")?;
        file.write_all(&serde_json::to_vec_pretty(&Settings::fake()).unwrap())
            .map_err(|_| "无法写入 fake 配置")?;
        file.sync_all().map_err(|_| "无法保存 fake 配置")?;
        let _agent =
            Agent::open(&dir, None, App::load(None, None).agent_summary()).map_err(|e| e.0)?;
        println!("已创建本地 fake / synthetic_test 配置与 owner-token；没有云端调用。使用 --agent-dir 指定此目录启动。");
        return Ok(());
    }
    if args.first().is_some_and(|s| s == "--agent-settle") && args.len() == 5 {
        let dir = PathBuf::from(&args[1]);
        let id = args[2].parse::<i64>().map_err(|_| "调用 ID 无效")?;
        let actual = args[3]
            .parse::<i64>()
            .map_err(|_| "账单金额必须为 micro 整数")?;
        let agent =
            Agent::open(&dir, None, App::load(None, None).agent_summary()).map_err(|e| e.0)?;
        agent
            .store()
            .settle(id, actual, &args[4], chrono::Utc::now())
            .map_err(|e| e.0)?;
        println!("已记录 Owner 外部账单核对；任务未知执行结果不会因此自动重试。");
        return Ok(());
    }
    if args == ["--help"] || args == ["-h"] {
        println!("Stratide 本地 Paper Dashboard + 研究 Agent\nstratided [--report-dir <六报告目录>] [--evaluation-file <独立 evaluation.json>] [--port 8710] [--assets-dir <构建目录>] [--agent-dir <独立 Agent 目录>] [--agent-config <本机可信 JSON>] [--agent-eod-store <名称，仅本地fake、显式课题>]\nstratided --agent-init-fake <新目录>\nstratided --agent-settle <目录> <call-id> <actual-micro> <invoice-reference>\n账户快照固定；Agent 没有交易权限。未配置预算/授权时禁止付费调用。");
        return Ok(());
    }
    let config = Config::parse(args.into_iter())?;
    let assets = Assets::load(&config.assets_dir)?;
    let app = App::load(
        config.report_dir.as_deref(),
        config.evaluation_file.as_deref(),
    );
    let server = bind_local(config.port)?;
    let report_source = config.report_dir.clone();
    let evaluation_source = config.evaluation_file.clone();
    if config.agent_config.is_some() && config.agent_dir.is_none() {
        return Err("--agent-config 需要 --agent-dir".into());
    }
    let agent_result = config
        .agent_dir
        .as_deref()
        .map(|dir| {
            if let Some(name) = &config.agent_eod_store {
                let source = stratide_research::eod_snapshot::SnapshotSource::named(name)?;
                let initial = source.read(chrono::Utc::now().timestamp_millis())?;
                return Agent::open(dir, config.agent_config.as_deref(), initial).map(|a| {
                    a.with_summary_source(move || {
                        source.read(chrono::Utc::now().timestamp_millis())
                    })
                });
            }
            Agent::open(dir, config.agent_config.as_deref(), app.agent_summary()).map(|a| {
                a.with_summary_source(move || {
                    Ok(
                        App::load(report_source.as_deref(), evaluation_source.as_deref())
                            .agent_summary(),
                    )
                })
            })
        })
        .transpose();
    let agent = match agent_result {
        Ok(Some(agent)) => match agent.start() {
            Ok(()) => Some(agent),
            Err(e) => {
                eprintln!("研究服务不可用：{}；Paper 只读服务继续运行。", e.0);
                None
            }
        },
        Ok(None) => None,
        Err(e) => {
            eprintln!("研究服务不可用：{}；Paper 只读服务继续运行。", e.0);
            None
        }
    };
    println!(
        "Stratide Paper Dashboard: http://127.0.0.1:{}\nPaper 账户只读；研究控制需本机 Owner 令牌。Ctrl+C 停止。",
        config.port
    );
    for req in server.incoming_requests() {
        handle_with_agent(&app, &assets, req, config.port, agent.as_ref());
    }
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
