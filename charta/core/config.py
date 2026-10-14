"""Central config: everything configurable lives in config.toml (repo root).

Environment overrides (handy for CI / CI secrets / one-off runs):
    CHARTA_BASE_URL    -> [llm] base_url
    CHARTA_API_KEY     -> [llm] api_key (fallback: OPENAI_API_KEY for cloud providers)
    CHARTA_MODEL       -> [models] generation
    CHARTA_EMBED_MODEL -> [models] embedding
"""
from __future__ import annotations

import os
import pathlib
from dataclasses import dataclass

try:
    import tomllib  # py3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

# Providers we know a default base_url for. `custom` = whatever you point at.
PROVIDER_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
    "together": "https://api.together.xyz/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

# Cloud providers: safe to pick up OPENAI_API_KEY from the environment.
_CLOUD_PROVIDERS = {"openai", "openrouter", "groq", "together", "deepseek"}


@dataclass
class AppConfig:
    port: int = 8123
    host: str = "127.0.0.1"
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    generation_model: str = "gemma3:4b"
    embedding_model: str = "nomic-embed-text"
    vision_model: str = ""  # defaults to generation_model when blank
    vision: bool = True  # read images/scanned PDFs with a vision model
    llm_timeout: int = 60
    llm_retries: int = 1
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
        llm = data.get("llm", {})
        watcher = data.get("watcher", {})
        safety = data.get("safety", {})
        voice = data.get("voice", {})

        provider = str(llm.get("provider", "ollama")).lower()
        env_url = os.environ.get("CHARTA_BASE_URL", "")
        base_url = (env_url or str(llm.get("base_url", ""))
                    or PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["ollama"]))
        api_key = os.environ.get("CHARTA_API_KEY", "") or str(llm.get("api_key", ""))
        if not api_key and provider in _CLOUD_PROVIDERS:
            api_key = os.environ.get("OPENAI_API_KEY", "")

        return cls(
            port=int(app.get("port", 8123)),
            host=str(app.get("host", "127.0.0.1")),
            llm_provider=provider,
            llm_base_url=base_url,
            llm_api_key=api_key,
            generation_model=os.environ.get("CHARTA_MODEL")
            or str(models.get("generation", "gemma3:4b")),
            embedding_model=os.environ.get("CHARTA_EMBED_MODEL")
            or str(models.get("embedding", "nomic-embed-text")),
            vision_model=str(models.get("vision", "")),
            vision=bool(llm.get("vision", True)),
            llm_timeout=int(models.get("timeout_seconds", 60)),
            llm_retries=int(models.get("retries", 1)),
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
