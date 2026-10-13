"""Central config: everything configurable lives in config.toml (repo root)."""
from __future__ import annotations

import pathlib
from dataclasses import dataclass, field

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore


@dataclass
class AppConfig:
    port: int = 8123
    host: str = "127.0.0.1"
    generation_model: str = "gemma3:4b"
    embedding_model: str = "nomic-embed-text"
    llm_timeout: int = 60
    llm_retries: int = 1
    ollama_host: str = "http://localhost:11434"
    stable_seconds: float = 2.0
    mode: str = "suggest"
    exclude_sensitive: bool = True
    voice_provider: str = "local"
    whisper_model: str = "small"

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "AppConfig":
        cfg_path = path or _default_path()
        data: dict = {}
        if cfg_path.exists():
            with open(cfg_path, "rb") as f:
                data = tomllib.load(f)
        app = data.get("app", {})
        models = data.get("models", {})
        ollama = data.get("ollama", {})
        watcher = data.get("watcher", {})
        safety = data.get("safety", {})
        voice = data.get("voice", {})
        return cls(
            port=int(app.get("port", 8123)),
            host=str(app.get("host", "127.0.0.1")),
            generation_model=str(models.get("generation", "gemma3:4b")),
            embedding_model=str(models.get("embedding", "nomic-embed-text")),
            llm_timeout=int(models.get("timeout_seconds", 60)),
            llm_retries=int(models.get("retries", 1)),
            ollama_host=str(ollama.get("host", "http://localhost:11434")),
            stable_seconds=float(watcher.get("stable_seconds", 2.0)),
            mode=str(safety.get("mode", "suggest")),
            exclude_sensitive=bool(safety.get("exclude_sensitive_from_index", True)),
            voice_provider=str(voice.get("provider", "local")),
            whisper_model=str(voice.get("whisper_model", "small")),
        )


def _default_path() -> pathlib.Path:
    # config.toml at repo root (parent of charta pkg) or cwd fallback
    here = pathlib.Path(__file__).resolve()
    for parent in [here.parent.parent, pathlib.Path.cwd()]:
        cand = parent / "config.toml"
        if cand.exists():
            return cand
    return pathlib.Path.cwd() / "config.toml"
