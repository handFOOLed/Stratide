//! Local installation/runtime control for the packaged Windows product.
//!
//! Read-only diagnostics use same-origin checks. Writes additionally require
//! the per-install runtime token created by the supervisor (never logged and
//! never sent to any remote service). Financial, budget and egress authority
//! stay with the existing Owner flows and are not modified here.
use crate::{App, Reply};
use crate::runtime_status_cache::{self, SERVE_MAX_AGE};
use serde_json::{json, Value};
use std::process::Command;
use std::sync::RwLock;
use std::time::Duration;
use stratide_runtime::Layout;
use tiny_http::Request;

/// Serialize dependency-changing runtime POST handlers (config, probe, market, …).
static RUNTIME_WRITE: RwLock<()> = RwLock::new(());

fn collect_status_light(app: &App, layout: &Layout) -> Result<Value, &'static str> {
    let service = json!({"healthy": true, "instance_id": app.instance_id(),
        "pid": std::process::id().to_string()});
    stratide_runtime::diagnostics::collect_light(layout, service)
}

fn diagnostics_slow_collect_enabled() -> bool {
    std::env::var("STRATIDE_DIAGNOSTICS_SLEEP_MS")
        .ok()
        .and_then(|raw| raw.parse::<u64>().ok())
        .is_some_and(|ms| ms > 0)
}

fn schedule_status_refresh(app: &App, layout: &Layout) {
    let stale = runtime_status_cache::should_refresh_background() || diagnostics_slow_collect_enabled();
    if !stale || !runtime_status_cache::try_begin_background_refresh(stale) {
        return;
    }
    let layout = layout.clone();
    let instance_id = app.instance_id().to_string();
    let pid = std::process::id();
    let captured_epoch = runtime_status_cache::epoch();
    let generation_at_start = runtime_status_cache::generation();
    std::thread::spawn(move || {
        let service = json!({"healthy": true, "instance_id": instance_id, "pid": pid.to_string()});
        if let Ok(value) = stratide_runtime::diagnostics::collect(&layout, service) {
            runtime_status_cache::publish_if_not_superseded(value, captured_epoch, generation_at_start);
        }
        runtime_status_cache::end_background_refresh();
    });
}

fn publish_light_snapshot(app: &App, layout: &Layout) -> Result<(), Reply> {
    let value = collect_status_light(app, layout).map_err(|code| layout_error(503, code))?;
    runtime_status_cache::publish(value);
    Ok(())
}

