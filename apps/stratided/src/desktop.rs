//! Fixed local research bridge. Browser input never becomes a path or command.
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::{
    io::Write,
    path::{Path, PathBuf},
    process::{Command, Stdio},
};
use stratide_research::{ensure, Agent, Result};

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Operation {
    pub id: String,
    pub label: String,
    pub kind: String,
    pub batch: String,
}
#[derive(Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    pub schema_version: u32,
    pub python: String,
    pub workspace: PathBuf,
    pub operations: Vec<Operation>,
    pub timesfm_batches: Vec<String>,
    pub fusion_batches: Vec<String>,
    pub evaluation_dirs: Vec<PathBuf>,
    pub registry_dirs: Vec<PathBuf>,
    pub evidence_files: Vec<PathBuf>,
    pub backup_manifest: Option<PathBuf>,
}
#[derive(Clone)]
pub struct Desktop {
    pub config: Config,
    path: PathBuf,
}
impl Desktop {
    pub fn load(path: &Path) -> Result<Self> {
        let config: Config = serde_json::from_slice(
            &crate::snapshot::read_bounded(path).map_err(stratide_research::Error)?,
        )
        .map_err(|_| "DESKTOP_CONFIG_INVALID")?;
        ensure(
            config.schema_version == 1
                && config.workspace.is_absolute()
                && config
                    .workspace
                    .join("scripts/dashboard-workspace.py")
                    .is_file(),
            "DESKTOP_WORKSPACE_INVALID",
        )?;
        ensure(
            config.operations.len() <= 24
                && config.timesfm_batches.len() <= 50
                && config.fusion_batches.len() <= 50
                && config.evaluation_dirs.len() <= 20
                && config.registry_dirs.len() <= 10
                && config.evidence_files.len() <= 20,
            "DESKTOP_INPUT_LIMIT",
        )?;
        let mut ids = std::collections::BTreeSet::new();
        for op in &config.operations {
            ensure(
                valid_name(&op.id)
                    && valid_name(&op.batch)
                    && ids.insert(&op.id)
                    && !op.label.is_empty()
                    && op.label.len() <= 120
                    && [
                        "local_timesfm",
                        "synthetic_fusion",
                        "recorded_fusion",
                        "risk_evaluation",
                    ]
                    .contains(&op.kind.as_str()),
                "DESKTOP_OPERATION_INVALID",
            )?;
        }
        for name in config.timesfm_batches.iter().chain(&config.fusion_batches) {
            ensure(valid_name(name), "DESKTOP_BATCH_INVALID")?;
        }
        Ok(Self {
            config,
            path: std::fs::canonicalize(path).map_err(|_| "DESKTOP_CONFIG_PATH_INVALID")?,
        })
    }
    pub fn actions(&self) -> Value {
        json!({"operations":self.config.operations,"scope":"LOCAL_RESEARCH_ONLY","real_market_cloud_egress":false})
    }
    fn command(&self, action: &str) -> Command {
        let mut c = Command::new(&self.config.python);
        c.current_dir(&self.config.workspace)
            .args(["-B", "scripts/dashboard-workspace.py", action, "--config"])
            .arg(&self.path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            c.creation_flags(0x08000000);
        }
        c
    }
    pub fn snapshot(&self) -> Result<Value> {
        let output = self
            .command("snapshot")
            .output()
            .map_err(|_| "DESKTOP_BRIDGE_UNAVAILABLE")?;
        ensure(
            output.stdout.len() <= 4 * 1024 * 1024,
            "DESKTOP_RESPONSE_LIMIT",
        )?;
        let v: Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "DESKTOP_RESPONSE_INVALID")?;
        ensure(
            output.status.success(),
            v["error_code"].as_str().unwrap_or("DESKTOP_READ_FAILED"),
        )?;
        Ok(v)
    }
    pub fn request(&self, agent: &Agent, id: &str, operation: &str) -> Result<Value> {
        let op = self
            .config
            .operations
            .iter()
            .find(|o| o.id == operation)
            .ok_or("DESKTOP_OPERATION_NOT_FOUND")?;
        agent.store().desktop_request(
            id,
            &serde_json::to_value(op).expect("operation JSON"),
            chrono::Utc::now(),
        )
    }
    pub fn start(&self, agent: &Agent, id: &str) -> Result<Value> {
        let binding = self
            .command("binding")
            .output()
            .map_err(|_| "DESKTOP_BINDING_UNAVAILABLE")?;
        ensure(binding.status.success(), "DESKTOP_BINDING_UNAVAILABLE")?;
        let binding: Value =
            serde_json::from_slice(&binding.stdout).map_err(|_| "DESKTOP_BINDING_INVALID")?;
        let expected =
            std::fs::canonicalize(agent.store().path.parent().expect("Agent store parent"))
                .map_err(|_| "DESKTOP_BINDING_INVALID")?;
        let actual = std::fs::canonicalize(
            binding["agent_dir"]
                .as_str()
                .ok_or("DESKTOP_BINDING_INVALID")?,
        )
        .map_err(|_| "DESKTOP_BINDING_INVALID")?;
        ensure(expected == actual, "DESKTOP_AGENT_AUTHORITY_MISMATCH")?;
        // Persist the permission consumption BEFORE spawning. A crash cannot
        // turn an uncertain attempt into an automatically repeated cloud call.
        let record = agent
            .store()
            .desktop_decide(id, "start", chrono::Utc::now())?;
        ensure(
            self.config
                .operations
                .iter()
                .any(|o| serde_json::to_value(o).expect("operation JSON") == record["action"]),
            "DESKTOP_ACTION_CHANGED",
        )?;
        let mut command = self.command("run");
        command.arg("--operation").arg(
            record["action"]["id"]
                .as_str()
                .expect("validated operation"),
        );
        let store = agent.store().clone();
        let id = id.to_string();
        match command.spawn() {
            Ok(mut child) => {
                let mut stdin = child.stdin.take().expect("piped stdin");
                stdin.write_all(b"{}").map_err(|_| "DESKTOP_BRIDGE_INPUT")?;
                drop(stdin);
                std::thread::Builder::new()
                    .name("owner-research-command".into())
                    .spawn(move || {
                        let outcome = child.wait_with_output();
                        let (success, reason) = match outcome {
                            Ok(o) => match serde_json::from_slice::<Value>(&o.stdout) {
                                Ok(_) if o.status.success() => {
                                    (true, "LOCAL_COMMAND_COMPLETED".to_string())
                                }
                                Ok(v) => (
                                    false,
                                    v["error_code"]
                                        .as_str()
                                        .unwrap_or("RESEARCH_COMMAND_REJECTED")
                                        .to_string(),
                                ),
                                Err(_) => (false, "RESEARCH_COMMAND_OUTPUT_INVALID".to_string()),
                            },
                            Err(_) => (false, "RESEARCH_COMMAND_OUTCOME_UNKNOWN".to_string()),
                        };
                        if let Err(e) =
                            store.desktop_finish(&id, success, &reason, chrono::Utc::now())
                        {
                            eprintln!("Owner research receipt: {}", e.0);
                        }
                    })
                    .map_err(|_| "DESKTOP_THREAD_UNAVAILABLE")?;
            }
            Err(_) => {
                agent.store().desktop_finish(
                    &id,
                    false,
                    "DESKTOP_BRIDGE_UNAVAILABLE",
                    chrono::Utc::now(),
                )?;
                return Err("DESKTOP_BRIDGE_UNAVAILABLE".into());
            }
        }
        Ok(record)
    }
    pub fn stop_local(&self) -> Result<Value> {
        let output = self
            .command("stop")
            .output()
            .map_err(|_| "DESKTOP_BRIDGE_UNAVAILABLE")?;
        let v: Value =
            serde_json::from_slice(&output.stdout).map_err(|_| "DESKTOP_RESPONSE_INVALID")?;
        ensure(output.status.success(), "LOCAL_STOP_FAILED")?;
        Ok(v)
    }
}
fn valid_name(s: &str) -> bool {
    !s.is_empty()
        && s.len() <= 64
        && s.bytes()
            .all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || b == b'_' || b == b'-')
}
