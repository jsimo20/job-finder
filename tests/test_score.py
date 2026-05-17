from boston_pm_tracker.score import comp_score, domain_score, stage_score


def test_domain_score_sums_weights():
    assert domain_score(["ai_agentic", "developer_platform"]) == 9
    assert domain_score([]) == 0
    assert domain_score(["unknown_tag"]) == 0


def test_stage_score():
    assert stage_score("series_b_d_ai_native") == 4
    assert stage_score(None) == 0
    assert stage_score("seed_series_a") == 1


def test_comp_score_tiers():
    assert comp_score(210000, "posted") == 2
    assert comp_score(180000, "posted") == 1
    assert comp_score(150000, "posted") == 0
    assert comp_score(None, None) == 0
    assert comp_score(210000, None) == 0
