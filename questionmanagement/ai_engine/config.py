"""AI options, quality profiles and the stored AI configuration.

Everything the admin page saves lives in one dict, ``game_settings['ai_config']``:

    {
      "active": "openai" | "anthropic" | "custom",
      "options": {
        "openai":    {"model": ..., "quality": ..., "advanced": {...}},
        "anthropic": {"model": ..., "quality": ..., "advanced": {...}},
        "custom":    {"model": ..., "quality": ..., "advanced": {...},
                      "api_format": "openai" | "anthropic", "base_url": ...},
      },
      "use_sources": true,       # Wikipedia grounding for generation
    }

API keys are never stored here (see ``keys.py``).

Each option picks the right request parameters for the game automatically via
a *quality profile*; the "advanced" block only holds explicit overrides.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional

OPTION_IDS = ("openai", "anthropic", "custom")

OPTIONS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "label": "ChatGPT (OpenAI)",
        "api_format": "openai",
        "base_url": "https://api.openai.com/v1",
        "secret_name": "OPENAI_API_KEY",
        "key_managed": True,   # key lives in Google Cloud Secret Manager; never entered on the page
        "default_model": "gpt-5.5",
        # Curated suggestions; the admin page can also load the live list.
        "models": [
            {"id": "gpt-5.5", "label": "GPT-5.5", "note": "Recommended: the most accurate OpenAI model for writing and fact-checking."},
            {"id": "gpt-5.4", "label": "GPT-5.4", "note": "Very accurate reasoning model."},
            {"id": "gpt-5.4-mini", "label": "GPT-5.4 mini", "note": "Budget choice: reasoning model at a fraction of the cost."},
            {"id": "gpt-4.1", "label": "GPT-4.1", "note": "Fast, good instruction following, no reasoning step."},
            {"id": "gpt-4.1-mini", "label": "GPT-4.1 mini", "note": "Fast and cheap."},
            {"id": "gpt-4o", "label": "GPT-4o", "note": "Not recommended: older flagship, may be retired."},
            {"id": "gpt-4o-mini", "label": "GPT-4o mini", "note": "Not recommended: old, weakest at fact-checking, may be retired."},
        ],
    },
    "anthropic": {
        "label": "Claude (Anthropic)",
        "api_format": "anthropic",
        "base_url": "https://api.anthropic.com/v1",
        "secret_name": "ANTHROPIC_API_KEY",
        "key_managed": True,
        "default_model": "claude-opus-5-5",
        "models": [
            {"id": "claude-opus-5-5", "label": "Claude Opus 5.5", "note": "Recommended: the most accurate Claude model."},
            {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5", "note": "Everyday choice: excellent accuracy at half the cost of Opus."},
            {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5", "note": "Fastest and cheapest; not recommended for fact-checking."},
            {"id": "claude-fable-5-2", "label": "Claude Fable 5.2", "note": "Alternative Claude model."},
            {"id": "claude-opus-4-8", "label": "Claude Opus 4.8", "note": "Previous generation; replaced by Opus 5.5."},
            {"id": "claude-sonnet-5", "label": "Claude Sonnet 5", "note": "Previous generation."},
            {"id": "claude-haiku-4-5-20251001", "label": "Claude Haiku 4.5", "note": "Previous generation."},
        ],
    },
    "custom": {
        "label": "Your own AI key",
        "api_format": "openai",
        "base_url": "",
        "secret_name": "CUSTOM_AI_API_KEY",
        "key_managed": False,  # the only option whose key is entered on the admin page
        "default_model": "",
        "models": [],
    },
}

# Known OpenAI-compatible endpoints offered as shortcuts for the custom option.
CUSTOM_ENDPOINT_PRESETS = [
    {"label": "OpenRouter", "api_format": "openai", "base_url": "https://openrouter.ai/api/v1"},
    {"label": "Google Gemini (OpenAI-compatible)", "api_format": "openai", "base_url": "https://generativelanguage.googleapis.com/v1beta/openai"},
    {"label": "Groq", "api_format": "openai", "base_url": "https://api.groq.com/openai/v1"},
    {"label": "DeepSeek", "api_format": "openai", "base_url": "https://api.deepseek.com/v1"},
    {"label": "Mistral", "api_format": "openai", "base_url": "https://api.mistral.ai/v1"},
    {"label": "Together AI", "api_format": "openai", "base_url": "https://api.together.xyz/v1"},
    {"label": "Ollama (local)", "api_format": "openai", "base_url": "http://localhost:11434/v1"},
    {"label": "OpenAI (another account)", "api_format": "openai", "base_url": "https://api.openai.com/v1"},
    {"label": "Anthropic (another account)", "api_format": "anthropic", "base_url": "https://api.anthropic.com/v1"},
]

# Quality profiles: the game-specific parameters each option uses.
#   generate.*  - writing new questions (some variety, still careful)
#   verify.*    - blind solving / fact-checking (as deterministic as possible)
#   chunk       - questions requested per generation call
#   judge       - whether disagreements go to a second fact-check call
#                 (False = reject anything the blind check disagrees with)
QUALITY_PROFILES: Dict[str, Dict[str, Any]] = {
    "accurate": {
        "label": "Most accurate",
        "description": "Smaller batches, careful reasoning and a full fact-check of every question. Recommended.",
        "generate": {"temperature": 0.5, "reasoning_effort": "medium"},
        "verify": {"temperature": 0.0, "reasoning_effort": "high"},
        "chunk": 6,
        "judge": True,
    },
    "balanced": {
        "label": "Balanced",
        "description": "Medium batches with a full fact-check. Faster and cheaper, still safe.",
        "generate": {"temperature": 0.6, "reasoning_effort": "low"},
        "verify": {"temperature": 0.0, "reasoning_effort": "medium"},
        "chunk": 8,
        "judge": True,
    },
    "fast": {
        "label": "Fastest",
        "description": "Large batches and a quick blind check; anything doubtful is dropped instead of re-checked.",
        "generate": {"temperature": 0.7, "reasoning_effort": "low"},
        "verify": {"temperature": 0.0, "reasoning_effort": "low"},
        "chunk": 10,
        "judge": False,
    },
}
DEFAULT_QUALITY = "accurate"

REASONING_EFFORTS = ("minimal", "low", "medium", "high")

# Advanced overrides an admin may set (None/"" = use the quality profile).
ADVANCED_DEFAULTS: Dict[str, Any] = {
    "temperature": None,        # generation temperature override (0.0-1.0)
    "reasoning_effort": None,   # generation effort override for reasoning models
    "max_output_tokens": 12000,  # per call; the client lowers it if the model's cap is smaller
    "timeout": 120,             # seconds per call
}


def default_option_config(option_id: str) -> Dict[str, Any]:
    meta = OPTIONS[option_id]
    cfg = {
        "model": meta["default_model"],
        "quality": DEFAULT_QUALITY,
        "advanced": dict(ADVANCED_DEFAULTS),
    }
    if option_id == "custom":
        cfg["api_format"] = "openai"
        cfg["base_url"] = ""
    return cfg


def default_ai_config() -> Dict[str, Any]:
    return {
        "active": "openai",
        "options": {oid: default_option_config(oid) for oid in OPTION_IDS},
        "use_sources": True,
    }


def _num(value, lo, hi, cast=float):
    if value is None or str(value).strip() == "":
        return None
    try:
        v = cast(float(value))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, v))


def normalize_option_config(option_id: str, raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Return a clean option config, filling defaults and clamping values."""
    cfg = default_option_config(option_id)
    raw = raw if isinstance(raw, dict) else {}
    model = str(raw.get("model") or "").strip()
    if model:
        cfg["model"] = model
    quality = str(raw.get("quality") or "").strip()
    if quality in QUALITY_PROFILES:
        cfg["quality"] = quality
    adv_raw = raw.get("advanced") if isinstance(raw.get("advanced"), dict) else {}
    adv = dict(ADVANCED_DEFAULTS)
    adv["temperature"] = _num(adv_raw.get("temperature"), 0.0, 1.0)
    effort = str(adv_raw.get("reasoning_effort") or "").strip().lower()
    adv["reasoning_effort"] = effort if effort in REASONING_EFFORTS else None
    adv["max_output_tokens"] = _num(adv_raw.get("max_output_tokens"), 1000, 64000, int) or ADVANCED_DEFAULTS["max_output_tokens"]
    adv["timeout"] = _num(adv_raw.get("timeout"), 15, 600, int) or ADVANCED_DEFAULTS["timeout"]
    cfg["advanced"] = adv
    if option_id == "custom":
        fmt = str(raw.get("api_format") or "openai").strip().lower()
        cfg["api_format"] = fmt if fmt in ("openai", "anthropic") else "openai"
        cfg["base_url"] = str(raw.get("base_url") or "").strip().rstrip("/")
    return cfg


