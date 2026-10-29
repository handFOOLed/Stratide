use fs2::FileExt;
use serde_json::{json, Value};
use std::{
    fs,
    io::{Read, Write},
    net::TcpStream,
    path::{Path, PathBuf},
    thread,
};
use stratided::{
    bind_local, handle,
    snapshot::{safe_json, Snapshot, FILES},
    App, Assets, Config,
};

fn fixture() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../docs/evidence/m0-pr03/sample-report")
}

fn assets(dir: &Path) -> Assets {
    fs::create_dir_all(dir.join("assets")).unwrap();
    for name in ["index.html", "assets/app.js", "assets/app.css"] {
        fs::write(dir.join(name), "test asset").unwrap();
    }
    Assets::load(dir).unwrap()
}

fn copy_report(out: &Path) {
    fs::create_dir_all(out).unwrap();
    for name in FILES {
        fs::copy(fixture().join(name), out.join(name)).unwrap();
    }
}

fn request(app: &App, assets: &Assets, path: &str) -> (u16, Value) {
    let r = app.reply(assets, "GET", path, "127.0.0.1:8710", None, 8710);
    (r.status, serde_json::from_slice(&r.body).unwrap())
}

#[test]
fn sample_fields_fills_and_unfilled_orders_are_separate() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(tmp.path());
    let app = App::load(Some(&fixture()), None);
    let (status, a) = request(&app, &assets, "/api/account");
    assert_eq!(status, 200, "{a}");
    assert_eq!(a["snapshot"]["mode"], "synthetic_test");
    assert_eq!(a["snapshot"]["source_version"], "fixture-v1");
    assert_eq!(a["snapshot"]["last_day"], "20261102");
    assert_eq!(a["data"]["nav_fen"], "992893");
    assert_eq!(a["data"]["cumulative_pnl_fen"], "-7107");
    assert_eq!(a["data"]["session_pnl_fen"], "-76");
    assert_eq!(a["snapshot"]["forward_account"], "not_available");
    let (_, f) = request(&app, &assets, "/api/fills");
    let (_, o) = request(&app, &assets, "/api/orders");
    assert_eq!(f["data"].as_array().unwrap().len(), 2);
    assert_eq!(o["data"].as_array().unwrap().len(), 3);
    assert_eq!(o["data"][2]["status"], "Rejected");
    assert_eq!(o["data"][2]["confirmed_filled_shares"], "0");
    assert!(!o["data"][2]["reason"].as_str().unwrap().is_empty());
    assert_eq!(
        request(&app, &assets, "/api/positions").1["data"],
        json!([])
    );
    assert_eq!(
        request(&app, &assets, "/api/strategies").1["data"][0]["pnl_fen"],
        Value::Null
    );
}

#[test]
fn invalid_incomplete_or_mixed_publications_fail_closed() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("assets-root"));
    let report = tmp.path().join("report");
    copy_report(&report);
    fs::write(report.join("daily.csv"), "day,nav_fen\n20261102,0\n").unwrap();
    let app = App::load(Some(&report), None);
    let (status, response) = request(&app, &assets, "/api/account");
    assert_eq!(status, 503);
    assert!(response["data"].is_null());
    assert_eq!(response["error"]["code"], "INVALID_SNAPSHOT");
    copy_report(&report);
    fs::remove_file(report.join("fills.csv")).unwrap();
    assert!(Snapshot::load(&report).is_err());
    copy_report(&report);
    fs::write(report.join("report.json"), b"{broken").unwrap();
    assert!(Snapshot::load(&report).is_err());
    copy_report(&report);
    let mut raw: Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    raw["total_return_bps"] = json!(500);
    fs::write(
        report.join("report.json"),
        serde_json::to_vec(&raw).unwrap(),
    )
    .unwrap();
    assert!(
        Snapshot::load(&report).is_err(),
        "stale/contradictory return summaries cannot be displayed"
    );
    copy_report(&report);
    let mut raw: Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    raw["mode"] = json!("forward_paper");
    fs::write(
        report.join("report.json"),
        serde_json::to_vec(&raw).unwrap(),
    )
    .unwrap();
    assert!(
        Snapshot::load(&report).is_err(),
        "observe-only must not become a forward account"
    );
}

