use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeConfig {
    pub schema_version: u32,
    pub port: u16,
    pub data_root: PathBuf,
    /// Absolute or app-relative path to the bundled Python runtime. The
    /// installer writes it; development uses the same file.
    pub python: Option<PathBuf>,
}

impl RuntimeConfig {
    pub fn load(path: &Path) -> Result<Self, String> {
        let bytes =
            std::fs::read(path).map_err(|error| format!("RUNTIME_CONFIG_UNREADABLE: {error}"))?;
        let config: Self = serde_json::from_slice(&bytes).map_err(|_| "RUNTIME_CONFIG_INVALID")?;
        if config.schema_version != 1 || config.port == 0 {
            return Err("RUNTIME_CONFIG_INVALID".into());
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
        crate::state::atomic_write(
            path,
            serde_json::to_vec_pretty(self).expect("serializable runtime config"),
        )
    }
}