pub fn reply(app: &App, req: &mut Request, port: u16) -> Reply {
    let error = |status: u16, code: &str| app.error(status, code, code);
    let single = |name: &'static str| {
        let mut values = req
            .headers()
            .iter()
            .filter(|header| header.field.equiv(name));
        let first = values
            .next()
            .map(|header| header.value.as_str().to_string());
        if values.next().is_some() {
            None
        } else {
            first
        }
    };
    let host = single("Host").unwrap_or_default();
    let origin = single("Origin");
    if ![format!("127.0.0.1:{port}"), format!("localhost:{port}")].contains(&host)
        || origin
            .as_ref()
            .is_some_and(|value| value != &format!("http://{host}"))
    {
        return error(403, "LOCAL_ORIGIN_REQUIRED");
    }
    if single("Sec-Fetch-Site").is_some_and(|value| value != "same-origin" && value != "none") {
        return error(403, "SAME_ORIGIN_REQUIRED");
    }
    let method = req.method().as_str().to_string();
    if method != "GET" && method != "POST" {
        return error(405, "RUNTIME_METHOD_NOT_ALLOWED");
    }
    let home = match &app.runtime_home {
        Some(home) => home.clone(),
        None => return error(503, "RUNTIME_NOT_MANAGED"),
    };
    let layout = match Layout::from_home(home) {
        Ok(layout) => layout,
        Err(_) => return error(503, "RUNTIME_LAYOUT_INVALID"),
    };
    let path = req.url().to_string();
    if method == "GET" {
        if path == "/api/runtime/status" {
            return match status(app, &layout) {
                Ok(value) => app.envelope(200, value, Value::Null),
                Err(code) => error(503, code),
            };
        }
        return error(404, "RUNTIME_ROUTE_NOT_FOUND");
    }
    if origin.as_deref() != Some(&format!("http://{host}")) {
        return error(403, "EXPLICIT_ORIGIN_REQUIRED");
    }
    if single("Content-Type").as_deref() != Some("application/json") {
        return error(415, "JSON_REQUIRED");
    }
    let length = single("Content-Length").and_then(|value| value.parse::<usize>().ok());
    let length = match length.filter(|length| *length > 0 && *length <= 8192) {
        Some(length) => length,
        None => return error(413, "BODY_LIMIT"),
    };
    let mut bytes = Vec::new();
    use std::io::Read;
    if req.as_reader().take(8193).read_to_end(&mut bytes).is_err() || bytes.len() != length {
        return error(400, "BODY_INVALID");
    }
    let body: Value = match serde_json::from_slice(&bytes) {
        Ok(value) => value,
        Err(_) => return error(400, "JSON_INVALID"),
    };
    let _mutation = match RUNTIME_WRITE.write() {
        Ok(guard) => guard,
        Err(_) => return error(503, "RUNTIME_WRITE_BUSY"),
    };
    runtime_status_cache::bump_epoch();
    let affects_status = matches!(
        path.as_str(),
        "/api/runtime/wsl"
            | "/api/runtime/wsl-detect"
            | "/api/runtime/wsl-probe"
            | "/api/runtime/tushare-token"
            | "/api/runtime/market"
            | "/api/runtime/setup-complete"
            | "/api/runtime/autostart"
    );
    let result = (|| -> Result<Reply, Reply> {
        match path.as_str() {
            "/api/runtime/autostart" => autostart(app, &layout, &body),
            "/api/runtime/tushare-token" => tushare_token(&layout, &body),
            "/api/runtime/market" => market(&layout, &body),
            "/api/runtime/wsl" => configure_wsl(&layout, &body),
            "/api/runtime/wsl-detect" => detect_wsl(&layout),
            "/api/runtime/wsl-probe" => probe_wsl(app, &layout),
            "/api/runtime/open-folder" => open_folder(&layout, &body),
            "/api/runtime/setup-complete" => setup_complete(&layout, &body),
            "/api/runtime/update-check" => update_check(&layout),
            "/api/runtime/shutdown" => {
                let mut reply = app.envelope(200, json!({"state": "STOPPING"}), Value::Null);
                reply.exit_after = true;
                Ok(reply)
            }
            _ => Err(error(404, "RUNTIME_ROUTE_NOT_FOUND")),
        }
    })();
    if result.is_ok() && affects_status {
        schedule_status_refresh(app, &layout);
    } else if result.is_err() {
        runtime_status_cache::invalidate_cache();
    }
    match result {
        Ok(reply) => reply,
        Err(reply) => reply,
    }
}

fn status(app: &App, layout: &Layout) -> Result<Value, &'static str> {
    let _read = RUNTIME_WRITE
        .read()
        .map_err(|_| "RUNTIME_STATUS_BUSY")?;
    if let Some(value) = runtime_status_cache::cached_value(SERVE_MAX_AGE) {
        drop(_read);
        schedule_status_refresh(app, layout);
        return Ok(value);
    }
    let light = collect_status_light(app, layout)?;
    runtime_status_cache::publish(light.clone());
    drop(_read);
    schedule_status_refresh(app, layout);
    Ok(light)
}

fn autostart(app: &App, layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let enabled = body
        .get("enabled")
        .and_then(Value::as_bool)
        .ok_or_else(|| app.error(400, "AUTOSTART_INPUT_INVALID", "enabled must be boolean"))?;
    let launcher = layout.app.join("stratide-launcher.exe");
    if !launcher.is_file() {
        return Err(app.error(409, "LAUNCHER_MISSING", "launcher binary is missing"));
    }
    match stratide_runtime::autostart::set_enabled(&launcher, enabled) {
        Ok(status) => Ok(app.envelope(
            200,
            serde_json::to_value(status).expect("autostart"),
            Value::Null,
        )),
        Err(code) => Err(app.error(409, "AUTOSTART_OPERATION_FAILED", &code)),
    }
}

