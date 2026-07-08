from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ModelConfig:
    id: str
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


def load_settings(path: str = "config/settings.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = data["models"]
    return Settings(
        analyst=ModelConfig(**models["analyst"]),
        triage=ModelConfig(**models["triage"]),
        discovery=DiscoveryConfig(**(data.get("discovery") or {})),
        retrieval=RetrievalConfig(**(data.get("retrieval") or {})),
    )
