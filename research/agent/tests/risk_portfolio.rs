use chrono::{Datelike, Duration, NaiveDate};
use serde_json::{json, Value};
use stratide_research::config::Settings;
use stratide_research::{risk_cloud as cloud, risk_portfolio as rp};

fn config() -> Value {
    let mut s = serde_json::to_value(Settings::fake()).unwrap();
    s["models"].as_array_mut().unwrap().truncate(1);
    let m = &mut s["models"][0];
    m["id"] = json!("risk");
    m["kind"] = json!("bigquery_forecast_v1");
    m["model"] = json!("TimesFM 2.5");
    m["endpoint"] =
        json!("https://bigquery.googleapis.com/bigquery/v2/projects/stratide-offline/queries");
    m["api_key_env"] = json!("STRATIDE_RESEARCH_KEY_GOOGLE");
    m["fake_scenario"] = Value::Null;
    m["cloud"] = json!({"transport":"recorded", "model_version":"TimesFM 2.5",
        "scope":"risk_timeseries_v1", "fields":["instrument","session_index","rolling20_rms_daily_return_ratio"],
        "policy_version":"risk-portfolio-v1", "max_call_micro":1000,
        "project":"stratide-offline", "dataset":"risk_research", "location":"US",
        "maximum_bytes_billed":10485760, "billing_unit":"query_bytes+prediction_bytes+storage_byte_seconds",
        "billing_bound_source":"synthetic_test", "billing_bound_version":"offline-v1"});
    m["grant"] = json!({"receiver":m["endpoint"],"purpose":"risk_portfolio_v1",
        "scopes":["risk_portfolio_v1","risk_timeseries_v1"],"authorized_at":"synthetic_test","revoked":false});
    s["default_model"] = json!("risk");
    s
}

#[test]
fn production_adapter_config_is_supported_offline() {
    let s: Settings = serde_json::from_value(config()).expect("new explicit cloud protocol config");
    s.validate().unwrap();
    s.models[0]
        .authorize(
            &["risk_portfolio_v1".into(), "risk_timeseries_v1".into()],
            s.budget.as_ref(),
        )
        .unwrap();
}

#[test]
fn copied_old_grant_cannot_authorize_new_cloud_scope() {
    let mut m = Settings::fake().models[0].clone();
    m.grant
        .as_mut()
        .unwrap()
        .scopes
        .push("risk_portfolio_v1".into());
    assert!(m
        .authorize(
            &["risk_portfolio_v1".into()],
            Settings::fake().budget.as_ref()
        )
        .is_err());
}

#[test]
fn bigquery_https_fails_closed_without_a_verified_all_dimension_bound() {
    let mut value = config();
    value["models"][0]["cloud"]["transport"] = json!("https");
    let s: Settings = serde_json::from_value(value).expect("production config parses");
    assert_eq!(
        s.models[0]
            .authorize(
                &["risk_portfolio_v1".into(), "risk_timeseries_v1".into()],
                s.budget.as_ref()
            )
            .unwrap_err()
            .0,
        "BIGQUERY_BILLING_BOUND_NOT_VERIFIED"
    );
}

