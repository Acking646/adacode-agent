def normalize_event_name(name):
    return name.lower().replace(" ", "_")


def summarize_events(rows):
    counts = {}
    failed = 0

    for row in rows:
        event = row.get("event")
        status = row.get("status", "ok")
        counts[event] = counts.get(event, 0) + 1
        if status == "failed":
            failed += 1

    total = sum(counts.values())
    return {
        "total": total,
        "counts": counts,
        "failed": failed,
        "error_rate": failed / len(rows),
    }
