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
}

impl Config {
    pub fn parse(args: impl Iterator<Item = String>) -> Result<Self, String> {
        let mut config = Self {
            report_dir: None,
            evaluation_file: None,
            assets_dir: DEFAULT_ASSETS.into(),
            port: DEFAULT_PORT,
        };
        let mut args = args.peekable();
        let mut seen = std::collections::BTreeSet::new();
        while let Some(arg) = args.next() {
            if ![
                "--report-dir",
                "--evaluation-file",
                "--assets-dir",
                "--port",
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
                "--port" => {
                    config.port = value.parse::<u16>().map_err(|_| "端口必须为 1–65535")?;
                    if config.port == 0 {
                        return Err("端口必须为 1–65535".into());
                    }
                }
                _ => unreachable!(),
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
    snapshot: Option<Result<Snapshot, String>>,
    research: Option<Result<Value, String>>,
}

pub struct Reply {
    pub status: u16,
    pub mime: &'static str,
    pub body: Vec<u8>,
}

impl App {
    pub fn load(report_dir: Option<&Path>, evaluation_file: Option<&Path>) -> Self {
        Self {
            snapshot: report_dir.map(Snapshot::load),
            research: evaluation_file.map(snapshot::research),
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
        })).expect("JSON response contains only serializable values") }
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
            };
        }
        if path == "/api/health" {
            return self.envelope(200, json!({"service": "online", "paper_only": true,
                "market_data": "last_published_snapshot_not_live", "forward_account": "not_available",
                "agent": "not_implemented", "notifications": "not_implemented",
                "refresh_policy": "explicit_process_restart"}), Value::Null);
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
        let route = match path {
            "/api/account" => "account",
            "/api/equity" => "equity",
            "/api/positions" => "positions",
            "/api/strategies" => "strategies",
            "/api/fills" => "fills",
            "/api/orders" => "orders",
            _ => return self.error(404, "NOT_FOUND", "没有此路由"),
        };
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
    let header = |name: &'static str| {
        req.headers()
            .iter()
            .find(|h| h.field.equiv(name))
            .map(|h| h.value.as_str())
    };
    let reply = app.reply(
        assets,
        req.method().as_str(),
        req.url(),
        header("Host").unwrap_or(""),
        header("Origin"),
        port,
    );
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
}
