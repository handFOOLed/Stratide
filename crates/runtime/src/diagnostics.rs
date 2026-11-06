//! Read-only product diagnostics used by the local Dashboard setup page.
use crate::Layout;
use serde_json::{json, Value};
use std::path::Path;
use std::process::Command;

pub const REPO_URL: &str = "https://github.com/handFOOLed/Stratide";
pub const ISSUES_URL: &str = "https://github.com/handFOOLed/Stratide/issues";

/// `service` is supplied by the process answering this read-only request.
/// Probing our own single-threaded port from inside a handler would block and
/// report a healthy service as unavailable.
pub fn collect(layout: &Layout, service: Value) -> Result<Value, &'static str> {
    let config = layout.config();
    let config_error = config.as_ref().err().cloned();
    let state = crate::state::SupervisorState::read(&layout.state_path());
    let autostart = crate::autostart::status();
    let python = python_status(layout);
    let configured_wsl = config.as_ref().ok().and_then(|config| config.wsl.as_ref());
    let wsl = wsl_status(configured_wsl);
    let credential = credential_status(layout);
    let market = market_status(layout);
    let paper = paper_status(layout);
    let agent = agent_status(layout);
    let setup_complete = layout.runtime.join("setup-complete").is_file();
    let supervisor_running = state
        .as_ref()
        .is_some_and(|state| state.status != "STOPPED" && state.status != "FAILED");
    Ok(json!({
        "managed": true,
        "product_version": layout.version,
        "repo_url": REPO_URL,
        "issues_url": ISSUES_URL,
        "build": build_info(layout)?,
        "home": layout.home.to_string_lossy(),
        "app_dir": layout.app.to_string_lossy(),
        "data_root": layout.data.to_string_lossy(),
        "logs_dir": layout.logs.to_string_lossy(),
        "port": config.as_ref().map(|config| config.port).unwrap_or(0),
        "config_error": config_error,
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
        "service": service,
        "dependencies": {
            "python": python,
            "wsl": wsl,
            "timesfm": timesfm_status(layout, &wsl, configured_wsl),
            "tushare_credential": credential,
            "market_eod": market,
            "paper_account": paper,
            "agent": agent,
        },
        "log_tail": crate::log::tail(&layout.supervisor_log(), 25),
    }))
}

