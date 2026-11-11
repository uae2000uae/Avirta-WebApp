"""Optional Wikipedia reference notes for a topic (one API request, best-effort)."""
from __future__ import annotations

import re
from typing import Dict, List

import requests

_UA = {"User-Agent": "AvirtaTrivia/2.0 (trivia question generator)"}


def wikipedia_notes(topic: str, language: str = "arabic", pages: int = 6, max_notes: int = 40) -> Dict:
    """Return {"sources": [{title,url}], "facts": [{fact, source_title, source_url}]}.

    Uses the MediaWiki search generator with intro extracts so a single request
    returns several related pages. Any failure returns empty lists.
    """
    lang = "ar" if str(language).lower().startswith("ar") else "en"
    topic = (topic or "").strip()
    empty = {"sources": [], "facts": []}
    if not topic:
        return empty
    params = {
        "action": "query", "format": "json", "formatversion": 2,
        "generator": "search", "gsrsearch": topic, "gsrlimit": pages,
        "prop": "extracts|info", "exintro": 1, "explaintext": 1, "exlimit": pages,
        "inprop": "url", "redirects": 1,
    }
    try:
        resp = requests.get(f"https://{lang}.wikipedia.org/w/api.php", params=params, headers=_UA, timeout=15)
        if resp.status_code != 200:
            return empty
        page_list = (resp.json().get("query") or {}).get("pages") or []
    except Exception:
        return empty
    page_list.sort(key=lambda p: p.get("index", 99))
    sources, facts = [], []
    for page in page_list:
        text = page.get("extract") or ""
        if not text:
            continue
        title, url = page.get("title", ""), page.get("fullurl", "")
        sources.append({"title": title, "url": url})
        for sentence in re.split(r"(?<=[.!?؟])\s+", text):
            sentence = sentence.strip()
            if 50 <= len(sentence) <= 400:
                facts.append({"fact": sentence, "source_title": title, "source_url": url})
    return {"sources": sources, "facts": facts[:max_notes]}
