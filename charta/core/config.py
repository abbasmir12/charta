"""Central config: everything configurable lives in config.toml (repo root).

Environment overrides (handy for CI / CI secrets / one-off runs):
    CHARTA_BASE_URL    -> [llm] base_url
    CHARTA_API_KEY     -> [llm] api_key (fallback: OPENAI_API_KEY for cloud providers)
    CHARTA_MODEL       -> [models] generation
"""
from __future__ import annotations

import os
import pathlib
import sys
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


def default_state_dir() -> pathlib.Path:
    """Per-user app state (window geometry, logs). Never inside a watched folder."""
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or pathlib.Path.home()
        return pathlib.Path(base) / "Charta"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return pathlib.Path(xdg) / "charta" if xdg else pathlib.Path.home() / ".config" / "charta"


@dataclass
class AppConfig:
    port: int = 8123
    host: str = "127.0.0.1"
    state_dir: str = ""
    debug: bool = False
    mica: bool = True
    llm_provider: str = "ollama"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str = ""
    generation_model: str = "gemma4:e4b"
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
        file_url = str(llm.get("base_url", "")).strip()
        # A base_url equal to a *different* provider's stock default is almost
        # always a stale template value (e.g. the ollama URL left in place after
        # switching `provider` to openrouter). Let `provider` win in that case; a
        # genuine custom/self-hosted URL never matches a known default, so it is
        # always kept.
        if file_url and provider in PROVIDER_BASE_URLS:
            stock = {url.rstrip("/") for url in PROVIDER_BASE_URLS.values()}
            fresh = file_url.rstrip("/")
            if fresh in stock and fresh != PROVIDER_BASE_URLS[provider].rstrip("/"):
                file_url = ""
        base_url = (env_url or file_url
                    or PROVIDER_BASE_URLS.get(provider, PROVIDER_BASE_URLS["ollama"]))
        api_key = os.environ.get("CHARTA_API_KEY", "") or str(llm.get("api_key", ""))
        if not api_key and provider in _CLOUD_PROVIDERS:
            api_key = os.environ.get("OPENAI_API_KEY", "")

        return cls(
            port=int(app.get("port", 8123)),
            host=str(app.get("host", "127.0.0.1")),
            state_dir=os.environ.get("CHARTA_STATE_DIR", "") or str(app.get("state_dir", "")),
            debug=bool(app.get("debug", False)) or os.environ.get("CHARTA_DEBUG", "") not in ("", "0"),
            mica=bool(app.get("mica", True)),
            llm_provider=provider,
            llm_base_url=base_url,
            llm_api_key=api_key,
            generation_model=os.environ.get("CHARTA_MODEL")
            or str(models.get("generation", "gemma4:e4b")),
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

    def state_path(self) -> pathlib.Path:
        """Resolved state directory (configured, else per-platform default)."""
        return (pathlib.Path(self.state_dir).expanduser() if self.state_dir
                else default_state_dir())


def config_path() -> pathlib.Path:
    """The config.toml actually in use (repo root, else cwd)."""
    return _default_path()


def _default_path() -> pathlib.Path:
    # config.toml at repo root (parent of charta pkg) or cwd fallback
    here = pathlib.Path(__file__).resolve()
    for parent in [here.parent.parent, pathlib.Path.cwd()]:
        cand = parent / "config.toml"
        if cand.exists():
            return cand
    return pathlib.Path.cwd() / "config.toml"
