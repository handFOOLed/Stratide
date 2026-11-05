//! Read-only product diagnostics used by the local Dashboard setup page.
use crate::{health, Layout};
use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;

pub fn collect(layout: &Layout) -> Value {
    let config = layout.config();
    let state = crate::state::SupervisorState::read(&layout.state_path());
    let autostart = crate::autostart::status();
    let live = health::probe(config.as_ref().map(|config| config.port).unwrap_or(0));
    let python = python_status(layout);
    let wsl = wsl_status();
    let credential = credential_status(layout);
    let market = market_status(layout);
    let paper = paper_status(layout);
    let agent = agent_status(layout);
    let setup_complete = layout.runtime.join("setup-complete").is_file();
    let supervisor_running = state
        .as_ref()
        .is_some_and(|state| state.status != "STOPPED" && state.status != "FAILED");
    json!({
        "managed": true,
        "product_version": layout.version,
        "home": layout.home.to_string_lossy(),
        "app_dir": layout.app.to_string_lossy(),
        "data_root": layout.data.to_string_lossy(),
        "logs_dir": layout.logs.to_string_lossy(),
        "port": config.as_ref().map(|config| config.port).unwrap_or(0),
        "config_error": config.err(),
        "setup_complete": setup_complete,
        "autostart": autostart,
        "supervisor": {
            "running": supervisor_running,
            "status": state.as_ref().map(|state| state.status.clone()).unwrap_or_else(|| "NOT_STARTED".into()),
            "reason": state.as_ref().map(|state| state.reason.clone()).unwrap_or_default(),
            "pid": state.as_ref().map(|state| state.supervisor_pid).unwrap_or(0),
            "instance_id": state.as_ref().map(|state| state.instance_id.clone()).unwrap_or_default(),
            "started_at": state.as_ref().map(|state| state.started_at.clone()).unwrap_or_default(),
            "updated_at": state.as_ref().map(|state| state.updated_at.clone()).unwrap_or_default(),
            "dashboard": state.as_ref().and_then(|state| state.dashboard.clone()),
            "watch": state.as_ref().and_then(|state| state.watch.clone()),
        },
        "service": match live {
            Ok(value) => json!({"healthy": true, "instance_id": value.instance_id, "pid": value.process_id, "agent": value.agent}),
            Err(error) => json!({"healthy": false, "code": error.code()}),
        },
        "dependencies": {
            "python": python,
            "wsl": wsl,
            "timesfm": timesfm_status(layout, &wsl),
            "tushare_credential": credential,
            "market_eod": market,
            "paper_account": paper,
            "agent": agent,
        },
        "log_tail": crate::log::tail(&layout.supervisor_log(), 25),
    })
}

fn python_status(layout: &Layout) -> Value {
    let path = layout.python();
    if !path.is_file() {
        return json!({"state":"MISSING","path":path.to_string_lossy(),"reason":"BUNDLED_PYTHON_MISSING"});
    }
    let mut command = Command::new(&path);
    command.args([
        "-I",
        "-B",
        "-c",
        "import sys,sqlite3,ctypes,zoneinfo;print(sys.version.split()[0])",
    ]);
    match crate::run_capture(command, std::time::Duration::from_secs(10)) {
        Ok((Some(0), stdout, _)) => json!({
            "state":"READY",
            "path":path.to_string_lossy(),
            "version":String::from_utf8_lossy(&stdout).trim(),
        }),
        Ok((code, _, stderr)) => json!({
            "state":"BROKEN",
            "path":path.to_string_lossy(),
            "reason":format!("PYTHON_EXIT_{}", code.unwrap_or(-1)),
            "detail":String::from_utf8_lossy(&stderr).lines().next().unwrap_or("").chars().take(160).collect::<String>(),
        }),
        Err(error) => json!({"state":"BROKEN","path":path.to_string_lossy(),"reason":error}),
    }
}

fn wsl_status() -> Value {
    let mut command = Command::new("wsl.exe");
    command.args(["--list", "--quiet"]);
    match crate::run_capture(command, std::time::Duration::from_secs(8)) {
        Ok((Some(0), stdout, _)) => {
            let text = crate::win::decode_output(&stdout);
            let distros: Vec<String> = text
                .replace('\u{feff}', "")
                .lines()
                .map(|line| line.trim().trim_end_matches('\0').to_string())
                .filter(|line| !line.is_empty())
                .collect();
            json!({"state":"READY","distributions":distros})
        }
        Ok((Some(code), stdout, _)) => {
            let detail = crate::win::decode_output(&stdout);
            json!({
                "state":"UNAVAILABLE",
                "reason":format!("WSL_EXIT_{code}"),
                "detail":detail.lines().next().unwrap_or("").chars().take(160).collect::<String>(),
            })
        }
        Ok((None, _, _)) => json!({"state":"UNAVAILABLE","reason":"WSL_TERMINATED"}),
        Err(error) => {
            json!({"state":"UNAVAILABLE","reason":format!("WSL_NOT_INSTALLED_OR_BLOCKED:{error}")})
        }
    }
}

