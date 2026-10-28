use crate::model::*;
use fs2::FileExt;
use rusqlite::{params, Connection, OpenFlags, TransactionBehavior};
use sha2::{Digest, Sha256};
use std::{
    fs::{self, File, OpenOptions},
    path::Path,
};

/// One local writer for one canonical ledger directory. Never delete writer.lock:
/// the OS releases the advisory lock on death, without stale-PID guessing.
pub struct Ledger {
    db: Connection,
    _lock: File,
    state: State,
    head: String,
    sequence: i64,
    poisoned: bool,
}

/// Verified projection of one committed event. The digest is the v3 ledger
/// chain value; report code consumes this instead of inventing executions.
pub struct AuditEntry {
    pub seq: i64,
    pub event_id: String,
    pub command: Option<Command>,
    pub state: State,
    pub digest: String,
}

fn digest(previous: &str, seq: i64, id: &str, payload: &str, state: &State) -> Result<String> {
    let input =
        serde_json::to_vec(&(3, previous, seq, id, payload, state)).map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(input)))
}

fn connection(path: &Path, create: bool) -> Result<(Connection, File)> {
    let path = fs::canonicalize(path).map_err(|e| format!("账本目录不可用：{e}"))?;
    for name in ["writer.lock", "ledger.sqlite"] {
        if fs::symlink_metadata(path.join(name)).is_ok_and(|m| m.file_type().is_symlink()) {
            return Err("权威账本/锁文件不允许符号链接".into());
        }
    }
    let lock = OpenOptions::new()
        .create(true)
        .truncate(false)
        .read(true)
        .write(true)
        .open(path.join("writer.lock"))
        .map_err(|e| e.to_string())?;
    lock.try_lock_exclusive()
        .map_err(|e| format!("该账户已有本机写入者：{e}"))?;
    let flags = OpenFlags::SQLITE_OPEN_READ_WRITE
        | if create {
            OpenFlags::SQLITE_OPEN_CREATE
        } else {
            OpenFlags::empty()
        };
    if !create
        && fs::metadata(path.join("ledger.sqlite"))
            .map_err(|e| e.to_string())?
            .len()
            < 100
    {
        return Err("空/截断账本不能恢复或自动初始化".into());
    }
    let db = Connection::open_with_flags(path.join("ledger.sqlite"), flags)
        .map_err(|e| format!("账本不可恢复，禁止初始化：{e}"))?;
    db.busy_timeout(std::time::Duration::ZERO)
        .map_err(|e| e.to_string())?;
    db.execute_batch(
        "PRAGMA journal_mode=DELETE; PRAGMA synchronous=FULL; PRAGMA locking_mode=EXCLUSIVE;",
    )
    .map_err(|e| e.to_string())?;
    Ok((db, lock))
}

impl Ledger {
    /// Exclusive first creation. An existing/partly initialized directory is an
    /// error, even when empty: recovery may NEVER silently invent new principal.
    pub fn create(path: impl AsRef<Path>, genesis: Genesis) -> Result<Self> {
        let path = path.as_ref();
        let state = State::new(genesis.clone())?;
        fs::create_dir(path).map_err(|e| format!("首次创建失败（已有目录不得覆盖）：{e}"))?;
        let (mut db, lock) = connection(path, true)?;
        let payload = serde_json::to_string(&genesis).map_err(|e| e.to_string())?;
        let head = digest("", 0, "genesis", &payload, &state)?;
        let tx = db
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(|e| e.to_string())?;
        tx.execute_batch("PRAGMA user_version=3; CREATE TABLE events (seq INTEGER PRIMARY KEY, event_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL, digest TEXT NOT NULL); CREATE TABLE checkpoint (id INTEGER PRIMARY KEY CHECK(id=1), seq INTEGER NOT NULL, digest TEXT NOT NULL);")
            .map_err(|e| e.to_string())?;
        tx.execute(
            "INSERT INTO events VALUES (0, 'genesis', ?1, ?2)",
            params![payload, head],
        )
        .map_err(|e| e.to_string())?;
        tx.execute("INSERT INTO checkpoint VALUES (1,0,?1)", [&head])
            .map_err(|e| e.to_string())?;
        tx.commit().map_err(|e| e.to_string())?;
        Ok(Self {
            db,
            _lock: lock,
            state,
            head,
            sequence: 0,
            poisoned: false,
        })
    }

