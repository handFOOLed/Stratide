pub mod agent_api;
pub mod desktop;
pub mod paper_view;
pub mod runtime_api;
pub mod runtime_status_cache;
pub mod snapshot;

use serde_json::{json, Value};
use snapshot::Snapshot;
use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
};
use tiny_http::{Header, Request, Response, Server, StatusCode};

pub const DEFAULT_PORT: u16 = 8710;
pub const DEFAULT_ASSETS: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../dashboard/dist");

#[derive(Debug)]
pub struct Config {
    pub report_dir: Option<PathBuf>,
    pub evaluation_file: Option<PathBuf>,
    pub assets_dir: PathBuf,
    pub port: u16,
    pub agent_dir: Option<PathBuf>,
    pub agent_config: Option<PathBuf>,
    pub agent_eod_store: Option<String>,
    pub desktop_config: Option<PathBuf>,
    pub paper_ledger: Option<PathBuf>,
    pub runtime_home: Option<PathBuf>,
    /// Attached observation mode for a supervised install: the background watch
    /// owns the research worker lock and executes tasks; the Dashboard only reads
    /// and controls. Never starts an in-process worker thread.
    pub agent_observer: bool,
}

impl Config {
    pub fn parse(args: impl Iterator<Item = String>) -> Result<Self, String> {
        let mut config = Self {
            report_dir: None,
            evaluation_file: None,
            assets_dir: DEFAULT_ASSETS.into(),
            port: DEFAULT_PORT,
            agent_dir: None,
            agent_config: None,
            agent_eod_store: None,
            desktop_config: None,
            paper_ledger: None,
            runtime_home: None,
            agent_observer: false,
        };
        let mut args = args.peekable();
        let mut seen = std::collections::BTreeSet::new();
        while let Some(arg) = args.next() {
            // Boolean switch without a value: only the supervised background
            // watch may own the Agent worker lock.
            if arg == "--agent-observer" {
                if !seen.insert(arg.clone()) {
                    return Err(format!("未知或重复参数：{arg}"));
                }
                config.agent_observer = true;
                continue;
            }
            if ![
                "--report-dir",
                "--evaluation-file",
                "--assets-dir",
                "--port",
                "--agent-dir",
                "--agent-config",
                "--agent-eod-store",
                "--desktop-config",
                "--paper-ledger",
                "--runtime-home",
            ]
            .contains(&arg.as_str())
                || !seen.insert(arg.clone())
            {
                return Err(format!("未知或重复参数：{arg}"));
            }
            let value = args.next().ok_or_else(|| format!("{arg} 缺少参数值"))?;
            match arg.as_str() {
                "--report-dir" => config.report_dir = Some(value.into()),
                "--evaluation-file" => config.evaluation_file = Some(value.into()),
                "--assets-dir" => config.assets_dir = value.into(),
                "--agent-dir" => config.agent_dir = Some(value.into()),
                "--agent-config" => config.agent_config = Some(value.into()),
                "--agent-eod-store" => config.agent_eod_store = Some(value),
                "--desktop-config" => config.desktop_config = Some(value.into()),
                "--paper-ledger" => config.paper_ledger = Some(value.into()),
                "--runtime-home" => config.runtime_home = Some(value.into()),
                "--port" => {
                    config.port = value.parse::<u16>().map_err(|_| "端口必须为 1–65535")?;
                    if config.port == 0 {
                        return Err("端口必须为 1–65535".into());
                    }
                }
                _ => unreachable!(),
            }
        }
        if let Some(name) = &config.agent_eod_store {
            if config.agent_dir.is_none()
                || config.report_dir.is_some()
                || config.evaluation_file.is_some()
            {
                return Err("--agent-eod-store 需要 --agent-dir，且不能与 --report-dir/--evaluation-file 混用".into());
            }
            if !stratide_research::eod_snapshot::valid_name(name) {
                return Err("SNAPSHOT_STORE_NAME".into());
            }
        }
        Ok(config)
    }
}

