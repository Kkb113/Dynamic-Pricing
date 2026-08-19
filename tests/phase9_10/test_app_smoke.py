def test_app_and_all_pages_import():
    import app.streamlit_app  # noqa: F401
    import app.pages.ai_pricing_agent  # noqa: F401
    import app.pages.decision_audit  # noqa: F401
    import app.pages.executive_dashboard  # noqa: F401
    import app.pages.model_intelligence  # noqa: F401
    import app.pages.price_scenario_simulator  # noqa: F401
    import app.pages.recommendation_explorer  # noqa: F401


def test_feature_label_coverage(registry):
    import yaml

    labels = yaml.safe_load((registry.root / "config/explanation_feature_labels.yaml").read_text(encoding="utf-8"))
    assert set(registry.phase4_feature_names).issubset(labels)