fn tushare_token(layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let token = body
        .get("token")
        .and_then(Value::as_str)
        .ok_or_else(|| layout_error(400, "TOKEN_INPUT_INVALID"))?;
    if token.is_empty() || token.len() > 1024 {
        return Err(layout_error(400, "TOKEN_INPUT_INVALID"));
    }
    let helper = layout.app.join("scripts").join("stratide-credential.py");
    if !helper.is_file() {
        return Err(layout_error(409, "CREDENTIAL_HELPER_MISSING"));
    }
    let mut command = Command::new(layout.python());
    command
        .arg("-B")
        .arg("-X")
        .arg("utf8")
        .arg(&helper)
        .arg("write")
        .env("STRATIDE_STATE_ROOT", &layout.data);
    let outcome =
        stratide_runtime::run_capture_input(command, token.as_bytes(), Duration::from_secs(15));
    match outcome {
        Ok((Some(0), stdout, _)) => {
            let value: Value =
                serde_json::from_slice(&stdout).unwrap_or_else(|_| json!({"state": "UNKNOWN"}));
            Ok(layout_envelope(200, value))
        }
        Ok((code, _, _)) => Err(layout_error(
            409,
            &format!("CREDENTIAL_WRITE_FAILED_{}", code.unwrap_or(-1)),
        )),
        Err(code) => Err(layout_error(409, &code)),
    }
}

fn market(layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let action = body
        .get("action")
        .and_then(Value::as_str)
        .ok_or_else(|| layout_error(400, "MARKET_INPUT_INVALID"))?;
    if !["init", "enable", "disable", "status", "backfill", "backfill-state"].contains(&action) {
        return Err(layout_error(400, "MARKET_INPUT_INVALID"));
    }
    if action == "backfill-state" {
        let request = layout.data.join("backfill.request");
        let running = request.is_file();
        let progress: Value = std::fs::read(layout.data.join("backfill.progress.json"))
            .ok()
            .and_then(|raw| serde_json::from_slice(&raw).ok())
            .unwrap_or(Value::Null);
        return Ok(layout_envelope(
            200,
            json!({"running": running, "progress": progress}),
        ));
    }
    let script = layout.app.join("scripts").join("eod-operator.py");
    if !script.is_file() {
        return Err(layout_error(409, "EOD_OPERATOR_MISSING"));
    }
    if !layout.python().is_file() {
        return Err(layout_error(409, "PYTHON_RUNTIME_MISSING"));
    }
    let mut command = Command::new(layout.python());
    command
        .arg("-B")
        .arg("-X")
        .arg("utf8")
        .arg(&script)
        .args(["market", action])
        .current_dir(&layout.app)
        .env("STRATIDE_STATE_ROOT", &layout.data)
        .env("STRATIDE_BIN_DIR", layout.app.join("bin"))
        .env_remove("STRATIDE_TUSHARE_TOKEN");
    if action == "init" {
        let start_date = body
            .get("start_date")
            .and_then(Value::as_str)
            .ok_or_else(|| layout_error(400, "START_DATE_REQUIRED"))?;
        if start_date.len() != 8 || !start_date.bytes().all(|byte| byte.is_ascii_digit()) {
            return Err(layout_error(400, "START_DATE_INVALID"));
        }
        command.arg("--start-date").arg(start_date);
    }
    if action == "backfill" {
        return backfill(layout, command);
    }
    let timeout = if action == "status" { 60 } else { 180 };
    match stratide_runtime::run_capture(command, Duration::from_secs(timeout)) {
        Ok((Some(0), stdout, _)) => {
            let value: Value = serde_json::from_slice(&stdout)
                .unwrap_or_else(|_| json!({"raw": String::from_utf8_lossy(&stdout).chars().take(4000).collect::<String>()}));
            Ok(layout_envelope(200, value))
        }
        Ok((code, stdout, stderr)) => {
            let _ = stderr;
            let value: Value = serde_json::from_slice(&stdout).unwrap_or_else(|_| json!({}));
            let reason = value
                .get("reason")
                .and_then(Value::as_str)
                .unwrap_or("MARKET_COMMAND_REJECTED");
            Err(layout_error(
                409,
                &format!("MARKET_COMMAND_FAILED_{}_{}", code.unwrap_or(-1), reason),
            ))
        }
        Err(code) => Err(layout_error(504, &code)),
    }
}