/// Installer metadata lives next to the executables. Source-tree runs have no
/// BUILD_INFO.json, so the three fields stay null rather than being invented.
fn build_info(layout: &Layout) -> Result<Value, &'static str> {
    let path = layout.app.join("BUILD_INFO.json");
    if !path.is_file() {
        return Ok(json!({"version": null, "commit": null, "built_at": null}));
    }
    let bytes = std::fs::read(&path).map_err(|_| "BUILD_INFO_UNREADABLE")?;
    let info: Value = serde_json::from_slice(&bytes).map_err(|_| "BUILD_INFO_INVALID")?;
    Ok(json!({
        "version": info.get("version").cloned().unwrap_or(Value::Null),
        "commit": info.get("commit").cloned().unwrap_or(Value::Null),
        "built_at": info.get("built_at").cloned().unwrap_or(Value::Null),
    }))
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
    match crate::run_capture(command, std::time::Duration::from_secs(4)) {
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

fn wsl_status(configured: Option<&crate::WslSettings>) -> Value {
    let mut command = Command::new("wsl.exe");
    command.args(["--list", "--quiet"]);
    let mut value = match crate::run_capture(command, std::time::Duration::from_secs(4)) {
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
    };
    if let Some(object) = value.as_object_mut() {
        object.insert("configured".into(), json!(configured.is_some()));
        object.insert(
            "distribution".into(),
            json!(configured.map(|settings| settings.distribution.as_str())),
        );
        object.insert(
            "workspace".into(),
            json!(configured.map(|settings| settings.workspace.as_str())),
        );
        object.insert(
            "python".into(),
            json!(configured.map(|settings| settings.python_path())),
        );
        object.insert(
            "model".into(),
            json!(configured.map(|settings| settings.model_path())),
        );
    }
    value
}

fn timesfm_status(layout: &Layout, wsl: &Value, configured_wsl: Option<&crate::WslSettings>) -> Value {
    let worker_state = layout.data.join("state").join("timesfm-cpu");
    let binding = layout
        .data
        .join("state")
        .join("risk-portfolio")
        .join("agent-binding.json");
    let wsl_ready = wsl.get("state").and_then(Value::as_str) == Some("READY");
    let configured = wsl.get("configured").and_then(Value::as_bool) == Some(true);
    let probe = configured_wsl.and_then(|settings| crate::wsl_probe::matching(layout, settings));
    let probe_at = probe.as_ref().map(|record| record.probed_at.clone());
    let probe_present = probe.is_some();
    let (state, reason) = if configured {
        match probe.as_ref() {
            Some(record) if record.state == "READY" => ("READY", None),
            Some(record) => (
                "CONFIGURED",
                Some(
                    record
                        .reason
                        .clone()
                        .unwrap_or_else(|| "WSL_PROBE_FAILED".into()),
                ),
            ),
            None => ("CONFIGURED", Some("WSL_PROBE_REQUIRED".into())),
        }
    } else if wsl_ready {
        (
            "EXTERNAL_WSL_WORKSPACE_REQUIRED",
            Some("TIMESFM_CPU_REQUIRES_THE_EXISTING_LINUX_WORKSPACE_ISOLATION".into()),
        )
    } else {
        (
            "BLOCKED_MISSING_RUNTIME",
            Some("TIMESFM_CPU_REQUIRES_THE_EXISTING_LINUX_WORKSPACE_ISOLATION".into()),
        )
    };
    json!({
        "state": state,
        "wsl_ready": wsl_ready,
        "configured": configured,
        "worker_state_present": worker_state.is_dir(),
        "agent_binding_present": binding.is_file(),
        "reason": reason,
        "probe_at": probe_at,
        "note": if configured && !probe_present {
            "已保存 WSL 入口；请点“检查状态”执行真实前置/模型/隔离探针。未通过时研究保持 BLOCKED，EOD 采集继续。"
        } else if configured {
            "本地预测引擎入口已保存；最近一次检查结果见上方状态。"
        } else {
            "未配置 WSL 时研究保持 BLOCKED；不会下载或打包模型。"
        },
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
    match crate::run_capture(command, std::time::Duration::from_secs(4)) {
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

#[cfg(test)]
mod tests {
    use super::build_info;
    use crate::Layout;
    use serde_json::json;

    fn layout(root: &std::path::Path) -> Layout {
        Layout {
            home: root.to_path_buf(),
            app: root.join("app"),
            data: root.join("data"),
            runtime: root.join("runtime"),
            logs: root.join("logs"),
            config_path: root.join("runtime.json"),
            version: "0.0.0-test".into(),
        }
    }

    #[test]
    fn missing_build_info_is_null_not_invented() {
        let tmp = tempfile::tempdir().unwrap();
        assert_eq!(
            build_info(&layout(tmp.path())).unwrap(),
            json!({"version": null, "commit": null, "built_at": null})
        );
    }

    #[test]
    fn installer_build_info_is_projected() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        std::fs::create_dir_all(&layout.app).unwrap();
        std::fs::write(
            layout.app.join("BUILD_INFO.json"),
            br#"{"product":"Stratide","version":"0.3.0","commit":"abc123-dirty","built_at":"2026-11-05T00:00:00Z","paper_only":true}"#,
        )
        .unwrap();
        let build = build_info(&layout).unwrap();
        assert_eq!(build["version"], "0.3.0");
        assert_eq!(build["commit"], "abc123-dirty");
        assert_eq!(build["built_at"], "2026-11-05T00:00:00Z");
    }

    #[test]
    fn corrupt_build_info_fails_loudly() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        std::fs::create_dir_all(&layout.app).unwrap();
        std::fs::write(layout.app.join("BUILD_INFO.json"), b"{broken").unwrap();
        assert_eq!(build_info(&layout), Err("BUILD_INFO_INVALID"));
    }

    #[test]
    fn persisted_wsl_probe_marks_timesfm_ready() {
        use crate::WslSettings;
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        std::fs::create_dir_all(&layout.data.join("state")).unwrap();
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        crate::wsl_probe::write(
            &layout,
            crate::wsl_probe::WslProbeRecord::new(&wsl, "READY", None),
        )
        .expect("write probe");
        let wsl_json = json!({"state":"READY","configured": true});
        let timesfm = super::timesfm_status(&layout, &wsl_json, Some(&wsl));
        assert_eq!(timesfm["state"], "READY");
        assert!(timesfm["reason"].is_null());
        assert!(timesfm["probe_at"].is_string());
    }

    #[test]
    fn configured_without_probe_still_requires_check() {
        use crate::WslSettings;
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        let wsl_json = json!({"state":"READY","configured": true});
        let timesfm = super::timesfm_status(&layout, &wsl_json, Some(&wsl));
        assert_eq!(timesfm["state"], "CONFIGURED");
        assert_eq!(timesfm["reason"], "WSL_PROBE_REQUIRED");
    }

    #[test]
    fn blocked_probe_surfaces_reason_without_move_bug() {
        use crate::WslSettings;
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        std::fs::create_dir_all(&layout.data.join("state")).unwrap();
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        crate::wsl_probe::write(
            &layout,
            crate::wsl_probe::WslProbeRecord::new(
                &wsl,
                "BLOCKED",
                Some("TIMESFM_WSL_VENV_MISSING".into()),
            ),
        )
        .expect("write probe");
        let wsl_json = json!({"state":"READY","configured": true});
        let timesfm = super::timesfm_status(&layout, &wsl_json, Some(&wsl));
        assert_eq!(timesfm["state"], "CONFIGURED");
        assert_eq!(timesfm["reason"], "TIMESFM_WSL_VENV_MISSING");
        assert!(timesfm["probe_at"].is_string());
    }
}
