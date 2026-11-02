//! Trusted gate: no Provider text or task state can release a reservation.
use crate::{config::Budget, ensure, Result};
use chrono::{DateTime, Utc};
use rusqlite::{params, Connection, TransactionBehavior};
use serde_json::{json, Value};
pub fn periods(b: &Budget, now: DateTime<Utc>) -> Result<(String, String)> {
    let local = now.with_timezone(
        &b.timezone
            .parse::<chrono_tz::Tz>()
            .map_err(|_| "TIMEZONE_INVALID")?,
    );
    Ok((
        local.format("%Y-%m-%d").to_string(),
        local.format("%Y-%m").to_string(),
    ))
}
fn totals(c: &Connection, day: &str, month: &str) -> Result<(i64, i64, i64)> {
    Ok(c.query_row("SELECT
        COALESCE(SUM(CASE WHEN state='settled' AND day=?1 THEN settled_micro ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN state='settled' AND month=?2 THEN settled_micro ELSE 0 END),0),
        COALESCE(SUM(CASE WHEN state NOT IN ('settled','no_charge') THEN maximum_micro ELSE 0 END),0)
        FROM calls", params![day, month], |r| Ok((r.get(0)?,r.get(1)?,r.get(2)?)))?)
}
pub struct Reservation<'a> {
    pub task_id: i64,
    pub maximum_micro: i64,
    pub task_limit: Option<i64>,
    pub price_version: &'a str,
}
/// Recheck a just-reserved call against current caps/periods before dispatch.
pub fn check_dispatch(c: &Connection, b: &Budget, now: DateTime<Utc>) -> Result<()> {
    let (day, month) = periods(b, now)?;
    let (daily, monthly, held) = totals(c, &day, &month)?;
    ensure(
        i128::from(daily) + i128::from(held) <= i128::from(b.daily_limit_micro),
        "DAILY_BUDGET_EXHAUSTED",
    )?;
    ensure(
        i128::from(monthly) + i128::from(held) <= i128::from(b.monthly_limit_micro),
        "MONTHLY_BUDGET_EXHAUSTED",
    )
}
pub fn reserve(
    c: &mut Connection,
    b: &Budget,
    now: DateTime<Utc>,
    r: Reservation<'_>,
) -> Result<i64> {
    ensure(r.maximum_micro > 0, "RESERVATION_INVALID")?;
    let (day, month) = periods(b, now)?;
    let tx = c.transaction_with_behavior(TransactionBehavior::Immediate)?;
    let (daily, monthly, held) = totals(&tx, &day, &month)?;
    let overrun: i64 = tx.query_row(
        "SELECT COUNT(*) FROM calls WHERE settled_micro>maximum_micro OR violation=1",
        [],
        |row| row.get(0),
    )?;
    ensure(overrun == 0, "BILLING_OVERRUN_REQUIRES_OWNER")?;
    ensure(
        i128::from(daily) + i128::from(held) + i128::from(r.maximum_micro)
            <= i128::from(b.daily_limit_micro),
        "DAILY_BUDGET_EXHAUSTED",
    )?;
    ensure(
        i128::from(monthly) + i128::from(held) + i128::from(r.maximum_micro)
            <= i128::from(b.monthly_limit_micro),
        "MONTHLY_BUDGET_EXHAUSTED",
    )?;
    let task_cost: i64 = tx.query_row("SELECT COALESCE(SUM(CASE WHEN state='settled' THEN settled_micro WHEN state='no_charge' THEN 0 ELSE maximum_micro END),0) FROM calls WHERE task_id=?1", [r.task_id], |row| row.get(0))?;
    if let Some(limit) = r.task_limit {
        ensure(
            i128::from(task_cost) + i128::from(r.maximum_micro) <= i128::from(limit),
            "TASK_BUDGET_EXHAUSTED",
        )?;
    }
    tx.execute("INSERT INTO calls(task_id,day,month,maximum_micro,price_version,state,created_at) VALUES(?1,?2,?3,?4,?5,'reserved',?6)",
        params![r.task_id,day,month,r.maximum_micro,r.price_version,now.to_rfc3339()])?;
    let id = tx.last_insert_rowid();
    tx.commit()?;
    Ok(id)
}
pub fn view(c: &Connection, b: Option<&Budget>, now: DateTime<Utc>) -> Result<Value> {
    let Some(b) = b else {
        return Ok(json!({"state":"unconfigured"}));
    };
    let (day, month) = periods(b, now)?;
    let (daily, monthly, held) = totals(c, &day, &month)?;
    let usage: (i64,i64,i64,i64)=c.query_row("SELECT COUNT(*),COALESCE(SUM(input_tokens),0),COALESCE(SUM(output_tokens),0),COALESCE(SUM(usage_micro),0) FROM calls",[],|r|Ok((r.get(0)?,r.get(1)?,r.get(2)?,r.get(3)?)))?;
    Ok(
        json!({"state":"configured","currency":b.currency,"unit":"micro_currency_1e-6","timezone":b.timezone,
        "day":day,"month":month,"daily_limit_micro":b.daily_limit_micro.to_string(),"monthly_limit_micro":b.monthly_limit_micro.to_string(),
        "daily_settled_micro":daily.to_string(),"monthly_settled_micro":monthly.to_string(),"reserved_micro":held.to_string(),
        "daily_remaining_micro":(b.daily_limit_micro-daily-held).max(0).to_string(),
        "monthly_remaining_micro":(b.monthly_limit_micro-monthly-held).max(0).to_string(),
        "call_count":usage.0.to_string(),"input_tokens":usage.1.to_string(),"output_tokens":usage.2.to_string(),"usage_estimate_micro":usage.3.to_string(),
        "billing":"provider_usage_is_estimate_cloud_maximum_held_until_owner_invoice_reconciliation"}),
    )
}
