"""Avirta AI engine: one provider-agnostic layer for question generation and
fact-checking.

Modules:
- config:    the three AI options (ChatGPT, Claude, own key), quality profiles,
             and the settings stored in game_settings['ai_config'].
- keys:      API key storage (Google Secret Manager, env, local dev file).
- client:    a single LLM client for OpenAI-format and Anthropic-format APIs
             that adapts to whatever parameters the chosen model accepts.
- textnorm:  Arabic/English normalization and near-duplicate detection.
- checks:    deterministic structure checks for a question.
- prompts:   model-agnostic prompts (generate, blind solve, fact-check, review).
- generator: the generation pipeline (generate -> check -> de-duplicate -> verify).
- validator: fact-checks existing bank categories and applies approved fixes.
"""
