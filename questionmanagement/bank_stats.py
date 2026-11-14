"""Statistics for the Question Bank dashboard.

Pure functions over the loaded questions, so they are easy to test. Every
chart on the page is built from `bank_dashboard()`; titles state the finding
(e.g. "3 categories have fewer than 5 unplayed questions"), not the chart type.
"""
from collections import Counter, OrderedDict
from datetime import date, datetime, timedelta

TYPE_LABELS = OrderedDict([
    ("multiple_choice", "Multiple choice"),
    ("text", "Text"),
    ("true_false", "True / False"),
])
PLAY_BUCKETS = ["0", "1", "2", "3", "4", "5+"]
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _truthy(value):
    return value in (True, 1, "1") or str(value).strip().lower() == "true"


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _month_range(first, last):
    """Every (year, month) from first to last inclusive."""
    y, m = first
    while (y, m) <= last:
        yield y, m
        m += 1
        if m > 12:
            y, m = y + 1, 1


def bank_dashboard(questions, categories, category_tags=None, tag_defs=None, per_game=5, today=None):
    """Everything the Question Bank dashboard shows.

    questions      -- iterable of question dicts (question_bank.questions.values())
    categories     -- {category_id: {"name": ...}} for categories with questions
    category_tags  -- {category_id: [tag ids]} (category_tags.category_tag_map())
    tag_defs       -- {tag_id: {"en", "ar", "group"}} in display order
    per_game       -- questions a game takes from one category (admin setting)
    today          -- date used for "added in the last 30 days" (tests pass one)
    """
    questions = [q for q in questions if isinstance(q, dict)]
    category_tags = category_tags or {}
    tag_defs = tag_defs or {}
    total = len(questions)

    per_cat = {cid: {"id": cid, "name": c.get("name", cid), "total": 0, "fresh": 0, "plays": 0}
               for cid, c in categories.items()}
    points, types, plays_hist, months = Counter(), Counter(), Counter(), Counter()
    active = reported = explained = total_plays = recent = 0
    since = (today or date.today()) - timedelta(days=30)

    for q in questions:
        uses = _int(q.get("use_count"))
        total_plays += uses
        active += 1 if _truthy(q.get("active", True)) else 0
        reported += 1 if _truthy(q.get("reported", False)) else 0
        explained += 1 if str(q.get("explanation") or "").strip() else 0
        points[_int(q.get("points"))] += 1
        types[q.get("type") or "unknown"] += 1
        plays_hist[PLAY_BUCKETS[min(uses, 5)]] += 1
        created = str(q.get("created_at") or "")
        if len(created) >= 7 and created[4] == "-":
            months[(_int(created[:4]), _int(created[5:7]))] += 1
            try:
                if datetime.fromisoformat(created[:10]).date() >= since:
                    recent += 1
            except ValueError:
                pass
        row = per_cat.get(q.get("category_id"))
        if row is not None:
            row["total"] += 1
            row["plays"] += uses
            row["fresh"] += 1 if uses == 0 else 0

    never = plays_hist["0"]

    # ---- categories: unplayed questions left, fewest first ----------------
    cat_rows = []
    for row in per_cat.values():
        row["played"] = row["total"] - row["fresh"]
        row["usage_pct"] = _pct(row["plays"], total_plays)
        row["low"] = row["fresh"] < per_game
        cat_rows.append(row)
    cat_rows.sort(key=lambda r: (r["fresh"], r["name"]))
    low = [r for r in cat_rows if r["low"]]
    cat_max = max([r["total"] for r in cat_rows] or [0])

    # ---- tags: questions carrying each tag -------------------------------
    tag_rows = []
    for tid, d in tag_defs.items():
        cats = [cid for cid in per_cat if tid in category_tags.get(cid, [])]
        tag_rows.append({"id": tid, "label": d.get("en", tid), "ar": d.get("ar", ""),
                         "group": d.get("group", "topic"), "categories": len(cats),
                         "value": sum(per_cat[c]["total"] for c in cats)})
    untagged = [cid for cid in per_cat if not category_tags.get(cid)]
    if untagged:
        tag_rows.append({"id": "other", "label": "Other (untagged)", "ar": "", "group": "topic",
                         "categories": len(untagged), "value": sum(per_cat[c]["total"] for c in untagged)})
    tag_rows = [r for r in tag_rows if r["group"] == "language"] + \
        sorted([r for r in tag_rows if r["group"] != "language"], key=lambda r: -r["value"])

    # ---- simple distributions -------------------------------------------
    point_rows = [{"label": str(p), "name": f"{p} points", "value": n} for p, n in sorted(points.items())]
    type_rows = [{"label": TYPE_LABELS.get(t, t.replace("_", " ").title()), "value": n,
                  "pct": _pct(n, total)} for t, n in sorted(types.items(), key=lambda kv: -kv[1])]
    play_names = {"0": "Never played", "1": "Played once", "5+": "Played 5 or more times"}
    play_rows = [{"label": b, "name": play_names.get(b, f"Played {b} times"), "value": plays_hist[b]}
                 for b in PLAY_BUCKETS]

    month_rows = []
    if months:
        for y, m in _month_range(min(months), max(months)):
            month_rows.append({"label": f"{_MONTHS[m - 1]} {y}", "short": _MONTHS[m - 1],
                               "year": y, "value": months[(y, m)]})
    busiest = max(month_rows, key=lambda r: r["value"]) if month_rows else None

    top_type = type_rows[0] if type_rows else None
    top_points = max(point_rows, key=lambda r: r["value"]) if point_rows else None

    return {
        "kpis": {
            "total": total,
            "categories": len(per_cat),
            "active": active,
            "total_plays": total_plays,
            "never_played": never,
            "never_played_pct": _pct(never, total),
            "reported": reported,
            "explained_pct": _pct(explained, total),
            "avg_plays": round(total_plays / total, 1) if total else 0.0,
            "avg_per_category": round(total / len(per_cat)) if per_cat else 0,
            "added_30d": recent,
        },
        "per_game": per_game,
        "categories": {
            "rows": cat_rows, "max": cat_max, "low": low,
            "title": (f"{len(low)} categor{'y has' if len(low) == 1 else 'ies have'} fewer than "
                      f"{per_game} unplayed questions") if low else
                     f"Every category has at least {per_game} unplayed questions",
        },
        "points": {"rows": point_rows, "max": max([r["value"] for r in point_rows] or [0]),
                   "title": (f"Most questions are worth {top_points['label']} points"
                             if top_points else "Questions by point value")},
        "types": {"rows": type_rows, "max": max([r["value"] for r in type_rows] or [0]),
                  "title": (f"{top_type['label']} is the most common type ({top_type['pct']:g}%)"
                            if top_type else "Questions by type")},
        "plays": {"rows": play_rows, "max": max([r["value"] for r in play_rows] or [0]),
                  "title": f"{_pct(never, total):g}% of questions have never been played"},
        "tags": {"rows": tag_rows, "max": max([r["value"] for r in tag_rows] or [0]),
                 "untagged": untagged},
        "months": {"rows": month_rows, "max": max([r["value"] for r in month_rows] or [0]),
                   "busiest": busiest,
                   "title": (f"Most questions were added in {busiest['label']}" if busiest
                             else "Questions added per month")},
        "as_of": date.today().isoformat(),
    }