/// The collector may run for tens of minutes at the provider rate limit, so the
/// dashboard only leaves a request file; the long-lived supervisor owns the
/// process and clears the request when it exits.
fn backfill(layout: &Layout, _command: Command) -> Result<Reply, Reply> {
    let request = layout.data.join("backfill.request");
    if request.is_file() {
        return Err(layout_error(409, "BACKFILL_ALREADY_RUNNING"));
    }
    std::fs::write(&request, b"84").map_err(|_| layout_error(409, "BACKFILL_REQUEST_FAILED"))?;
    Ok(layout_envelope(200, json!({"state": "STARTED", "sessions": 84})))
}
fn update_check(layout: &Layout) -> Result<Reply, Reply> {
    let script = layout.app.join("scripts").join("update-check.py");
    if !script.is_file() {
        return Err(layout_error(409, "UPDATE_CHECK_MISSING"));
    }
    let mut command = Command::new(layout.python());
    command
        .args(["-B", "-X", "utf8"])
        .arg(&script)
        .current_dir(&layout.app)
        .env("STRATIDE_STATE_ROOT", &layout.data)
        .stdin(std::process::Stdio::null());
    match stratide_runtime::run_capture(command, Duration::from_secs(30)) {
        Ok((Some(0), stdout, _)) | Ok((Some(2), stdout, _)) => {
            let value: Value = serde_json::from_slice(&stdout)
                .unwrap_or_else(|_| json!({"state": "UNAVAILABLE"}));
            Ok(layout_envelope(200, value))
        }
        Ok((code, _, _)) => Err(layout_error(
            409,
            &format!("UPDATE_CHECK_FAILED_{}", code.unwrap_or(-1)),
        )),
        Err(code) => Err(layout_error(504, &code)),
    }
}

fn open_folder(layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let target = body
        .get("target")
        .and_then(Value::as_str)
        .ok_or_else(|| layout_error(400, "FOLDER_INPUT_INVALID"))?;
    let path = match target {
        "data" => &layout.data,
        "logs" => &layout.logs,
        _ => return Err(layout_error(400, "FOLDER_INPUT_INVALID")),
    };
    let mut command = Command::new("explorer.exe");
    command.arg(path);
    stratide_runtime::win::hide_console(&mut command);
    command
        .spawn()
        .map_err(|_| layout_error(409, "FOLDER_OPEN_FAILED"))?;
    Ok(layout_envelope(200, json!({"state": "OPENED"})))
}

fn optional_text(body: &Value, key: &str) -> Result<Option<String>, Reply> {
    let Some(value) = body.get(key) else {
        return Ok(None);
    };
    let Some(text) = value.as_str() else {
        return Err(layout_error(400, "WSL_PATH_INVALID"));
    };
    let text = text.trim();
    if text.is_empty() {
        Ok(None)
    } else {
        Ok(Some(text.to_string()))
    }
}

fn configure_wsl(layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let distribution = body
        .get("distribution")
        .and_then(Value::as_str)
        .map(str::trim)
        .ok_or_else(|| layout_error(400, "WSL_DISTRIBUTION_INVALID"))?;
    let workspace = body
        .get("workspace")
        .and_then(Value::as_str)
        .map(str::trim)
        .ok_or_else(|| layout_error(400, "WSL_WORKSPACE_INVALID"))?;
    let wsl = stratide_runtime::WslSettings {
        distribution: distribution.to_string(),
        workspace: workspace.to_string(),
        python: optional_text(body, "python")?,
        model: optional_text(body, "model")?,
    };
    let restart = store_wsl(layout, wsl.clone())?;
    Ok(layout_envelope(
        200,
        json!({"state": "CONFIGURED", "watch_restart": restart, "wsl": wsl}),
    ))
}

/// Persist one detected or Owner-entered WSL entry. Restarting the single watch
/// interrupts an in-flight collection or CPU task, so unchanged settings are
/// stored without disturbing the running chain.
fn store_wsl(layout: &Layout, wsl: stratide_runtime::WslSettings) -> Result<bool, Reply> {
    stratide_runtime::config::validate_wsl(&wsl).map_err(|code| layout_error(400, &code))?;
    let mut config = layout
        .config()
        .map_err(|_| layout_error(409, "RUNTIME_CONFIG_INVALID"))?;
    let restart = config.wsl.as_ref() != Some(&wsl);
    if restart {
        // Written before the config so a failed request leaves the old entry
        // intact; a restart with the old entry only restarts the same watch.
        stratide_runtime::state::atomic_write(&layout.watch_restart_path(), b"{}".to_vec())
            .map_err(|_| layout_error(409, "WATCH_RESTART_REQUEST_FAILED"))?;
        stratide_runtime::wsl_probe::clear(layout);
    }
    config.wsl = Some(wsl);
    config
        .save(&layout.config_path)
        .map_err(|_| layout_error(409, "RUNTIME_CONFIG_WRITE_FAILED"))?;
    Ok(restart)
}

