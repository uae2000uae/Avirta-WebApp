"""Model-agnostic prompts for Avirta.

Design notes (why the prompts look like this):
- Plain instructions + one explicit JSON schema work across OpenAI, Claude,
  Gemini, Llama, Mistral, DeepSeek etc. No provider-specific features.
- Factuality is enforced by process, not by asking nicely:
    1. the writer must state the single verifiable fact behind each answer and
       must drop anything it is not certain of;
    2. an independent *blind* solver answers each question without seeing the
       answer key (catches wrong keys and ambiguous wording);
    3. a fact-checker reviews every disagreement and may fix or reject.
- The game is read aloud and judged by a host, so "exactly one defensible
  answer" matters as much as correctness.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Optional

DIFFICULTY_RUBRIC = """DIFFICULTY - "points" is the difficulty, judged for a general adult audience in the Gulf/Arab region:
- 100 very easy: common knowledge most people know instantly.
- 200 easy: well known, but needs a moment of recall.
- 300 medium: needs real knowledge of the topic or linking two facts.
- 400 hard: enthusiasts know it; specific names, dates or comparisons.
- 500 very hard: expert-level detail - still a single clear fact, never a trick."""

TYPE_RULES = """QUESTION TYPES:
- "multiple_choice": exactly 4 options of the same kind (all people, all years, all cities...) and similar length.
  Exactly one is correct; the other three are definitely wrong yet plausible. Never "all/none of the above".
  "correct_answer" must be copied character-for-character from "options".
- "true_false": a single clear statement (not a question) that is unambiguously true or false.
  A false statement changes exactly one key detail of a true fact. No double negatives, no "always/never" traps.
  "correct_answer" is exactly "True" or "False" (in English, even for Arabic questions). Keep True and False roughly balanced.
- "text": the answer is a short canonical name, number or term (1-4 words) that a host can judge instantly.
  Put common alternative spellings or names in "acceptable_answers"."""

FACT_RULES = """FACTUAL ACCURACY - the most important rules:
1. Use only facts that are well established and verifiable in mainstream reference works. If you are not
   completely certain, leave the question out. Fewer questions are better than one wrong question.
2. Avoid facts that change over time (current office holders, "current/latest", records, rankings, populations,
   prices, recent statistics) unless the question fixes the date, e.g. "In 1998, ...".
3. Avoid disputed claims, legends, popular misconceptions and approximate numbers. Use superlatives
   ("first", "largest", "only") only when they are undisputed.
