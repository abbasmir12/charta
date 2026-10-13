from charta.core.config import AppConfig
from charta.core.llm import OllamaClient, ollama_ping


def test_config_defaults(tmp_path):
    cfg = AppConfig.load(tmp_path / "nonexistent.toml")
    assert cfg.port == 8123 and cfg.generation_model
    assert cfg.ollama_host.startswith("http")


def test_ollama_graceful():
    c = OllamaClient()
    r = c.generate("hi", json_mode=True)
    # either works (ollama up) or graceful fallback — never raises
    assert isinstance(r.ok, bool)
    assert r.text or r.error
    assert isinstance(ollama_ping("http://localhost:9"), bool)
