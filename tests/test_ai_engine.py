"""Offline tests for questionmanagement.ai_engine (no network, fake AI service)."""
import json

import pytest

from questionmanagement.ai_engine import checks, client as client_mod, config
from questionmanagement.ai_engine.client import AIError, LLMClient, parse_json, salvage_objects
from questionmanagement.ai_engine.textnorm import DedupIndex, answers_match, normalize


class FakeResponse:
    def __init__(self, status, payload=None, text=None, headers=None):
        self.status_code = status
        self._payload = payload
        self.text = text if text is not None else json.dumps(payload or {})
        self.headers = headers or {}

    def json(self):
        return self._payload


def runtime(api_format="openai", model="gpt-4o-mini", base="https://example.test/v1", quality="accurate"):
    cfg = config.default_ai_config()
    cfg["active"] = "custom"
    cfg["options"]["custom"].update({"api_format": api_format, "base_url": base, "model": model, "quality": quality})
    return config.resolve_runtime(cfg)


@pytest.fixture(autouse=True)
def clear_learned():
    client_mod._LEARNED.clear()
    yield
    client_mod._LEARNED.clear()


def test_normalize_arabic_variants():
    assert normalize("الإمارات العربيّة") == normalize("الامارات العربية")
    assert normalize("٢٠٢٢") == "2022"
    assert answers_match("القاهرة", "قاهره")
    assert not answers_match("15", "16")


def test_dedup_detects_paraphrase_and_same_fact():
    idx = DedupIndex()
    idx.add({"id": "Q1", "question": "What is the capital of France?", "correct_answer": "Paris"})
    assert idx.find_duplicate({"question": "What's the capital city of France?", "correct_answer": "Paris"})
    assert idx.find_duplicate({"question": "Which river flows through Cairo?", "correct_answer": "Nile"}) is None


def test_checks_reject_bad_multiple_choice():
    q = checks.clean_question({"type": "mcq", "question": "Which planet is largest?", "options": ["Mars", "Mars", "Venus"],
                               "correct_answer": "Jupiter", "points": 260})
    problems = checks.check_question(q)
    assert q["points"] == 300
    assert any("4 options" in p for p in problems)
    assert any("not one of the options" in p for p in problems)


def test_true_false_arabic_answer_normalized():
    q = checks.clean_question({"type": "true_false", "question": "القاهرة هي عاصمة مصر.", "correct_answer": "صح", "points": 100})
    assert q["correct_answer"] == "True" and not checks.check_question(q)


def test_parse_json_and_salvage():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"questions": [{"question": "x"}]} thanks') == {"questions": [{"question": "x"}]}
    cut = '{"questions":[{"question":"Q one?","correct_answer":"A"},{"question":"Q two?","correct_ans'
    assert [o["question"] for o in salvage_objects(cut)] == ["Q one?"]