    /// Re-run immutable commands through the same risk/execution reducer and
    /// verify every state hash and cash/share/fee conservation before any write.
    pub fn open(path: impl AsRef<Path>) -> Result<Self> {
        let (db, lock) = connection(path.as_ref(), false)?;
        let version: i64 = db
            .pragma_query_value(None, "user_version", |r| r.get(0))
            .map_err(|e| e.to_string())?;
        let check: String = db
            .query_row("PRAGMA integrity_check", [], |r| r.get(0))
            .map_err(|e| e.to_string())?;
        if version != 3 || check != "ok" {
            return Err(
                "账本匹配模型需 v3 或 SQLite 完整性失败；保留原文件，不自动迁移/重建，禁止新风险"
                    .into(),
            );
        }
        let mut state: Option<State> = None;
        let mut head = String::new();
        let mut sequence = -1;
        {
            let mut stmt = db
                .prepare("SELECT seq,event_id,payload,digest FROM events ORDER BY seq")
                .map_err(|e| e.to_string())?;
            let rows = stmt
                .query_map([], |r| {
                    Ok((
                        r.get::<_, i64>(0)?,
                        r.get::<_, String>(1)?,
                        r.get::<_, String>(2)?,
                        r.get::<_, String>(3)?,
                    ))
                })
                .map_err(|e| e.to_string())?;
            for row in rows {
                let (seq, id, payload, hash) = row.map_err(|e| e.to_string())?;
                if seq != sequence + 1 {
                    return Err("事件序列缺失，禁止新风险".into());
                }
                if seq == 0 {
                    if id != "genesis" {
                        return Err("缺少初始本金事件".into());
                    }
                    let genesis = serde_json::from_str(&payload)
                        .map_err(|e| format!("本金/配置记录损坏：{e}"))?;
                    state = Some(State::new(genesis)?);
                } else {
                    let cmd: Command =
                        serde_json::from_str(&payload).map_err(|e| format!("事件损坏：{e}"))?;
                    state
                        .as_mut()
                        .ok_or("缺失初始账户")?
                        .apply(&cmd)
                        .map_err(|e| format!("重放失败 seq={seq}：{e}"))?;
                }
                let s = state.as_ref().ok_or("缺失初始账户")?;
                s.validate()?;
                let expected = digest(&head, seq, &id, &payload, s)?;
                if hash != expected {
                    return Err(format!("账本状态/事件校验失败 seq={seq}，禁止新风险"));
                }
                head = hash;
                sequence = seq;
            }
        }
        let checkpoint: (i64, String) = db
            .query_row("SELECT seq,digest FROM checkpoint WHERE id=1", [], |r| {
                Ok((r.get(0)?, r.get(1)?))
            })
            .map_err(|e| e.to_string())?;
        if checkpoint != (sequence, head.clone()) {
            return Err("权威提交尾标与事件日志不一致，禁止恢复旧资金/风险状态".into());
        }
        Ok(Self {
            db,
            _lock: lock,
            state: state.ok_or("空账本不能恢复或自动初始化")?,
            head,
            sequence,
            poisoned: false,
        })
    }

    pub fn state(&self) -> &State {
        &self.state
    }

    pub fn head(&self) -> &str {
        &self.head
    }