def normalize_ai_config(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    cfg = default_ai_config()
    active = str(raw.get("active") or "").strip()
    if active in OPTION_IDS:
        cfg["active"] = active
    opts = raw.get("options") if isinstance(raw.get("options"), dict) else {}
    for oid in OPTION_IDS:
        cfg["options"][oid] = normalize_option_config(oid, opts.get(oid))
    cfg["use_sources"] = bool(raw.get("use_sources", True))
    return cfg


def migrate_legacy_settings(gs: Dict[str, Any]) -> Dict[str, Any]:
    """Build an ai_config from the old flat openai_*/anthropic_* settings."""
    cfg = default_ai_config()
    provider = str(gs.get("ai_provider") or "openai").strip().lower()
    cfg["active"] = provider if provider in ("openai", "anthropic") else "openai"
    if gs.get("openai_model"):
        cfg["options"]["openai"]["model"] = str(gs["openai_model"]).strip()
    if gs.get("anthropic_model"):
        cfg["options"]["anthropic"]["model"] = str(gs["anthropic_model"]).strip()
    for oid, prefix in (("openai", "openai_"), ("anthropic", "anthropic_")):
        t = gs.get(prefix + "request_timeout")
        if t:
            cfg["options"][oid]["advanced"]["timeout"] = max(120, int(float(t)))
    base = str(gs.get("openai_base_url") or "").strip().rstrip("/")
    if base and base != OPTIONS["openai"]["base_url"]:
        # A non-OpenAI base URL was configured: carry it over as the custom option.
        cfg["options"]["custom"].update({"base_url": base, "api_format": "openai",
                                          "model": cfg["options"]["openai"]["model"]})
    return normalize_ai_config(cfg)


def resolve_runtime(ai_config: Dict[str, Any], option_id: Optional[str] = None) -> Dict[str, Any]:
    """Everything a client needs for one option: format, URL, model, profile params.

    The API key is added by the caller (see keys.get_key) so this stays pure.
    """
    cfg = normalize_ai_config(ai_config)
    oid = option_id if option_id in OPTION_IDS else cfg["active"]
    opt = cfg["options"][oid]
    meta = OPTIONS[oid]
    profile = copy.deepcopy(QUALITY_PROFILES[opt["quality"]])
    adv = opt["advanced"]
    if adv.get("temperature") is not None:
        profile["generate"]["temperature"] = adv["temperature"]
    if adv.get("reasoning_effort"):
        profile["generate"]["reasoning_effort"] = adv["reasoning_effort"]
    return {
        "option_id": oid,
        "label": meta["label"],
        "api_format": opt.get("api_format", meta["api_format"]),
        "base_url": (opt.get("base_url") or meta["base_url"]).rstrip("/"),
        "model": opt["model"],
        "secret_name": meta["secret_name"],
        "quality": opt["quality"],
        "profile": profile,
        "max_output_tokens": adv["max_output_tokens"],
        "timeout": adv["timeout"],
        "use_sources": cfg["use_sources"],
    }


def normalize_preset(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Clean a saved preset. Old presets (flat openai_* keys) are converted:
    frequency/presence penalties and other per-call knobs are dropped because the
    engine now sets parameters per role (writing vs fact-checking)."""
    raw = dict(raw or {})
    if "option" not in raw and any(k.startswith("openai_") for k in raw):
        base = str(raw.get("openai_base_url") or "").rstrip("/")
        is_custom = bool(base) and base != OPTIONS["openai"]["base_url"]
        raw = {
            "option": "custom" if is_custom else "openai",
            "model": raw.get("openai_model") or OPTIONS["openai"]["default_model"],
            "quality": DEFAULT_QUALITY,
            "advanced": {"timeout": max(120, int(float(raw.get("openai_request_timeout") or 120)))},
            "api_format": "openai",
            "base_url": base if is_custom else "",
            "note": "Converted from an old preset: penalties removed; writing and fact-checking now use separate settings.",
        }
    option = raw.get("option") if raw.get("option") in OPTION_IDS else "openai"
    cfg = normalize_option_config(option, raw)
    preset = {"option": option, **cfg}
    if raw.get("note"):
        preset["note"] = str(raw["note"])[:300]
    return preset


def frontend_catalog() -> Dict[str, Any]:
    """Static data the settings page needs (option labels, models, profiles)."""
    return {
        "options": copy.deepcopy(OPTIONS),
        "quality_profiles": {k: {"label": v["label"], "description": v["description"]} for k, v in QUALITY_PROFILES.items()},
        "reasoning_efforts": list(REASONING_EFFORTS),
        "custom_presets": CUSTOM_ENDPOINT_PRESETS,
        "advanced_defaults": ADVANCED_DEFAULTS,
    }
