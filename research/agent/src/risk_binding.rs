//! Bind cloud research to an existing Owner Agent, never a second cost ledger.
use crate::{config::Settings, ensure, risk_portfolio as rp, Agent, InputSummary, Result};
use fs2::FileExt;
use rusqlite::{Connection, OpenFlags};
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

pub const ID_KEY: &str = "risk_portfolio_authority_id";
pub const CONFIG_KEY: &str = "risk_portfolio_settings_path";

#[derive(Clone, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Binding {
    pub schema_version: u32,
    pub agent_dir: PathBuf,
    pub settings_path: PathBuf,
    pub authority_id: String,
}

fn canonical(path: &Path) -> Result<PathBuf> {
    crate::eod_snapshot::no_links(path)?;
    let path = fs::canonicalize(path).map_err(|_| "EXISTING_OWNER_AGENT_REQUIRED")?;
    #[cfg(windows)]
    {
        let text = path.to_string_lossy();
        if let Some(unc) = text.strip_prefix(r"\\?\UNC\") {
            return Ok(PathBuf::from(format!(r"\\{unc}")));
        }
        if let Some(local) = text.strip_prefix(r"\\?\") {
            return Ok(PathBuf::from(local));
        }
    }
    Ok(path)
}
pub fn check_settings_path(store: &crate::Store, path: &Path) -> Result<()> {
    if let Some(expected) = store.setting(CONFIG_KEY)? {
        ensure(
            canonical(path)? == Path::new(&expected),
            "AGENT_SETTINGS_AUTHORITY_MISMATCH",
        )?;
    }
    Ok(())
}
impl Binding {
    pub fn verify(&self, c: &Connection) -> Result<()> {
        ensure(
            self.schema_version == 1 && rp::valid_sha(&self.authority_id),
            "CLOUD_AGENT_BINDING_INVALID",
        )?;
        ensure(
            c.pragma_query_value(None, "application_id", |r| r.get::<_, i64>(0))? == 1397899569
                && c.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? == 1,
            "ORIGINAL_AGENT_SCHEMA_REQUIRED",
        )?;
        let path = c.path().ok_or("ORIGINAL_AGENT_STORE_REQUIRED")?;
        ensure(
            canonical(Path::new(path))? == canonical(&self.agent_dir.join("agent.sqlite"))?,
            "CLOUD_AGENT_DATABASE_MISMATCH",
        )?;
        let id: String = c.query_row("SELECT value FROM meta WHERE key=?1", [ID_KEY], |r| {
            r.get(0)
        })?;
        let config: String =
            c.query_row("SELECT value FROM meta WHERE key=?1", [CONFIG_KEY], |r| {
                r.get(0)
            })?;
        ensure(
            id == self.authority_id && Path::new(&config) == self.settings_path,
            "CLOUD_AGENT_AUTHORITY_CHANGED",
        )?;
        canonical(&self.settings_path)?;
        Ok(())
    }
}
pub fn read() -> Result<Binding> {
    read_at(&rp::root()?)
}
/// Other research entry points bind the same Owner database and config identity.
pub fn read_at(root: &Path) -> Result<Binding> {
    let path = root.join("agent-binding.json");
    ensure(path.is_file(), "CLOUD_AGENT_BINDING_REQUIRED")?;
    let binding: Binding = serde_json::from_value(rp::read(&path, 8192)?)
        .map_err(|_| "CLOUD_AGENT_BINDING_INVALID")?;
    crate::eod_snapshot::no_links(&binding.agent_dir)?;
    for file in [
        "agent.sqlite",
        "agent.sqlite-wal",
        "agent.sqlite-shm",
        "agent.sqlite-journal",
        "agent.lock",
        "owner-token",
    ] {
        crate::eod_snapshot::no_links(&binding.agent_dir.join(file))?;
    }
    let c = Connection::open_with_flags(
        binding.agent_dir.join("agent.sqlite"),
        OpenFlags::SQLITE_OPEN_READ_ONLY,
    )?;
    binding.verify(&c)?;
    Ok(binding)
}
pub fn bind(dir: &Path, config: Option<&Path>) -> Result<Binding> {
    bind_at(&rp::root()?, dir, config)
}
pub fn bind_at(root: &Path, dir: &Path, config: Option<&Path>) -> Result<Binding> {
    let dir = canonical(dir)?;
    let config = canonical(
        &config
            .map(Path::to_path_buf)
            .unwrap_or_else(|| dir.join("settings.json")),
    )?;
    let database = dir.join("agent.sqlite");
    crate::eod_snapshot::no_links(&database)?;
    ensure(database.is_file(), "EXISTING_OWNER_AGENT_REQUIRED")?;
    // Check before Agent::open, which is also the original initializer/recoverer.
    let c = Connection::open_with_flags(&database, OpenFlags::SQLITE_OPEN_READ_ONLY)?;
    ensure(
        c.pragma_query_value(None, "application_id", |r| r.get::<_, i64>(0))? == 1397899569
            && c.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? == 1,
        "ORIGINAL_AGENT_SCHEMA_REQUIRED",
    )?;
    let restricted: i64 = c.query_row(
        "SELECT COUNT(*) FROM meta WHERE key IN ('multimodal_agent_v1','eod_auto_binding')",
        [],
        |r| r.get(0),
    )?;
    ensure(restricted == 0, "CLOUD_AGENT_SCOPE_RESTRICTED")?;
    drop(c);
    let agent = Agent::open(
        &dir,
        Some(&config),
        InputSummary {
            version: "binding:no-input".into(),
            source_day: String::new(),
            mode: "no_input".into(),
            scopes: vec!["owner_task".into()],
            summary: json!({}),
            eod_eligible: false,
        },
    )?;
    finish(root, &dir, &config, agent.store())
}