pub struct Assets(BTreeMap<&'static str, (&'static str, Vec<u8>)>);
impl Assets {
    pub fn load(dir: &Path) -> Result<Self, String> {
        let mut files = BTreeMap::new();
        for (url, name, mime) in [
            ("/", "index.html", "text/html; charset=utf-8"),
            (
                "/assets/app.js",
                "assets/app.js",
                "text/javascript; charset=utf-8",
            ),
            (
                "/assets/app.css",
                "assets/app.css",
                "text/css; charset=utf-8",
            ),
        ] {
            files.insert(url, (mime, snapshot::read_bounded(&dir.join(name))
                .map_err(|_| "缺少前端构建：先执行 npm --prefix apps/dashboard ci 和 npm --prefix apps/dashboard run build".to_string())?));
        }
        Ok(Self(files))
    }
}

pub struct App {
    instance_id: String,
    snapshot: Option<Result<Snapshot, String>>,
    research: Option<Result<Value, String>>,
    pub desktop: Option<desktop::Desktop>,
    pub paper_ledger: Option<PathBuf>,
    pub runtime_home: Option<PathBuf>,
}

pub struct Reply {
    pub status: u16,
    pub mime: &'static str,
    pub body: Vec<u8>,
    pub exit_after: bool,
}

impl App {
    /// Stable identity of this running service instance (never a secret).
    pub fn instance_id(&self) -> &str {
        &self.instance_id
    }

    /// A bounded projection, never raw reports, identities, lots or account cash.
    pub fn agent_summary(&self) -> stratide_research::InputSummary {
        let mut summary = stratide_research::InputSummary {
            version: "paper-summary-v1:no-input".into(),
            source_day: String::new(),
            mode: "no_input".into(),
            scopes: vec!["owner_task".into()],
            summary: json!({"paper":"not_configured"}),
            eod_eligible: false,
        };
        if let Some(Ok(s)) = &self.snapshot {
            let r = &s.report;
            let raw = r.last_day.0.to_string();
            summary.source_day = format!("{}-{}-{}", &raw[..4], &raw[4..6], &raw[6..]);
            summary.mode = s.metadata["mode"].as_str().unwrap_or("unknown").to_string();
            summary.version = format!(
                "paper-summary-v1:{}",
                s.metadata["snapshot_id"].as_str().unwrap_or("invalid")
            );
            summary.scopes.push("paper_summary_v1".into());
            summary.summary = json!({"snapshot_id":s.metadata["snapshot_id"],"mode":summary.mode,
                "first_day":s.metadata["first_day"],"last_day":s.metadata["last_day"],
                "evidence_class":s.metadata["evidence_class"],"report_days":r.daily.len().to_string(),
                "simulated_fills":r.fills.len().to_string(),"risk_rejections":r.risk_rejections.len().to_string(),
                "total_return_bps":r.total_return_bps.map(|v|v.to_string()),
                "drawdown_bps":r.max_daily_observation_drawdown_bps.map(|v|v.to_string()),
                "missing_valuation_days":r.daily.iter().filter(|d|d.nav_fen.is_none()).count().to_string(),
                "provenance":"published_six_report_consistency_checked_not_independent_qualification"});
            // The report's observed session date is used, never a guessed weekday.
            summary.eod_eligible = summary.mode == "historical_replay"
                && r.daily.last().is_some_and(|d| d.nav_fen.is_some())
                && r.unverified_status_sessions == 0;
        }
        if let Some(Ok(e)) = &self.research {
            summary.scopes.push("historical_summary_v1".into());
            let brief = json!({"research_evidence":e["research_evidence"],"engineering":e["engineering"],
                "window_count":e["windows"].as_array().map(|a|a.len().to_string()),"account_inclusion":false});
            let digest = stratide_research::hash(brief.to_string().as_bytes());
            summary.version.push_str(&format!(":evaluation:{digest}"));
            summary.summary["historical_evaluation"] = brief;
        }
        summary
    }
    pub fn load(report_dir: Option<&Path>, evaluation_file: Option<&Path>) -> Self {
        Self {
            instance_id: stratide_research::nonce().expect("OS random instance identity"),
            snapshot: report_dir.map(Snapshot::load),
            research: evaluation_file.map(snapshot::research),
            desktop: None,
            paper_ledger: None,
            runtime_home: None,
        }
    }

    fn envelope(&self, status: u16, data: Value, error: Value) -> Reply {
        let snapshot = self.snapshot.as_ref().and_then(|r| r.as_ref().ok());
        let state = match &self.snapshot {
            None => "no_input",
            Some(Ok(_)) => "ready",
            Some(Err(_)) => "invalid_snapshot",
        };
        Reply { status, mime: "application/json; charset=utf-8", body: serde_json::to_vec(&json!({
            "api_version": 1, "state": state, "snapshot": snapshot.map(|s| &s.metadata), "data": data, "error": error,
        })).expect("JSON response contains only serializable values"), exit_after: false }
    }

