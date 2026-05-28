"""Social doctrine hypothesis generation tests."""


def test_generate_hypotheses_for_repeated_ote_fvg_htf_bias():
    from backend.social.hypotheses import generate_hypotheses

    doctrines = [
        {
            "symbols": ["BTC/USDT"],
            "timeframes": ["1d"],
            "bias": "bullish",
            "structure_terms": ["MSB"],
            "zones": ["OTE", "FVG"],
            "liquidity_terms": [],
            "risk_terms": [],
        },
        {
            "symbols": ["ETH/USDT"],
            "timeframes": ["4h"],
            "bias": "bullish",
            "structure_terms": [],
            "zones": ["FVG"],
            "liquidity_terms": ["liquidity_target"],
            "risk_terms": ["risk_management"],
        },
    ]

    hypotheses = generate_hypotheses(doctrines)

    ids = {h["id"] for h in hypotheses}
    assert "social_ote_fvg_htf_bias_v1" in ids
    hypothesis = next(h for h in hypotheses if h["id"] == "social_ote_fvg_htf_bias_v1")
    assert hypothesis["risk"] == "research_only"
    assert hypothesis["candidate_config_patch"]
    assert "FVG" in hypothesis["doctrine_tags"]
    assert "stop_hunt_rate" in hypothesis["metrics_to_watch"]


def test_generate_hypotheses_for_liquidity_sweep_education():
    from backend.social.hypotheses import generate_hypotheses

    doctrines = [
        {
            "symbols": [],
            "bias": "educational",
            "structure_terms": ["MPA"],
            "zones": [],
            "liquidity_terms": ["liquidity_sweep"],
            "risk_terms": [],
        }
    ]

    hypotheses = generate_hypotheses(doctrines)

    assert any(h["id"] == "social_liquidity_sweep_filter_v1" for h in hypotheses)
