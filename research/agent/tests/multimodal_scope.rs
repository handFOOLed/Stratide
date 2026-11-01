use stratide_research::config::{Settings, PURPOSE};

#[test]
fn multimodal_scope_rejects_cloud_even_with_a_copied_grant_before_key_lookup() {
    let settings = Settings::fake();
    let mut model = settings.models[0].clone();
    model.kind = "chat_completions_v1".into();
    model.endpoint = Some("https://provider.example.com/v1/chat/completions".into());
    model.api_key_env = Some("STRATIDE_RESEARCH_KEY_MULTIMODAL_UNSET".into());
    model.fake_scenario = None;
    let grant = model.grant.as_mut().unwrap();
    grant.receiver = model.endpoint.clone().unwrap();
    grant.purpose = PURPOSE.into();
    grant.scopes.push("multimodal_research_v1".into());
    assert_eq!(
        model
            .authorize(
                &["owner_task".into(), "multimodal_research_v1".into()],
                settings.budget.as_ref()
            )
            .unwrap_err()
            .0,
        "MULTIMODAL_LOCAL_FAKE_ONLY"
    );
}