    fn error(&self, status: u16, code: &str, message: &str) -> Reply {
        self.envelope(
            status,
            Value::Null,
            json!({"code": code, "message": message}),
        )
    }

    pub fn reply(
        &self,
        assets: &Assets,
        method: &str,
        path: &str,
        host: &str,
        origin: Option<&str>,
        port: u16,
    ) -> Reply {
        let allowed = [format!("127.0.0.1:{port}"), format!("localhost:{port}")];
        if !allowed.iter().any(|s| s == host)
            || origin.is_some_and(|origin| origin != format!("http://{host}"))
        {
            return self.error(403, "LOCAL_ORIGIN_REQUIRED", "仅接受本机同源访问");
        }
        if method != "GET" {
            return self.error(405, "READ_ONLY", "此服务仅提供只读 GET 接口");
        }
        // Routes are a literal allowlist. Query strings, encoded paths and path
        // traversal never become filesystem paths.
        if let Some((mime, bytes)) = assets.0.get(path) {
            return Reply {
                status: 200,
                mime,
                body: bytes.clone(),
                exit_after: false,
            };
        }
        if path == "/api/health" {
            return self.envelope(200, json!({"service": "online", "paper_only": true,
                "process_id":std::process::id().to_string(),"instance_id":self.instance_id,
                "market_data": "last_published_snapshot_not_live", "forward_account": "not_available",
                "agent": "not_configured", "notifications": "not_configured",
                "refresh_policy": "explicit_process_restart"}), Value::Null);
        }
        if path == "/api/v1/workspace" {
            return match &self.desktop {
                Some(d)=>match d.snapshot() {Ok(v)=>self.envelope(200,v,Value::Null),Err(e)=>self.error(503,&e.0,&e.0)},
                None=>self.envelope(200,json!({"schema_version":1,"state":"not_configured","studies":[],"evaluations":[],"candidates":[],"evidence":[],"paper_allowed":false,"live_allowed":false}),Value::Null),
            };
        }
        if path == "/api/research" {
            return match &self.research {
                None => self.envelope(
                    200,
                    json!({"results": [], "status": "not_configured"}),
                    Value::Null,
                ),
                Some(Ok(r)) => self.envelope(
                    200,
                    json!({"results": [r], "status": "stored_research_only"}),
                    Value::Null,
                ),
                Some(Err(e)) => self.error(503, "INVALID_RESEARCH", e),
            };
        }
        let current_only = path.starts_with("/api/v1/");
        let financial_path = if current_only {
            path.strip_prefix("/api/v1").expect("known prefix")
        } else {
            match path.strip_prefix("/api") {
                Some(p) => p,
                None => return self.error(404, "NOT_FOUND", "没有此路由"),
            }
        };
        let route = match financial_path {
            "/account" => "account",
            "/equity" => "equity",
            "/positions" => "positions",
            "/strategies" => "strategies",
            "/fills" => "fills",
            "/orders" => "orders",
            _ => return self.error(404, "NOT_FOUND", "没有此路由"),
        };
        if let Some(path) = self
            .paper_ledger
            .as_ref()
            .filter(|_| current_only || self.snapshot.is_none())
        {
            return match paper_view::load(path) {
                Ok((meta,data))=>Reply{status:200,mime:"application/json; charset=utf-8",body:serde_json::to_vec(&json!({"api_version":1,"state":"ready","snapshot":meta,"data":data[route],"error":Value::Null})).expect("paper JSON"),exit_after:false},
                Err(e)=>self.error(503,"INVALID_CURRENT_LEDGER",&e),
            };
        }
        if current_only
            && (self.snapshot.is_none()
                || self.snapshot.as_ref().is_some_and(|s| {
                    s.as_ref()
                        .is_ok_and(|s| s.report.mode == stratide_ledger::DataMode::HistoricalReplay)
                }))
        {
            return self.error(
                409,
                "CURRENT_PAPER_ACCOUNT_UNCONFIGURED",
                "尚未指定当前 Paper 账本；所选历史报告仅供历史页读取。",
            );
        }
        match &self.snapshot {
            None => self.error(409, "NO_SNAPSHOT", "尚未指定 Paper 报告。请通过 --report-dir 选择一个已发布的六报告目录，然后重启服务。"),
            Some(Err(e)) => self.error(503, "INVALID_SNAPSHOT", e),
            Some(Ok(snapshot)) => match snapshot.data(route) {
                Ok(data) => self.envelope(200, data, Value::Null),
                Err(e) => self.error(503, "INVALID_SNAPSHOT", &e),
            },
        }
    }
}

