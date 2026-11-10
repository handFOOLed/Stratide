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
    // Local single-Owner install: Host/Origin/Sec-Fetch-Site above still bound
    // the caller to this exact loopback origin; no separate page token is kept.
    let path = req.url().to_string();
    let request_key = single("X-Stratide-Idempotency");
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
        if method == "GET" && path == "/api/agent/consent" {
            return stratide_research::consent::status(agent);
        }
        if method == "POST" && path == "/api/agent/consent" && body == json!({}) {
            return stratide_research::consent::accept(agent);
        }
        if method == "GET" && path == "/api/agent/market-research" {
            return stratide_research::market_research::status(agent);
        }
        if method == "GET" {
            if let Some(day) = path.strip_prefix("/api/agent/market-research/preview?day=") {
                return stratide_research::market_research::preview(agent, day);
            }
        }
        if method == "POST" {
            if let Some(action) = path.strip_prefix("/api/agent/market-research/") {
                return if action == "install-model" && body == json!({}) {
                    stratide_research::market_research::install_model(agent)
                } else {
                    stratide_research::market_research::control(agent, action, body)
                };
            }
        }
        if method == "GET" && path == "/api/agent/provider" {
            return stratide_research::provider_setup::status(agent);
        }
        if method == "POST" {
            if path == "/api/agent/provider" {
                return stratide_research::provider_setup::configure(agent, &body);
            }
            if path == "/api/agent/provider/test" {
                let expected = body["provider"].as_str();
                stratide_research::ensure(body == json!({}) || expected.is_some_and(|name| body == json!({"provider": name})), "PROVIDER_REQUIRED")?;
                return stratide_research::provider_setup::test(agent, expected);
            }
            if path == "/api/agent/provider/price-review" {
                return stratide_research::provider_setup::review_price(agent, &body);
            }
            if path == "/api/agent/provider/remove" && body == json!({}) {
                return stratide_research::provider_setup::remove(agent);
            }
        }
        if method == "POST" && path == "/api/agent/budget" {
            return stratide_research::budget_admin::update(agent, &body, now);
        }
        if method == "GET" && path == "/api/agent/status" {
            return agent.status(now);
        }
        if method == "GET" && path == "/api/agent/inbox" {
            return agent.store().desktop_inbox(now);
        }
        if method == "POST" && path == "/api/agent/stop-local" && body == json!({}) {
            return app
                .desktop
                .as_ref()
                .ok_or("DESKTOP_NOT_CONFIGURED")?
                .stop_local();
        }
        if method == "GET" && path == "/api/agent/prompts" {
            return Ok(
                json!({"version":"fusion-researcher-v1","visibility":"SAFE_BUILTIN_PROMPT_NO_CONTEXT_OR_CREDENTIALS",
                "developer":include_str!("../../../research/agent/prompts/fusion-researcher-v1-developer.txt")}),
            );
        }
        if method == "GET" && path == "/api/agent/operations" {
            return Ok(app.desktop.as_ref().map(|d|d.actions()).unwrap_or_else(||json!({"operations":[],"scope":"LOCAL_RESEARCH_ONLY","real_market_cloud_egress":false})));
        }
        if method == "POST" && path == "/api/agent/approvals" {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Input {
                id: String,
                operation: String,
            }
            let input: Input =
                serde_json::from_value(body).map_err(|_| "APPROVAL_INPUT_INVALID")?;
            return app
                .desktop
                .as_ref()
                .ok_or("DESKTOP_NOT_CONFIGURED")?
                .request(agent, &input.id, &input.operation);
        }
        if method == "POST" && path == "/api/agent/decide" {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Input {
                id: String,
                decision: String,
            }
            let input: Input =
                serde_json::from_value(body).map_err(|_| "APPROVAL_INPUT_INVALID")?;
            return if input.decision == "start" {
                app.desktop
                    .as_ref()
                    .ok_or("DESKTOP_NOT_CONFIGURED")?
                    .start(agent, &input.id)
            } else {
                agent
                    .store()
                    .desktop_decide(&input.id, &input.decision, now)
            };
        }
        if method == "POST" && path == "/api/agent/read-notifications" {
            #[derive(Deserialize)]
            #[serde(deny_unknown_fields)]
            struct Input {
                ids: Vec<String>,
            }
            let input: Input = serde_json::from_value(body).map_err(|_| "TASK_ID_INVALID")?;
            stratide_research::ensure(
                !input.ids.is_empty() && input.ids.len() <= 50,
                "NOTIFICATION_INPUT_LIMIT",
            )?;
            return agent.store().desktop_mark_read(
                &input
                    .ids
                    .iter()
                    .map(|s| parse_id(s))
                    .collect::<stratide_research::Result<Vec<_>>>()?,
            );
        }
        if method == "GET"
            && (path == "/api/agent/tasks" || path.starts_with("/api/agent/tasks?before="))
        {
            let before = if let Some(raw) = path.strip_prefix("/api/agent/tasks?before=") {
                Some(parse_id(raw)?)
            } else {
                None
            };
            let mut list = agent.store().list(before)?;
            if let Some(tasks) = list["tasks"].as_array_mut() {
                for task in tasks {
                    project_retry(agent, task);
                }
            }
            return Ok(list);
        }
        if method == "POST" && path == "/api/agent/tasks" {
            // Supervised installs run the one research worker in the background
            // watch; an attached Dashboard must not queue a second manual task
            // or take the worker lock. Reads/controls stay unaffected.
            stratide_research::ensure(
                agent.is_worker(),
                "MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE",
            )?;
            stratide_research::ensure(
                app.desktop.is_none(),
                "DASHBOARD_USE_REGISTERED_RESEARCH_OPERATION",
            )?;
            let input: TaskRequest =
                serde_json::from_value(body).map_err(|_| "TASK_INPUT_INVALID")?;
            let id = if let Some(key) = &request_key {
                agent.create_once(&input, key, now)?
            } else {
                agent.create(&input, now)?
            };
            return agent.store().task(id);
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
                let mut task = agent.store().task(id)?;
                project_retry(agent, &mut task);
                return Ok(task);
            }
            if method == "POST" && parts.len() == 2 && body == json!({}) {
                match parts[1] {
                    "cancel" => agent.store().cancel(id, now)?,
                    "retry" => {
                        let task = agent.store().task(id)?;
                        stratide_research::ensure(can_consume_retry(agent, &task), "TASK_RETRY_UNAVAILABLE_IN_BACKGROUND_MODE")?;
                        agent.store().retry(id)?;
                    }
                    _ => return Err("AGENT_ROUTE_NOT_FOUND".into()),
                }
                return agent.store().task(id);
            }
        }
        Err("AGENT_ROUTE_NOT_FOUND".into())
    })();
    match result {
        Ok(data) => app.envelope(200, data, Value::Null),
        // Budget request-shape errors are client errors (400); every other
        // Agent rejection keeps the existing 409 contract.
        Err(e) => error(
            if e.0 == "AGENT_ROUTE_NOT_FOUND" || e.0 == "TASK_NOT_FOUND" {
                404
            } else if e.0 == "BUDGET_INPUT_INVALID" {
                400
            } else {
                409
            },
            &e.0,
        ),
    }
}
fn can_consume_retry(agent: &Agent, task: &Value) -> bool {
    agent.is_worker() || task["provider_id"] == stratide_research::market_research::MODEL_ID
}

fn project_retry(agent: &Agent, task: &mut Value) {
    if !can_consume_retry(agent, task) {
        task["retryable"] = json!(false);
    }
}

fn parse_id(s: &str) -> stratide_research::Result<i64> {
    let id = s.parse::<i64>().map_err(|_| "TASK_ID_INVALID")?;
    stratide_research::ensure(id > 0 && id.to_string() == s, "TASK_ID_INVALID")?;
    Ok(id)
}
