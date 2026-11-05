use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};
use stratide_runtime::state::{ChildState, ExitState, SupervisorState};
use stratide_runtime::{autostart, health, win, Layout};

struct Dashboard {
    child: Option<Child>,
    pid: u32,
    started_at: String,
    instance_id: String,
    last_exit: Option<ExitState>,
}

struct Watch {
    child: Option<Child>,
    pid: u32,
    started_at: String,
    last_exit: Option<ExitState>,
    next_start: Instant,
    restarts: u32,
}

struct Supervisor {
    layout: Layout,
    job: win::Job,
    instance_id: String,
    started_at: String,
    port: u16,
    token: String,
    previous: Option<SupervisorState>,
    dashboard: Option<Dashboard>,
    watch: Option<Watch>,
    dashboard_next: Instant,
    dashboard_failures: u32,
    dashboard_healthy: bool,
    reason: String,
    status: String,
    autostart_enabled: bool,
    last_publish: Instant,
}

pub fn run() -> Result<i32, String> {
    let layout = Layout::load()?;
    layout.ensure_directories()?;
    let lock_path = layout.runtime.join("supervisor.lock");
    let lock = std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .open(&lock_path)
        .map_err(|error| format!("SUPERVISOR_LOCK_UNAVAILABLE: {error}"))?;
    match lock.try_lock() {
        Ok(()) => {}
        Err(std::fs::TryLockError::WouldBlock) => return Ok(0),
        Err(std::fs::TryLockError::Error(error)) => {
            return Err(format!("SUPERVISOR_LOCK_FAILED: {error}"))
        }
    }
    layout.clear_stop_request();
    let config = layout.config()?;
    let token = layout.runtime_token()?;
    let previous = SupervisorState::read(&layout.state_path());
    let job = win::Job::create().map_err(|error| format!("WINDOWS_JOB_UNAVAILABLE: {error}"))?;
    let started_at = stratide_runtime::timestamp();
    let mut supervisor = Supervisor {
        layout,
        job,
        instance_id: stratide_runtime::random_hex(8)?,
        started_at,
        port: config.port,
        token,
        previous,
        dashboard: None,
        watch: None,
        dashboard_next: Instant::now(),
        dashboard_failures: 0,
        dashboard_healthy: false,
        reason: "STARTING".into(),
        status: "STARTING".into(),
        autostart_enabled: autostart::status().enabled,
        last_publish: Instant::now() - Duration::from_secs(60),
    };
    log(&supervisor.layout, "supervisor starting");
    supervisor.publish()?;
    let outcome = supervisor.run_loop();
    let _ = lock.unlock();
    outcome
}

impl Supervisor {
    fn run_loop(&mut self) -> Result<i32, String> {
        let mut last_autostart_check = Instant::now();
        loop {
            if self.layout.read_stop_request() {
                self.stop()?;
                log(&self.layout, "supervisor stopped by request");
                return Ok(0);
            }
            if last_autostart_check.elapsed() > Duration::from_secs(60) {
                self.autostart_enabled = autostart::status().enabled;
                last_autostart_check = Instant::now();
            }
            self.ensure_dashboard()?;
            self.ensure_watch()?;
            self.publish()?;
            std::thread::sleep(Duration::from_millis(750));
        }
    }

