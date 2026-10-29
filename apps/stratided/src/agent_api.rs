//! Narrow Owner-controlled research API; legacy financial endpoints remain GET.
use crate::{App, Reply};
use serde::Deserialize;
use serde_json::{json, Value};
use stratide_research::{Agent, TaskRequest};
use tiny_http::Request;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Control {
    action: String,
    #[serde(default)]
    enabled: Option<bool>,
    #[serde(default)]
    model_id: Option<String>,
}

pub fn reply(app: &App, agent: Option<&Agent>, req: &mut Request, port: u16) -> Reply {
    let error = |status, code: &str| app.error(status, code, code);
    let single = |name: &'static str| {
        let mut values = req.headers().iter().filter(|h| h.field.equiv(name));
        let first = values.next().map(|h| h.value.as_str().to_string());
        if values.next().is_some() {
            None
        } else {
            first
        }
    };
    let host = single("Host").unwrap_or_default();
    let origin = single("Origin");
    if ![format!("127.0.0.1:{port}"), format!("localhost:{port}")].contains(&host)
        || origin
            .as_ref()
            .is_some_and(|v| v != &format!("http://{host}"))
    {
        return error(403, "LOCAL_ORIGIN_REQUIRED");
    }
    let method = req.method().as_str().to_string();
    if method != "GET" && method != "POST" {
        return error(405, "AGENT_METHOD_NOT_ALLOWED");
    }
    // Missing Origin is rejected on all writes; Host alone is never authority.
    if method == "POST" && origin.as_deref() != Some(&format!("http://{host}")) {
        return error(403, "EXPLICIT_ORIGIN_REQUIRED");
    }
    if single("Sec-Fetch-Site").is_some_and(|v| v != "same-origin" && v != "none") {
        return error(403, "SAME_ORIGIN_REQUIRED");
    }
    let Some(agent) = agent else {
        return error(503, "AGENT_NOT_CONFIGURED");
    };
    if !single("X-Stratide-Owner").is_some_and(|v| agent.authorized(&v)) {
        return error(401, "OWNER_TOKEN_REQUIRED");
    }
    let path = req.url().to_string();
    let body = if method == "POST" {
        if single("Content-Type").as_deref() != Some("application/json") {
            return error(415, "JSON_REQUIRED");
        }
        let length = single("Content-Length").and_then(|v| v.parse::<usize>().ok());
        let Some(length) = length.filter(|n| *n > 0 && *n <= 8192) else {
            return error(413, "BODY_LIMIT");
        };
        let mut bytes = vec![];
        use std::io::Read;
        if req.as_reader().take(8193).read_to_end(&mut bytes).is_err() || bytes.len() != length {
            return error(400, "BODY_INVALID");
        }
        match serde_json::from_slice::<Value>(&bytes) {
            Ok(v) => v,
            Err(_) => return error(400, "JSON_INVALID"),
        }
    } else {
        Value::Null
    };
    let now = chrono::Utc::now();
    let result: stratide_research::Result<Value> = (|| {
        if method == "GET" && path == "/api/agent/status" {
            return agent.status(now);
        }
        if method == "GET"
            && (path == "/api/agent/tasks" || path.starts_with("/api/agent/tasks?before="))
        {
            let before = if let Some(raw) = path.strip_prefix("/api/agent/tasks?before=") {
                Some(parse_id(raw)?)
            } else {
                None
            };
            return agent.store().list(before);
        }
        if method == "POST" && path == "/api/agent/tasks" {
            let input: TaskRequest =
                serde_json::from_value(body).map_err(|_| "TASK_INPUT_INVALID")?;
            return Ok(json!({"id":agent.create(&input,now)?.to_string(),"status":"queued"}));
        }
        if method == "POST" && path == "/api/agent/control" {
            let control: Control = serde_json::from_value(body).map_err(|_| "CONTROL_INVALID")?;
            return agent.control(
                &control.action,
                &json!({"enabled":control.enabled,"model_id":control.model_id}),
                now,
            );
        }
        if let Some(tail) = path.strip_prefix("/api/agent/tasks/") {
            let parts: Vec<_> = tail.split('/').collect();
            let id = parse_id(parts[0])?;
            if method == "GET" && parts.len() == 1 {
                return agent.store().task(id);
            }
            if method == "POST" && parts.len() == 2 && body == json!({}) {
                match parts[1] {
                    "cancel" => agent.store().cancel(id, now)?,
                    "retry" => agent.store().retry(id)?,
                    _ => return Err("AGENT_ROUTE_NOT_FOUND".into()),
                }
                return agent.store().task(id);
            }
        }
        Err("AGENT_ROUTE_NOT_FOUND".into())
    })();
    match result {
        Ok(data) => app.envelope(200, data, Value::Null),
        Err(e) => error(
            if e.0 == "AGENT_ROUTE_NOT_FOUND" || e.0 == "TASK_NOT_FOUND" {
                404
            } else {
                409
            },
            &e.0,
        ),
    }
}
fn parse_id(s: &str) -> stratide_research::Result<i64> {
    let id = s.parse::<i64>().map_err(|_| "TASK_ID_INVALID")?;
    stratide_research::ensure(id > 0 && id.to_string() == s, "TASK_ID_INVALID")?;
    Ok(id)
}
