use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ExitState {
    pub code: Option<i32>,
    pub at: String,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct ChildState {
    pub pid: u32,
    pub started_at: String,
    pub restarts: u32,
    #[serde(default)]
    pub instance_id: Option<String>,
    #[serde(default)]
    pub last_exit: Option<ExitState>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct SupervisorState {
    pub schema_version: u32,
    pub status: String,
    pub reason: String,
    pub instance_id: String,
    pub supervisor_pid: u32,
    pub started_at: String,
    pub updated_at: String,
    pub port: u16,
    pub data_root: String,
    pub product_version: String,
    pub dashboard: Option<ChildState>,
    pub watch: Option<ChildState>,
    pub autostart: bool,
    pub logs_dir: String,
}

impl SupervisorState {
    pub fn read(path: &Path) -> Option<Self> {
        let bytes = std::fs::read(path).ok()?;
        serde_json::from_slice(&bytes).ok()
    }

    pub fn write(&self, path: &Path) -> Result<(), String> {
        atomic_write(
            path,
            serde_json::to_vec_pretty(self).expect("serializable state"),
        )
    }
}

pub fn backfill_progress(data: &Path) -> Result<serde_json::Value, String> {
    let path = data.join("backfill.progress.json");
    match std::fs::read(path) {
        Ok(bytes) => serde_json::from_slice::<serde_json::Value>(&bytes)
            .ok()
            .filter(serde_json::Value::is_object)
            .ok_or_else(|| "BACKFILL_PROGRESS_UNREADABLE".into()),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(serde_json::json!({})),
        Err(_) => Err("BACKFILL_PROGRESS_UNREADABLE".into()),
    }
}

pub fn record_backfill(data: &Path, phase: &str, reason: Option<&str>) -> Result<(), String> {
    let mut value = if phase == "QUEUED" {
        serde_json::json!({})
    } else {
        backfill_progress(data).unwrap_or_else(|_| serde_json::json!({}))
    };
    value["phase"] = serde_json::json!(phase);
    value["reason"] = serde_json::json!(reason);
    atomic_write(
        &data.join("backfill.progress.json"),
        serde_json::to_vec(&value).expect("serializable backfill progress"),
    )
}

pub fn atomic_write(path: &Path, body: Vec<u8>) -> Result<(), String> {
    let temporary = path.with_extension(format!("tmp-{}", std::process::id()));
    use std::io::Write;
    let mut file = std::fs::File::create(&temporary)
        .map_err(|error| format!("WRITE_FAILED {}: {error}", temporary.display()))?;
    file.write_all(&body)
        .map_err(|error| format!("WRITE_FAILED: {error}"))?;
    file.sync_all()
        .map_err(|error| format!("WRITE_FAILED: {error}"))?;
    drop(file);
    #[cfg(windows)]
    {
        crate::win::replace_file(&temporary, path)
            .map_err(|error| format!("RENAME_FAILED: {error}"))?;
    }
    #[cfg(not(windows))]
    {
        std::fs::rename(&temporary, path).map_err(|error| format!("RENAME_FAILED: {error}"))?;
    }
    Ok(())
}