    fn ensure_dashboard(&mut self) -> Result<(), String> {
        let exited = self.poll_dashboard_exit();
        if let Some(exit) = exited {
            self.dashboard_failures += 1;
            self.dashboard_healthy = false;
            self.dashboard_next = Instant::now() + backoff(self.dashboard_failures, 10);
            self.reason = "DASHBOARD_EXITED".into();
            log(
                &self.layout,
                &format!("dashboard exited code={:?}; retry scheduled", exit.code),
            );
        }
        let has_child = self
            .dashboard
            .as_ref()
            .and_then(|dashboard| dashboard.child.as_ref())
            .is_some();
        if has_child {
            match health::probe(self.port) {
                Ok(data) => {
                    if let Some(dashboard) = self.dashboard.as_mut() {
                        dashboard.instance_id = data.instance_id;
                    }
                    self.dashboard_healthy = true;
                    self.dashboard_failures = 0;
                    if [
                        "DASHBOARD_EXITED",
                        "DASHBOARD_START_FAILED",
                        "DASHBOARD_STARTING",
                    ]
                    .contains(&self.reason.as_str())
                    {
                        self.reason = "OK".into();
                    }
                }
                Err(_) => {
                    self.dashboard_healthy = false;
                }
            }
            return Ok(());
        }
        if self
            .dashboard
            .as_ref()
            .is_some_and(|dashboard| dashboard.pid != 0)
        {
            // Adoption of an instance started by the previous supervisor run.
            match health::probe(self.port) {
                Ok(data)
                    if self
                        .dashboard
                        .as_ref()
                        .is_some_and(|dashboard| dashboard.instance_id == data.instance_id) =>
                {
                    self.dashboard_healthy = true;
                    return Ok(());
                }
                _ => {
                    self.dashboard = None;
                    self.dashboard_healthy = false;
                }
            }
        }
        match health::probe(self.port) {
            Ok(data) => {
                let previous_match = self
                    .previous
                    .as_ref()
                    .and_then(|previous| previous.dashboard.as_ref())
                    .is_some_and(|dashboard| {
                        dashboard.instance_id.as_deref() == Some(data.instance_id.as_str())
                    });
                if previous_match {
                    let started_at = self
                        .previous
                        .as_ref()
                        .and_then(|previous| previous.dashboard.as_ref())
                        .map(|dashboard| dashboard.started_at.clone())
                        .unwrap_or_else(stratide_runtime::timestamp);
                    let pid = data
                        .process_id
                        .parse::<u32>()
                        .map_err(|_| "SERVICE_PID_INVALID")?;
                    self.dashboard = Some(Dashboard {
                        child: None,
                        pid,
                        started_at,
                        instance_id: data.instance_id,
                        last_exit: None,
                    });
                    self.dashboard_healthy = true;
                    self.reason = "OK".into();
                    log(
                        &self.layout,
                        "adopted the existing managed dashboard instance",
                    );
                } else {
                    self.dashboard_healthy = false;
                    self.reason = "EXTERNAL_STRATIDE_INSTANCE".into();
                }
            }
            Err(_) if !health::port_available(self.port) => {
                self.dashboard_healthy = false;
                self.reason = "PORT_IN_USE_BY_OTHER_APPLICATION".into();
            }
            Err(_) if Instant::now() >= self.dashboard_next => {
                self.start_dashboard()?;
            }
            Err(_) => {}
        }
        Ok(())
    }

    fn poll_dashboard_exit(&mut self) -> Option<ExitState> {
        let dashboard = self.dashboard.as_mut()?;
        let child = dashboard.child.as_mut()?;
        let outcome = child.try_wait();
        match outcome {
            Ok(Some(status)) => {
                let exit = ExitState {
                    code: status.code(),
                    at: stratide_runtime::timestamp(),
                };
                dashboard.last_exit = Some(exit.clone());
                dashboard.child = None;
                Some(exit)
            }
            Ok(None) => None,
            Err(_) => {
                let exit = ExitState {
                    code: None,
                    at: stratide_runtime::timestamp(),
                };
                dashboard.last_exit = Some(exit.clone());
                dashboard.child = None;
                Some(exit)
            }
        }
    }

