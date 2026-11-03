//! Compiled only into libtest; no installed CLI transport or fault override.
use crate::{local_fusion as f, Result};
use serde_json::{json, Value};
use std::{io::Read, time::Duration};
pub fn transport(ctx: &f::Context) -> Result<(reqwest::blocking::Client, reqwest::Url)> {
    assert!(ctx.batch.starts_with("rp-test-pr19-"));
    let port = std::env::var("STRATIDE_PR19_LOOPBACK_PORT")
        .map_err(|_| "LIBTEST_REQUIRES_LOOPBACK_NO_EXTERNAL_DNS")?
        .parse::<u16>()
        .map_err(|_| "TEST_PORT")?;
    assert_ne!(port, 0);
    Ok((
        reqwest::blocking::Client::builder()
            .no_proxy()
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_millis(300))
            .build()
            .unwrap(),
        reqwest::Url::parse(&format!("http://127.0.0.1:{port}/chat/completions")).unwrap(),
    ))
}
#[test]
fn process_driver() {
    if std::env::var("STRATIDE_PR19_DRIVER").as_deref() != Ok("1") {
        return;
    }
    let mut raw = String::new();
    std::io::stdin().read_to_string(&mut raw).unwrap();
    let v: Value = serde_json::from_str(&raw).unwrap();
    let batch = v["batch"].as_str().unwrap();
    assert!(batch.starts_with("rp-test-pr19-"));
    let result = match v["action"].as_str().unwrap_or("once") {
        "verify" => f::inspect(batch, true),
        _ => f::execute(batch, false),
    };
    println!(
        "PR19_RESULT={}",
        match result {
            Ok(v) => v,
            Err(e) => json!({"state":"BLOCKED","error_code":e.0}),
        }
    );
}
