"""One LLM client for every AI option.

Supports two wire formats:
- "openai":    POST {base_url}/chat/completions  (OpenAI and every
               OpenAI-compatible service: OpenRouter, Gemini, Groq, Ollama...)
- "anthropic": POST {base_url}/messages          (Anthropic Messages API)

Models differ in which parameters they accept (reasoning models reject
temperature, some reject response_format, newer Claude models reject
temperature, output caps vary). Instead of hard-coding every model, the client
sends sensible parameters for the role and, when the API answers 400/422
naming a parameter, drops or adjusts that parameter and retries. What it learns
is remembered per (format, base_url, model) for the life of the process.
"""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

ANTHROPIC_VERSION = "2023-06-01"

# Parameters the client may drop when a model rejects them.
_OPTIONAL_PARAMS = ("temperature", "top_p", "response_format", "reasoning_effort", "seed")

_LEARNED: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
_LEARNED_LOCK = threading.Lock()

_SECRET_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{6,}"), "sk-***"),
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}"), "sk-ant-***"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{10,}"), "AIza***"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{8,}"), r"\1***"),
]


class AIError(Exception):
    """A provider error with a message that is safe to show admins."""


def redact(text: str) -> str:
    out = str(text or "")
    for pat, repl in _SECRET_PATTERNS:
        out = pat.sub(repl, out)
    return out


def is_reasoning_model(api_format: str, model: str) -> bool:
    """OpenAI reasoning families use max_completion_tokens + reasoning_effort."""
    if api_format != "openai":
        return False
    m = (model or "").lower().split("/")[-1]
    return bool(re.match(r"^(o\d|gpt-5)", m))