pub fn bind_local(port: u16) -> Result<Server, String> {
    Server::http(("127.0.0.1", port)).map_err(|_| "无法绑定 127.0.0.1，请确认端口未被使用".into())
}

pub fn handle(app: &App, assets: &Assets, req: Request, port: u16) {
    handle_with_agent(app, assets, req, port, None)
}

pub fn handle_with_agent(
    app: &App,
    assets: &Assets,
    mut req: Request,
    port: u16,
    agent: Option<&stratide_research::Agent>,
) {
    if req.url().starts_with("/api/agent/") {
        let reply = agent_api::reply(app, agent, &mut req, port);
        respond(req, reply);
        return;
    }
    if req.url().starts_with("/api/runtime/") {
        let reply = runtime_api::reply(app, &mut req, port);
        respond(req, reply);
        return;
    }
    let header = |name: &'static str| {
        req.headers()
            .iter()
            .find(|h| h.field.equiv(name))
            .map(|h| h.value.as_str())
    };
    let mut reply = app.reply(
        assets,
        req.method().as_str(),
        req.url(),
        header("Host").unwrap_or(""),
        header("Origin"),
        port,
    );
    if req.url() == "/api/health" && reply.status == 200 && agent.is_some() {
        if let Ok(mut value) = serde_json::from_slice::<Value>(&reply.body) {
            value["data"]["agent"] = json!("local_research_available");
            value["data"]["notifications"] = json!("local_persistent_inbox");
            reply.body = serde_json::to_vec(&value).expect("health JSON");
        }
    }
    respond(req, reply);
}

