//! Local Owner decisions and read receipts in the existing Agent database.
//! These records never grant provider scopes, budget, or trading authority.
use crate::{ensure, Result, Store};
use chrono::{DateTime, Utc};
use rusqlite::{params, OptionalExtension, TransactionBehavior};
use serde_json::{json, Value};

impl Store {
    pub fn desktop_recover(&self) -> Result<()> {
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let records = {
            let mut q =
                tx.prepare("SELECT key,value FROM meta WHERE key LIKE 'desktop-approval:%'")?;
            let rows = q
                .query_map([], |r| Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?)))?
                .collect::<std::result::Result<Vec<_>, _>>()?;
            rows
        };
        for (key, raw) in records {
            let mut v: Value = serde_json::from_str(&raw).map_err(|_| "APPROVAL_RECORD_INVALID")?;
            if v["status"] == "running" {
                v["status"] = json!("outcome_uncertain");
                v["reason"] = json!("DAEMON_RESTART_RECONCILE_ORIGINAL_TASK");
                tx.execute(
                    "UPDATE meta SET value=?1 WHERE key=?2",
                    params![v.to_string(), key],
                )?;
            }
        }
        tx.commit()?;
        Ok(())
    }
    pub fn desktop_inbox(&self, now: DateTime<Utc>) -> Result<Value> {
        let c = self.connect()?;
        let mut q = c.prepare("SELECT value FROM meta WHERE key LIKE 'desktop-approval:%' ORDER BY json_extract(value,'$.created_at') DESC,key DESC LIMIT 100")?;
        let mut approvals = q
            .query_map([], |r| r.get::<_, String>(0))?
            .map(|r| Ok(serde_json::from_str::<Value>(&r?).map_err(|_| "APPROVAL_RECORD_INVALID")?))
            .collect::<Result<Vec<_>>>()?;
        for item in &mut approvals {
            if matches!(item["status"].as_str(), Some("pending" | "approved"))
                && item["expires_at"]
                    .as_i64()
                    .ok_or("APPROVAL_RECORD_INVALID")?
                    <= now.timestamp()
            {
                item["status"] = json!("expired");
            }
        }
        let mut q = c.prepare("SELECT t.id,t.status,t.reason,t.finished_at,m.key IS NOT NULL FROM tasks t LEFT JOIN meta m ON m.key='desktop-notice-read:'||t.id WHERE t.finished_at IS NOT NULL ORDER BY t.finished_at DESC,t.id DESC LIMIT 50")?;
        let notifications = q.query_map([], |r| {
            let id = r.get::<_, i64>(0)?.to_string();
            Ok(json!({"id":id,"status":r.get::<_,String>(1)?,"reason":r.get::<_,Option<String>>(2)?,
                "at":r.get::<_,String>(3)?,"read":r.get::<_,bool>(4)?}))
        })?.collect::<std::result::Result<Vec<_>,_>>()?;
        Ok(
            json!({"approvals":approvals,"notifications":notifications,"authority":"LOCAL_RESEARCH_ONLY"}),
        )
    }

    pub fn desktop_request(&self, id: &str, action: &Value, now: DateTime<Utc>) -> Result<Value> {
        ensure(
            id.len() == 32 && id.bytes().all(|c| c.is_ascii_hexdigit()),
            "APPROVAL_ID_INVALID",
        )?;
        let key = format!("desktop-approval:{id}");
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let prior: Option<String> = tx
            .query_row("SELECT value FROM meta WHERE key=?1", [&key], |r| r.get(0))
            .optional()?;
        let record = if let Some(prior) = prior {
            let prior: Value =
                serde_json::from_str(&prior).map_err(|_| "APPROVAL_RECORD_INVALID")?;
            ensure(prior["action"] == *action, "APPROVAL_ID_CONFLICT")?;
            prior
        } else {
            let v = json!({"id":id,"action":action,"action_sha256":crate::hash(action.to_string().as_bytes()),
                "status":"pending","created_at":now.to_rfc3339(),"expires_at":now.timestamp()+3600,
                "decided_at":Value::Null,"started_at":Value::Null,"finished_at":Value::Null,"reason":Value::Null});
            tx.execute(
                "INSERT INTO meta(key,value) VALUES(?1,?2)",
                params![key, v.to_string()],
            )?;
            v
        };
        tx.commit()?;
        Ok(record)
    }

    /// Compare-and-set under the same SQLite write transaction. No click or
    /// duplicate HTTP request can execute a second paid/local research attempt.
    pub fn desktop_decide(&self, id: &str, decision: &str, now: DateTime<Utc>) -> Result<Value> {
        let key = format!("desktop-approval:{id}");
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let raw: String = tx
            .query_row("SELECT value FROM meta WHERE key=?1", [&key], |r| r.get(0))
            .optional()?
            .ok_or("APPROVAL_NOT_FOUND")?;
        let mut v: Value = serde_json::from_str(&raw).map_err(|_| "APPROVAL_RECORD_INVALID")?;
        let old = v["status"]
            .as_str()
            .ok_or("APPROVAL_RECORD_INVALID")?
            .to_string();
        let target = match decision {
            "approve" => "approved",
            "reject" => "rejected",
            "revoke" => "revoked",
            "start" => "running",
            _ => return Err("APPROVAL_DECISION_INVALID".into()),
        };
        if old == target && decision != "start" {
            return Ok(v);
        }
        ensure(
            v["expires_at"].as_i64().ok_or("APPROVAL_RECORD_INVALID")? > now.timestamp(),
            "APPROVAL_EXPIRED",
        )?;
        ensure(
            match decision {
                "approve" | "reject" => old == "pending",
                "revoke" => old == "approved" || old == "pending",
                "start" => old == "approved",
                _ => unreachable!(),
            },
            "APPROVAL_STATE_CONFLICT",
        )?;
        v["status"] = json!(target);
        v[if decision == "start" {
            "started_at"
        } else {
            "decided_at"
        }] = json!(now.to_rfc3339());
        tx.execute(
            "UPDATE meta SET value=?1 WHERE key=?2",
            params![v.to_string(), key],
        )?;
        tx.commit()?;
        Ok(v)
    }

    pub fn desktop_finish(
        &self,
        id: &str,
        success: bool,
        reason: &str,
        now: DateTime<Utc>,
    ) -> Result<()> {
        let key = format!("desktop-approval:{id}");
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        let raw: String =
            tx.query_row("SELECT value FROM meta WHERE key=?1", [&key], |r| r.get(0))?;
        let mut v: Value = serde_json::from_str(&raw).map_err(|_| "APPROVAL_RECORD_INVALID")?;
        ensure(v["status"] == "running", "APPROVAL_STATE_CONFLICT")?;
        v["status"] = json!(if success {
            "completed"
        } else if matches!(reason, "OWNER_STOPPED" | "OWNER_CANCEL_REQUESTED") {
            "cancelled"
        } else {
            "failed"
        });
        v["reason"] = json!(reason);
        v["finished_at"] = json!(now.to_rfc3339());
        tx.execute(
            "UPDATE meta SET value=?1 WHERE key=?2",
            params![v.to_string(), key],
        )?;
        tx.commit()?;
        Ok(())
    }

    pub fn desktop_mark_read(&self, ids: &[i64]) -> Result<Value> {
        let mut c = self.connect()?;
        let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
        for id in ids {
            let finished: Option<String> = tx
                .query_row("SELECT finished_at FROM tasks WHERE id=?1", [id], |r| {
                    r.get(0)
                })
                .optional()?
                .flatten();
            ensure(finished.is_some(), "NOTIFICATION_NOT_FINISHED")?;
            tx.execute(
                "INSERT OR IGNORE INTO meta(key,value) VALUES(?1,'true')",
                [format!("desktop-notice-read:{id}")],
            )?;
        }
        tx.commit()?;
        Ok(json!({"read_ids":ids.iter().map(i64::to_string).collect::<Vec<_>>()}))
    }
}