class LLMClient:
    def __init__(self, runtime: Dict[str, Any], api_key: str):
        self.api_format = runtime["api_format"]
        self.base_url = (runtime.get("base_url") or "").rstrip("/")
        self.model = runtime["model"]
        self.profile = runtime["profile"]
        self.max_output_tokens = int(runtime.get("max_output_tokens") or 12000)
        self.timeout = float(runtime.get("timeout") or 120)
        self.api_key = (api_key or "").strip()
        if not self.base_url:
            raise AIError("No API base URL is configured for this AI option.")
        if not self.model:
            raise AIError("No model is selected for this AI option.")
        self._learn_key = (self.api_format, self.base_url, self.model)

    # ------------------------------------------------------------------ HTTP
    def _headers(self) -> Dict[str, str]:
        if self.api_format == "anthropic":
            return {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION,
                    "content-type": "application/json"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        if "openrouter.ai" in self.base_url:
            headers["X-Title"] = "Avirta"
        return headers

    def _post(self, url: str, body: Dict[str, Any], timeout: float) -> requests.Response:
        """POST with retries on 429/5xx/network errors (honours Retry-After)."""
        last_exc: Optional[Exception] = None
        for attempt in range(4):
            try:
                resp = requests.post(url, headers=self._headers(), json=body,
                                     timeout=(10, timeout))
            except requests.RequestException as exc:
                last_exc = exc
                time.sleep(2 ** attempt)
                continue
            if resp.status_code in (429, 500, 502, 503, 504, 529) and attempt < 3:
                retry_after = resp.headers.get("retry-after")
                try:
                    wait = min(30.0, float(retry_after)) if retry_after else 2.0 ** (attempt + 1)
                except ValueError:
                    wait = 2.0 ** (attempt + 1)
                time.sleep(wait)
                continue
            return resp
        raise AIError(redact(f"Could not reach the AI service: {last_exc}"))

    # --------------------------------------------------------------- request
    def _learned(self) -> Dict[str, Any]:
        with _LEARNED_LOCK:
            return dict(_LEARNED.get(self._learn_key, {}))

    def _remember(self, **updates) -> None:
        with _LEARNED_LOCK:
            entry = _LEARNED.setdefault(self._learn_key, {"drop": set()})
            for k, v in updates.items():
                if k == "drop":
                    entry["drop"] = set(entry.get("drop", set())) | set(v)
                else:
                    entry[k] = v

    def _build_body(self, system: str, user: str, role: str, max_tokens: int, json_mode: bool) -> Dict[str, Any]:
        params = self.profile.get(role, {})
        learned = self._learned()
        drop = learned.get("drop", set())
        max_tokens = min(max_tokens, learned.get("max_tokens_cap", max_tokens))

        if self.api_format == "anthropic":
            body: Dict[str, Any] = {
                "model": self.model,
                "max_tokens": max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }
            if "temperature" not in drop and params.get("temperature") is not None:
                body["temperature"] = float(params["temperature"])
            return body

        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        token_field = learned.get("token_field") or (
            "max_completion_tokens" if is_reasoning_model(self.api_format, self.model) else "max_tokens")
        body[token_field] = max_tokens
        if is_reasoning_model(self.api_format, self.model):
            if "reasoning_effort" not in drop and params.get("reasoning_effort"):
                body["reasoning_effort"] = params["reasoning_effort"]
        elif "temperature" not in drop and params.get("temperature") is not None:
            body["temperature"] = float(params["temperature"])
        if json_mode and "response_format" not in drop:
            body["response_format"] = {"type": "json_object"}
        return body

    def _adapt(self, body: Dict[str, Any], status: int, err_text: str) -> bool:
        """Adjust ``body`` after a 400/422 that names a parameter. True if changed."""
        low = err_text.lower()
        changed = False
        # max_tokens <-> max_completion_tokens
        if "max_completion_tokens" in low and "max_tokens" in body:
            body["max_completion_tokens"] = body.pop("max_tokens")
            self._remember(token_field="max_completion_tokens")
            return True
        # Output cap too large: pick the largest number mentioned below our value.
        for field in ("max_tokens", "max_completion_tokens"):
            if field in body and ("max_tokens" in low or "max_completion_tokens" in low or "output tokens" in low):
                nums = [int(n) for n in re.findall(r"\b(\d{3,6})\b", err_text)]
                smaller = [n for n in nums if 256 <= n < body[field]]
                if smaller:
                    body[field] = max(smaller)
                    self._remember(max_tokens_cap=body[field])
                    return True
        for param in _OPTIONAL_PARAMS:
            if param in body and param.replace("_", " ") in low.replace("_", " "):
                body.pop(param, None)
                self._remember(drop={param})
                changed = True
        if not changed and "json" in low and "response_format" in body:
            body.pop("response_format", None)
            self._remember(drop={"response_format"})
            changed = True
        return changed

    def complete(self, system: str, user: str, role: str = "generate",
                 max_tokens: Optional[int] = None, json_mode: bool = True,
                 timeout: Optional[float] = None) -> Tuple[str, Dict[str, Any]]:
        """Send one request. Returns (text, info) where info has model/finish/usage."""
        if not self.api_key and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
            raise AIError("No API key is configured for this AI option.")
        max_tokens = int(max_tokens or self.max_output_tokens)
        body = self._build_body(system, user, role, max_tokens, json_mode)
        url = f"{self.base_url}/messages" if self.api_format == "anthropic" else f"{self.base_url}/chat/completions"
        call_timeout = timeout or self.timeout

        for _ in range(6):
            resp = self._post(url, body, call_timeout)
            if resp.status_code == 200:
                break
            text = resp.text[:2000]
            if resp.status_code in (400, 422) and self._adapt(body, resp.status_code, text):
                continue
            if resp.status_code in (401, 403):
                raise AIError("The AI service rejected the API key (HTTP %d). Check the key for this option." % resp.status_code)
            if resp.status_code == 404:
                raise AIError(redact(f"Model or endpoint not found (HTTP 404). Check the model name and base URL. {text[:300]}"))
            raise AIError(redact(f"AI service error HTTP {resp.status_code}: {text[:500]}"))
        else:
            raise AIError("The AI service kept rejecting the request parameters.")

        try:
            data = resp.json()
        except ValueError:
            raise AIError("The AI service returned a response that is not JSON.")
        return self._extract_text(data)

    def _extract_text(self, data: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        if self.api_format == "anthropic":
            parts = [b.get("text", "") for b in data.get("content", []) or [] if b.get("type") == "text"]
            finish = data.get("stop_reason")
            usage = data.get("usage") or {}
        else:
            choices = data.get("choices") or []
            if not choices:
                raise AIError(redact(f"The AI service returned no choices: {json.dumps(data)[:300]}"))
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if isinstance(content, list):  # some compatible APIs return content parts
                parts = [p.get("text", "") for p in content if isinstance(p, dict)]
            else:
                parts = [content or ""]
            finish = choices[0].get("finish_reason")
            usage = data.get("usage") or {}
        text = "".join(parts).strip()
        info = {"model": data.get("model") or self.model, "finish": finish, "usage": usage,
                "truncated": finish in ("length", "max_tokens")}
        if not text:
            hint = " (the output limit was reached; raise Max output tokens)" if info["truncated"] else ""
            raise AIError("The AI service returned an empty answer" + hint + ".")
        return text, info

    def complete_json(self, system: str, user: str, role: str = "generate",
                      max_tokens: Optional[int] = None, list_key: Optional[str] = None) -> Tuple[Any, Dict[str, Any]]:
        """Like complete() but parses JSON; salvages complete objects from truncated output."""
        text, info = self.complete(system, user, role=role, max_tokens=max_tokens, json_mode=True)
        try:
            return parse_json(text), info
        except ValueError:
            if list_key:
                salvaged = salvage_objects(text)
                if salvaged:
                    info["salvaged"] = True
                    return {list_key: salvaged}, info
            raise AIError("The AI answer was not valid JSON" + (" (it was cut off - raise Max output tokens)" if info.get("truncated") else "") + ".")

    # ------------------------------------------------------------- utilities
    def list_models(self) -> List[str]:
        url = f"{self.base_url}/models"
        params = {"limit": 100} if self.api_format == "anthropic" else None
        try:
            resp = requests.get(url, headers=self._headers(), params=params, timeout=(10, 20))
        except requests.RequestException as exc:
            raise AIError(redact(f"Could not reach the AI service: {exc}"))
        if resp.status_code in (401, 403):
            raise AIError("The AI service rejected the API key.")
        if resp.status_code != 200:
            raise AIError(redact(f"Could not list models (HTTP {resp.status_code}): {resp.text[:200]}"))
        items = (resp.json() or {}).get("data") or []
        ids = [str(m.get("id")) for m in items if isinstance(m, dict) and m.get("id")]
        if "api.openai.com" in self.base_url:
            skip = ("embedding", "tts", "whisper", "dall-e", "image", "audio", "realtime", "transcribe",
                    "moderation", "search", "davinci", "babbage", "computer-use", "codex")
            ids = [i for i in ids if re.match(r"^(gpt-|o\d|chatgpt)", i) and not any(s in i for s in skip)]
        return sorted(set(ids), reverse=True)

    def test(self) -> Dict[str, Any]:
        start = time.time()
        data, info = self.complete_json(
            "You are a connectivity check. Reply with JSON only.",
            'Return exactly this JSON object: {"ok": true, "capital_of_france": "<answer>"}',
            role="verify", max_tokens=1200, list_key=None)
        latency = int((time.time() - start) * 1000)
        answer = str((data or {}).get("capital_of_france", "")) if isinstance(data, dict) else ""
        return {"ok": True, "latency_ms": latency, "model": info.get("model"),
                "sample_correct": "paris" in answer.lower()}


# ---------------------------------------------------------------- JSON utils
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def parse_json(text: str) -> Any:
    s = _FENCE.sub("", (text or "").strip()).strip()
    try:
        return json.loads(s)
    except ValueError:
        pass
    # Find the first balanced {...} or [...] block.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(s)):
                ch = s[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == opener:
                    depth += 1
                elif ch == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(s[start:i + 1])
                        except ValueError:
                            break
            start = s.find(opener, start + 1)
    raise ValueError("no JSON found")


def salvage_objects(text: str) -> List[Dict[str, Any]]:
    """Recover complete {...} objects that contain a "question" key from cut-off output."""
    out: List[Dict[str, Any]] = []
    s = text or ""
    i = 0
    while True:
        start = s.find("{", i)
        if start == -1:
            break
        depth, in_str, esc, end = 0, False, False, -1
        for j in range(start, len(s)):
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = j
                    break
        if end == -1:
            # Unclosed (e.g. the cut-off outer {"questions": [...): look inside it.
            i = start + 1
            continue
        chunk = s[start:end + 1]
        try:
            obj = json.loads(chunk)
            if isinstance(obj, dict) and ("question" in obj or "id" in obj):
                out.append(obj)
                i = end + 1
                continue
        except ValueError:
            pass
        i = start + 1
    return out