fn write_daily_variant(report: &Path, raw: &Value) {
    fs::write(report.join("report.json"), serde_json::to_vec(raw).unwrap()).unwrap();
    let original = fs::read(fixture().join("daily.csv")).unwrap();
    let mut reader = csv::Reader::from_reader(original.as_slice());
    let header = reader.headers().unwrap();
    let mut writer = csv::Writer::from_writer(Vec::new());
    writer.write_record(header).unwrap();
    for row in raw["daily"].as_array().unwrap() {
        writer
            .write_record(header.iter().map(|name| match &row[name] {
                Value::Null => String::new(),
                Value::String(s) => s.clone(),
                v => v.to_string(),
            }))
            .unwrap();
    }
    fs::write(report.join("daily.csv"), writer.into_inner().unwrap()).unwrap();
}

#[test]
fn null_valuation_is_unavailable_and_not_zero_or_skipped_for_daily_pnl() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("assets-root"));
    let report = tmp.path().join("report");
    copy_report(&report);
    let mut raw: Value =
        serde_json::from_slice(&fs::read(report.join("report.json")).unwrap()).unwrap();
    raw["daily"][3]["nav_fen"] = Value::Null;
    raw["daily"][3]["valuation_error"] = json!("missing trusted closing mark");
    raw["ending_nav_fen"] = Value::Null;
    raw["total_return_bps"] = Value::Null;
    raw["max_daily_observation_drawdown_bps"] = Value::Null;
    write_daily_variant(&report, &raw);
    let app = App::load(Some(&report), None);
    let (status, a) = request(&app, &assets, "/api/account");
    assert_eq!(status, 200, "{a}");
    for field in ["nav_fen", "session_pnl_fen", "cumulative_pnl_fen"] {
        assert!(a["data"][field].is_null());
    }
    assert_eq!(a["snapshot"]["as_of"], "20261030");
    assert_eq!(a["snapshot"]["gaps"].as_array().unwrap().len(), 1);
    assert!(request(&app, &assets, "/api/equity").1["data"][3]["nav_fen"].is_null());
    raw["daily"][3].as_object_mut().unwrap().remove("nav_fen");
    write_daily_variant(&report, &raw);
    assert!(
        Snapshot::load(&report).is_err(),
        "missing field is not a declared valuation gap"
    );
}

#[test]
fn exact_integer_transport_and_research_never_change_account_nav() {
    assert_eq!(
        safe_json(
            json!({"fen": 9_007_199_254_740_993_i64, "quantity": 9_007_199_254_740_995_i64,
        "missing": null})
        )
        .unwrap(),
        json!({"fen":"9007199254740993", "quantity":"9007199254740995", "missing":null})
    );
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("assets"));
    let evaluation = tmp.path().join("evaluation.json");
    fs::write(
        &evaluation,
        serde_json::to_vec(&json!({"evaluation_schema":1,
        "research_evidence":"INSUFFICIENT_EVIDENCE", "engineering":"TEST_ONLY",
        "windows":{"full":{"ending_nav_fen":999999999,"net_pnl_fen":888888888}}}))
        .unwrap(),
    )
    .unwrap();
    let without = App::load(Some(&fixture()), None);
    let with = App::load(Some(&fixture()), Some(&evaluation));
    assert_eq!(
        request(&without, &assets, "/api/account"),
        request(&with, &assets, "/api/account")
    );
    let (_, r) = request(&with, &assets, "/api/research");
    assert_eq!(r["data"]["results"][0]["account_inclusion"], false);
    assert_eq!(
        r["data"]["results"][0]["windows"][0]["net_pnl_fen"],
        "888888888"
    );
}

