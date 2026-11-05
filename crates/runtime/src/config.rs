use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct WslSettings {
    pub distribution: String,
    pub workspace: String,
    #[serde(default)]
    pub python: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
}

impl WslSettings {
    pub fn python_path(&self) -> &str {
        self.python.as_deref().unwrap_or(".venv/bin/python")
    }

    pub fn model_path(&self) -> &str {
        self.model.as_deref().unwrap_or("models/timesfm-2.5")
    }
}

pub fn validate_wsl(wsl: &WslSettings) -> Result<(), String> {
    let text = |value: &str| {
        !value.is_empty()
            && value.len() <= 4096
            && value.chars().all(|character| !character.is_control())
    };
    if !text(&wsl.distribution) || wsl.distribution.len() > 128 {
        return Err("WSL_DISTRIBUTION_INVALID".into());
    }
    if !text(&wsl.workspace) || !wsl.workspace.starts_with('/') {
        return Err("WSL_WORKSPACE_INVALID".into());
    }
    for value in [wsl.python.as_deref(), wsl.model.as_deref()].into_iter().flatten() {
        if !text(value) {
            return Err("WSL_PATH_INVALID".into());
        }
    }
    Ok(())
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeConfig {
    pub schema_version: u32,
    pub port: u16,
    pub data_root: PathBuf,
    /// Absolute or app-relative path to the bundled Python runtime. The
    /// installer writes it; development uses the same file.
    #[serde(default)]
    pub python: Option<PathBuf>,
    /// Existing Owner-managed WSL2 environment used only for local TimesFM CPU
    /// inference. Absent means research stays BLOCKED; EOD still runs.
    #[serde(default)]
    pub wsl: Option<WslSettings>,
}

impl RuntimeConfig {
    pub fn load(path: &Path) -> Result<Self, String> {
        let bytes =
            std::fs::read(path).map_err(|error| format!("RUNTIME_CONFIG_UNREADABLE: {error}"))?;
        let config: Self = serde_json::from_slice(&bytes).map_err(|_| "RUNTIME_CONFIG_INVALID")?;
        if config.schema_version != 1 || config.port == 0 {
            return Err("RUNTIME_CONFIG_INVALID".into());
        }
        if let Some(wsl) = &config.wsl {
            validate_wsl(wsl)?;
        }
        Ok(config)
    }

    pub fn load_or_create(path: &Path) -> Result<Self, String> {
        if path.is_file() {
            return Self::load(path);
        }
        let config = Self {
            schema_version: 1,
            port: 8710,
            data_root: path
                .parent()
                .ok_or("RUNTIME_HOME_UNAVAILABLE")?
                .join("data"),
            python: None,
            wsl: None,
        };
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).map_err(|_| "RUNTIME_HOME_UNAVAILABLE")?;
        }
        let body = serde_json::to_vec_pretty(&config).expect("serializable runtime config");
        crate::state::atomic_write(path, body)?;
        Ok(config)
    }

    pub fn python_path(&self, app: &Path) -> PathBuf {
        match &self.python {
            Some(path) if path.is_absolute() => path.clone(),
            Some(path) => app.join(path),
            None => app.join("runtime").join("python").join("python.exe"),
        }
    }

    pub fn save(&self, path: &Path) -> Result<(), String> {
        if let Some(wsl) = &self.wsl {
            validate_wsl(wsl)?;
        }
        crate::state::atomic_write(
            path,
            serde_json::to_vec_pretty(self).expect("serializable runtime config"),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn settings() -> WslSettings {
        WslSettings {
            distribution: "Ubuntu-24.04".into(),
            workspace: "/home/owner/Stratide".into(),
            python: None,
            model: None,
        }
    }

    #[test]
    fn wsl_settings_accepts_absolute_workspace_and_defaults() {
        let wsl = settings();
        assert_eq!(validate_wsl(&wsl), Ok(()));
        assert_eq!(wsl.python_path(), ".venv/bin/python");
        assert_eq!(wsl.model_path(), "models/timesfm-2.5");
    }

    #[test]
    fn wsl_settings_rejects_invalid_entries() {
        let mut relative = settings();
        relative.workspace = "home/owner/Stratide".into();
        assert_eq!(
            validate_wsl(&relative),
            Err("WSL_WORKSPACE_INVALID".into())
        );
        let mut control = settings();
        control.distribution = "Ubuntu\u{7f}".into();
        assert_eq!(
            validate_wsl(&control),
            Err("WSL_DISTRIBUTION_INVALID".into())
        );
        let mut path = settings();
        path.model = Some(String::new());
        assert_eq!(validate_wsl(&path), Err("WSL_PATH_INVALID".into()));
    }

    #[test]
    fn config_round_trips_the_wsl_entry() {
        let directory = tempfile::tempdir().expect("tempdir");
        let path = directory.path().join("runtime.json");
        let mut config = RuntimeConfig::load_or_create(&path).expect("create config");
        assert_eq!(config.wsl, None);
        config.wsl = Some(settings());
        config.save(&path).expect("save config");
        assert_eq!(
            RuntimeConfig::load(&path).expect("reload").wsl,
            Some(settings())
        );
    }
}
