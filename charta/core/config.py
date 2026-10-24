"""Central config: everything configurable lives in config.toml (yours).

Search order for the file: CHARTA_CONFIG → next to the installed package →
the per-user state dir → the current directory. config.toml is git-ignored, so
a `git pull` can never undo your settings.

Environment overrides (handy for CI / CI secrets / one-off runs):
    CHARTA_BASE_URL    -> [llm] base_url
    CHARTA_API_KEY     -> [llm] api_key (the file wins; this is the fallback)
    CHARTA_MODEL       -> [models] generation
    CHARTA_CONFIG      -> the config.toml to read
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
_CLOUD_PROVIDERS = {"openai", "openrouter", "groq", "together", "deepseek", "elevenlabs"}


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
    history: bool = True  # keep a private git history per watched folder
    voice_provider: str = "local"
    whisper_model: str = "small"
    voice_api_key: str = ""

    @classmethod
    def load(cls, path: pathlib.Path | None = None) -> "AppConfig":
        cfg_path = path or config_path()
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
        # The key comes from your config.toml first, then the environment.
        # config.toml belongs to the machine (it is git-ignored), so a key in
        # it never leaves your disk; CHARTA_API_KEY is the fallback for
        # machines that keep secrets out of files.
        api_key = str(llm.get("api_key", "")).strip()
        if not api_key:
            api_key = os.environ.get("CHARTA_API_KEY", "").strip()
        if not api_key and provider in _CLOUD_PROVIDERS:
            api_key = os.environ.get("OPENAI_API_KEY", "").strip()

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
            history=(os.environ.get("CHARTA_HISTORY", "") not in ("", "0", "false"))
            and bool(app.get("history", True)),
            voice_provider=str(voice.get("provider", "local")),
            whisper_model=str(voice.get("whisper_model", "small")),
        )

    def state_path(self) -> pathlib.Path:
        """Resolved state directory (configured, else per-platform default)."""
        return (pathlib.Path(self.state_dir).expanduser() if self.state_dir
                else default_state_dir())


def config_path() -> pathlib.Path:
    """The config.toml in use.

    One file, one place. The search order:
      1. ``CHARTA_CONFIG`` — an explicit path, if you set it
      2. ``config.toml`` next to the installed package (a checkout)
      3. ``config.toml`` in the per-user state dir (an installed app)
      4. ``config.toml`` in the current directory

    ``config.toml`` is git-ignored: it belongs to the machine, and a
    ``git pull`` can never bring back the file you edited.
    """
    for candidate in config_candidates():
        if candidate.exists():
            return candidate
    return config_candidates()[-1]


def config_candidates() -> list[pathlib.Path]:
    """Every place a config.toml is looked for, in order."""
    explicit = os.environ.get("CHARTA_CONFIG", "").strip()
    here = pathlib.Path(__file__).resolve()
    candidates: list[pathlib.Path] = []
    if explicit:
        candidates.append(pathlib.Path(explicit))
    candidates.append(here.parent.parent / "config.toml")
    candidates.append(AppConfig().state_path().parent / "config.toml")
    candidates.append(pathlib.Path.cwd() / "config.toml")
    return candidates


def config_files() -> list[pathlib.Path]:
    """The config file in use (a single file — Charta has exactly one)."""
    return [config_path()]
