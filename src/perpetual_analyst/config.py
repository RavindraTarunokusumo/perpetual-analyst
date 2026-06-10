from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class ModelConfig:
    id: str
    thinking: bool = False


@dataclass
class Settings:
    analyst: ModelConfig
    triage: ModelConfig


def load_settings(path: str = "config/settings.yaml") -> Settings:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    models = data["models"]
    return Settings(
        analyst=ModelConfig(**models["analyst"]),
        triage=ModelConfig(**models["triage"]),
    )
