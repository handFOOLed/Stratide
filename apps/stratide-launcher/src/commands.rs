use serde_json::json;
use std::path::Path;
use std::process::Command;
use std::time::{Duration, Instant};
use stratide_runtime::{health, Layout};

const START_TIMEOUT: Duration = Duration::from_secs(75);
const STOP_TIMEOUT: Duration = Duration::from_secs(45);

pub fn launch(layout: &Layout, quiet: bool, no_browser: bool) -> Result<i32, String> {
    let config = layout.config()?;
    let token = layout.runtime_token()?;
    log(layout, &format!("launch requested on port {}", config.port));
    match health::probe(config.port) {
        Ok(data) => {
            log(
                layout,
                &format!("existing healthy instance {}", data.instance_id),
            );
            if !no_browser {
                open_dashboard(layout, config.port, &token, &data)?;
            }
            Ok(0)
        }
        Err(error) => {
            if !health::port_available(config.port) {
                log(
                    layout,
                    &format!("port {} unavailable: {}", config.port, error.code()),
                );
                fail(
                    quiet,
                    &format!(
                        "127.0.0.1:{} 已被其他程序占用；Stratide 不会误连或结束该进程。请释放端口后重试。",
                        config.port
                    ),
                );
                return Ok(2);
            }
            start_supervisor(layout)?;
            let deadline = Instant::now() + START_TIMEOUT;
            loop {
                match health::probe(config.port) {
                    Ok(data) => {
                        log(
                            layout,
                            &format!("dashboard ready instance {}", data.instance_id),
                        );
                        if !no_browser {
                            open_dashboard(layout, config.port, &token, &data)?;
                        }
                        return Ok(0);
                    }
                    Err(_) if Instant::now() < deadline => {
                        std::thread::sleep(Duration::from_millis(300));
                    }
                    Err(error) => {
                        let reason =
                            blocking_reason(layout).unwrap_or_else(|| error.code().to_string());
                        log(
                            layout,
                            &format!("dashboard did not become healthy: {reason}"),
                        );
                        fail(
                            quiet,
                            &format!(
                                "Stratide 未能在本机启动（{reason}）。\n日志：{}",
                                layout.supervisor_log().display()
                            ),
                        );
                        return Ok(3);
                    }
                }
            }
        }
    }
}

pub fn stop(layout: &Layout, quiet: bool) -> Result<i32, String> {
    let token = layout.runtime_token()?;
    let port = layout.config()?.port;
    let mut supervisor_running = supervisor_alive(layout);
    if supervisor_running {
        layout.write_stop_request("desktop stop")?;
        let deadline = Instant::now() + STOP_TIMEOUT;
        while Instant::now() < deadline {
            let state = stratide_runtime::state::SupervisorState::read(&layout.state_path());
            let stopped = state
                .as_ref()
                .is_some_and(|state| state.status == "STOPPED");
            if stopped && health::probe(port).is_err() {
                supervisor_running = false;
                break;
            }
            std::thread::sleep(Duration::from_millis(300));
        }
        if supervisor_running {
            fail(
                quiet,
                "后台服务未在限定时间内停止。未结束任何未验证的进程；请查看日志。",
            );
            return Ok(4);
        }
    }
    if health::probe(port).is_ok() {
        health::request_shutdown(port, &token).map_err(|error| error.code().to_string())?;
        let deadline = Instant::now() + Duration::from_secs(10);
        while Instant::now() < deadline {
            if health::probe(port).is_err() {
                return Ok(0);
            }
            std::thread::sleep(Duration::from_millis(250));
        }
        fail(quiet, "本地服务仍在运行；未结束未知进程。请查看日志。");
        return Ok(4);
    }
    Ok(0)
}

pub fn status(layout: &Layout, file: Option<&Path>) -> Result<i32, String> {
    let config = layout.config()?;
    let state = stratide_runtime::state::SupervisorState::read(&layout.state_path());
    let value = json!({
        "layout": {
            "home": layout.home.to_string_lossy(),
            "app": layout.app.to_string_lossy(),
            "data": layout.data.to_string_lossy(),
            "version": layout.version,
        },
        "config": config,
        "supervisor_alive": supervisor_alive(layout),
        "state": state,
        "health": match health::probe(config.port) {
            Ok(value) => json!({"healthy":true,"instance_id":value.instance_id,"pid":value.process_id}),
            Err(error) => json!({"healthy":false,"code":error.code()}),
        },
        "autostart": stratide_runtime::autostart::status(),
    });
    crate::write_json(&value, file);
    Ok(0)
}

pub fn autostart(layout: &Layout, action: &str, file: Option<&Path>) -> Result<i32, String> {
    let result = match action {
        "enable" => stratide_runtime::autostart::set_enabled(&current_exe()?, true),
        "disable" => stratide_runtime::autostart::set_enabled(&current_exe()?, false),
        "remove" => stratide_runtime::autostart::remove(),
        "status" => Ok(stratide_runtime::autostart::status()),
        other => return Err(format!("UNKNOWN_AUTOSTART_ACTION:{other}")),
    };
    match result {
        Ok(status) => {
            log(layout, &format!("autostart {action}: {:?}", status));
            crate::write_json(
                &serde_json::to_value(status).expect("autostart status"),
                file,
            );
            Ok(0)
        }
        Err(code) => {
            log(layout, &format!("autostart {action} failed: {code}"));
            crate::write_json(
                &serde_json::json!({"state": "FAILED", "action": action, "reason": code}),
                file,
            );
            Ok(1)
        }
    }
}

