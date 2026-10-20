from charta.core.config import AppConfig
from charta.core.llm import LLMClient, llm_ping


def test_config_defaults(tmp_path):
    cfg = AppConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.port == 8123 and cfg.generation_model
    assert cfg.llm_base_url.startswith("http") and cfg.llm_base_url.endswith("/v1")
    assert cfg.llm_provider == "ollama"


def test_provider_fills_default_base_url(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\nprovider = "openai"\n')
    assert AppConfig.load(cfg_file).llm_base_url == "https://api.openai.com/v1"


def test_provider_wins_over_a_stale_default_base_url(tmp_path):
    """Flipping provider but leaving the ollama URL must not keep hitting localhost.

    This is the exact trap the shipped config.toml set: an explicit base_url
    outranked `provider`, so `provider = "openrouter"` still called ollama and
    the UI reported the AI engine offline.
    """
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\nprovider = "openrouter"\n'
                        'base_url = "http://localhost:11434/v1"\n')
    assert AppConfig.load(cfg_file).llm_base_url == "https://openrouter.ai/api/v1"


def test_custom_base_url_is_kept(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\nprovider = "openrouter"\n'
                        'base_url = "http://192.168.1.9:8080/v1"\n')
    assert AppConfig.load(cfg_file).llm_base_url == "http://192.168.1.9:8080/v1"


def test_explicit_base_url_for_the_same_provider_is_kept(tmp_path):
    cfg_file = tmp_path / "config.toml"
    cfg_file.write_text('[llm]\nprovider = "ollama"\n'
                        'base_url = "http://127.0.0.1:11435/v1"\n')
    assert AppConfig.load(cfg_file).llm_base_url == "http://127.0.0.1:11435/v1"


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARTA_BASE_URL", "http://127.0.0.1:1234/v1")
    monkeypatch.setenv("CHARTA_API_KEY", "sk-test")
    monkeypatch.setenv("CHARTA_MODEL", "llama3.2")
    cfg = AppConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.llm_base_url == "http://127.0.0.1:1234/v1"
    assert cfg.llm_api_key == "sk-test"
    assert cfg.generation_model == "llama3.2"


def test_repo_config_toml_is_valid():
    cfg = AppConfig.load()
    assert cfg.llm_provider and cfg.llm_base_url.startswith("http")
    assert cfg.vision is True and cfg.mode == "suggest"


def test_llm_graceful_never_raises():
    c = LLMClient()
    r = c.generate("hi", json_mode=True)
    # either works (provider up) or graceful fallback — never raises
    assert isinstance(r.ok, bool)
    assert r.text or r.error
    assert isinstance(llm_ping("http://localhost:9/v1"), bool)
