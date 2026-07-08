from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Qwen ids match Nexus's validated stack: T2/fast = qwen3.6-flash (triage),
# benchmark reader = qwen3.7-plus (Nexus/docs/architecture.md), T3/strong = qwen3.7-max.
DEFAULT_TRIAGE_MODEL_ID = "qwen3.6-flash"
DEFAULT_ANALYST_MODEL_ID = "qwen3.7-plus"
DEFAULT_LLM_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

# The substrate reuses Nexus's settings/LLMClient, which read QWEN_CLOUD_API_KEY
# from Nexus/.env. PA references the same name so there is one source of truth.
SECRET_ENV_VARS: tuple[str, ...] = (
    "ANTHROPIC_API_KEY",
    "QWEN_CLOUD_API_KEY",
    "OPENROUTER_API_KEY",
    "PERPLEXITY_API_KEY",
    "TELEGRAM_BOT_TOKEN",
)


def get_qwen_api_key() -> str:
    return os.environ.get("QWEN_CLOUD_API_KEY", "")


def get_llm_base_url() -> str:
    return os.environ.get("LLM_BASE_URL", DEFAULT_LLM_BASE_URL)


@dataclass
class ModelConfig:
    id: str = ""
    provider: str = "qwen"
    thinking: bool = False


@dataclass
class DiscoveryConfig:
    provider: str = "openrouter_web"
    model: str | None = None


@dataclass
class RetrievalConfig:
    embeddings_enabled: bool = False
    embeddings_provider: str = "voyage"
    embedding_model: str = "voyage-3.5"
    require_fts_failure: bool = True


@dataclass
class Settings:
    analyst: ModelConfig
    triage: ModelConfig
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)


def _parse_model_config(raw: dict, *, default_id: str) -> ModelConfig:
    return ModelConfig(
        id=raw.get("id", default_id),
        provider=raw.get("provider", "qwen"),
        thinking=raw.get("thinking", False),
    )


def load_settings(path: str = "config/settings.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = data["models"]
    return Settings(
        analyst=_parse_model_config(models["analyst"], default_id=DEFAULT_ANALYST_MODEL_ID),
        triage=_parse_model_config(models["triage"], default_id=DEFAULT_TRIAGE_MODEL_ID),
        discovery=DiscoveryConfig(**(data.get("discovery") or {})),
        retrieval=RetrievalConfig(**(data.get("retrieval") or {})),
    )
