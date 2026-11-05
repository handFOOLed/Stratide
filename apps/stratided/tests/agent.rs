use serde_json::Value;
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::{Path, PathBuf},
    thread,
    time::Duration,
};
use stratide_research::{config::Settings, Agent};
use stratided::{bind_local, handle_with_agent, App, Assets};

#[test]
fn eod_snapshot_source_is_opt_in_and_cannot_silently_mix_report_dates_or_modes() {
    let parse = |args: &[&str]| stratided::Config::parse(args.iter().map(|s| s.to_string()));
    assert!(parse(&[]).unwrap().agent_eod_store.is_none());
    assert!(parse(&["--agent-eod-store", "demo"]).is_err());
    assert!(parse(&[
        "--agent-dir",
        "state/new-agent",
        "--agent-eod-store",
        "../escape"
    ])
    .is_err());
    for old in ["--report-dir", "--evaluation-file"] {
        assert!(parse(&[
            "--agent-dir",
            "state/new-agent",
            "--agent-eod-store",
            "demo",
            old,
            "old-source"
        ])
        .is_err());
    }
    assert_eq!(
        parse(&[
            "--agent-dir",
            "state/new-agent",
            "--agent-eod-store",
            "demo"
        ])
        .unwrap()
        .agent_eod_store
        .as_deref(),
        Some("demo")
    );
}

#[test]
fn agent_observer_is_a_value_less_config_flag_that_defaults_off() {
    let parse = |args: &[&str]| stratided::Config::parse(args.iter().map(|s| s.to_string()));
    assert!(!parse(&[]).unwrap().agent_observer);
    assert!(parse(&["--agent-observer"]).unwrap().agent_observer);
    assert!(parse(&["--agent-observer", "--agent-observer"]).is_err());
    assert!(parse(&["--agent-observer=1"]).is_err());
    assert_eq!(
        parse(&["--port", "8711", "--agent-observer"])
            .unwrap()
            .port,
        8711
    );
}

fn assets(dir: &Path) -> Assets {
    std::fs::create_dir_all(dir.join("assets")).unwrap();
    for name in ["index.html", "assets/app.js", "assets/app.css"] {
        std::fs::write(dir.join(name), "test asset").unwrap();
    }
    Assets::load(dir).unwrap()
}

fn agent_dir(root: &Path) -> PathBuf {
    let dir = root.join("agent");
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("settings.json"),
        serde_json::to_vec(&Settings::fake()).unwrap(),
    )
    .unwrap();
    dir
}

fn http(addr: SocketAddr, raw: &str) -> String {
    let mut stream = TcpStream::connect(addr).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    stream.write_all(raw.as_bytes()).unwrap();
    let mut response = String::new();
    stream.read_to_string(&mut response).unwrap();
    response
}

fn post_request(host: &str, path: &str, body: &str) -> String {
    format!(
        "POST {path} HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    )
}

#[test]
fn observer_dashboard_serves_status_and_controls_but_rejects_manual_tasks() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("static"));
    let app = App::load(None, None);
    let dir = agent_dir(tmp.path());
    let agent = Agent::attach(&dir, None, App::load(None, None).agent_summary()).unwrap();
    let server = bind_local(0).unwrap();
    let addr = server.server_addr().to_ip().unwrap();
    let port = addr.port();
    let host = format!("127.0.0.1:{port}");
    let handler = thread::spawn(move || {
        for _ in 0..3 {
            handle_with_agent(&app, &assets, server.recv().unwrap(), port, Some(&agent));
        }
    });
    let status = http(
        addr,
        &format!("GET /api/agent/status HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"),
    );
    let task_body = r#"{"name":"manual","goal":"goals","scope":"owner","start_day":"2026-11-04","end_day":"2026-11-04","task_budget_micro":null}"#;
    let task = http(addr, &post_request(&host, "/api/agent/tasks", task_body));
    let pause = http(
        addr,
        &post_request(&host, "/api/agent/control", r#"{"action":"pause"}"#),
    );
    handler.join().unwrap();
    assert!(status.starts_with("HTTP/1.1 200"), "{status}");
    assert!(
        status.contains("\"manual_research_available\":false"),
        "{status}"
    );
    assert!(task.starts_with("HTTP/1.1 409"), "{task}");
    assert!(
        task.contains("MANUAL_RESEARCH_UNAVAILABLE_IN_BACKGROUND_MODE"),
        "{task}"
    );
    assert!(pause.starts_with("HTTP/1.1 200"), "{pause}");
}

#[test]
fn worker_agent_reports_manual_research_available() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("static"));
    let app = App::load(None, None);
    let dir = agent_dir(tmp.path());
    let agent = Agent::open(&dir, None, App::load(None, None).agent_summary()).unwrap();
    let server = bind_local(0).unwrap();
    let addr = server.server_addr().to_ip().unwrap();
    let port = addr.port();
    let host = format!("127.0.0.1:{port}");
    let handler = thread::spawn(move || {
        handle_with_agent(&app, &assets, server.recv().unwrap(), port, Some(&agent));
    });
    let status = http(
        addr,
        &format!("GET /api/agent/status HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n"),
    );
    handler.join().unwrap();
    assert!(status.starts_with("HTTP/1.1 200"), "{status}");
    assert!(
        status.contains("\"manual_research_available\":true"),
        "{status}"
    );
    assert!(status.contains("\"dashboard_mode\":\"worker\""), "{status}");
}

#[test]
fn cloud_summary_is_a_versioned_projection_without_account_identity_cash_or_private_strategy_payloads(
) {
    let report =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../docs/evidence/m0-pr03/sample-report");
    let summary = App::load(Some(&report), None).agent_summary();
    assert_eq!(summary.mode, "synthetic_test");
    assert!(!summary.eod_eligible);
    assert!(summary.version.starts_with("paper-summary-v1:"));
    assert_eq!(summary.summary["simulated_fills"], "2");
    for field in [
        "account_id",
        "cash_fen",
        "positions",
        "lots",
        "orders",
        "fills",
        "group_id",
        "strategy_id",
        "events",
        "risk",
        "api_key",
        "holdout_answers",
    ] {
        assert_eq!(
            summary.summary.get(field),
            None,
            "field must not enter cloud context: {field}"
        );
    }
    assert_eq!(
        summary.summary["mode"],
        Value::String("synthetic_test".into())
    );
    assert_eq!(
        App::load(None, None).agent_summary().scopes,
        vec!["owner_task"]
    );
}
