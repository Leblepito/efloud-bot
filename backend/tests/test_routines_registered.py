def test_resolver_and_report_registered():
    import scripts.routines.edge_report as e
    import scripts.routines.resolve_signals as r
    assert hasattr(r, "main") and callable(r.main)
    assert hasattr(e, "main") and callable(e.main)