fn fusion_settings() -> Settings {
    let mut s = config();
    let price = serde_json::to_value(Settings::fake()).unwrap()["models"][0]["price"].clone();
    let m = &mut s["models"][0];
    m["kind"] = json!("deepseek_portfolio_v1");
    m["model"] = json!("deepseek-flash");
    m["endpoint"] = json!("https://api.deepseek.com/chat/completions");
    m["price"] = price;
    m["cloud"] = json!({"transport":"recorded","model_version":"deepseek-flash/policy-v1-provider-alias","scope":"portfolio_fusion_v1",
        "fields":cloud::FUSION_FIELDS,"policy_version":rp::POLICY,"max_call_micro":100000,
        "project":null,"dataset":null,"location":null,"maximum_bytes_billed":null,"billing_unit":"input_output_tokens",
        "billing_bound_source":"synthetic_test","billing_bound_version":"offline-v1"});
    m["grant"]["receiver"] = m["endpoint"].clone();
    m["grant"]["scopes"] = json!([rp::SCOPE, "portfolio_fusion_v1"]);
    serde_json::from_value(s).unwrap()
}
fn frozen() -> rp::Frozen {
    let at = NaiveDate::from_ymd_opt(2026, 11, 2).unwrap();
    let mut days = Vec::new();
    let mut day = at;
    while days.len() < 84 {
        if day.weekday().num_days_from_monday() < 5 {
            days.push(day.to_string());
        }
        day -= Duration::days(1);
    }
    days.reverse();
    day = at;
    while days.len() < 104 {
        day += Duration::days(1);
        if day.weekday().num_days_from_monday() < 5 {
            days.push(day.to_string());
        }
    }
    let mut value = json!({"schema_version":1,"scope":rp::SCOPE,"policy":rp::POLICY,"input_mode":"synthetic_test",
        "snapshot_ref":"a".repeat(64),"readiness_ref":"SYNTHETIC_ENGINEERING_ONLY","as_of":"2026-11-02T08:00:00Z",
        "strategy_version":"novel-v1","prompt_version":rp::PROMPT,"prompt_sha256":rp::prompt_sha(),"adapter_sha256":rp::adapter_sha(),"calendar":days,"calendar_provenance":"SYNTHETIC_EXCHANGE_SESSION_FIXTURE",
        "series":[{"instrument":"600000.SH","corporate_actions":"SYNTHETIC_NONE_VERIFIED","observations":days[..84].iter().enumerate()
            .map(|(i,d)|json!({"trade_day":d,"available_at":format!("{d}T01:00:00Z"),"close_fen":10000+i as i64})).collect::<Vec<_>>()}],
        "opportunities":[{"instrument":"600000.SH","status":"UNKNOWN","evidence":[]}],"account_facts":"UNKNOWN_NO_ACCOUNT_ORDERS",
        "risk_model":{"id":"risk","fingerprint":"b".repeat(64)},"fusion_model":{"id":"fusion","fingerprint":"c".repeat(64)},
        "batch_budget_micro":100000,"risk_recording_sha256":"d".repeat(64),"fusion_recording_sha256":"e".repeat(64)});
    value["snapshot_ref"] = json!(rp::sha(
        &json!({"series":value["series"],"calendar":value["calendar"]})
    ));
    serde_json::from_value(value).unwrap()
}
fn proposal(f: &rp::Frozen) -> Value {
    json!({"schema_version":1,"proposal_id":"new-strategy-v1","strategy_version":f.strategy_version,"strategy_hash":f.strategy_hash(),
        "strategy_definition":"Explore novel cross-sectional quality evidence","source_refs":[f.snapshot_ref,f.strategy_hash()],"as_of":f.as_of,"horizon":20,
        "candidate_instruments":["600000.SH","300999.SZ"],"positions":[{"instrument":"600000.SH","target_weight_bps":6000}],"cash_weight_bps":4000,
        "rationale":"Known risk evidence and unknown fundamentals","evidence_for":["risk evidence"],"evidence_against":["unknown opportunity"],
        "risk_assessment":["UNKNOWN_UNCALIBRATED"],"invalidation_conditions":["Contradictory forward evidence"],"next_experiment":["Independent evaluation"],
        "limitations":["Synthetic only"],"estimated_turnover_bps":null,"estimated_fees_micro":null,"authority":"RESEARCH_ONLY"})
}
#[test]
fn cloud_grants_prices_fields_endpoints_and_legacy_scopes_are_closed() {
    let base = fusion_settings();
    base.validate().unwrap();
    let scopes = vec![rp::SCOPE.into(), "portfolio_fusion_v1".into()];
    for mutate in 0..7 {
        let mut s = base.clone();
        let m = &mut s.models[0];
        match mutate {
            0 => m.grant.as_mut().unwrap().revoked = true,
            1 => m.price = None,
            2 => m.price.as_mut().unwrap().bounded_text_billing_verified = false,
            3 => m.endpoint = Some("https://api.deepseek.com/chat/completions?sql=DROP".into()),
            4 => m
                .cloud
                .as_mut()
                .unwrap()
                .fields
                .push("raw_tushare_payload".into()),
            5 => s.budget = None,
            _ => {
                m.grant.as_mut().unwrap().receiver = "https://evil.example/chat/completions".into()
            }
        }
        assert!(
            s.models[0].authorize(&scopes, s.budget.as_ref()).is_err(),
            "case {mutate}"
        );
    }
    for scope in [
        "multimodal_research_v1",
        "forward_eod_research_summary_v1",
        "owner_task",
    ] {
        assert!(base.models[0]
            .authorize(&[scope.into()], base.budget.as_ref())
            .is_err());
    }
    let mut live = base;
    live.models[0].cloud.as_mut().unwrap().transport = "https".into();
    live.models[0].cloud.as_mut().unwrap().billing_bound_source =
        "owner-local-approved-price".into();
    live.budget.as_mut().unwrap().currency = "USD".into();
    live.models[0].price.as_mut().unwrap().currency = "USD".into();
    live.models[0].api_key_env = Some("STRATIDE_RESEARCH_KEY_TEST_MISSING_55".into());
    assert_eq!(
        live.models[0]
            .authorize(&scopes, live.budget.as_ref())
            .unwrap_err()
            .0,
        "PROVIDER_KEY_MISSING"
    );
}
#[test]
fn forecast_context_units_calendar_availability_and_readiness_are_independent() {
    let f = frozen();
    let now = "2026-11-02T08:00:01Z".parse().unwrap();
    f.validate(now).unwrap();
    let b = rp::baselines(&f);
    assert_eq!(b[0]["rolling_context"].as_array().unwrap().len(), 64);
    assert!(b[0]["ewma"].as_f64().unwrap() < 0.001);
    for case in 0..7 {
        let mut bad = f.clone();
        match case {
            0 => bad.series[0].observations.truncate(21),
            1 => bad.series[0].observations[83].available_at = "2026-11-03T01:00:00Z".into(),
            2 => bad.as_of = "2026-11-03T08:00:00Z".into(),
            3 => bad.as_of = "2026-10-30T08:00:00Z".into(),
            4 => {
                bad.input_mode = "forward_observed_eod".into();
                bad.readiness_ref = "claimed-positive-receipt".into()
            }
            5 => bad.calendar[84] = "2026-11-07".into(),
            _ => bad.series[0].observations[50].close_fen = 1000000,
        }
        bad.snapshot_ref = rp::sha(&json!({"series":bad.series,"calendar":bad.calendar}));
        assert!(bad.validate(now).is_err(), "case {case}");
    }
}