fn respond(req: Request, reply: Reply) {
    let mut response = Response::from_data(reply.body).with_status_code(StatusCode(reply.status));
    for (key, value) in [
        ("Content-Type", reply.mime), ("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
        ("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"),
    ] { response.add_header(Header::from_bytes(key, value).expect("constant HTTP headers")); }
    if reply.status == 405 {
        response.add_header(Header::from_bytes("Allow", "GET").unwrap());
    }
    let _ = req.respond(response);
    if reply.exit_after {
        std::thread::spawn(|| {
            std::thread::sleep(std::time::Duration::from_millis(250));
            std::process::exit(0);
        });
    }
}

#[cfg(test)]
mod current_account_tests {
    use super::*;
    #[test]
    fn current_projection_preserves_fill_costs_flows_and_assumption_provenance() {
        use stratide_contracts::{Cny, Timestamp, TradingDay};
        use stratide_ledger::{synthetic as f, Command, DataMode, Ledger};
        let app = App::load(
            Some(Path::new(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/../../docs/evidence/m0-pr03/sample-report"
            ))),
            None,
        );
        let mut config = app.snapshot.unwrap().unwrap().report.config;
        config.max_mark_age_ms = 7_200_000;
        config.authorized_principal = Cny::from_fen(1_010_000).unwrap(); // explicit synthetic cap for the flow check
        let mut g = f::genesis(config);
        g.at = Timestamp(f::T0 + 3_600_000);
        g.provenance.mode = DataMode::HistoricalReplay;
        g.provenance.source_version = "paper-eod-assumption-v1:synthetic_test".into();
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("paper");
        let mut l = Ledger::create(&path, g).unwrap();
        let mut p = f::proposal(&l.state().config, 1);
        p.limit_price = Cny::from_fen(1020).unwrap();
        p.decision_at = l.state().snapshot.as_of;
        p.data_available_at = p.decision_at;
        p.earliest_execution_at = Timestamp(p.decision_at.0 + 1);
        l.execute(
            "intent",
            f::submit(p, TradingDay(20261028), Timestamp(f::T0 + 3_600_000)),
        )
        .unwrap();
        l.execute(
            "freeze",
            Command::FreezePaperIntentsV1 {
                now: Timestamp(f::T0 + 3_600_000),
                target_day: TradingDay(20261029),
                decision_source_sha256: "a".repeat(64),
            },
        )
        .unwrap();
        let mut bar = f::bar(TradingDay(20261029), 1);
        bar.provenance = l.state().provenance.clone();
        bar.available_at = Timestamp(bar.closes_at.0 + 3_600_000);
        l.execute(
            "confirm",
            Command::ExPostOpenAssumptionV1 {
                now: bar.available_at,
                rules: f::rules(bar.day, bar.available_at),
                source_received_at: bar.available_at,
                source_sha256: "b".repeat(64),
                corporate_actions_verified: true,
                bar,
            },
        )
        .unwrap();
        drop(l); // The existing writer keeps SQLite EXCLUSIVE until CLI exit.
        let (meta, data) = paper_view::load(&path).unwrap();
        assert_eq!(meta["mode"], "synthetic_test");
        assert_eq!(data["account"]["nav_fen"], "999867");
        assert_eq!(data["account"]["cumulative_pnl_fen"], "-133");
        assert_eq!(data["account"]["session_pnl_fen"], "-133");
        assert_eq!(data["account"]["max_daily_observation_drawdown_bps"], "1");
        assert_eq!(data["positions"][0]["cost_basis_fen"], "100133");
        assert_eq!(data["positions"][0]["unrealized_pnl_fen"], "-133");
        assert_eq!(data["positions"][0]["sellable_shares"], "0");
        assert!(data["fills"][0]["execution_assumption"]
            .as_str()
            .unwrap()
            .starts_with("EX_POST_OPEN_ASSUMPTION"));
        let mut l = Ledger::open(&path).unwrap();
        l.execute(
            "flow",
            Command::Observe {
                now: Timestamp(l.state().snapshot.as_of.0 + 1),
                day: l.state().snapshot.trading_day,
                marks: l.state().snapshot.marks.clone(),
                external_flow_fen: 10000,
            },
        )
        .unwrap();
        drop(l);
        let (_, data) = paper_view::load(&path).unwrap();
        assert_eq!(data["account"]["cumulative_pnl_fen"], "-133");
        assert_eq!(data["account"]["session_pnl_fen"], "-133");
        assert!(data["account"]["total_return_bps"].is_null());
    }
    #[test]
    fn selected_historical_projection_never_becomes_current_nav() {
        let mut app = App::load(
            Some(Path::new(concat!(
                env!("CARGO_MANIFEST_DIR"),
                "/../../docs/evidence/m0-pr03/sample-report"
            ))),
            None,
        );
        // Synthetic router counterproof: classify the selected report as history.
        let snapshot = app.snapshot.as_mut().unwrap().as_mut().unwrap();
        snapshot.report.mode = stratide_ledger::DataMode::HistoricalReplay;
        let config = snapshot.report.config.clone();
        let assets = Assets(BTreeMap::new());
        assert_eq!(
            app.reply(&assets, "GET", "/api/account", "127.0.0.1:8710", None, 8710)
                .status,
            200
        );
        assert_eq!(
            app.reply(
                &assets,
                "GET",
                "/api/v1/account",
                "127.0.0.1:8710",
                None,
                8710
            )
            .status,
            409
        );
        let tmp = tempfile::tempdir().unwrap();
        let path = tmp.path().join("current");
        let mut genesis = stratide_ledger::synthetic::genesis(config);
        genesis.provenance.mode = stratide_ledger::DataMode::HistoricalReplay;
        genesis.provenance.source_version = "paper-eod-assumption-v1:synthetic_test".into();
        let ledger = stratide_ledger::Ledger::create(&path, genesis).unwrap();
        drop(ledger);
        app.paper_ledger = Some(path);
        let current = app.reply(
            &assets,
            "GET",
            "/api/v1/account",
            "127.0.0.1:8710",
            None,
            8710,
        );
        assert_eq!(current.status, 200);
        let current: Value = serde_json::from_slice(&current.body).unwrap();
        let report = app.reply(&assets, "GET", "/api/account", "127.0.0.1:8710", None, 8710);
        let report: Value = serde_json::from_slice(&report.body).unwrap();
        assert_eq!(current["data"]["nav_fen"], "1000000");
        assert_eq!(report["data"]["nav_fen"], "992893");
        assert_ne!(
            current["snapshot"]["snapshot_id"],
            report["snapshot"]["snapshot_id"]
        );
    }
}