4. Names, dates and numbers must be exact.
5. The wording must lead to exactly one defensible answer. Add qualifiers (country, year, field) to remove any
   ambiguity, and never reveal the answer in the question."""


def _lang_rule(language: str) -> str:
    if str(language).lower().startswith("ar"):
        return ("LANGUAGE: write every question, option, answer and explanation in clear Modern Standard Arabic with "
                "correct grammar and spelling. Use the most common Arabic spelling of names. Keep numbers as digits.")
    return "LANGUAGE: write everything in clear, natural English."


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------- generation
GENERATE_SYSTEM = (
    "You write questions for Avirta, a competitive team trivia game. Questions are read aloud by a host who "
    "judges answers, so every question must be 100% correct, unambiguous and fair. You always answer with one "
    "valid JSON object and nothing else."
)


def generation_prompt(*, topic: str, focus: str, count: int, types: List[str], distribution: Dict[int, int],
                      language: str, explanations: bool, avoid: Iterable[str], facts: Optional[List[Dict]] = None,
                      category: str = "") -> str:
    type_line = ("Allowed types: " + ", ".join(types) + ". Mix them roughly evenly."
                 if len(types) > 1 else f'Every question must be of type "{types[0]}".')
    dist = ", ".join(f"{n} x {p} points" for p, n in sorted(distribution.items()) if n)
    parts = [
        f"TOPIC: {topic}",
    ]
    if category and category.strip().lower() != topic.strip().lower():
        parts.append(f"CATEGORY IN THE GAME: {category}")
    if focus:
        parts.append(f"FOCUS FROM THE GAME HOST: {focus}")
    parts += [
        f"TASK: write {count} new trivia questions. Every question must be squarely about the TOPIC.",
        "Cover different sub-topics, people, places and periods; do not ask about the same fact twice.",
        type_line,
        f"Difficulty mix: {dist}.",
        FACT_RULES,
        DIFFICULTY_RUBRIC,
        TYPE_RULES,
        _lang_rule(language),
    ]
    if facts:
        parts.append(
            "REFERENCE NOTES (from Wikipedia; may be incomplete or off-topic). Prefer facts that these notes "
            "confirm, ignore notes that are not about the TOPIC, and never mention the notes in a question:\n"
            + "\n".join(f"- {f.get('fact')}" for f in facts[:40] if f.get("fact"))
        )
    avoid = [a for a in avoid if a][:80]
    if avoid:
        parts.append(
            "ALREADY IN THE GAME - do not repeat these or ask about the same facts in other words:\n"
            + "\n".join(f"- {a}" for a in avoid)
        )
    parts.append(
        "OUTPUT - one JSON object exactly like this (no markdown):\n"
        '{"questions":[{"type":"multiple_choice","question":"...","options":["...","...","...","..."],'
        '"correct_answer":"...","acceptable_answers":[],"explanation":"...","points":300,'
        '"fact":"One plain sentence stating the verified fact the answer depends on.","confidence":"high"}]}\n'
        'Use "options": [] for true_false and text. "confidence" is "high" or "medium"; do not output anything '
        "you would rate lower."
        + ("" if explanations else ' Set "explanation" to "".')
        + (" The explanation is one short sentence that teaches why the answer is right." if explanations else "")
    )
    return "\n\n".join(parts)


# ---------------------------------------------------------------- blind solve
SOLVE_SYSTEM = (
    "You are an expert quiz champion. Answer each trivia question from your own knowledge, independently, "
    "as if you were a contestant. Be honest about uncertainty. Reply with one valid JSON object only."
)


def solve_prompt(items: List[Dict[str, Any]]) -> str:
    """``items``: [{"id", "type", "question", "options"}] - no answers included."""
    return (
        "Answer every question below.\n"
        "- multiple_choice: reply with the exact text of the option you choose.\n"
        '- true_false: reply exactly "True" or "False".\n'
        "- text: reply with the shortest precise answer.\n"
        'Set "ambiguous": true if the question could reasonably have more than one correct answer, '
        "depends on the date, or is unclear; explain briefly in \"note\".\n\n"
        f"QUESTIONS: {_json(items)}\n\n"
        'OUTPUT: {"answers":[{"id":"...","answer":"...","confidence":"high|medium|low","ambiguous":false,"note":""}]}'
    )


# ---------------------------------------------------------------- fact-check
CHECK_SYSTEM = (
    "You are the senior fact-checker for a trivia game. You are skeptical and precise: a question is only kept "
    "when its answer is certainly correct and it has exactly one defensible answer. Reply with one valid JSON "
    "object only."
)


def check_prompt(items: List[Dict[str, Any]], language: str) -> str:
    """``items``: questions with id, answer key, the writer's stated fact and the blind solver's result."""
    return (
        "Each item below is a trivia question with its proposed answer, the writer's supporting fact, and the "
        "answer an independent contestant gave WITHOUT seeing the key.\n\n"
        "For every item decide:\n"
        '- "correct": the proposed answer is certainly right and the question is unambiguous (if the contestant '
        "disagreed, the contestant was simply wrong).\n"
        '- "fixed": there is an error or ambiguity you can repair with certainty (wrong key, wrong option, '
        "missing qualifier, wrong fact in the explanation, wrong points). Return the full corrected question.\n"
        '- "reject": the fact is uncertain, disputed, time-sensitive, a misconception, unverifiable, or the '
        "question cannot be made unambiguous.\n"
        "When in doubt, reject.\n\n"
        + FACT_RULES + "\n\n" + TYPE_RULES + "\n\n" + _lang_rule(language) + "\n\n"
        f"ITEMS: {_json(items)}\n\n"
        'OUTPUT: {"reviews":[{"id":"...","verdict":"correct|fixed|reject","issues":["short reason"],'
        '"question":null}]}\n'
        'For "fixed", "question" is the complete corrected object: {"type","question","options","correct_answer",'
        '"explanation","points"}. Otherwise "question" is null.'
    )


# ---------------------------------------------------------------- bank review
REVIEW_SYSTEM = (
    "You are the senior editor and fact-checker of a trivia game's question bank. You fix what is wrong, "
    "improve what is weak, and remove what cannot be trusted. Reply with one valid JSON object only."
)


def review_prompt(items: List[Dict[str, Any]], *, language: str, category: str,
                  improve_wording: bool, add_explanations: bool, rescore_points: bool) -> str:
    tasks = ["Verify that the answer is certainly correct and that the question has exactly one defensible answer."]
    if improve_wording:
        tasks.append("Fix grammar, spelling and unclear wording without changing what is asked.")
    if add_explanations:
        tasks.append("Add a one-sentence explanation where it is missing or wrong.")
    if rescore_points:
        tasks.append("Correct the points value if it clearly does not match the difficulty rubric.")
    else:
        tasks.append("Keep the existing points value.")
    return (
        f"CATEGORY: {category}\n\n"
        "Review each question from the bank. Where available, an independent contestant's blind answer is "
        "included as evidence - a disagreement means you must check the fact carefully.\n\n"
        "TASKS:\n" + "\n".join(f"- {t}" for t in tasks) + "\n\n"
        "VERDICTS:\n"
        '- "ok": nothing needs to change.\n'
        '- "improve": the facts are right, but wording/explanation/points were improved.\n'
        '- "fix": the answer, an option or a fact was wrong (or the question was ambiguous) and you corrected it '
        "with certainty.\n"
        '- "remove": the question cannot be trusted - uncertain, disputed, time-sensitive, a misconception, or '
        "impossible to make unambiguous.\n\n"
        + FACT_RULES + "\n\n" + DIFFICULTY_RUBRIC + "\n\n" + TYPE_RULES + "\n\n" + _lang_rule(language) + "\n\n"
        f"QUESTIONS: {_json(items)}\n\n"
        'OUTPUT: {"reviews":[{"id":"...","verdict":"ok|improve|fix|remove","issues":["short reason"],'
        '"question":null}]}\n'
        'For "improve" and "fix", "question" is the complete updated object {"type","question","options",'
        '"correct_answer","explanation","points"}; otherwise null. Keep the same type unless it is broken.'
    )