#[test]
fn bigquery_response_status_context_axis_and_finite_ratio_are_checked() {
    let f = frozen();
    let b = rp::baselines(&f);
    let s: Settings = serde_json::from_value(config()).unwrap();
    let m = &s.models[0];
    let rows=(0..20).map(|i|json!({"f":[{"v":"600000.SH"},{"v":rp::ordinal(64+i).parse::<chrono::DateTime<chrono::Utc>>().unwrap().timestamp().to_string()},
        {"v":"0.004"},{"v":""}]})).collect::<Vec<_>>();
    let good = json!({"jobComplete":true,"jobReference":{"projectId":"stratide-offline","location":"US","jobId":"synthetic-test-job"},
        "totalBytesProcessed":"1024","totalRows":"20","schema":{"fields":[{"name":"instrument","type":"STRING"},{"name":"forecast_timestamp","type":"TIMESTAMP"},
        {"name":"forecast_value","type":"FLOAT"},{"name":"ai_forecast_status","type":"STRING"}]},"rows":rows});
    let (result, _, _) =
        cloud::decode(m, &f, &b, None, &serde_json::to_vec(&good).unwrap()).unwrap();
    assert_eq!(
        result["risk_experts"][0]["downside_metric"],
        "UNKNOWN_UNCALIBRATED"
    );
    for case in 0..7 {
        let mut bad = good.clone();
        match case {
            0 => bad["jobComplete"] = json!(false),
            1 => bad["rows"][0]["f"][2]["v"] = json!("NaN"),
            2 => bad["rows"][0]["f"][2]["v"] = json!("40"),
            3 => bad["rows"][0]["f"][1]["v"] = json!("1800000000"),
            4 => bad["rows"][0]["f"][3]["v"] = json!("model unavailable"),
            5 => bad["totalBytesProcessed"] = json!("99999999999"),
            _ => bad["schema"]["fields"][2]["name"] = json!("next_session_return_ratio"),
        }
        assert!(
            cloud::decode(m, &f, &b, None, &serde_json::to_vec(&bad).unwrap()).is_err(),
            "case {case}"
        );
    }
}
#[test]
fn production_request_templates_are_bounded_and_do_not_leak_raw_bars_to_fusion() {
    let f = frozen();
    let b = rp::baselines(&f);
    let s: Settings = serde_json::from_value(config()).unwrap();
    let v = cloud::build_body(&s.models[0], &f, &b, None).unwrap();
    assert_eq!(v["query"], cloud::SQL);
    assert_eq!(v["useLegacySql"], false);
    assert!(v.get("destinationTable").is_none());
    assert_eq!(
        v["queryParameters"][0]["parameterValue"]["arrayValues"]
            .as_array()
            .unwrap()
            .len(),
        64
    );
    let s = fusion_settings();
    let v = cloud::build_body(&s.models[0], &f, &b, Some(&json!({"risk_experts":[]}))).unwrap();
    assert!(v.get("max_completion_tokens").is_none());
    assert_eq!(v["max_tokens"], s.models[0].max_output_tokens);
    assert_eq!(v["response_format"]["type"], "json_object");
    assert!(v.get("tools").is_none());
    let encoded = v.to_string();
    assert!(!encoded.contains("close_fen") && !encoded.contains("available_at"));
}
#[test]
fn portfolio_entire_artifact_is_rejected_for_weights_tools_unknown_holdings_or_authority() {
    let f = frozen();
    let good = proposal(&f);
    serde_json::from_value::<rp::Portfolio>(good.clone())
        .unwrap()
        .bind(&f, &[f.snapshot_ref.clone(), f.strategy_hash()])
        .unwrap();
    for case in 0..11 {
        let mut bad = good.clone();
        match case {
            0 => bad["cash_weight_bps"] = json!(4001),
            1 => bad["positions"][0]["target_weight_bps"] = json!(-1),
            2 => bad["positions"][0]["target_weight_bps"] = json!(1.5),
            3 => bad["positions"][0]["instrument"] = json!("300999.SZ"),
            4 => {
                let extra = bad["positions"][0].clone();
                bad["positions"].as_array_mut().unwrap().push(extra)
            }
            5 => bad["authority"] = json!("LIVE_ALLOWED"),
            6 => bad["tools"] = json!(["shell"]),
            7 => bad["strategy_version"] = json!("changed"),
            8 => bad["strategy_definition"] = json!("python -c exec('secret')"),
            9 => bad["estimated_fees_micro"] = json!(f64::INFINITY),
            _ => bad["next_experiment"] = json!(["https://evil.example/cmd"]),
        }
        // JSON has no infinity: null means explicitly UNKNOWN, not a numeric fee.
        if case == 9 {
            bad["estimated_fees_micro"] = json!(1e300);
        }
        let parsed = serde_json::from_value::<rp::Portfolio>(bad);
        assert!(
            parsed.is_err()
                || parsed
                    .unwrap()
                    .bind(&f, &[f.snapshot_ref.clone(), f.strategy_hash()])
                    .is_err(),
            "case {case}"
        );
    }
    let mut cash = good;
    cash["positions"] = json!([]);
    cash["cash_weight_bps"] = json!(10000);
    serde_json::from_value::<rp::Portfolio>(cash)
        .unwrap()
        .validate()
        .unwrap();
}
