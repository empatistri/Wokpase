from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib


CONFIG_PATH = Path.home() / ".config" / "wokpase" / "config.toml"


@dataclass(frozen=True)
class AgentConfig:
    provider: str
    model: str


@dataclass(frozen=True)
class AppConfig:
    planner: AgentConfig
    executor: AgentConfig

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "AppConfig":
        data: dict[str, Any] = {}
        if path.exists():
            with path.open("rb") as config_file:
                parsed = tomllib.load(config_file)
            data = parsed.get("agents", {})

        def agent_config(name: str, provider: str, model: str) -> AgentConfig:
            values = data.get(name, {})
            return AgentConfig(
                provider=str(values.get("provider", provider)).lower(),
                model=str(values.get("model", model)),
            )

        return cls(
            planner=agent_config("planner", "gemini", "gemini-2.0-flash"),
            executor=agent_config("executor", "groq", "llama-3.3-70b-versatile"),
        )

    def api_key(self, provider: str) -> str:
        env_names = {
            "gemini": "WOKPASE_GEMINI_KEY",
            "groq": "WOKPASE_GROQ_KEY",
            "openrouter": "WOKPASE_OPENROUTER_KEY",
        }
        if provider not in env_names:
            raise ValueError(f"provider tidak didukung: {provider}")
        key = os.environ.get(env_names[provider])
        if not key:
            raise ValueError(
                f"API key {provider} belum tersedia; set {env_names[provider]}"
            )
        return key
