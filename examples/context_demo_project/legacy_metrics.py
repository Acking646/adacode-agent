def summarize_legacy_campaigns(rows):
    campaigns = {}
    for row in rows:
        name = row.get("campaign", "unknown")
        campaigns[name] = campaigns.get(name, 0) + 1
    return campaigns


def convert_legacy_status(value):
    return "failed" if value in {"error", "timeout"} else "ok"