/// One-click local model discovery: find an existing WSL venv + TimesFM model
/// and store it, so a new user never has to type a worktree path.
fn detect_wsl(layout: &Layout) -> Result<Reply, Reply> {
    let script = layout.app.join("scripts").join("timesfm-cpu.py");
    if !script.is_file() {
        return Err(layout_error(409, "TIMESFM_CLI_MISSING"));
    }
    let mut command = Command::new(layout.python());
    command
        .args(["-B", "-X", "utf8"])
        .arg(&script)
        .arg("detect")
        .current_dir(&layout.app)
        .env("STRATIDE_STATE_ROOT", &layout.data)
        .env("STRATIDE_BIN_DIR", layout.app.join("bin"))
        .env_remove("STRATIDE_TUSHARE_TOKEN")
        .env_remove("STRATIDE_WSL_DISTRIBUTION")
        .env_remove("STRATIDE_WSL_WORKSPACE")
        .env_remove("STRATIDE_WSL_PYTHON")
        .env_remove("STRATIDE_WSL_MODEL");
    let value: Value = match stratide_runtime::run_capture(command, Duration::from_secs(180)) {
        Ok((_, stdout, _)) => match serde_json::from_slice(&stdout) {
            Ok(value) => value,
            Err(_) => return Err(layout_error(409, "WSL_DETECT_OUTPUT_INVALID")),
        },
        Err(_) => return Err(layout_error(504, "WSL_DETECT_FAILED")),
    };
    let Some(detected) = value.get("wsl").filter(|entry| entry.is_object()) else {
        return Ok(layout_envelope(
            200,
            json!({"state": "NOT_FOUND", "reason": "LOCAL_MODEL_NOT_FOUND"}),
        ));
    };
    let wsl = stratide_runtime::WslSettings {
        distribution: detected
            .get("distribution")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        workspace: detected
            .get("workspace")
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string(),
        python: detected
            .get("python")
            .and_then(Value::as_str)
            .map(str::to_string),
        model: detected
            .get("model")
            .and_then(Value::as_str)
            .map(str::to_string),
    };
    let restart = store_wsl(layout, wsl.clone())?;
    Ok(layout_envelope(
        200,
        json!({"state": "FOUND", "watch_restart": restart, "wsl": wsl}),
    ))
}

fn probe_wsl(app: &App, layout: &Layout) -> Result<Reply, Reply> {
    let config = layout
        .config()
        .map_err(|_| layout_error(409, "RUNTIME_CONFIG_INVALID"))?;
    let Some(wsl) = config.wsl else {
        return Err(layout_error(409, "WSL_NOT_CONFIGURED"));
    };
    let script = layout.app.join("scripts").join("timesfm-cpu.py");
    if !script.is_file() {
        return Err(layout_error(409, "TIMESFM_CLI_MISSING"));
    }
    let mut command = Command::new(layout.python());
    command
        .args(["-B", "-X", "utf8"])
        .arg(&script)
        .arg("preflight")
        .current_dir(&layout.app)
        .env("STRATIDE_STATE_ROOT", &layout.data)
        .env("STRATIDE_BIN_DIR", layout.app.join("bin"))
        .env("STRATIDE_WSL_DISTRIBUTION", &wsl.distribution)
        .env("STRATIDE_WSL_WORKSPACE", &wsl.workspace)
        .env("STRATIDE_WSL_PYTHON", wsl.python_path())
        .env("STRATIDE_WSL_MODEL", wsl.model_path())
        .env_remove("STRATIDE_TUSHARE_TOKEN");
    let value = match stratide_runtime::run_capture(command, Duration::from_secs(300)) {
        Ok((code, stdout, _)) => {
            let mut value: Value = serde_json::from_slice(&stdout)
                .unwrap_or_else(|_| json!({"error_code": "WSL_PROBE_OUTPUT_INVALID"}));
            if code != Some(0) {
                value["state"] = json!("BLOCKED");
            }
            value
        }
        Err(_) => json!({"state": "BLOCKED", "error_code": "WSL_PROBE_FAILED"}),
    };
    let ready = value.get("state").and_then(Value::as_str) == Some("READY");
    let reason = if ready {
        None
    } else {
        value
            .get("error_code")
            .and_then(Value::as_str)
            .map(str::to_string)
            .or_else(|| Some("WSL_PROBE_FAILED".into()))
    };
    let record = stratide_runtime::wsl_probe::WslProbeRecord::new(
        &wsl,
        if ready { "READY" } else { "BLOCKED" },
        reason.clone(),
    );
    stratide_runtime::wsl_probe::write(layout, record).map_err(|_| {
        layout_error(409, "WSL_PROBE_PERSIST_FAILED")
    })?;
    publish_light_snapshot(app, layout)?;
    Ok(layout_envelope(
        200,
        json!({
            "state": if ready { "READY" } else { "BLOCKED" },
            "reason": if ready { Value::Null } else { json!(reason) },
            "probe": value,
            "persisted": true,
        }),
    ))
}