def test_client_drops_rejected_parameter_and_remembers(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(dict(json))
        if "temperature" in json:
            return FakeResponse(400, text='{"error":{"message":"Unsupported parameter: \'temperature\' is not supported with this model."}}')
        return FakeResponse(200, {"model": "m", "choices": [{"message": {"content": '{"ok": true}'}, "finish_reason": "stop"}]})

    monkeypatch.setattr(client_mod.requests, "post", fake_post)
    c = LLMClient(runtime(), "sk-test")
    data, info = c.complete_json("s", "u JSON")
    assert data == {"ok": True}
    assert "temperature" in calls[0] and "temperature" not in calls[1]
    c.complete_json("s", "u JSON")
    assert "temperature" not in calls[2]  # learned


def test_client_switches_token_field(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append(dict(json))
        if "max_tokens" in json:
            return FakeResponse(400, text="Unsupported parameter: 'max_tokens'. Use 'max_completion_tokens' instead.")
        return FakeResponse(200, {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(client_mod.requests, "post", fake_post)
    LLMClient(runtime(model="some-new-model"), "k").complete_json("s", "u")
    assert "max_completion_tokens" in calls[-1]


def test_anthropic_format_and_cap(monkeypatch):
    calls = []

    def fake_post(url, headers=None, json=None, timeout=None):
        calls.append((url, dict(headers), dict(json)))
        if json["max_tokens"] > 8192:
            return FakeResponse(400, text="max_tokens: 12000 > 8192, which is the maximum allowed for this model")
        return FakeResponse(200, {"content": [{"type": "text", "text": '{"ok":1}'}], "stop_reason": "end_turn"})

    monkeypatch.setattr(client_mod.requests, "post", fake_post)
    data, _ = LLMClient(runtime("anthropic", "claude-x"), "sk-ant-key").complete_json("s", "u")
    url, headers, body = calls[-1]
    assert url.endswith("/messages") and headers["x-api-key"] == "sk-ant-key" and body["max_tokens"] == 8192
    assert data == {"ok": 1}


def test_auth_error_message_is_safe(monkeypatch):
    monkeypatch.setattr(client_mod.requests, "post",
                        lambda *a, **k: FakeResponse(401, text="invalid key sk-abcdefghijklmnop"))
    with pytest.raises(AIError) as exc:
        LLMClient(runtime(), "sk-abcdefghijklmnop").complete("s", "u")
    assert "sk-abcdefghijklmnop" not in str(exc.value)


class ScriptedClient:
    """Stands in for LLMClient: answers by inspecting the prompt."""

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, role="generate", max_tokens=None, list_key=None):
        self.calls.append(system[:20])
        if "write questions" in system:
            return {"questions": [
                {"type": "multiple_choice", "question": "Which planet is known as the Red Planet?",
                 "options": ["Mars", "Venus", "Jupiter", "Mercury"], "correct_answer": "Mars",
                 "explanation": "Iron oxide.", "points": 100, "fact": "Mars is called the Red Planet.", "confidence": "high"},
                {"type": "text", "question": "Which element has the chemical symbol O?",
                 "correct_answer": "Oxygen", "explanation": "", "points": 100, "fact": "O is oxygen.", "confidence": "high"},
                {"type": "true_false", "question": "The Pacific is the largest ocean on Earth.",
                 "correct_answer": "True", "explanation": "", "points": 200, "fact": "", "confidence": "high"},
                {"type": "text", "question": "What is the capital of France?", "correct_answer": "Paris",
                 "points": 100, "confidence": "high"},  # duplicate of the bank
            ]}, {}
        if "quiz champion" in system:
            items = json.loads(user.split("QUESTIONS: ", 1)[1].split("\n\nOUTPUT")[0])
            answers = {"Which planet": "Mars", "Which element": "Nitrogen", "The Pacific": "True"}
            return {"answers": [{"id": it["id"], "answer": next(v for k, v in answers.items() if it["question"].startswith(k)),
                                 "confidence": "high", "ambiguous": False} for it in items]}, {}
        if "senior fact-checker" in system:
            items = json.loads(user.split("ITEMS: ", 1)[1].split("\n\nOUTPUT")[0])
            return {"reviews": [{"id": it["id"], "verdict": "correct", "issues": []} for it in items]}, {}
        raise AssertionError("unexpected prompt")


def test_generation_pipeline_dedups_and_verifies(monkeypatch, tmp_path):
    from questionmanagement.ai_engine import batches, generator, service
    monkeypatch.setattr(batches, "BATCH_DIR", str(tmp_path))
    monkeypatch.setattr(generator, "recent_questions", lambda: [])
    monkeypatch.setattr(generator, "wikipedia_notes", lambda *a, **k: {"sources": [], "facts": []})
    job = service.jobs.create("generate")
    fake = ScriptedClient()
    rt = runtime(quality="accurate")
    generator.generate(job, fake, rt, {"topic": "Science", "count": 3, "language": "english", "verify": True},
                       bank_questions=[{"id": "Q1", "question": "What is the capital of France?", "correct_answer": "Paris"}])
    state = service.jobs.get(job)
    assert state["status"] == "done", state
    qs = batches.get_batch(state["batch_id"])
    assert len(qs) == 3
    assert {q["verification"] for q in qs} == {"verified"}
    assert all("France" not in q["question"] for q in qs)
    meta = batches.get_batch_metadata(state["batch_id"])
    assert meta["stats"]["duplicate"] >= 1


def test_validator_review_and_apply(monkeypatch, tmp_path):
    from questionmanagement.ai_engine import service, validator

    class ReviewClient:
        def complete_json(self, system, user, role="generate", max_tokens=None, list_key=None):
            if "quiz champion" in system:
                return {"answers": []}, {}
            items = json.loads(user.split("QUESTIONS: ", 1)[1].split("\n\nOUTPUT")[0])
            out = []
            for it in items:
                if it["id"] == "Q2":
                    out.append({"id": "Q2", "verdict": "fix", "issues": ["wrong answer"],
                                "question": {**it, "correct_answer": "Canberra", "options": ["Sydney", "Canberra", "Melbourne", "Perth"]}})
                else:
                    out.append({"id": it["id"], "verdict": "ok", "issues": []})
            return {"reviews": out}, {}

    monkeypatch.setattr(validator, "RESULTS_DIR", str(tmp_path))
    bank = [
        {"id": "Q1", "category_id": "geo", "type": "text", "question": "What is the capital of Japan?", "correct_answer": "Tokyo", "points": 100},
        {"id": "Q2", "category_id": "geo", "type": "multiple_choice", "question": "What is the capital of Australia?",
         "options": ["Sydney", "Canberra", "Melbourne", "Perth"], "correct_answer": "Sydney", "points": 200},
    ]
    job = service.jobs.create("validate")
    validator.review(job, ReviewClient(), runtime(), groups={"geo": bank}, bank_questions=bank,
                     options={"blind_check": True}, source="bank")
    data = validator.load_results(job)
    by_id = {e["id"]: e for e in data["results"]}
    assert by_id["Q1"]["verdict"] == "ok"
    assert by_id["Q2"]["verdict"] == "fix" and by_id["Q2"]["proposed"]["correct_answer"] == "Canberra"

    class Bank:
        storage_path = str(tmp_path)

        def __init__(self):
            self.questions = {q["id"]: dict(q) for q in bank}
            self.saved = {}

        def load_questions(self):
            pass

        def _save_question(self, qid, q):
            self.saved[qid] = q

    b = Bank()
    counts = validator.apply_changes(job, [{"id": "Q2", "action": "update"}], b)
    assert counts["updated"] == 1 and b.saved["Q2"]["correct_answer"] == "Canberra"


def test_managed_keys_cannot_be_saved_from_the_page():
    from questionmanagement.ai_engine import keys
    for option in ("openai", "anthropic"):
        ok, message = keys.save_key(option, "sk-should-not-be-stored")
        assert not ok and "Secret Manager" in message
        status = keys.key_status(option)
        assert status["managed"] is True
        assert status["hint"] != "…ored"
    assert keys.key_status("custom")["managed"] is False
