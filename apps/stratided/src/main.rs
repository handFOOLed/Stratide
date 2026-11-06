use std::{fs::OpenOptions, io::Write, path::PathBuf};
use stratide_research::{config::Settings, Agent};
use stratided::{bind_local, handle_with_agent, App, Assets, Config};

fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if (args.first().is_some_and(|s| s == "--agent-init-fake" || s == "--agent-init-local"))
        && args.len() == 2
    {
        let synthetic = args[0] == "--agent-init-fake";
        let dir = PathBuf::from(&args[1]);
        std::fs::create_dir_all(&dir).map_err(|_| "无法创建 Agent 目录")?;
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(dir.join("settings.json"))
            .map_err(|_| "配置已存在或无法写入；不会覆盖 Owner 设置")?;
        let settings = if synthetic {
            Settings::fake()
        } else {
            Settings::local_default()
        };
        file.write_all(&serde_json::to_vec_pretty(&settings).unwrap())
            .map_err(|_| "无法写入 Agent 配置")?;
        file.sync_all().map_err(|_| "无法保存 Agent 配置")?;
        let _agent =
            Agent::open(&dir, None, App::load(None, None).agent_summary()).map_err(|e| e.0)?;
        if synthetic {
            println!("已创建本地 fake / synthetic_test 配置与 owner-token；没有云端调用。使用 --agent-dir 指定此目录启动。");
        } else {
            println!("已创建本机 Agent（尚无 AI 服务与模型）并在该目录生成 owner-token；不会发起任何云调用。");
        }
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
        println!("Stratide 本地 Paper Dashboard + 研究 Agent\nstratided [--report-dir <六报告目录>] [--evaluation-file <独立 evaluation.json>] [--port 8710] [--assets-dir <构建目录>] [--agent-dir <独立 Agent 目录>] [--agent-config <本机可信 JSON>] [--agent-eod-store <名称，仅本地fake、显式课题>] [--runtime-home <安装运行目录>] [--agent-observer]\nstratided --agent-init-fake <新目录>\nstratided --agent-settle <目录> <call-id> <actual-micro> <invoice-reference>\n账户快照固定；Agent 没有交易权限。未配置预算/授权时禁止付费调用。");
        return Ok(());
    }
    let config = Config::parse(args.into_iter())?;
    // The supervised background watch is the only research worker. In this mode
    // the Dashboard must attach without taking agent.lock and must never start
    // an in-process worker thread of its own.
    let attach_only = config.desktop_config.is_some() || config.agent_observer;
    if let Some(home) = &config.runtime_home {
        if std::env::var_os("STRATIDE_STATE_ROOT").is_none() {
            let layout = stratide_runtime::Layout::from_home(home.clone())?;
            std::env::set_var("STRATIDE_STATE_ROOT", &layout.data);
        }
    }
    let assets = Assets::load(&config.assets_dir)?;
    let mut app = App::load(
        config.report_dir.as_deref(),
        config.evaluation_file.as_deref(),
    );
    app.desktop = config
        .desktop_config
        .as_deref()
        .map(stratided::desktop::Desktop::load)
        .transpose()
        .map_err(|e| e.0)?;
    app.paper_ledger = config.paper_ledger.clone();
    app.runtime_home = config.runtime_home.clone();
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
                let attached = if attach_only {
                    Agent::attach(dir, config.agent_config.as_deref(), initial)
                } else {
                    Agent::open(dir, config.agent_config.as_deref(), initial)
                };
                return attached.map(|a| {
                    a.with_summary_source(move || {
                        source.read(chrono::Utc::now().timestamp_millis())
                    })
                });
            }
            let a = if attach_only {
                Agent::attach(dir, config.agent_config.as_deref(), app.agent_summary())
            } else {
                Agent::open(dir, config.agent_config.as_deref(), app.agent_summary())
            };
            a.map(|a| {
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
        Ok(Some(agent)) => match if attach_only {
            Ok(())
        } else {
            agent.start()
        } {
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
    if let Some(a) = &agent {
        a.store().desktop_recover().map_err(|e| e.0)?;
    }
    println!(
        "Stratide Paper Dashboard: http://127.0.0.1:{}\nPaper 账户只读；研究控制需本机 Owner 令牌。Ctrl+C 停止。",
        config.port
    );
    let app = std::sync::Arc::new(app);
    let assets = std::sync::Arc::new(assets);
    let agent = agent.map(std::sync::Arc::new);
    for req in server.incoming_requests() {
        // Local loopback only; bounded by single-user desktop load. Each request owns
        // its thread so long runtime probes cannot block `/api/health`.
        let app = std::sync::Arc::clone(&app);
        let assets = std::sync::Arc::clone(&assets);
        let agent = agent.as_ref().map(std::sync::Arc::clone);
        let port = config.port;
        std::thread::spawn(move || {
            handle_with_agent(
                &app,
                &assets,
                req,
                port,
                agent.as_deref(),
            );
        });
    }
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
