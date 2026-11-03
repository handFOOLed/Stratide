//! Libtest-only transport/fault injection; none of these switches exist in the CLI.
use crate::{config::Settings, structured as s, InputSummary};
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    net::TcpListener,
    path::{Path, PathBuf},
    process::{Command, Stdio},
    time::{Duration, Instant},
};

pub fn fault(point: &str, input: &InputSummary) {
    let Ok(raw) = std::env::var("STRATIDE_STRUCTURED_TEST") else {
        return;
    };
    let v: Value = serde_json::from_str(&raw).unwrap();
    if v["point"] != point {
        return;
    }
    let ctx = s::context(input).unwrap();
    assert_eq!(ctx.experiment.to_str(), v["experiment"].as_str());
    fs::write(ctx.experiment.join("test-marker"), point).unwrap();
    if v["behavior"] == "kill" {
        std::process::exit(86)
    }
    let start = Instant::now();
    while !ctx.experiment.join("test-release").exists() {
        assert!(start.elapsed() < Duration::from_secs(30));
        std::thread::sleep(Duration::from_millis(10));
    }
}
pub fn transport(p: &s::Prepared) -> std::result::Result<Vec<u8>, &'static str> {
    if let Ok(raw) = std::env::var("STRATIDE_STRUCTURED_TEST") {
        let v: Value = serde_json::from_str(&raw).unwrap();
        assert_eq!(p.ctx.experiment.to_str(), v["experiment"].as_str());
        if let Some(port) = v["port"].as_u64() {
            let client = reqwest::blocking::Client::builder()
                .no_proxy()
                .redirect(reqwest::redirect::Policy::none())
                .retry(reqwest::retry::never())
                .timeout(Duration::from_millis(300))
                .build()
                .unwrap();
            return crate::provider::send(
                &client,
                &format!("http://127.0.0.1:{port}/chat/completions"),
                "synthetic-no-secret",
                &p.body,
            );
        }
    }
    Ok(p.bytes.clone())
}
fn blank() -> InputSummary {
    InputSummary {
        version: "no-input".into(),
        source_day: String::new(),
        mode: "no_input".into(),
        scopes: vec!["owner_task".into()],
        summary: json!({}),
        eod_eligible: false,
    }
}
fn write(p: &Path, v: &Value) {
    fs::create_dir_all(p.parent().unwrap()).unwrap();
    fs::write(p, serde_json::to_vec(v).unwrap()).unwrap();
}
struct Fixture {
    _temp: tempfile::TempDir,
    root: PathBuf,
    owner: PathBuf,
    ctx: s::Context,
}
fn fixture() -> Fixture {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("experiment");
    let owner = temp.path().join("owner");
    fs::create_dir_all(&owner).unwrap();
    let mut settings = Settings::fake();
    settings.models.push(s::recorded_model());
    write(
        &owner.join("settings.json"),
        &serde_json::to_value(&settings).unwrap(),
    );
    drop(crate::Agent::open(&owner, None, blank()).unwrap());
    let b = crate::risk_binding::bind_at(&root, &owner, None).unwrap();
    let model = s::recorded_model();
    let mut ctx = s::Context {
        experiment: root.clone(),
        round: 1,
        plan_sha: "a".repeat(64),
        request_sha: String::new(),
        recording_sha: String::new(),
        boundary_sha: String::new(),
        model_id: model.id.clone(),
        model_sha: model.fingerprint(),
        authority_id: b.authority_id.clone(),
    };
    let config = json!({"windows":[{"name":"dev","role":"development","start":"20211101","end":"20221230"}],
        "cost_scenarios":[{"name":"gross"},{"name":"base"},{"name":"stress"}],"max_positions":2});
    let plan = json!({"plan_sha":ctx.plan_sha,"proposer":"rust_agent_structured_v1","source_sha":"b".repeat(64),
        "source_refs":{"version_bounds":{"v1":90,"v2":360}},"config":config,"limits":{"candidates":4},
        "cloud":{"mode":"recorded_cloud","model":{"fingerprint":model.fingerprint()},"authority_id":b.authority_id,"parser_sha":"c".repeat(64)}});
    write(&root.join("plan.json"), &plan);
    write(
        &root.join("control/state.json"),
        &json!({"paused":false,"cancelled":false}),
    );
    write(&root.join("cloud/boundary.json"), &plan);
    ctx.boundary_sha = crate::hash(&fs::read(root.join("cloud/boundary.json")).unwrap());
    let request = json!({"response_source":{"kind":"rust_agent_structured_v1","task_ref":ctx.trigger(),"plan_sha":ctx.plan_sha,"round":1,
        "producer_sha":s::adapter_sha(),"model_sha":model.fingerprint(),"prompt_sha":s::prompt_sha(),"parser_sha":"c".repeat(64)},
        "research_boundary":{"source_sha":plan["source_sha"],"dataset_versions":plan["source_refs"]["version_bounds"],"windows":config["windows"],
            "cost_scenarios":config["cost_scenarios"],"max_positions":2,"candidate_limit":4,"training_knowledge":"UNKNOWN_POSSIBLY_TRAINED_ON_EXPOSED_HISTORY",
            "historical_pit_status":"NOT_VERIFIED","target":"next_session_open_ex_post_fractional_exposure"},
        "development_summary":{"mode":"synthetic_test","role":"development","start":"20211101","end":"20221230","observed_sessions":0,"universe_count":0,"missing_count":0,"prior_failure_count":0,"feedback":null},
        "grammar":s::grammar(),"output_contract":s::output_contract()});
    let wire = json!({"choices":[{"index":0,"message":{"role":"assistant","content":"{\"contract\":\"inert-recorded-output\"}"},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":4096,"completion_tokens":1024,"total_tokens":5120}});
    write(&ctx.folder().join("request.json"), &request);
    write(&ctx.folder().join("recording.json"), &wire);
    ctx.request_sha = crate::hash(&fs::read(ctx.folder().join("request.json")).unwrap());
    ctx.recording_sha = crate::hash(&fs::read(ctx.folder().join("recording.json")).unwrap());
    write(
        &ctx.folder().join("context.json"),
        &serde_json::to_value(&ctx).unwrap(),
    );
    Fixture {
        _temp: temp,
        root,
        owner,
        ctx,
    }
}
fn db(f: &Fixture) -> rusqlite::Connection {
    rusqlite::Connection::open(f.owner.join("agent.sqlite")).unwrap()
}
fn child(f: &Fixture, env: Value) -> std::process::Child {
    assert_eq!(env["experiment"].as_str(), f.root.to_str());
    Command::new(std::env::current_exe().unwrap())
        .args(["--exact", "structured_tests::process_driver", "--nocapture"])
        .env("STRATIDE_STRUCTURED_TEST", env.to_string())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap()
}
fn wait_marker(f: &Fixture) {
    let start = Instant::now();
    while !f.root.join("test-marker").exists() {
        assert!(start.elapsed() < Duration::from_secs(20));
        std::thread::sleep(Duration::from_millis(10));
    }
}
#[test]
fn process_driver() {
    let Ok(raw) = std::env::var("STRATIDE_STRUCTURED_TEST") else {
        return;
    };
    let v: Value = serde_json::from_str(&raw).unwrap();
    let result = s::execute(Path::new(v["experiment"].as_str().unwrap()), 1, false).unwrap();
    println!("STRUCTURED_RESULT={result}");
}
#[test]
fn old_grants_cannot_authorize_new_scope() {
    let mut old = Settings::fake();
    old.models[0]
        .grant
        .as_mut()
        .unwrap()
        .scopes
        .push(s::SCOPE.into());
    assert!(old.models[0]
        .authorize(&[s::SCOPE.into()], old.budget.as_ref())
        .is_err());
    let mut m = s::recorded_model();
    m.grant.as_mut().unwrap().purpose = "paper_research_v1".into();
    assert!(m
        .authorize(&[s::SCOPE.into()], old.budget.as_ref())
        .is_err());
    m = s::recorded_model();
    m.cloud.as_mut().unwrap().transport = "https".into();
    assert!(m
        .authorize(&[s::SCOPE.into()], old.budget.as_ref())
        .unwrap_err()
        .0
        .starts_with("AUTHORIZED_CLOUD_BLOCKED"));
}
#[test]
fn recorded_exact_task_shared_budget_and_no_repeat() {
    let f = fixture();
    let legacy_id = {
        let a = crate::Agent::open(&f.owner, None, blank()).unwrap();
        let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
        let request = crate::TaskRequest {
            name: "Earlier queued Owner task".into(),
            goal: "Must not be dispatched by bridge".into(),
            scope: "owner_task".into(),
            start_day: "2026-11-03".into(),
            end_day: "2026-11-03".into(),
            task_budget_micro: None,
        };
        a.store()
            .create(&settings, &request, &blank(), chrono::Utc::now(), None)
            .unwrap()
    };
    let a = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(a["status"], "completed");
    assert_eq!(a["calls"][0]["state"], "settled");
    assert_eq!(a["calls"][0]["settled_micro"], "6144");
    let result = a["result"].clone();
    assert_eq!(s::execute(&f.root, 1, false).unwrap()["result"], result);
    assert_eq!(
        db(&f)
            .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
    assert_eq!(
        db(&f)
            .query_row(
                "SELECT value FROM meta WHERE key='default_model'",
                [],
                |r| r.get::<_, String>(0)
            )
            .unwrap(),
        "fake"
    );
    assert_eq!(
        db(&f)
            .query_row("SELECT status FROM tasks WHERE id=?1", [legacy_id], |r| {
                r.get::<_, String>(0)
            })
            .unwrap(),
        "queued"
    );
}

#[test]
fn recorded_status_before_dispatch_is_not_cloud() {
    let f = fixture();
    let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
    let agent = crate::Agent::open(&f.owner, None, blank()).unwrap();
    for status in [
        agent.store().status(&settings, chrono::Utc::now()).unwrap(),
        agent.status(chrono::Utc::now()).unwrap(),
    ] {
        let model = status["models"]
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["id"] == "structured-recorded")
            .unwrap();
        assert_eq!(model["verification"], "RECORDED_ADAPTER_NOT_CLOUD");
    }
    assert_eq!(
        agent.status(chrono::Utc::now()).unwrap()["budget"]["call_count"],
        "0"
    );
}

#[test]
fn recorded_status_after_settlement_is_not_cloud() {
    let f = fixture();
    let task = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(task["status"], "completed");
    assert_eq!(task["calls"][0]["state"], "settled");
    assert_eq!(task["calls"][0]["settled_micro"], "6144");
    assert!(task["result"]["research"]["structured_research"].is_object());

    // Reopen exactly the original Owner directory after its real recorded
    // task/reserve/dispatch/settlement path; status must preserve that origin.
    let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
    let agent = crate::Agent::open(&f.owner, None, blank()).unwrap();
    let status = agent.status(chrono::Utc::now()).unwrap();
    let model = status["models"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["id"] == "structured-recorded")
        .unwrap();
    assert_eq!(model["availability"], "last_task_completed");
    assert_eq!(model["verification"], "RECORDED_ADAPTER_NOT_CLOUD");
    let stored = agent.store().status(&settings, chrono::Utc::now()).unwrap();
    let model = stored["models"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["id"] == "structured-recorded")
        .unwrap();
    assert_eq!(model["verification"], "RECORDED_ADAPTER_NOT_CLOUD");
    assert_eq!(status["budget"]["call_count"], "1");
    assert_eq!(status["budget"]["daily_settled_micro"], "6144");
    assert_eq!(status["budget"]["reserved_micro"], "0");
}
#[test]
fn insufficient_original_budget_and_revoked_grant_never_dispatch() {
    for revoked in [false, true] {
        let f = fixture();
        s::execute(&f.root, 1, true).unwrap();
        let path = f.owner.join("settings.json");
        let mut settings = Settings::load(&path).unwrap();
        if revoked {
            settings
                .models
                .last_mut()
                .unwrap()
                .grant
                .as_mut()
                .unwrap()
                .revoked = true;
        } else {
            settings.budget.as_mut().unwrap().daily_limit_micro = 1;
        }
        write(&path, &serde_json::to_value(&settings).unwrap());
        let out = s::execute(&f.root, 1, false).unwrap();
        assert_eq!(out["status"], "failed");
        assert!(out["calls"].as_array().unwrap().is_empty());
    }
}
#[test]
fn loopback_production_dispatch_and_unknown_no_retry() {
    for timeout in [false, true] {
        let f = fixture();
        let server = TcpListener::bind("127.0.0.1:0").unwrap();
        let port = server.local_addr().unwrap().port();
        let wire = fs::read(f.ctx.folder().join("recording.json")).unwrap();
        let handle = std::thread::spawn(move || {
            let (mut socket, _) = server.accept().unwrap();
            socket
                .set_read_timeout(Some(Duration::from_secs(5)))
                .unwrap();
            let mut raw = Vec::new();
            let mut buf = [0; 8192];
            loop {
                let n = socket.read(&mut buf).unwrap();
                raw.extend_from_slice(&buf[..n]);
                if let Some(end) = raw.windows(4).position(|v| v == b"\r\n\r\n") {
                    let h = String::from_utf8_lossy(&raw[..end]);
                    let len = h
                        .lines()
                        .find_map(|l| {
                            l.to_ascii_lowercase()
                                .strip_prefix("content-length:")
                                .and_then(|s| s.trim().parse::<usize>().ok())
                        })
                        .unwrap();
                    if raw.len() >= end + 4 + len {
                        let body: Value = serde_json::from_slice(&raw[end + 4..]).unwrap();
                        assert_eq!(body["response_format"]["type"], "json_object");
                        assert_eq!(body["stream"], false);
                        break;
                    }
                }
            }
            if timeout {
                std::thread::sleep(Duration::from_millis(700));
            } else {
                write!(
                    socket,
                    "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                    wire.len()
                )
                .unwrap();
                socket.write_all(&wire).unwrap();
            }
        });
        let p = child(&f, json!({"experiment":f.root,"port":port}));
        let output = p.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        handle.join().unwrap();
        let c = db(&f);
        let state: String = c
            .query_row("SELECT status FROM tasks", [], |r| r.get(0))
            .unwrap();
        assert_eq!(
            state,
            if timeout {
                "outcome_uncertain"
            } else {
                "completed"
            }
        );
        let before: i64 = c
            .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get(0))
            .unwrap();
        s::execute(&f.root, 1, false).unwrap();
        assert_eq!(
            c.query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            before
        );
        if timeout {
            assert_eq!(
                c.query_row("SELECT maximum_micro FROM calls", [], |r| r
                    .get::<_, i64>(0))
                    .unwrap(),
                81920
            );
        }
    }
}
#[test]
fn crash_after_dispatch_holds_original_reservation_across_month() {
    let f = fixture();
    let p = child(
        &f,
        json!({"experiment":f.root,"point":"after_dispatch","behavior":"kill"}),
    );
    assert_eq!(p.wait_with_output().unwrap().status.code(), Some(86));
    let task = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(task["status"], "outcome_uncertain");
    let c = db(&f);
    assert_eq!(
        c.query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        1
    );
    c.execute("UPDATE calls SET day='2026-10-31',month='2026-10'", [])
        .unwrap();
    let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
    let view = crate::budget::view(
        &c,
        settings.budget.as_ref(),
        "2026-12-01T00:00:00Z".parse().unwrap(),
    )
    .unwrap();
    assert_eq!(view["reserved_micro"], "81920");
}
#[test]
fn cancel_or_revoke_after_reserve_has_no_send_or_charge() {
    for revoke in [false, true] {
        let f = fixture();
        let p = child(
            &f,
            json!({"experiment":f.root,"point":"after_reserve","behavior":"wait"}),
        );
        wait_marker(&f);
        if revoke {
            let path = f.owner.join("settings.json");
            let mut settings = Settings::load(&path).unwrap();
            settings
                .models
                .last_mut()
                .unwrap()
                .grant
                .as_mut()
                .unwrap()
                .revoked = true;
            write(&path, &serde_json::to_value(&settings).unwrap());
        } else {
            write(
                &f.root.join("control/state.json"),
                &json!({"paused":false,"cancelled":true}),
            );
        }
        fs::write(f.root.join("test-release"), "").unwrap();
        let output = p.wait_with_output().unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
        assert_eq!(
            db(&f)
                .query_row("SELECT state FROM calls", [], |r| r.get::<_, String>(0))
                .unwrap(),
            "no_charge"
        );
        assert_eq!(
            db(&f)
                .query_row("SELECT status FROM tasks", [], |r| r.get::<_, String>(0))
                .unwrap(),
            "cancelled"
        );
    }
}

#[test]
fn paused_after_reserve_can_explicitly_resume_without_second_dispatch() {
    let f = fixture();
    let p = child(
        &f,
        json!({"experiment":f.root,"point":"after_reserve","behavior":"wait"}),
    );
    wait_marker(&f);
    write(
        &f.root.join("control/state.json"),
        &json!({"paused":true,"cancelled":false}),
    );
    fs::write(f.root.join("test-release"), "").unwrap();
    assert!(p.wait_with_output().unwrap().status.success());
    let c = db(&f);
    assert_eq!(
        c.query_row("SELECT state FROM calls", [], |r| r.get::<_, String>(0))
            .unwrap(),
        "no_charge"
    );
    write(
        &f.root.join("control/state.json"),
        &json!({"paused":false,"cancelled":false}),
    );
    let task = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(task["status"], "completed");
    assert_eq!(
        c.query_row(
            "SELECT COUNT(*) FROM calls WHERE state='settled'",
            [],
            |r| r.get::<_, i64>(0)
        )
        .unwrap(),
        1
    );
    assert_eq!(
        c.query_row("SELECT SUM(settled_micro) FROM calls", [], |r| r
            .get::<_, i64>(0))
            .unwrap(),
        6144
    );
}

#[test]
fn usage_overrun_and_duplicate_wire_keys_keep_unknown_reservation() {
    for duplicate in [false, true] {
        let mut f = fixture();
        let mut wire: Value =
            serde_json::from_slice(&fs::read(f.ctx.folder().join("recording.json")).unwrap())
                .unwrap();
        wire["usage"] =
            json!({"prompt_tokens":65537,"completion_tokens":8193,"total_tokens":73730});
        let raw = if duplicate {
            wire.to_string()
                .replacen(
                    "\"prompt_tokens\":65537",
                    "\"prompt_tokens\":1,\"prompt_tokens\":65537",
                    1,
                )
                .into_bytes()
        } else {
            serde_json::to_vec(&wire).unwrap()
        };
        fs::write(f.ctx.folder().join("recording.json"), &raw).unwrap();
        f.ctx.recording_sha = crate::hash(&raw);
        write(
            &f.ctx.folder().join("context.json"),
            &serde_json::to_value(&f.ctx).unwrap(),
        );
        let task = s::execute(&f.root, 1, false).unwrap();
        assert_eq!(task["status"], "outcome_uncertain");
        let call = &task["calls"][0];
        assert_eq!(call["state"], "outcome_uncertain");
        assert_eq!(call["settled_micro"], "0");
        s::execute(&f.root, 1, false).unwrap();
        assert_eq!(
            db(&f)
                .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            1
        );
    }
}