/// Bind the already-open Owner Agent without taking the worker lock. The
/// dashboard attaches without exclusivity, so a lock-free binding is the only
/// way the running product can register the same authority once.
pub fn bind_attached(agent: &Agent) -> Result<Binding> {
    let root = rp::root()?;
    let dir = canonical(
        agent
            .store()
            .path
            .parent()
            .ok_or("EXISTING_OWNER_AGENT_REQUIRED")?,
    )?;
    let config = canonical(agent.settings_path())?;
    finish(&root, &dir, &config, agent.store())
}

fn finish(root: &Path, dir: &Path, config: &Path, store: &crate::Store) -> Result<Binding> {
    let c = store.connect()?;
    ensure(
        c.pragma_query_value(None, "application_id", |r| r.get::<_, i64>(0))? == 1397899569
            && c.pragma_query_value(None, "user_version", |r| r.get::<_, i64>(0))? == 1,
        "ORIGINAL_AGENT_SCHEMA_REQUIRED",
    )?;
    let restricted: i64 = c.query_row(
        "SELECT COUNT(*) FROM meta WHERE key IN ('multimodal_agent_v1','eod_auto_binding')",
        [],
        |r| r.get(0),
    )?;
    ensure(restricted == 0, "CLOUD_AGENT_SCOPE_RESTRICTED")?;
    drop(c);
    crate::eod_snapshot::no_links(root)?;
    fs::create_dir_all(root).map_err(|_| "CLOUD_STATE_ROOT")?;
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(root.join("binding.lock"))
        .map_err(|_| "CLOUD_BINDING_LOCK")?;
    lock.try_lock_exclusive()
        .map_err(|_| "CLOUD_BINDING_BUSY")?;
    if root.join("agent-binding.json").exists() {
        let old = read_at(root)?;
        ensure(
            old.agent_dir == dir && old.settings_path == config,
            "CLOUD_AGENT_BINDING_IMMUTABLE",
        )?;
        return Ok(old);
    }
    let id = if let Some(id) = store.setting(ID_KEY)? {
        id
    } else {
        let id = crate::nonce()?;
        store.set(ID_KEY, &id)?;
        id
    };
    check_settings_path(store, config)?;
    store.set(CONFIG_KEY, &config.to_string_lossy())?;
    let binding = Binding {
        schema_version: 1,
        agent_dir: dir.to_path_buf(),
        settings_path: config.to_path_buf(),
        authority_id: id,
    };
    binding.verify(&store.connect()?)?;
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(root.join("agent-binding.json"))
        .map_err(|_| "CLOUD_BINDING_WRITE")?;
    file.write_all(&serde_json::to_vec_pretty(&binding).unwrap())
        .map_err(|_| "CLOUD_BINDING_WRITE")?;
    file.sync_all().map_err(|_| "CLOUD_BINDING_WRITE")?;
    Ok(binding)
}
/// Explicit synthetic configuration, preserving the original budget and selection.
pub fn add_recorded_models(binding: &Binding, models: Vec<crate::config::Model>) -> Result<()> {
    let mut settings = Settings::load(&binding.settings_path)?;
    ensure(
        settings
            .budget
            .as_ref()
            .is_some_and(|b| b.currency == "TST"),
        "RECORDING_IS_NOT_CLOUD_AUTHORIZATION",
    )?;
    for model in models {
        if let Some(old) = settings.models.iter().find(|m| m.id == model.id) {
            ensure(
                old.fingerprint() == model.fingerprint(),
                "CLOUD_MODEL_ID_CONFLICT",
            )?;
        } else {
            settings.models.push(model);
        }
    }
    settings.validate()?;
    let temp = binding
        .settings_path
        .with_extension("json.risk-portfolio-pending");
    crate::eod_snapshot::no_links(&temp)?;
    let mut file = OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temp)
        .map_err(|_| "CLOUD_CONFIG_WRITE")?;
    file.write_all(&serde_json::to_vec_pretty(&settings).unwrap())
        .map_err(|_| "CLOUD_CONFIG_WRITE")?;
    file.sync_all().map_err(|_| "CLOUD_CONFIG_WRITE")?;
    drop(file);
    fs::rename(temp, &binding.settings_path).map_err(|_| "CLOUD_CONFIG_WRITE")?;
    Ok(())
}