#[test]
fn pinning_refresh_and_restart_are_readonly_even_with_busy_writer_lock() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(&tmp.path().join("assets"));
    let report = tmp.path().join("report");
    copy_report(&report);
    let lock = fs::File::create(tmp.path().join("writer.lock")).unwrap();
    lock.try_lock_exclusive().unwrap();
    let before: Vec<_> = FILES
        .iter()
        .map(|n| fs::read(report.join(n)).unwrap())
        .collect();
    let app = App::load(Some(&report), None);
    let restarted = App::load(Some(&report), None);
    assert_eq!(
        request(&app, &assets, "/api/account"),
        request(&restarted, &assets, "/api/account")
    );
    for (n, bytes) in FILES.iter().zip(before) {
        assert_eq!(fs::read(report.join(n)).unwrap(), bytes);
    }
    fs::write(report.join("daily.csv"), "incomplete new publication").unwrap();
    assert_eq!(
        request(&app, &assets, "/api/account").0,
        200,
        "browser refresh reads the pinned snapshot"
    );
    assert_eq!(
        request(&App::load(Some(&report), None), &assets, "/api/account").0,
        503
    );
}

#[test]
fn real_loopback_http_has_no_write_file_or_cross_origin_routes() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(tmp.path());
    let server = bind_local(0).unwrap();
    let addr = server.server_addr().to_ip().unwrap();
    assert!(addr.ip().is_loopback());
    assert_eq!(addr.ip().to_string(), "127.0.0.1");
    let port = addr.port();
    let cases = vec![
        ("GET", "/api/account", format!("127.0.0.1:{port}"), "", 200),
        ("POST", "/api/orders", format!("127.0.0.1:{port}"), "", 405),
        (
            "GET",
            "/api/account?path=../../secrets",
            format!("127.0.0.1:{port}"),
            "",
            404,
        ),
        (
            "GET",
            "/../../Cargo.toml",
            format!("127.0.0.1:{port}"),
            "",
            404,
        ),
        ("GET", "/api/account", "untrusted.example".into(), "", 403),
        (
            "GET",
            "/api/account",
            format!("127.0.0.1:{port}"),
            "Origin: https://untrusted.example\r\n",
            403,
        ),
    ];
    let count = cases.len();
    let task = thread::spawn(move || {
        let app = App::load(Some(&fixture()), None);
        for _ in 0..count {
            handle(&app, &assets, server.recv().unwrap(), port);
        }
    });
    for (method, path, host, origin, status) in cases {
        let mut stream = TcpStream::connect(addr).unwrap();
        stream
            .set_read_timeout(Some(std::time::Duration::from_secs(5)))
            .unwrap();
        write!(stream, "{method} {path} HTTP/1.1\r\nHost: {host}\r\n{origin}Connection: close\r\nContent-Length: 0\r\n\r\n").unwrap();
        let mut response = String::new();
        stream.read_to_string(&mut response).unwrap();
        assert!(
            response.starts_with(&format!("HTTP/1.1 {status}")),
            "{response}"
        );
        assert!(!response
            .to_ascii_lowercase()
            .contains("access-control-allow-origin"));
        assert!(response.contains("Content-Security-Policy:"));
    }
    task.join().unwrap();
    assert!(Config::parse(["--host".into(), "0.0.0.0".into()].into_iter()).is_err());
}

#[test]
fn no_input_is_an_honest_empty_state_with_healthy_service() {
    let tmp = tempfile::tempdir().unwrap();
    let assets = assets(tmp.path());
    let app = App::load(None, None);
    let (status, a) = request(&app, &assets, "/api/account");
    assert_eq!(status, 409);
    assert_eq!(a["state"], "no_input");
    assert!(a["data"].is_null());
    assert!(a["snapshot"].is_null());
    assert_eq!(
        request(&app, &assets, "/api/health").1["data"]["service"],
        "online"
    );
}
