//! Local Windows product runtime: layout, health, autostart, supervisor state.
//!
//! No trading, budget or ledger code lives here. The desktop shell only starts
//! the existing service and the existing foreground EOD watch as its children.
use std::path::{Path, PathBuf};

pub mod autostart;
pub mod config;
pub mod diagnostics;
pub mod health;
pub mod log;
pub mod state;
pub mod win;

pub use config::{RuntimeConfig, WslSettings};
pub use health::{HealthData, ProbeError};

pub const SUPERVISOR_TASK: &str = "Stratide";
pub const RUNTIME_STOP_FILE: &str = "stop.request";
pub const RUNTIME_TOKEN_FILE: &str = "runtime-token";
pub const SUPERVISOR_STATE_FILE: &str = "supervisor.json";

/// Absolute product locations. The install directory and user data directory
/// are deliberately separate so upgrades never touch prices, ledger or models.
#[derive(Clone, Debug)]
pub struct Layout {
    pub home: PathBuf,
    pub app: PathBuf,
    pub data: PathBuf,
    pub runtime: PathBuf,
    pub logs: PathBuf,
    pub config_path: PathBuf,
    pub version: String,
}

impl Layout {
    pub fn load() -> Result<Self, String> {
        Self::from_home(default_home()?)
    }

    pub fn from_home(home: PathBuf) -> Result<Self, String> {
        let app = match std::env::var_os("STRATIDE_APP_DIR") {
            Some(value) if !value.is_empty() => PathBuf::from(value),
            _ => std::env::current_exe()
                .map_err(|error| format!("CURRENT_EXE_UNAVAILABLE: {error}"))?
                .parent()
                .ok_or("APP_DIRECTORY_UNAVAILABLE")?
                .to_path_buf(),
        };
        let config_path = home.join("runtime.json");
        let config = RuntimeConfig::load_or_create(&config_path)?;
        let version = product_version(&app);
        Ok(Self {
            data: config.data_root.clone(),
            runtime: home.join("runtime"),
            logs: home.join("logs"),
            home,
            app,
            config_path,
            version,
        })
    }

    pub fn ensure_directories(&self) -> Result<(), String> {
        for path in [&self.home, &self.data, &self.runtime, &self.logs] {
            std::fs::create_dir_all(path)
                .map_err(|error| format!("DIRECTORY_CREATE_FAILED {}: {error}", path.display()))?;
        }
        Ok(())
    }

    pub fn config(&self) -> Result<RuntimeConfig, String> {
        RuntimeConfig::load(&self.config_path)
    }

    pub fn python(&self) -> PathBuf {
        let config = self.config();
        match config {
            Ok(config) => config.python_path(&self.app),
            Err(_) => self.app.join("runtime").join("python").join("python.exe"),
        }
    }

    pub fn state_path(&self) -> PathBuf {
        self.runtime.join(SUPERVISOR_STATE_FILE)
    }

    pub fn stop_path(&self) -> PathBuf {
        self.runtime.join(RUNTIME_STOP_FILE)
    }

    pub fn token_path(&self) -> PathBuf {
        self.runtime.join(RUNTIME_TOKEN_FILE)
    }

    pub fn market_root(&self) -> PathBuf {
        self.data
            .join("state")
            .join("historical-warehouse")
            .join("market-eod")
    }

    pub fn market_database(&self) -> PathBuf {
        self.market_root().join("warehouse.sqlite")
    }

    pub fn agent_dir(&self) -> PathBuf {
        self.data.join("agent")
    }

    pub fn supervisor_log(&self) -> PathBuf {
        self.logs.join("supervisor.log")
    }

    pub fn read_stop_request(&self) -> bool {
        self.stop_path().is_file()
    }

    pub fn write_stop_request(&self, reason: &str) -> Result<(), String> {
        let body = serde_json::json!({
            "requested_at": chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true),
            "reason": reason,
        });
        state::atomic_write(
            &self.stop_path(),
            serde_json::to_vec_pretty(&body).expect("JSON value"),
        )
    }

    pub fn clear_stop_request(&self) {
        let _ = std::fs::remove_file(self.stop_path());
    }

    pub fn watch_restart_path(&self) -> PathBuf {
        self.runtime.join("watch-restart.request")
    }

    pub fn clear_watch_restart(&self) {
        let _ = std::fs::remove_file(self.watch_restart_path());
    }

    /// A per-install secret used only by local runtime control endpoints and
    /// the desktop launcher. Never placed in logs, config or installer.
    pub fn runtime_token(&self) -> Result<String, String> {
        let path = self.token_path();
        if let Ok(bytes) = std::fs::read(&path) {
            let token = String::from_utf8(bytes).map_err(|_| "RUNTIME_TOKEN_INVALID")?;
            let token = token.trim().to_string();
            if token.len() >= 32 {
                return Ok(token);
            }
        }
        let token = random_hex(32)?;
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|_| "RUNTIME_DIRECTORY_UNAVAILABLE")?;
        }
        let mut options = std::fs::OpenOptions::new();
        options.write(true).create(true).truncate(true);
        #[cfg(windows)]
        {
            use std::os::windows::fs::OpenOptionsExt;
            // Owner-only ACL is inherited from the per-user LocalAppData tree.
            options.share_mode(0);
        }
        use std::io::Write;
        let mut file = options
            .open(&path)
            .map_err(|error| format!("RUNTIME_TOKEN_WRITE_FAILED: {error}"))?;
        file.write_all(token.as_bytes())
            .map_err(|_| "RUNTIME_TOKEN_WRITE_FAILED")?;
        file.sync_all().map_err(|_| "RUNTIME_TOKEN_WRITE_FAILED")?;
        Ok(token)
    }
}