/// Absent `completed` keeps the 0.3.0 write behaviour; only a boolean may
/// revoke, so an accidentally malformed body can never erase the marker.
fn setup_completed(body: &Value) -> Result<bool, ()> {
    match body.get("completed") {
        None => Ok(true),
        Some(Value::Bool(completed)) => Ok(*completed),
        Some(_) => Err(()),
    }
}

/// Write (default, or `{"completed":true}`) or revoke (`{"completed":false}`)
/// the first-run marker. Rewriting an existing marker stays idempotent, and
/// revoking an absent marker succeeds because the requested state already holds.
fn setup_complete(layout: &Layout, body: &Value) -> Result<Reply, Reply> {
    let marker = layout.runtime.join("setup-complete");
    let completed =
        setup_completed(body).map_err(|()| layout_error(400, "SETUP_INPUT_INVALID"))?;
    if !completed {
        match std::fs::remove_file(&marker) {
            Ok(()) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => return Err(layout_error(409, "SETUP_MARKER_DELETE_FAILED")),
        }
        return Ok(layout_envelope(
            200,
            json!({"state": "INCOMPLETE", "setup_complete": false, "completed_at": Value::Null}),
        ));
    }
    let marker_body = json!({"completed_at": stratide_runtime::timestamp()});
    stratide_runtime::state::atomic_write(
        &marker,
        serde_json::to_vec_pretty(&marker_body).expect("JSON value"),
    )
    .map_err(|_| layout_error(409, "SETUP_MARKER_WRITE_FAILED"))?;
    Ok(layout_envelope(
        200,
        json!({"state": "COMPLETE", "setup_complete": true, "completed_at": marker_body["completed_at"]}),
    ))
}

fn layout_envelope(status: u16, data: Value) -> Reply {
    let bytes = serde_json::to_vec(&json!({
        "api_version": 1,
        "state": if status == 200 { "ready" } else { "error" },
        "snapshot": Value::Null,
        "data": data,
        "error": if status == 200 { Value::Null } else { data },
    }))
    .expect("JSON response");
    Reply {
        status,
        mime: "application/json; charset=utf-8",
        body: bytes,
        exit_after: false,
    }
}

fn layout_error(status: u16, code: &str) -> Reply {
    let code: String = code.chars().take(320).collect();
    layout_envelope(status, json!({"code": code}))
}

#[cfg(test)]
mod tests {
    use super::setup_completed;
    use serde_json::json;

    #[test]
    fn setup_body_defaults_to_complete_and_only_boolean_can_revoke() {
        assert_eq!(setup_completed(&json!({})), Ok(true));
        assert_eq!(setup_completed(&json!({"completed": true})), Ok(true));
        assert_eq!(setup_completed(&json!({"completed": false})), Ok(false));
        assert_eq!(setup_completed(&json!({"completed": "false"})), Err(()));
        assert_eq!(setup_completed(&json!({"completed": null})), Err(()));
    }
}
