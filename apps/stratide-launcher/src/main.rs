#![windows_subsystem = "windows"]
//! Stratide desktop launcher and per-user supervisor.
//!
//! The launcher never places orders, calls a model or writes the ledger. It
//! starts the existing service and the existing EOD watch, keeps one instance,
//! and opens the local Dashboard in the default browser.
mod commands;
mod supervisor;

use std::io::Write;
use stratide_runtime::Layout;

#[derive(Default)]
struct Options {
    mode: String,
    action: String,
    quiet: bool,
    no_browser: bool,
    status_file: Option<std::path::PathBuf>,
    home: Option<std::path::PathBuf>,
    data_dir: Option<std::path::PathBuf>,
    port: Option<u16>,
    yes: bool,
}

fn parse_options() -> Result<Options, String> {
    let mut options = Options {
        mode: "launch".into(),
        ..Default::default()
    };
    let mut args = std::env::args().skip(1);
    while let Some(arg) = args.next() {
        match arg.as_str() {
            "--background" => options.mode = "background".into(),
            "--stop" => options.mode = "stop".into(),
            "--status" => options.mode = "status".into(),
            "--autostart" => {
                options.mode = "autostart".into();
                options.action = args
                    .next()
                    .ok_or("--autostart requires enable|disable|status")?;
            }
            "--delete-user-data" => options.mode = "delete-user-data".into(),
            "--open-runtime" => options.mode = "launch".into(),
            "--quiet" | "--no-gui" => options.quiet = true,
            "--no-browser" => options.no_browser = true,
            "--yes" => options.yes = true,
            "--status-file" => {
                options.status_file =
                    Some(args.next().ok_or("--status-file requires a path")?.into())
            }
            "--home" => {
                options.home = Some(args.next().ok_or("--home requires a path")?.into());
            }
            "--data-dir" => {
                options.data_dir = Some(args.next().ok_or("--data-dir requires a path")?.into());
            }
            "--port" => {
                options.port = Some(
                    args.next()
                        .ok_or("--port requires a value")?
                        .parse::<u16>()
                        .map_err(|_| "PORT_INVALID")?,
                );
            }
            "--configure" => options.mode = "configure".into(),
            "--open-data" => options.mode = "open-data".into(),
            "--open-logs" => options.mode = "open-logs".into(),
            "--version" => {
                let app = std::env::current_exe()
                    .ok()
                    .and_then(|exe| exe.parent().map(|parent| parent.to_path_buf()))
                    .unwrap_or_default();
                println!("Stratide {}", stratide_runtime::product_version(&app));
                std::process::exit(0);
            }
            "--help" | "-h" => {
                println!("stratide-launcher [--background|--stop|--status|--autostart <enable|disable|remove|status>|--configure] [--home <dir>] [--no-browser] [--quiet]");
                std::process::exit(0);
            }
            other => return Err(format!("UNKNOWN_ARGUMENT:{other}")),
        }
    }
    Ok(options)
}

fn main() {
    let code = match run() {
        Ok(code) => code,
        Err(error) => {
            let message = format!("Stratide 启动失败：{error}");
            eprintln!("{message}");
            if !std::env::args().any(|arg| arg == "--quiet" || arg == "--no-gui") {
                stratide_runtime::win::message(&message, "Stratide", true);
            }
            1
        }
    };
    std::process::exit(code);
}

fn run() -> Result<i32, String> {
    let options = parse_options()?;
    if let Some(home) = &options.home {
        std::env::set_var("STRATIDE_HOME", home);
    }
    if options.mode == "configure" {
        return commands::configure(&options.port, options.data_dir.as_deref());
    }
    if options.mode == "background" {
        return supervisor::run();
    }
    let layout = Layout::load()?;
    layout.ensure_directories()?;
    match options.mode.as_str() {
        "stop" => commands::stop(&layout, options.quiet),
        "status" => commands::status(&layout, options.status_file.as_deref()),
        "autostart" => {
            commands::autostart(&layout, &options.action, options.status_file.as_deref())
        }
        "open-data" => commands::open_folder(&layout.data),
        "open-logs" => commands::open_folder(&layout.logs),
        "delete-user-data" => commands::delete_user_data(&layout, options.quiet, options.yes),
        "launch" => commands::launch(&layout, options.quiet, options.no_browser),
        other => Err(format!("UNKNOWN_MODE:{other}")),
    }
}

pub(crate) fn write_json(value: &serde_json::Value, path: Option<&std::path::Path>) {
    let body = serde_json::to_vec_pretty(value).expect("JSON value");
    match path {
        Some(path) => {
            let _ = std::fs::write(path, &body);
        }
        None => {
            let mut stdout = std::io::stdout();
            let _ = stdout.write_all(&body);
            let _ = stdout.write_all(b"\n");
            let _ = stdout.flush();
        }
    }
}