pub fn default_home() -> Result<PathBuf, String> {
    match std::env::var_os("STRATIDE_HOME") {
        Some(value) if !value.is_empty() => Ok(PathBuf::from(value)),
        _ => Ok(local_app_data()?.join("Stratide")),
    }
}

fn local_app_data() -> Result<PathBuf, String> {
    match std::env::var_os("LOCALAPPDATA") {
        Some(value) if !value.is_empty() => Ok(PathBuf::from(value)),
        _ => Err("LOCALAPPDATA_UNAVAILABLE".into()),
    }
}

pub fn product_version(app: &Path) -> String {
    match std::fs::read_to_string(app.join("VERSION")) {
        Ok(value) => value.trim().to_string(),
        Err(_) => "0.0.0-dev".to_string(),
    }
}

pub fn random_hex(bytes: usize) -> Result<String, String> {
    let mut buffer = vec![0u8; bytes];
    getrandom::fill(&mut buffer).map_err(|_| "OS_RANDOM_UNAVAILABLE")?;
    Ok(buffer.iter().map(|byte| format!("{byte:02x}")).collect())
}

pub fn timestamp() -> String {
    chrono::Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, true)
}

/// Run a short-lived helper and return (exit code, stdout, stderr), bounded.
pub fn run_capture(
    mut command: std::process::Command,
    timeout: std::time::Duration,
) -> Result<(Option<i32>, Vec<u8>, Vec<u8>), String> {
    use std::process::Stdio;
    command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(Stdio::null());
    #[cfg(windows)]
    win::hide_console(&mut command);
    let mut child = command.spawn().map_err(|error| error.to_string())?;
    let started = std::time::Instant::now();
    loop {
        match child.try_wait().map_err(|error| error.to_string())? {
            Some(status) => {
                let output = child
                    .wait_with_output()
                    .map_err(|error| error.to_string())?;
                return Ok((status.code(), output.stdout, output.stderr));
            }
            None if started.elapsed() > timeout => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("HELPER_TIMEOUT".into());
            }
            None => std::thread::sleep(std::time::Duration::from_millis(20)),
        }
    }
}

/// Helper with a secret on stdin, never in argv or the environment.
pub fn run_capture_input(
    mut command: std::process::Command,
    input: &[u8],
    timeout: std::time::Duration,
) -> Result<(Option<i32>, Vec<u8>, Vec<u8>), String> {
    use std::io::Write;
    use std::process::Stdio;
    command
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(Stdio::piped());
    #[cfg(windows)]
    win::hide_console(&mut command);
    let mut child = command.spawn().map_err(|error| error.to_string())?;
    if let Some(mut stdin) = child.stdin.take() {
        stdin.write_all(input).map_err(|error| error.to_string())?;
    }
    let started = std::time::Instant::now();
    loop {
        match child.try_wait().map_err(|error| error.to_string())? {
            Some(status) => {
                let output = child
                    .wait_with_output()
                    .map_err(|error| error.to_string())?;
                return Ok((status.code(), output.stdout, output.stderr));
            }
            None if started.elapsed() > timeout => {
                let _ = child.kill();
                let _ = child.wait();
                return Err("HELPER_TIMEOUT".into());
            }
            None => std::thread::sleep(std::time::Duration::from_millis(20)),
        }
    }
}

#[cfg(test)]
mod product_runtime_tests {
    use super::*;

    #[test]
    fn atomic_state_write_replaces_previous_bytes() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("state.json");
        state::atomic_write(&path, b"first".to_vec()).expect("write");
        state::atomic_write(&path, b"second".to_vec()).expect("write");
        assert_eq!(std::fs::read(&path).expect("read"), b"second");
    }

    #[test]
    fn port_probe_distinguishes_free_and_bound_ports() {
        let listener = std::net::TcpListener::bind(("127.0.0.1", 0)).expect("bind");
        let port = listener.local_addr().expect("addr").port();
        assert!(!health::port_available(port));
        drop(listener);
        assert!(health::port_available(port));
        assert!(health::probe(port).is_err());
    }
}