pub fn delete_user_data(layout: &Layout, quiet: bool, yes: bool) -> Result<i32, String> {
    if !yes {
        if quiet {
            return Err("EXPLICIT_CONFIRMATION_REQUIRED".into());
        }
        let answer = stratide_runtime::win::confirm(
            "这会删除本机 Stratide 的行情、Paper 账本、研究记录与配置。\n应用目录和 WSL2 环境不会被删除。\n\n仍要删除用户数据吗？",
            "删除 Stratide 本地数据",
        );
        if !answer {
            return Ok(0);
        }
    }
    if layout.home.starts_with(&layout.app) || layout.app.starts_with(&layout.data) {
        return Err("UNSAFE_DATA_DIRECTORY_LAYOUT".into());
    }
    let stopped = stop(layout, true)?;
    if stopped != 0 {
        return Ok(stopped);
    }
    for path in [&layout.data, &layout.logs, &layout.runtime] {
        if path.exists() {
            std::fs::remove_dir_all(path)
                .map_err(|error| format!("DELETE_FAILED {}: {error}", path.display()))?;
        }
    }
    Ok(0)
}

pub fn open_folder(path: &Path) -> Result<i32, String> {
    let mut command = Command::new("explorer.exe");
    command.arg(path).stdin(std::process::Stdio::null());
    stratide_runtime::win::hide_console(&mut command);
    command
        .spawn()
        .map_err(|error| format!("FOLDER_OPEN_FAILED: {error}"))?;
    Ok(0)
}

pub fn configure(port: &Option<u16>, data: Option<&Path>) -> Result<i32, String> {
    let home = stratide_runtime::default_home()?;
    let config_path = home.join("runtime.json");
    if config_path.is_file() {
        return Ok(0);
    }
    let port = port.unwrap_or(8710);
    if port == 0 {
        return Err("PORT_INVALID".into());
    }
    let data_root = match data {
        Some(path) => path.to_path_buf(),
        None => home.join("data"),
    };
    let config = stratide_runtime::RuntimeConfig {
        schema_version: 1,
        port,
        data_root: data_root.clone(),
        python: None,
    };
    std::fs::create_dir_all(&home).map_err(|error| format!("RUNTIME_HOME_UNAVAILABLE: {error}"))?;
    for path in [&data_root, &home.join("logs"), &home.join("runtime")] {
        std::fs::create_dir_all(path)
            .map_err(|error| format!("DIRECTORY_CREATE_FAILED {}: {error}", path.display()))?;
    }
    config.save(&config_path)?;
    Ok(0)
}

fn open_dashboard(
    layout: &Layout,
    port: u16,
    token: &str,
    health: &health::HealthData,
) -> Result<(), String> {
    let complete = layout.runtime.join("setup-complete").is_file();
    let route = if complete {
        "overview"
    } else {
        "settings/runtime"
    };
    let url = format!("http://127.0.0.1:{port}/#/{route}?rt={token}");
    let mut command = Command::new("cmd.exe");
    command
        .args(["/d", "/c", "start", "", &url])
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());
    stratide_runtime::win::hide_console(&mut command);
    command
        .spawn()
        .map_err(|error| format!("BROWSER_OPEN_FAILED: {error}"))?;
    let _ = health;
    Ok(())
}

fn start_supervisor(layout: &Layout) -> Result<(), String> {
    let exe = current_exe()?;
    let log = layout.logs.join("launcher.log");
    let stdout = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log)
        .map_err(|error| format!("LAUNCHER_LOG_UNAVAILABLE: {error}"))?;
    let stderr = stdout
        .try_clone()
        .map_err(|error| format!("LAUNCHER_LOG_UNAVAILABLE: {error}"))?;
    let mut command = Command::new(&exe);
    command
        .arg("--background")
        .current_dir(&layout.app)
        .stdin(std::process::Stdio::null())
        .stdout(stdout)
        .stderr(stderr);
    stratide_runtime::win::hide_console(&mut command);
    command
        .spawn()
        .map_err(|error| format!("SUPERVISOR_SPAWN_FAILED: {error}"))?;
    Ok(())
}

fn supervisor_alive(layout: &Layout) -> bool {
    let state = match stratide_runtime::state::SupervisorState::read(&layout.state_path()) {
        Some(state) => state,
        None => return false,
    };
    if state.status == "STOPPED" || state.status == "FAILED" {
        return false;
    }
    let updated = chrono::DateTime::parse_from_rfc3339(&state.updated_at)
        .map(|time| time.with_timezone(&chrono::Utc))
        .ok();
    updated.is_some_and(|time| {
        chrono::Utc::now().signed_duration_since(time) < chrono::Duration::seconds(20)
    })
}

fn blocking_reason(layout: &Layout) -> Option<String> {
    let state = stratide_runtime::state::SupervisorState::read(&layout.state_path())?;
    if state.reason.is_empty() || state.reason == "OK" {
        None
    } else {
        Some(state.reason)
    }
}

fn current_exe() -> Result<std::path::PathBuf, String> {
    std::env::current_exe().map_err(|error| format!("CURRENT_EXE_UNAVAILABLE: {error}"))
}

fn log(layout: &Layout, message: &str) {
    stratide_runtime::log::append(&layout.logs.join("launcher.log"), message);
}

fn fail(quiet: bool, message: &str) {
    eprintln!("{message}");
    if !quiet {
        stratide_runtime::win::message(message, "Stratide", true);
    }
}