pub fn recorded_models() -> Vec<crate::config::Model> {
    let mut s = Settings::fake();
    s.models.truncate(1);
    s.backup_model = None;
    let mut risk = s.models[0].clone();
    risk.id = "risk-timesfm".into();
    risk.label = "BigQuery TimesFM 2.5 / recorded transport".into();
    risk.kind = "bigquery_forecast_v1".into();
    risk.model = "TimesFM 2.5".into();
    risk.endpoint = Some(
        "https://bigquery.googleapis.com/bigquery/v2/projects/stratide-offline/queries".into(),
    );
    risk.api_key_env = Some("STRATIDE_RESEARCH_KEY_GOOGLE".into());
    risk.fake_scenario = None;
    risk.price = None;
    risk.max_input_tokens = 131072;
    risk.max_output_tokens = 8192;
    risk.cloud = Some(crate::risk_cloud::Cloud {
        transport: "recorded".into(),
        model_version: "TimesFM 2.5".into(),
        scope: "risk_timeseries_v1".into(),
        fields: crate::risk_cloud::RISK_FIELDS.map(String::from).to_vec(),
        policy_version: crate::risk_portfolio::POLICY.into(),
        max_call_micro: 1000,
        project: Some("stratide-offline".into()),
        dataset: Some("risk_research".into()),
        location: Some("US".into()),
        maximum_bytes_billed: Some(10485760),
        billing_unit: "query_bytes+prediction_bytes+storage_byte_seconds".into(),
        billing_bound_source: "synthetic_test".into(),
        billing_bound_version: "offline-v1".into(),
    });
    let mut fusion = s.models[0].clone();
    fusion.id = "fusion-deepseek".into();
    fusion.label = "DeepSeek flash / recorded transport".into();
    fusion.kind = "deepseek_portfolio_v1".into();
    fusion.model = "deepseek-flash".into();
    fusion.fake_scenario = None;
    fusion.endpoint = Some("https://api.deepseek.com/chat/completions".into());
    fusion.api_key_env = Some("STRATIDE_RESEARCH_KEY_DEEPSEEK".into());
    fusion.max_input_tokens = 65536;
    fusion.max_output_tokens = 8192;
    fusion.cloud = Some(crate::risk_cloud::Cloud {
        transport: "recorded".into(),
        model_version: "deepseek-flash/pinned-policy-v1-provider-alias".into(),
        scope: "portfolio_fusion_v1".into(),
        fields: crate::risk_cloud::FUSION_FIELDS.map(String::from).to_vec(),
        policy_version: crate::risk_portfolio::POLICY.into(),
        max_call_micro: 100000,
        project: None,
        dataset: None,
        location: None,
        maximum_bytes_billed: None,
        billing_unit: "input_output_tokens".into(),
        billing_bound_source: "synthetic_test".into(),
        billing_bound_version: "offline-v1".into(),
    });
    for m in [&mut risk, &mut fusion] {
        let g = m.grant.as_mut().unwrap();
        g.receiver = m.endpoint.clone().unwrap();
        g.purpose = crate::risk_portfolio::SCOPE.into();
        g.scopes = vec![
            crate::risk_portfolio::SCOPE.into(),
            m.cloud.as_ref().unwrap().scope.clone(),
        ];
    }
    vec![risk, fusion]
}