    pub fn history(&self) -> Result<Vec<AuditEntry>> {
        let mut stmt = self
            .db
            .prepare("SELECT seq,event_id,payload,digest FROM events ORDER BY seq")
            .map_err(|e| e.to_string())?;
        let rows = stmt
            .query_map([], |r| {
                Ok((
                    r.get::<_, i64>(0)?,
                    r.get::<_, String>(1)?,
                    r.get::<_, String>(2)?,
                    r.get::<_, String>(3)?,
                ))
            })
            .map_err(|e| e.to_string())?;
        let mut history = Vec::new();
        let mut current: Option<State> = None;
        let mut previous = String::new();
        for row in rows {
            let (seq, event_id, payload, hash) = row.map_err(|e| e.to_string())?;
            if seq != history.len() as i64 {
                return Err("审计事件序列缺失".into());
            }
            let command = if seq == 0 {
                if event_id != "genesis" {
                    return Err("审计缺少 genesis".into());
                }
                current = Some(State::new(
                    serde_json::from_str(&payload).map_err(|e| e.to_string())?,
                )?);
                None
            } else {
                let command: Command = serde_json::from_str(&payload).map_err(|e| e.to_string())?;
                current
                    .as_mut()
                    .ok_or("审计缺少初始账户")?
                    .apply(&command)?;
                Some(command)
            };
            let state = current.as_ref().ok_or("审计缺少状态")?;
            state.validate()?;
            if digest(&previous, seq, &event_id, &payload, state)? != hash {
                return Err("审计事件摘要不匹配".into());
            }
            previous = hash.clone();
            history.push(AuditEntry {
                seq,
                event_id,
                command,
                state: state.clone(),
                digest: hash,
            });
        }
        if previous != self.head || current.as_ref() != Some(&self.state) {
            return Err("审计尾状态与权威账本不一致".into());
        }
        Ok(history)
    }

    /// true = committed new event; false = identical retry, no new economic event.
    /// After any storage/commit uncertainty this handle is poisoned: close and
    /// recover authoritative SQLite contents instead of blindly retrying in RAM.
    pub fn execute(&mut self, event_id: &str, command: Command) -> Result<bool> {
        if self.poisoned {
            return Err("持久化状态未知；关闭并恢复账本，禁止继续提交".into());
        }
        if event_id.trim().is_empty() || event_id == "genesis" {
            return Err("事件 ID 为空或保留".into());
        }
        let payload = serde_json::to_string(&command).map_err(|e| e.to_string())?;
        let existing = self.db.query_row(
            "SELECT payload FROM events WHERE event_id=?1",
            [event_id],
            |r| r.get::<_, String>(0),
        );
        match existing {
            Ok(old) if old == payload => return Ok(false),
            Ok(_) => return Err("事件 ID 冲突，拒绝改写已提交事件".into()),
            Err(rusqlite::Error::QueryReturnedNoRows) => {}
            Err(e) => {
                self.poisoned = true;
                return Err(e.to_string());
            }
        }
        let mut draft = self.state.clone();
        fault("before_transaction");
        let tx = match self
            .db
            .transaction_with_behavior(TransactionBehavior::Immediate)
        {
            Ok(tx) => tx,
            Err(e) => {
                self.poisoned = true;
                return Err(e.to_string());
            }
        };
        fault("before_reservation");
        draft.apply(&command)?;
        fault("after_reservation");
        let seq = self.sequence.checked_add(1).ok_or("事件序号溢出")?;
        let head = digest(&self.head, seq, event_id, &payload, &draft)?;
        if let Err(e) = tx.execute(
            "INSERT INTO events VALUES (?1,?2,?3,?4)",
            params![seq, event_id, payload, head],
        ) {
            self.poisoned = true;
            return Err(e.to_string());
        }
        match tx.execute(
            "UPDATE checkpoint SET seq=?1,digest=?2 WHERE id=1",
            params![seq, head],
        ) {
            Ok(1) => {}
            result => {
                self.poisoned = true;
                return Err(format!("提交尾标写入失败：{result:?}"));
            }
        }
        fault("before_commit");
        if let Err(e) = tx.commit() {
            self.poisoned = true;
            return Err(format!("提交结果未知，必须恢复：{e}"));
        }
        fault("after_commit");
        self.state = draft;
        self.head = head;
        self.sequence = seq;
        Ok(true)
    }
}

#[cfg(not(test))]
fn fault(_: &str) {}

#[cfg(test)]
fn fault(point: &str) {
    if std::env::var("STRATIDE_TEST_CRASH_AT").as_deref() == Ok(point) {
        std::process::exit(86);
    }
}

#[cfg(test)]
mod tests;