    fn start_dashboard(&mut self) -> Result<(), String> {
        let exe = self.layout.app.join("stratided.exe");
        if !exe.is_file() {
            self.reason = "DASHBOARD_BINARY_MISSING".into();
            self.dashboard_next = Instant::now() + Duration::from_secs(60);
            return Ok(());
        }
        let mut command = Command::new(&exe);
        command
            .arg("--port")
            .arg(self.port.to_string())
            .arg("--assets-dir")
            .arg(self.layout.app.join("dashboard"))
            .arg("--runtime-home")
            .arg(&self.layout.home)
            .current_dir(&self.layout.app)
            .stdin(Stdio::null());
        let agent_dir = self.layout.agent_dir();
        if agent_dir.join("settings.json").is_file() {
            command.arg("--agent-dir").arg(&agent_dir);
            if agent_dir.join("owner-config.json").is_file() {
                command
                    .arg("--agent-config")
                    .arg(agent_dir.join("owner-config.json"));
            }
        }
        if let Some(ledger) = paper_ledger(&self.layout) {
            command.arg("--paper-ledger").arg(ledger);
        }
        let stdout = append_log(&self.layout.logs.join("dashboard.out.log"))?;
        let stderr = append_log(&self.layout.logs.join("dashboard.err.log"))?;
        command.stdout(stdout).stderr(stderr);
        win::hide_console(&mut command);
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                self.dashboard_failures += 1;
                self.dashboard_next = Instant::now() + backoff(self.dashboard_failures, 15);
                self.reason = "DASHBOARD_START_FAILED".into();
                log(&self.layout, &format!("dashboard spawn failed: {error}"));
                return Ok(());
            }
        };
        if let Err(error) = self.job.assign(&child) {
            let _ = child.kill();
            let _ = child.wait();
            self.reason = "WINDOWS_JOB_ASSIGN_FAILED".into();
            self.dashboard_next = Instant::now() + Duration::from_secs(30);
            log(
                &self.layout,
                &format!("dashboard job assign failed: {error}"),
            );
            return Ok(());
        }
        let pid = child.id();
        self.dashboard = Some(Dashboard {
            child: Some(child),
            pid,
            started_at: stratide_runtime::timestamp(),
            instance_id: String::new(),
            last_exit: None,
        });
        self.dashboard_healthy = false;
        self.reason = "DASHBOARD_STARTING".into();
        log(
            &self.layout,
            &format!("dashboard started pid={pid} port={}", self.port),
        );
        Ok(())
    }

    fn ensure_watch(&mut self) -> Result<(), String> {
        let exited = self.poll_watch_exit();
        if let Some(exit) = exited {
            let watch = self.watch.as_mut().expect("watch exists after poll");
            watch.restarts += 1;
            watch.next_start = Instant::now() + backoff(watch.restarts, 30);
            self.reason = "WATCH_EXITED".into();
            log(
                &self.layout,
                &format!("eod watch exited code={:?}; retry scheduled", exit.code),
            );
        }
        if self.reason == "EXTERNAL_STRATIDE_INSTANCE" {
            return Ok(());
        }
        if !self.layout.market_database().is_file() {
            if self.dashboard_healthy {
                self.reason = "EOD_NOT_CONFIGURED".into();
            }
            return Ok(());
        }
        if !self.layout.python().is_file() {
            if self.dashboard_healthy {
                self.reason = "PYTHON_RUNTIME_MISSING".into();
            }
            return Ok(());
        }
        if self
            .watch
            .as_ref()
            .and_then(|watch| watch.child.as_ref())
            .is_some()
        {
            return Ok(());
        }
        if let Some(watch) = self.watch.as_ref() {
            if Instant::now() < watch.next_start {
                return Ok(());
            }
        }
        self.start_watch()
    }

    fn poll_watch_exit(&mut self) -> Option<ExitState> {
        let watch = self.watch.as_mut()?;
        let child = watch.child.as_mut()?;
        match child.try_wait() {
            Ok(Some(status)) => {
                let exit = ExitState {
                    code: status.code(),
                    at: stratide_runtime::timestamp(),
                };
                watch.last_exit = Some(exit.clone());
                watch.child = None;
                Some(exit)
            }
            Ok(None) => None,
            Err(_) => {
                let exit = ExitState {
                    code: None,
                    at: stratide_runtime::timestamp(),
                };
                watch.last_exit = Some(exit.clone());
                watch.child = None;
                Some(exit)
            }
        }
    }

    fn start_watch(&mut self) -> Result<(), String> {
        let script = self.layout.app.join("scripts").join("eod-operator.py");
        if !script.is_file() {
            self.reason = "EOD_OPERATOR_MISSING".into();
            return Ok(());
        }
        let mut command = Command::new(self.layout.python());
        command
            .args(["-B", "-X", "utf8"])
            .arg(&script)
            .args(["market", "watch"])
            .current_dir(&self.layout.app)
            .env("STRATIDE_STATE_ROOT", &self.layout.data)
            .env("STRATIDE_BIN_DIR", self.layout.app.join("bin"))
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .env_remove("STRATIDE_TUSHARE_TOKEN")
            .stdin(Stdio::null());
        let stdout = append_log(&self.layout.logs.join("eod-watch.out.log"))?;
        let stderr = append_log(&self.layout.logs.join("eod-watch.err.log"))?;
        command.stdout(stdout).stderr(stderr);
        win::hide_console(&mut command);
        let mut child = match command.spawn() {
            Ok(child) => child,
            Err(error) => {
                self.reason = "EOD_WATCH_START_FAILED".into();
                log(&self.layout, &format!("eod watch spawn failed: {error}"));
                if let Some(watch) = self.watch.as_mut() {
                    watch.next_start = Instant::now() + Duration::from_secs(60);
                }
                return Ok(());
            }
        };
        if let Err(error) = self.job.assign(&child) {
            let _ = child.kill();
            let _ = child.wait();
            self.reason = "WINDOWS_JOB_ASSIGN_FAILED".into();
            log(
                &self.layout,
                &format!("eod watch job assign failed: {error}"),
            );
            return Ok(());
        }
        let pid = child.id();
        let restarts = self.watch.as_ref().map(|watch| watch.restarts).unwrap_or(0);
        let started_at = stratide_runtime::timestamp();
        self.watch = Some(Watch {
            child: Some(child),
            pid,
            started_at,
            last_exit: None,
            next_start: Instant::now() + Duration::from_secs(30),
            restarts,
        });
        self.reason = "OK".into();
        log(&self.layout, &format!("eod watch started pid={pid}"));
        Ok(())
    }

    fn stop(&mut self) -> Result<(), String> {
        self.status = "STOPPING".into();
        self.reason = "STOPPED_BY_OWNER".into();
        self.last_publish = Instant::now() - Duration::from_secs(60);
        self.publish()?;
        if let Some(watch) = self.watch.as_mut() {
            if let Some(child) = watch.child.as_mut() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
        let health = health::probe(self.port);
        if health.is_ok() {
            let _ = health::request_shutdown(self.port, &self.token);
            let deadline = Instant::now() + Duration::from_secs(10);
            while Instant::now() < deadline {
                if health::probe(self.port).is_err() {
                    break;
                }
                std::thread::sleep(Duration::from_millis(200));
            }
        }
        if let Some(dashboard) = self.dashboard.as_mut() {
            if let Some(child) = dashboard.child.as_mut() {
                if child.try_wait().ok().flatten().is_none() {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
        if health::probe(self.port).is_ok() {
            self.reason = "STOPPED_WITH_UNMANAGED_SERVICE".into();
        }
        self.stopping_state();
        self.last_publish = Instant::now() - Duration::from_secs(60);
        self.publish()?;
        self.layout.clear_stop_request();
        Ok(())
    }

    fn stopping_state(&mut self) {
        self.status = "STOPPED".into();
        self.dashboard = None;
        self.watch = None;
    }

    fn publish(&mut self) -> Result<(), String> {
        if self.status != "STOPPED" && self.last_publish.elapsed() < Duration::from_millis(1500) {
            return Ok(());
        }
        self.last_publish = Instant::now();
        let status = self.derived_status();
        let state = SupervisorState {
            schema_version: 1,
            status: status.clone(),
            reason: self.reason.clone(),
            instance_id: self.instance_id.clone(),
            supervisor_pid: std::process::id(),
            started_at: self.started_at.clone(),
            updated_at: stratide_runtime::timestamp(),
            port: self.port,
            data_root: self.layout.data.to_string_lossy().to_string(),
            product_version: self.layout.version.clone(),
            dashboard: self.dashboard.as_ref().map(|dashboard| ChildState {
                pid: dashboard.pid,
                started_at: dashboard.started_at.clone(),
                restarts: self.dashboard_failures,
                instance_id: if dashboard.instance_id.is_empty() {
                    None
                } else {
                    Some(dashboard.instance_id.clone())
                },
                last_exit: dashboard.last_exit.clone(),
            }),
            watch: self.watch.as_ref().map(|watch| ChildState {
                pid: watch.pid,
                started_at: watch.started_at.clone(),
                restarts: watch.restarts,
                instance_id: None,
                last_exit: watch.last_exit.clone(),
            }),
            autostart: self.autostart_enabled,
            logs_dir: self.layout.logs.to_string_lossy().to_string(),
        };
        state.write(&self.layout.state_path())
    }

    fn derived_status(&self) -> String {
        if self.status == "STOPPED" || self.status == "STOPPING" {
            return self.status.clone();
        }
        if self.reason == "EXTERNAL_STRATIDE_INSTANCE"
            || self.reason == "PORT_IN_USE_BY_OTHER_APPLICATION"
        {
            return "BLOCKED".into();
        }
        if self.dashboard_healthy {
            if self
                .watch
                .as_ref()
                .and_then(|watch| watch.child.as_ref())
                .is_some()
            {
                return "RUNNING".into();
            }
            return "DEGRADED".into();
        }
        if self.dashboard.is_some() {
            return "STARTING".into();
        }
        "BLOCKED".into()
    }
}

fn paper_ledger(layout: &Layout) -> Option<std::path::PathBuf> {
    let binding = layout
        .data
        .join("state")
        .join("paper-portfolio")
        .join("binding.json");
    let bytes = std::fs::read(binding).ok()?;
    let value: serde_json::Value = serde_json::from_slice(&bytes).ok()?;
    let ledger = Path::new(value.get("ledger")?.as_str()?);
    if ledger.exists() {
        Some(ledger.to_path_buf())
    } else {
        None
    }
}

fn append_log(path: &Path) -> Result<std::fs::File, String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|_| "LOG_DIRECTORY_UNAVAILABLE")?;
    }
    std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("LOG_UNAVAILABLE: {error}"))
}

fn backoff(failures: u32, base_seconds: u64) -> Duration {
    let exponent = failures.saturating_sub(1).min(4);
    Duration::from_secs((base_seconds << exponent).min(300))
}

fn log(layout: &Layout, message: &str) {
    stratide_runtime::log::append(&layout.supervisor_log(), message);
}
