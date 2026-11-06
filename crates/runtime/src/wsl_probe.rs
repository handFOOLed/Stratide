//! Persisted WSL TimesFM preflight results for setup-page dependency status.
use crate::{Layout, WslSettings};
use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::time::Duration;

const PROBE_FILE: &str = "timesfm-wsl-probe.json";

/// READY/BLOCKED probe records older than this are not trusted for dependency status.
pub const TRUST_MAX_AGE: Duration = Duration::from_secs(7 * 24 * 3600);

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WslProbeRecord {
    pub schema_version: u32,
    pub probed_at: String,
    pub fingerprint: String,
    pub state: String,
    #[serde(default)]
    pub reason: Option<String>,
}

impl WslProbeRecord {
    pub fn new(wsl: &WslSettings, state: &str, reason: Option<String>) -> Self {
        Self {
            schema_version: 1,
            probed_at: crate::timestamp(),
            fingerprint: fingerprint(wsl),
            state: state.into(),
            reason,
        }
    }

    pub fn is_trusted(&self) -> bool {
        if self.schema_version != 1 {
            return false;
        }
        let Ok(at) = chrono::DateTime::parse_from_rfc3339(&self.probed_at) else {
            return false;
        };
        let age = chrono::Utc::now().signed_duration_since(at.with_timezone(&chrono::Utc));
        match age.to_std() {
            Ok(elapsed) => elapsed <= TRUST_MAX_AGE,
            Err(_) => false,
        }
    }
}

pub fn fingerprint(wsl: &WslSettings) -> String {
    format!(
        "{}|{}|{}|{}",
        wsl.distribution,
        wsl.workspace,
        wsl.python_path(),
        wsl.model_path()
    )
}

pub fn path(layout: &Layout) -> PathBuf {
    layout.data.join("state").join(PROBE_FILE)
}

pub fn read(layout: &Layout) -> Option<WslProbeRecord> {
    let bytes = std::fs::read(path(layout)).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn write(layout: &Layout, record: WslProbeRecord) -> Result<(), String> {
    let path = path(layout);
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| format!("PROBE_DIR_FAILED: {error}"))?;
    }
    crate::state::atomic_write(
        &path,
        serde_json::to_vec_pretty(&record).expect("serializable probe"),
    )
}

pub fn clear(layout: &Layout) {
    let path = path(layout);
    match std::fs::remove_file(&path) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(_) => {}
    }
}

pub fn fingerprint_matches_layout(layout: &Layout, expected: &str) -> bool {
    let config = match layout.config() {
        Ok(config) => config,
        Err(_) => return false,
    };
    let Some(wsl) = config.wsl else {
        return false;
    };
    fingerprint(wsl) == expected
}

pub fn matching(layout: &Layout, wsl: &WslSettings) -> Option<WslProbeRecord> {
    let record = read(layout)?;
    if record.fingerprint != fingerprint(wsl) {
        return None;
    }
    if !record.is_trusted() {
        return None;
    }
    Some(record)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::Layout;

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
    fn fingerprint_matches_layout_reflects_current_config() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        std::fs::create_dir_all(tmp.path().join("runtime")).unwrap();
        std::fs::write(
            tmp.path().join("runtime.json"),
            br#"{"schema_version":1,"port":8710,"data_root":"data","python":null,"wsl":{"distribution":"Ubuntu-24.04","workspace":"/home/a"}}"#,
        )
        .unwrap();
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/a".into(),
            python: None,
            model: None,
        };
        let fp = fingerprint(&wsl);
        assert!(fingerprint_matches_layout(&layout, &fp));
        assert!(!fingerprint_matches_layout(&layout, "stale|fp"));
    }

    #[test]
    fn expired_probe_record_is_not_matching() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        let record = WslProbeRecord {
            schema_version: 1,
            probed_at: "2020-01-01T00:00:00+00:00".into(),
            fingerprint: fingerprint(&wsl),
            state: "READY".into(),
            reason: None,
        };
        write(&layout, record).expect("write probe");
        assert!(matching(&layout, &wsl).is_none());
    }

    #[test]
    fn probe_record_is_invalidated_when_wsl_entry_changes() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        write(
            &layout,
            WslProbeRecord::new(&wsl, "READY", None),
        )
        .expect("write probe");
        let changed = WslSettings {
            workspace: "/home/other".into(),
            ..wsl.clone()
        };
        assert!(matching(&layout, &wsl).is_some());
        assert!(matching(&layout, &changed).is_none());
    }

    #[test]
    fn write_to_read_only_parent_fails_without_panic() {
        let tmp = tempfile::tempdir().unwrap();
        let layout = layout(tmp.path());
        let wsl = WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/stratide".into(),
            python: None,
            model: None,
        };
        let record = WslProbeRecord::new(&wsl, "READY", None);
        std::fs::create_dir_all(&layout.data).unwrap();
        // Block `data/state/` as a directory on all platforms (file at that path).
        std::fs::write(layout.data.join("state"), b"").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let blocked = layout.data.join("state-blocked");
            std::fs::create_dir_all(&blocked).unwrap();
            let mut perms = std::fs::metadata(&blocked).unwrap().permissions();
            perms.set_mode(0o500);
            std::fs::set_permissions(&blocked, perms).unwrap();
            let mut blocked_layout = layout.clone();
            blocked_layout.data = blocked;
            assert!(write(&blocked_layout, record.clone()).is_err());
        }
        assert!(write(&layout, record).is_err());
    }
}
