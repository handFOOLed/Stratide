//! Regression: `/api/health` must stay responsive while runtime status refresh is slow.
use std::{
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    path::Path,
    sync::Arc,
    thread,
    time::{Duration, Instant},
};
use stratided::{bind_local, handle_with_agent, App, Assets};

fn assets(dir: &Path) -> Assets {
    std::fs::create_dir_all(dir.join("assets")).unwrap();
    for name in ["index.html", "assets/app.js", "assets/app.css"] {
        std::fs::write(dir.join(name), "test asset").unwrap();
    }
    Assets::load(dir).unwrap()
}

fn runtime_home(root: &Path) -> std::path::PathBuf {
    let home = root.join("runtime-home");
    std::fs::create_dir_all(home.join("runtime")).unwrap();
    std::fs::create_dir_all(home.join("data/state")).unwrap();
    std::fs::write(
        home.join("runtime.json"),
        br#"{"schema_version":1,"port":8710,"data_root":"data","python":null}"#,
    )
    .unwrap();
    home
}

fn http(addr: SocketAddr, raw: &str) -> (u16, Duration) {
    let started = Instant::now();
    let mut stream = TcpStream::connect(addr).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .unwrap();
    stream.write_all(raw.as_bytes()).unwrap();
    let mut response = String::new();
    stream.read_to_string(&mut response).unwrap();
    let status = response
        .lines()
        .next()
        .and_then(|line| line.split_whitespace().nth(1))
        .and_then(|code| code.parse().ok())
        .unwrap_or(0);
    (status, started.elapsed())
}

#[test]
fn health_stays_fast_while_runtime_status_triggers_slow_background_refresh() {
    let tmp = tempfile::tempdir().unwrap();
    let _slow = RestoreEnv::push("STRATIDE_DIAGNOSTICS_SLEEP_MS", "1500");
    let assets = assets(&tmp.path().join("static"));
    let mut app = App::load(None, None);
    app.runtime_home = Some(runtime_home(tmp.path()));
    let app = Arc::new(app);
    let assets = Arc::new(assets);
    let server = bind_local(0).unwrap();
    let addr = server.server_addr().to_ip().unwrap();
    let port = addr.port();
    let host = format!("127.0.0.1:{port}");
    let listener = thread::spawn(move || {
        for _ in 0..4 {
            let app = Arc::clone(&app);
            let assets = Arc::clone(&assets);
            let req = server.recv().unwrap();
            thread::spawn(move || handle_with_agent(&app, &assets, req, port, None));
        }
    });
    let status_req = format!(
        "GET /api/runtime/status HTTP/1.1\r\nHost: {host}\r\nOrigin: http://{host}\r\nConnection: close\r\n\r\n"
    );
    let health_req = format!("GET /api/health HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n");
    let (status_code, status_elapsed) = http(addr, &status_req);
    assert_eq!(status_code, 200, "status should succeed");
    assert!(
        status_elapsed < Duration::from_millis(800),
        "status GET must not wait for slow diagnostics (got {:?})",
        status_elapsed
    );
    let (health_code, health_elapsed) = http(addr, &health_req);
    assert_eq!(health_code, 200, "health should succeed");
    assert!(
        health_elapsed < Duration::from_millis(800),
        "health must stay responsive during background refresh (got {:?})",
        health_elapsed
    );
    listener.join().unwrap();
}

struct RestoreEnv {
    key: &'static str,
    previous: Option<String>,
}

impl RestoreEnv {
    fn push(key: &'static str, value: &str) -> Self {
        let previous = std::env::var(key).ok();
        std::env::set_var(key, value);
        Self { key, previous }
    }
}

impl Drop for RestoreEnv {
    fn drop(&mut self) {
        match &self.previous {
            Some(value) => std::env::set_var(self.key, value),
            None => std::env::remove_var(self.key),
        }
    }
}
