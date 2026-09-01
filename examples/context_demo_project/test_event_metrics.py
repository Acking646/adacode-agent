from event_metrics import normalize_event_name, summarize_events


def test_normalize_event_name():
    assert normalize_event_name("  Page View ") == "page_view"
    assert normalize_event_name("Add-To-Cart") == "add_to_cart"


def test_summarize_events_ignores_malformed_rows():
    rows = [
        {"event": "Page View", "status": "ok"},
        {"event": " page-view ", "status": "failed"},
        {"event": "Checkout", "status": "ok"},
        {"event": "", "status": "failed"},
        {"status": "failed"},
    ]

    report = summarize_events(rows)

    assert report["total"] == 3
    assert report["failed"] == 1
    assert report["counts"] == {"page_view": 2, "checkout": 1}
    assert report["error_rate"] == 1 / 3


def test_summarize_events_empty_input():
    assert summarize_events([]) == {
        "total": 0,
        "counts": {},
        "failed": 0,
        "error_rate": 0.0,
    }
