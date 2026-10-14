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
