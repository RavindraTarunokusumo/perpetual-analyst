from __future__ import annotations

import os
from pathlib import Path

import openai
from dotenv import load_dotenv

load_dotenv()

_system_prompt: str | None = None
_PROMPT_PATH = Path(__file__).parent / "prompts" / "analyst_system.md"


def load_system_prompt() -> str:
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = _PROMPT_PATH.read_text(encoding="utf-8")
    return _system_prompt


def make_client(provider: str = "openrouter") -> openai.OpenAI:
    if provider in {"openrouter", "openrouter_web"}:
        api_key_env = "OPENROUTER_API_KEY"
        base_url = "https://openrouter.ai/api/v1"
    elif provider == "perplexity":
        api_key_env = "PERPLEXITY_API_KEY"
        base_url = "https://api.perplexity.ai"
    elif provider in {"qwen", "dashscope"}:
        api_key_env = "QWEN_CLOUD_API_KEY"
        base_url = os.environ.get("LLM_BASE_URL") or (
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
        )
    else:
        raise RuntimeError(f"Unsupported client provider: {provider}")

    api_key = os.environ.get(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"{api_key_env} is not set — add it to .env or set it in the environment"
        )
    return openai.OpenAI(
        base_url=base_url,
        api_key=api_key,
    )


def with_cache_control(messages: list[dict]) -> list[dict]:
    """Return a copy of messages with an ephemeral cache_control breakpoint on the system
    prompt, so OpenRouter/Anthropic can cache the stable prefix across runs.

    The OpenAI-style string content is converted to a single text content-block carrying
    cache_control. Non-system messages are passed through unchanged. Used by the weekly
    (run_weekly_review) call path.
    """
    result = []
    for msg in messages:
        if msg["role"] == "system":
            result.append(
                {
                    **msg,
                    "content": [
                        {
                            "type": "text",
                            "text": msg["content"],
                            "cache_control": {"type": "ephemeral"},
                        }
                    ],
                }
            )
        else:
            result.append(dict(msg))
    return result
