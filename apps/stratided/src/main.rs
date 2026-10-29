use stratided::{bind_local, handle, App, Assets, Config};

fn run() -> Result<(), String> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args == ["--help"] || args == ["-h"] {
        println!("Stratide 本地只读 Paper Dashboard\nstratided [--report-dir <六报告目录>] [--evaluation-file <独立 evaluation.json>] [--port 8710] [--assets-dir <构建目录>]\n不指定报告时显示未配置状态。快照只在启动时读取，更新请显式重启。");
        return Ok(());
    }
    let config = Config::parse(args.into_iter())?;
    let assets = Assets::load(&config.assets_dir)?;
    let app = App::load(
        config.report_dir.as_deref(),
        config.evaluation_file.as_deref(),
    );
    let server = bind_local(config.port)?;
    println!(
        "Stratide Paper Dashboard: http://127.0.0.1:{}\n只读已发布快照；Ctrl+C 停止。",
        config.port
    );
    for req in server.incoming_requests() {
        handle(&app, &assets, req, config.port);
    }
    Ok(())
}

fn main() {
    if let Err(e) = run() {
        eprintln!("{e}");
        std::process::exit(1);
    }
}
