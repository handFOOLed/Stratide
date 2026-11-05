//! Local installation/runtime control for the packaged Windows product.
//!
//! Read-only diagnostics use same-origin checks. Writes additionally require
//! the per-install runtime token created by the supervisor (never logged and
//! never sent to any remote service). Financial, budget and egress authority
//! stay with the existing Owner flows and are not modified here.
use crate::{App, Reply};
use serde_json::{json, Value};
use std::process::Command;
use std::sync::Mutex;
use std::time::{Duration, Instant};
use stratide_runtime::Layout;
use tiny_http::Request;

static STATUS_CACHE: Mutex<Option<(Instant, Value)>> = Mutex::new(None);

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
    let token = match layout.runtime_token() {
        Ok(token) => token,
        Err(_) => return error(503, "RUNTIME_TOKEN_UNAVAILABLE"),
    };
    let presented = single("X-Stratide-Runtime").unwrap_or_default();
    if !constant_time_eq(token.as_bytes(), presented.as_bytes()) {
        return error(401, "RUNTIME_TOKEN_REQUIRED");
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
    let result = (|| -> Result<Reply, Reply> {
        match path.as_str() {
            "/api/runtime/autostart" => autostart(app, &layout, &body),
            "/api/runtime/tushare-token" => tushare_token(&layout, &body),
            "/api/runtime/market" => market(&layout, &body),
            "/api/runtime/wsl" => configure_wsl(&layout, &body),
            "/api/runtime/wsl-detect" => detect_wsl(&layout),
            "/api/runtime/wsl-probe" => probe_wsl(&layout),
            "/api/runtime/open-folder" => open_folder(&layout, &body),
            "/api/runtime/setup-complete" => setup_complete(&layout),
            "/api/runtime/shutdown" => {
                let mut reply = app.envelope(200, json!({"state": "STOPPING"}), Value::Null);
                reply.exit_after = true;
                Ok(reply)
            }
            _ => Err(error(404, "RUNTIME_ROUTE_NOT_FOUND")),
        }
    })();
    invalidate();
    match result {
        Ok(reply) => reply,
        Err(reply) => reply,
    }
}

fn status(app: &App, layout: &Layout) -> Result<Value, &'static str> {
    let mut cache = STATUS_CACHE.lock().map_err(|_| "RUNTIME_STATUS_BUSY")?;
    if let Some((at, value)) = cache.as_ref() {
        if at.elapsed() < Duration::from_secs(4) {
            return Ok(value.clone());
        }
    }
    // This handler runs inside the service, so it is online by definition.
    let service = json!({"healthy": true, "instance_id": app.instance_id(),
        "pid": std::process::id().to_string()});
    let value = stratide_runtime::diagnostics::collect(layout, service);
    *cache = Some((Instant::now(), value.clone()));
    Ok(value)
}

fn invalidate() {
    if let Ok(mut cache) = STATUS_CACHE.lock() {
        *cache = None;
    }
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
    if !["init", "enable", "disable"].contains(&action) {
        return Err(layout_error(400, "MARKET_INPUT_INVALID"));
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
    match stratide_runtime::run_capture(command, Duration::from_secs(180)) {
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

fn probe_wsl(layout: &Layout) -> Result<Reply, Reply> {
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
    Ok(layout_envelope(
        200,
        json!({
            "state": if ready { "READY" } else { "BLOCKED" },
            "reason": if ready { Value::Null } else { value.get("error_code").cloned().unwrap_or_else(|| json!("WSL_PROBE_FAILED")) },
            "probe": value,
        }),
    ))
}

fn setup_complete(layout: &Layout) -> Result<Reply, Reply> {
    let marker = layout.runtime.join("setup-complete");
    let body = json!({"completed_at": stratide_runtime::timestamp()});
    stratide_runtime::state::atomic_write(
        &marker,
        serde_json::to_vec_pretty(&body).expect("JSON value"),
    )
    .map_err(|_| layout_error(409, "SETUP_MARKER_WRITE_FAILED"))?;
    Ok(layout_envelope(
        200,
        json!({"state": "COMPLETE", "completed_at": body["completed_at"]}),
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

fn constant_time_eq(expected: &[u8], presented: &[u8]) -> bool {
    if expected.len() != presented.len() {
        return false;
    }
    let mut difference = 0u8;
    for (left, right) in expected.iter().zip(presented.iter()) {
        difference |= left ^ right;
    }
    difference == 0
}
