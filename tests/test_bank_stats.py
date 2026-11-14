"""Question Bank dashboard figures (questionmanagement/bank_stats.py)."""
from datetime import date

from questionmanagement.bank_stats import bank_dashboard


def _q(cat, uses=0, points=100, qtype="text", created="2026-11-01T10:00:00", **extra):
    return {"category_id": cat, "use_count": str(uses), "points": str(points), "type": qtype,
            "created_at": created, "active": "True", **extra}


QUESTIONS = [
    _q("a", 0, 100, "text", explanation="why"),
    _q("a", 2, 200, "multiple_choice"),
    _q("a", 7, 200, "multiple_choice", reported=True),
    _q("b", 0, 300, "true_false", created="2026-08-15T00:00:00"),
    _q("b", 0, 300, "multiple_choice", created="2026-08-20T00:00:00"),
]
CATS = {"a": {"name": "Alpha"}, "b": {"name": "Beta"}}
TAGS = {"arabic": {"en": "Arabic", "ar": "عربي", "group": "language"},
        "science": {"en": "Science", "ar": "علوم", "group": "topic"}}


def dash(**kw):
    return bank_dashboard(QUESTIONS, CATS, {"a": ["arabic", "science"]}, TAGS,
                          per_game=2, today=date(2026, 11, 14), **kw)


def test_headline_figures():
    k = dash()["kpis"]
    assert k["total"] == 5 and k["categories"] == 2
    assert k["total_plays"] == 9 and k["never_played"] == 3 and k["never_played_pct"] == 60.0
    assert k["reported"] == 1 and k["explained_pct"] == 20.0
    assert k["added_30d"] == 3          # the three November questions


def test_categories_sorted_by_fewest_unplayed_and_flagged_low():
    c = dash()["categories"]
    assert [(r["id"], r["fresh"], r["played"], r["low"]) for r in c["rows"]] == \
        [("a", 1, 2, True), ("b", 2, 0, False)]
    assert c["title"] == "1 category has fewer than 2 unplayed questions"


def test_distributions():
    d = dash()
    assert [(r["label"], r["value"]) for r in d["plays"]["rows"]] == \
        [("0", 3), ("1", 0), ("2", 1), ("3", 0), ("4", 0), ("5+", 1)]
    assert d["types"]["rows"][0] == {"label": "Multiple choice", "value": 3, "pct": 60.0}
    assert [(r["label"], r["value"]) for r in d["points"]["rows"]] == [("100", 1), ("200", 2), ("300", 2)]


def test_months_fill_gaps_and_tags_count_questions():
    d = dash()
    assert [r["label"] for r in d["months"]["rows"]] == ["Aug 2026", "Sep 2026", "Oct 2026", "Nov 2026"]
    assert [r["value"] for r in d["months"]["rows"]] == [2, 0, 0, 3]
    tags = {r["id"]: (r["value"], r["categories"]) for r in d["tags"]["rows"]}
    assert tags == {"arabic": (3, 1), "science": (3, 1), "other": (2, 1)}
    assert d["tags"]["untagged"] == ["b"]


def test_empty_bank_does_not_crash():
    d = bank_dashboard([], {}, {}, {}, per_game=10)
    assert d["kpis"]["total"] == 0 and d["months"]["rows"] == [] and d["categories"]["rows"] == []


def test_question_bank_page_has_dashboard_and_tabs(client):
    with client.session_transaction() as s:
        s["admin_authenticated"] = True
    html = client.get("/question_bank").get_data(as_text=True)
    assert 'class="qb-dashboard"' in html and 'role="tablist"' in html
    assert 'aria-controls="qb-panel-categories"' in html and 'id="category-tags"' in html
    assert html.count('<details class="chart-table">') == 6     # every chart has a table view