fn timesfm_status(layout: &Layout, wsl: &Value) -> Value {
    let worker_state = layout.data.join("state").join("timesfm-cpu");
    let binding = layout
        .data
        .join("state")
        .join("risk-portfolio")
        .join("agent-binding.json");
    let wsl_ready = wsl.get("state").and_then(Value::as_str) == Some("READY");
    json!({
        "state": if wsl_ready { "EXTERNAL_WSL_WORKSPACE_REQUIRED" } else { "BLOCKED_MISSING_RUNTIME" },
        "wsl_ready": wsl_ready,
        "worker_state_present": worker_state.is_dir(),
        "agent_binding_present": binding.is_file(),
        "reason": "TIMESFM_CPU_REQUIRES_THE_EXISTING_LINUX_WORKSPACE_ISOLATION",
        "note": "本安装包不自动安装 GB 级模型或 WSL2 推理环境；未配置时研究保持 BLOCKED，不伪造成功。",
        "billing": "LOCAL_NO_BILLING",
    })
}

fn credential_status(layout: &Layout) -> Value {
    let helper = layout.app.join("scripts").join("stratide-credential.py");
    if !helper.is_file() {
        return json!({"state":"UNKNOWN","reason":"CREDENTIAL_HELPER_MISSING"});
    }
    let mut command = Command::new(layout.python());
    command
        .args([
            "-B",
            "-X",
            "utf8",
            helper.to_string_lossy().as_ref(),
            "check",
        ])
        .env("STRATIDE_STATE_ROOT", &layout.data)
        .env("PYTHONUTF8", "1");
    match crate::run_capture(command, std::time::Duration::from_secs(10)) {
        Ok((Some(0), stdout, _)) => match serde_json::from_slice::<Value>(&stdout) {
            Ok(value) => value,
            Err(_) => json!({"state":"UNKNOWN","reason":"CREDENTIAL_HELPER_INVALID"}),
        },
        Ok((code, _, stderr)) => json!({
            "state":"UNKNOWN",
            "reason":format!("CREDENTIAL_HELPER_EXIT_{}", code.unwrap_or(-1)),
            "detail":String::from_utf8_lossy(&stderr).lines().next().unwrap_or("").chars().take(160).collect::<String>(),
        }),
        Err(error) => json!({"state":"UNKNOWN","reason":error}),
    }
}

fn market_status(layout: &Layout) -> Value {
    let database = layout.market_database();
    let modified = database
        .metadata()
        .ok()
        .and_then(|metadata| metadata.modified().ok())
        .map(|time| {
            chrono::DateTime::<chrono::Utc>::from(time)
                .to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
        });
    json!({
        "state": if database.is_file() { "INITIALIZED" } else { "NOT_CONFIGURED" },
        "database": database.to_string_lossy(),
        "modified_at": modified,
        "note": if database.is_file() { "采集开关与交易日窗口由原 eod-operator market 状态管理。" } else { "首次设置需显式初始化并启用采集。" },
    })
}

fn paper_status(layout: &Layout) -> Value {
    let binding_path = layout
        .data
        .join("state")
        .join("paper-portfolio")
        .join("binding.json");
    if !binding_path.is_file() {
        return json!({"state":"NOT_CONFIGURED","binding":binding_path.to_string_lossy()});
    }
    let binding = std::fs::read(&binding_path)
        .ok()
        .and_then(|bytes| serde_json::from_slice::<Value>(&bytes).ok());
    let ledger = binding
        .as_ref()
        .and_then(|value| value.get("ledger"))
        .and_then(Value::as_str)
        .map(Path::new);
    json!({
        "state": if ledger.is_some_and(|ledger| ledger.exists()) { "CONFIGURED" } else { "BINDING_INVALID_OR_MISSING_LEDGER" },
        "binding": binding_path.to_string_lossy(),
        "ledger": ledger.map(|ledger| ledger.to_string_lossy().to_string()),
        "note": "本金、风险限额与 fixed-ticket-paper-v1 政策只能由 Owner 在本机显式配置；安装/向导不会代填。",
    })
}

fn agent_status(layout: &Layout) -> Value {
    let settings = layout.agent_dir().join("settings.json");
    let binding = layout
        .data
        .join("state")
        .join("risk-portfolio")
        .join("agent-binding.json");
    json!({
        "state": if settings.is_file() { "CONFIGURED" } else { "NOT_CONFIGURED" },
        "settings": settings.to_string_lossy(),
        "role_binding": binding.is_file(),
        "note": "本地研究/预算 Gate 由既有 Agent 配置控制；未配置时不发起任何云调用。",
    })
}
