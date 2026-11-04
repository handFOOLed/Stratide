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

#[test]
fn deepseek_https_cannot_accept_an_unapproved_receiver() {
    let mut model = s::recorded_model();
    model.cloud.as_mut().unwrap().transport = "https".into();
    model.model = "deepseek-flash".into();
    model.endpoint = Some("https://unapproved.example/chat/completions".into());
    assert!(
        s::validate_model(&model).is_err(),
        "an HTTPS structured model must be restricted to the approved DeepSeek receiver"
    );
}

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
                p.secret
                    .as_deref()
                    .map(|s| s.as_str())
                    .unwrap_or("synthetic-no-secret"),
                &p.body,
            );
        }
    }
    Ok(p.bytes.clone())
}
pub fn has_transport(ctx: &s::Context) -> bool {
    std::env::var("STRATIDE_STRUCTURED_TEST")
        .ok()
        .and_then(|s| serde_json::from_str::<Value>(&s).ok())
        .is_some_and(|v| {
            v["experiment"].as_str() == ctx.experiment.to_str() && v["port"].as_u64().is_some()
        })
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
    fixture_for(false)
}
fn fixture_for(real: bool) -> Fixture {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path().join("experiment");
    let owner = temp.path().join("owner");
    fs::create_dir_all(&owner).unwrap();
    let mut settings = Settings::fake();
    if real {
        settings = Settings::default();
        settings.budget = Some(crate::config::Budget {
            currency: "CNY".into(),
            timezone: "Asia/Shanghai".into(),
            daily_limit_micro: 1_000_000,
            monthly_limit_micro: 10_000_000,
        });
    } else {
        settings.models.push(s::recorded_model());
    }
    write(
        &owner.join("settings.json"),
        &serde_json::to_value(&settings).unwrap(),
    );
    drop(crate::Agent::open(&owner, None, blank()).unwrap());
    let b = crate::risk_binding::bind_at(&root, &owner, None).unwrap();
    let model = if real {
        let cfg = test_deepseek_config(temp.path());
        write(
            &temp.path().join("owner-config.json"),
            &serde_json::to_value(&cfg).unwrap(),
        );
        crate::deepseek::configure(&root, &temp.path().join("owner-config.json")).unwrap();
        cfg.model()
    } else {
        s::recorded_model()
    };
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
        "source_refs":{"version_bounds":{"v1":90,"v2":360}},"config":config,"limits":{"candidates":4,"rounds":1},
        "cloud":{"mode":if real{"authorized_cloud"}else{"recorded_cloud"},"model":{"fingerprint":model.fingerprint()},"authority_id":b.authority_id,"parser_sha":"c".repeat(64)}});
    write(&root.join("plan.json"), &plan);
    write(
        &root.join("control/state.json"),
        &json!({"paused":false,"cancelled":false}),
    );
    write(&root.join("cloud/boundary.json"), &plan);
    ctx.boundary_sha = crate::hash(&fs::read(root.join("cloud/boundary.json")).unwrap());
    let mut request = json!({"response_source":{"kind":"rust_agent_structured_v1","task_ref":ctx.trigger(),"plan_sha":ctx.plan_sha,"round":1,
        "producer_sha":s::adapter_sha(),"model_sha":model.fingerprint(),"prompt_sha":s::prompt_sha(),"parser_sha":"c".repeat(64)},
        "research_boundary":{"source_sha":plan["source_sha"],"dataset_versions":plan["source_refs"]["version_bounds"],"windows":config["windows"],
            "cost_scenarios":config["cost_scenarios"],"max_positions":2,"candidate_limit":4,"training_knowledge":"UNKNOWN_POSSIBLY_TRAINED_ON_EXPOSED_HISTORY",
            "historical_pit_status":"NOT_VERIFIED","target":"next_session_open_ex_post_fractional_exposure"},
        "development_summary":{"mode":"synthetic_test","role":"development","start":"20211101","end":"20221230","observed_sessions":0,"universe_count":0,"missing_count":0,"prior_failure_count":0,"feedback":null},
        "grammar":s::grammar(),"output_contract":s::output_contract()});
    if real {
        request = crate::deepseek::safe_request(request["response_source"].clone());
    }
    let wire = json!({"choices":[{"index":0,"message":{"role":"assistant","content":"{\"contract\":\"inert-recorded-output\"}"},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":4096,"completion_tokens":1024,"total_tokens":5120}});
    write(&ctx.folder().join("request.json"), &request);
    if !real {
        write(&ctx.folder().join("recording.json"), &wire);
    }
    ctx.request_sha = crate::hash(&fs::read(ctx.folder().join("request.json")).unwrap());
    ctx.recording_sha = if real {
        "0".repeat(64)
    } else {
        crate::hash(&fs::read(ctx.folder().join("recording.json")).unwrap())
    };
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
fn test_deepseek_config(dir: &Path) -> crate::deepseek::Config {
    let key_file = dir.join("credential.md");
    fs::write(
        &key_file,
        "# Synthetic test credential\n```text\nsk-syntheticTESTcredential1234567890\n```\n",
    )
    .unwrap();
    // Match the Python fixture's margin while WSL synchronizes its clock.
    // Production authorization and price-time checks remain unchanged.
    let now = chrono::Utc::now() - chrono::Duration::minutes(5);
    crate::deepseek::Config {
        version: 1,
        key_file,
        grant_version: "deepseek-synthetic-grant-v1".into(),
        synthetic_only: true,
        provider_terms_reviewed: true,
        authorized_at: now.to_rfc3339(),
        price_reviewed_at: now.to_rfc3339(),
        price_valid_until: (now + chrono::Duration::days(1)).to_rfc3339(),
        max_call_micro: 100000,
    }
}
fn real_wire(content: &str) -> Value {
    json!({"id":"synthetic-wire","object":"chat.completion","created":1793084842,
        "model":"deepseek-flash","system_fingerprint":"synthetic-fp-1",
        "choices":[{"index":0,"logprobs":null,"message":{"role":"assistant","content":content,"reasoning_content":null},"finish_reason":"stop"}],
        "usage":{"prompt_tokens":4096,"completion_tokens":1024,"total_tokens":5120,
            "prompt_cache_hit_tokens":1000,"prompt_cache_miss_tokens":3096,
            "prompt_tokens_details":{"cached_tokens":1000},"completion_tokens_details":{"reasoning_tokens":0}}})
}
fn enable_real(f: &Fixture) {
    crate::deepseek::enable(&f.root, "APPROVE_ONE_SYNTHETIC_DEEPSEEK_REQUEST").unwrap();
}
fn one_real_loopback(
    f: &Fixture,
    wire: Value,
    status: u16,
    disconnect: bool,
    fault: Option<&str>,
) -> Value {
    let server = TcpListener::bind("127.0.0.1:0").unwrap();
    let port = server.local_addr().unwrap().port();
    server.set_nonblocking(true).unwrap();
    let handle = std::thread::spawn(move || {
        let start = Instant::now();
        let (mut socket, _) = loop {
            if let Ok(s) = server.accept() {
                break s;
            }
            assert!(
                start.elapsed() < Duration::from_secs(10),
                "loopback never received request"
            );
            std::thread::sleep(Duration::from_millis(5));
        };
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut raw = Vec::new();
        let mut buf = [0; 8192];
        let body = loop {
            let n = socket.read(&mut buf).unwrap();
            assert!(n > 0);
            raw.extend_from_slice(&buf[..n]);
            if let Some(end) = raw.windows(4).position(|v| v == b"\r\n\r\n") {
                let headers = String::from_utf8_lossy(&raw[..end]);
                let len = headers
                    .lines()
                    .find_map(|l| {
                        l.to_ascii_lowercase()
                            .strip_prefix("content-length:")
                            .and_then(|s| s.trim().parse::<usize>().ok())
                    })
                    .unwrap();
                if raw.len() >= end + 4 + len {
                    assert!(headers.contains("Bearer sk-syntheticTESTcredential1234567890"));
                    break serde_json::from_slice::<Value>(&raw[end + 4..]).unwrap();
                }
            }
        };
        assert_eq!(body["model"], "deepseek-flash");
        assert_eq!(body["thinking"]["type"], "disabled");
        assert!(body.get("max_completion_tokens").is_none());
        assert_eq!(body["max_tokens"], 4096);
        assert!(body.get("tools").is_none());
        assert!(body.get("functions").is_none());
        let user: Value =
            serde_json::from_str(body["messages"][1]["content"].as_str().unwrap()).unwrap();
        assert_eq!(
            user,
            crate::deepseek::safe_request(user["response_source"].clone())
        );
        if status == 0 {
            std::thread::sleep(Duration::from_millis(700));
        } else if !disconnect {
            let wire = wire.to_string();
            write!(
                socket,
                "HTTP/1.1 {status} Test\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",
                wire.len()
            )
            .unwrap();
            socket.write_all(wire.as_bytes()).unwrap();
        }
        body
    });
    let mut env = json!({"experiment":f.root,"port":port});
    if let Some(point) = fault {
        env["point"] = json!(point);
        env["behavior"] = json!("wait");
    }
    let output = child(f, env).wait_with_output().unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let body = handle.join().unwrap();
    assert!(
        !String::from_utf8_lossy(&output.stdout).contains("sk-syntheticTESTcredential1234567890")
    );
    assert_eq!(
        db(f)
            .query_row(
                "SELECT COUNT(*) FROM calls WHERE state!='no_charge'",
                [],
                |r| r.get::<_, i64>(0)
            )
            .unwrap(),
        1
    );
    body
}

#[test]
fn deepseek_default_off_metadata_only_preflight_and_peak_price() {
    let f = fixture_for(true);
    let before = fs::read(f.owner.join("settings.json")).unwrap();
    let view = crate::deepseek::preflight(&f.root).unwrap();
    assert_eq!(view["enabled"], false);
    assert_eq!(view["maximum_micro"], 98304);
    assert!(!view.to_string().contains("credential.md"));
    assert!(!view.to_string().contains("sk-"));
    // An unreadable-format key proves authorization fails before content parsing.
    fs::write(
        f._temp.path().join("credential.md"),
        "deliberately invalid credential content",
    )
    .unwrap();
    assert_eq!(
        s::execute(&f.root, 1, false).unwrap_err().0,
        "DEEPSEEK_DISABLED_OR_ONCE_CONSUMED"
    );
    assert_eq!(
        db(&f)
            .query_row("SELECT COUNT(*) FROM tasks", [], |r| r.get::<_, i64>(0))
            .unwrap(),
        0
    );
    assert_eq!(before, fs::read(f.owner.join("settings.json")).unwrap());
    let mut m = Settings::load(&f.owner.join("settings.json"))
        .unwrap()
        .models
        .remove(0);
    m.model = "ds4.1flash".into();
    assert!(s::validate_model(&m).is_err());
    m.model = "deepseek-flash".into();
    m.price.as_mut().unwrap().input_micro_per_million = 1_000_000;
    assert!(m
        .authorize(
            &[s::SCOPE.into()],
            Settings::load(&f.owner.join("settings.json"))
                .unwrap()
                .budget
                .as_ref()
        )
        .is_err());
}
#[test]
fn deepseek_cny_usage_is_estimate_maximum_held_once_consumed_and_not_real_observed() {
    let f = fixture_for(true);
    enable_real(&f);
    one_real_loopback(
        &f,
        real_wire("{\"refusal\":\"synthetic\"}"),
        200,
        false,
        None,
    );
    let task = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(task["status"], "completed");
    assert_eq!(task["calls"][0]["state"], "usage_received");
    assert_eq!(task["calls"][0]["usage_micro"], "16384");
    assert_eq!(task["calls"][0]["settled_micro"], "0");
    let result = &task["result"]["research"]["structured_research"]["provider_metadata"];
    assert_eq!(result["verification"], "LOOPBACK_NOT_REAL_PROVIDER");
    assert_eq!(result["prompt_cache_miss_tokens"], 3096);
    let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
    let a = crate::Agent::open(&f.owner, None, blank()).unwrap();
    assert_eq!(
        a.status(chrono::Utc::now()).unwrap()["models"][0]["verification"],
        "REAL_PROVIDER_NOT_VERIFIED"
    );
    assert_eq!(
        crate::budget::view(&db(&f), settings.budget.as_ref(), chrono::Utc::now()).unwrap()
            ["reserved_micro"],
        "98304"
    );
    drop(a);
    assert_eq!(
        crate::deepseek::preflight(&f.root).unwrap()["enabled"],
        false
    );
    crate::deepseek::disable(&f.root).unwrap();
    assert_eq!(
        s::execute(&f.root, 1, false).unwrap()["calls"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn deepseek_blank_truncated_missing_usage_forgery_http_and_disconnect_no_retry() {
    for variant in [
        "blank",
        "length",
        "missing_usage",
        "model",
        "reasoning",
        "usage_overrun",
        "secret",
        "429",
        "500",
        "disconnect",
        "timeout",
    ] {
        let f = fixture_for(true);
        enable_real(&f);
        let mut wire = real_wire("{}");
        match variant {
            "blank" => wire["choices"][0]["message"]["content"] = json!("   "),
            "length" => wire["choices"][0]["finish_reason"] = json!("length"),
            "missing_usage" => {
                wire.as_object_mut().unwrap().remove("usage");
            }
            "model" => wire["model"] = json!("forged-model"),
            "reasoning" => {
                wire["choices"][0]["message"]["reasoning_content"] = json!("unexpected reasoning")
            }
            "usage_overrun" => {
                wire["usage"]["completion_tokens"] = json!(4097);
                wire["usage"]["total_tokens"] = json!(8193);
            }
            "secret" => {
                wire["choices"][0]["message"]["content"] =
                    json!("sk-syntheticTESTcredential1234567890")
            }
            _ => {}
        }
        one_real_loopback(
            &f,
            wire,
            if variant == "timeout" {
                0
            } else {
                variant.parse::<u16>().unwrap_or(200)
            },
            variant == "disconnect",
            None,
        );
        let task = s::execute(&f.root, 1, false).unwrap();
        assert_eq!(task["calls"].as_array().unwrap().len(), 1);
        assert_eq!(task["calls"][0]["maximum_micro"], "98304");
        assert_eq!(task["calls"][0]["settled_micro"], "0");
        assert_eq!(
            task["status"],
            if matches!(variant, "blank" | "length") {
                "completed"
            } else {
                "outcome_uncertain"
            },
            "{variant}"
        );
        if variant == "secret" {
            assert!(!task
                .to_string()
                .contains("sk-syntheticTESTcredential1234567890"));
        }
        let c = db(&f);
        c.execute("UPDATE calls SET day='2026-10-31',month='2026-10'", [])
            .unwrap();
        let settings = Settings::load(&f.owner.join("settings.json")).unwrap();
        assert_eq!(
            crate::budget::view(
                &c,
                settings.budget.as_ref(),
                "2026-12-01T00:00:00Z".parse().unwrap()
            )
            .unwrap()["reserved_micro"],
            "98304"
        );
    }
}
#[test]
fn deepseek_disabled_revoked_cancelled_or_mutated_after_reserve_cannot_dispatch() {
    for variant in [
        "disabled",
        "revoked",
        "cancelled",
        "paused",
        "budget",
        "request",
    ] {
        let f = fixture_for(true);
        enable_real(&f);
        // Port 1 exists only as a libtest preparation override; no send should reach it.
        let p = child(
            &f,
            json!({"experiment":f.root,"port":1,"point":"after_reserve","behavior":"wait"}),
        );
        wait_marker(&f);
        match variant {
            "disabled" => {
                crate::deepseek::disable(&f.root).unwrap();
            }
            "cancelled" => write(
                &f.root.join("control/state.json"),
                &json!({"paused":false,"cancelled":true}),
            ),
            "paused" => {
                db(&f)
                    .execute("UPDATE meta SET value='true' WHERE key='paused'", [])
                    .unwrap();
            }
            "request" => {
                fs::write(f.ctx.folder().join("request.json"), "{}").unwrap();
            }
            _ => {
                let path = f.owner.join("settings.json");
                let mut settings = Settings::load(&path).unwrap();
                if variant == "revoked" {
                    settings.models[0].grant.as_mut().unwrap().revoked = true;
                } else {
                    settings.budget.as_mut().unwrap().daily_limit_micro = 1;
                }
                write(&path, &serde_json::to_value(settings).unwrap());
            }
        }
        fs::write(f.root.join("test-release"), "").unwrap();
        assert!(p.wait_with_output().unwrap().status.success());
        assert_eq!(
            db(&f)
                .query_row("SELECT state FROM calls", [], |r| r.get::<_, String>(0))
                .unwrap(),
            "no_charge",
            "{variant}"
        );
    }
}
#[test]
fn deepseek_crash_dispatch_consumes_permit_and_preserves_unknown_on_restart() {
    let f = fixture_for(true);
    enable_real(&f);
    let p = child(
        &f,
        json!({"experiment":f.root,"port":1,"point":"after_dispatch","behavior":"kill"}),
    );
    assert_eq!(p.wait_with_output().unwrap().status.code(), Some(86));
    let task = s::execute(&f.root, 1, false).unwrap();
    assert_eq!(task["status"], "outcome_uncertain");
    assert_eq!(task["calls"][0]["maximum_micro"], "98304");
    assert_eq!(
        crate::deepseek::preflight(&f.root).unwrap()["enabled"],
        false
    );
    assert_eq!(
        s::execute(&f.root, 1, false).unwrap()["calls"]
            .as_array()
            .unwrap()
            .len(),
        1
    );
}
#[test]
fn deepseek_key_parser_rejects_multiple_other_credentials_and_placeholders() {
    for invalid in [
        "",
        "sk-placeholder01234567890123456789",
        "sk-syntheticTESTcredential1234567890\nsk-syntheticSECONDcredential1234567890",
        "sk-syntheticTESTcredential1234567890\nOTHER_TOKEN: confidential",
        "# sk-syntheticTESTcredential1234567890",
    ] {
        assert!(crate::deepseek::parse_key(invalid).is_err());
    }
    assert!(crate::deepseek::parse_key("API Key: `sk-syntheticTESTcredential1234567890`").is_ok());
}
#[test]
fn deepseek_remaining_budget_and_synthetic_scope_checked_before_key_read() {
    for variant in ["budget", "payload", "parser"] {
        let mut f = fixture_for(true);
        enable_real(&f);
        fs::write(
            f._temp.path().join("credential.md"),
            "invalid key that must never be parsed",
        )
        .unwrap();
        if variant == "budget" {
            let p = f.owner.join("settings.json");
            let mut settings = Settings::load(&p).unwrap();
            settings.budget.as_mut().unwrap().daily_limit_micro = 98303;
            write(&p, &serde_json::to_value(settings).unwrap());
        } else {
            let request = f.ctx.folder().join("request.json");
            let mut value: Value = serde_json::from_slice(&fs::read(&request).unwrap()).unwrap();
            if variant == "payload" {
                value["development_summary"]["account_position"] = json!(100);
            } else {
                value["response_source"]["parser_sha"] = json!("unapproved instruction");
                let path = f.root.join("cloud/boundary.json");
                let mut plan: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
                plan["cloud"]["parser_sha"] = json!("unapproved instruction");
                write(&path, &plan);
                f.ctx.boundary_sha = crate::hash(&fs::read(path).unwrap());
            }
            write(&request, &value);
            f.ctx.request_sha = crate::hash(&fs::read(request).unwrap());
            write(
                &f.ctx.folder().join("context.json"),
                &serde_json::to_value(&f.ctx).unwrap(),
            );
        }
        let error = s::execute(&f.root, 1, false).unwrap_err().0;
        assert!(
            !error.contains("KEY_FILE"),
            "authorization must precede key parsing: {error}"
        );
        assert!(
            error.contains("BUDGET")
                || error.contains("SYNTHETIC")
                || error.contains("SYNTHETIC_ROUND"),
            "{error}"
        );
        assert_eq!(
            db(&f)
                .query_row("SELECT COUNT(*) FROM calls", [], |r| r.get::<_, i64>(0))
                .unwrap(),
            0
        );
    }
}
#[test]
fn deepseek_key_source_must_be_untracked_and_ignored_without_content_read() {
    let temp = tempfile::tempdir().unwrap();
    let root = temp.path();
    assert!(Command::new("git")
        .args(["init", "--quiet"])
        .arg(root)
        .status()
        .unwrap()
        .success());
    let key = root.join("credential.md");
    fs::write(&key, "not even a parseable key").unwrap();
    assert!(crate::deepseek::key_metadata(&key).is_err());
    fs::write(root.join(".gitignore"), "/credential.md\n").unwrap();
    crate::deepseek::key_metadata(&key).unwrap();
    assert!(Command::new("git")
        .arg("-C")
        .arg(root)
        .args(["add", "--force", "--", "credential.md"])
        .status()
        .unwrap()
        .success());
    assert_eq!(
        crate::deepseek::key_metadata(&key).unwrap_err().0,
        "DEEPSEEK_KEY_FILE_TRACKED_REMOVE_FROM_GIT_WITH_OWNER"
    );
}
#[test]
fn deepseek_expired_price_or_tst_currency_cannot_authorize_real_route() {
    let temp = tempfile::tempdir().unwrap();
    let mut cfg = test_deepseek_config(temp.path());
    cfg.price_valid_until = "2020-01-01T00:00:00Z".into();
    let m = cfg.model();
    assert!(m
        .authorize(&[s::SCOPE.into()], Settings::fake().budget.as_ref())
        .is_err());
    let f = fixture_for(true);
    let b = crate::risk_binding::read_at(&f.root).unwrap();
    write(
        &temp.path().join("expired.json"),
        &serde_json::to_value(cfg).unwrap(),
    );
    assert!(
        crate::deepseek::configure(&f.root, &temp.path().join("expired.json"))
            .unwrap_err()
            .0
            .contains("PRICE_EXPIRED")
    );
    assert_eq!(
        Settings::load(&b.settings_path)
            .unwrap()
            .budget
            .unwrap()
            .currency,
        "CNY"
    );
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
fn process_driver_init_cny() {
    let Ok(raw) = std::env::var("STRATIDE_STRUCTURED_TEST") else {
        return;
    };
    let v: Value = serde_json::from_str(&raw).unwrap();
    let Some(owner) = v["initialize_cny"].as_str() else {
        return;
    };
    let owner = Path::new(owner);
    assert!(!owner.exists());
    let settings = Settings {
        budget: Some(crate::config::Budget {
            currency: "CNY".into(),
            timezone: "Asia/Shanghai".into(),
            daily_limit_micro: 1_000_000,
            monthly_limit_micro: 10_000_000,
        }),
        ..Settings::default()
    };
    write(
        &owner.join("settings.json"),
        &serde_json::to_value(settings).unwrap(),
    );
    drop(crate::Agent::open(owner, None, blank()).unwrap());
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
        .starts_with("DEEPSEEK_FIXED_MODEL_ENDPOINT_REQUIRED"));
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
