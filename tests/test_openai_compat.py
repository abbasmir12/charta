"""OpenAI-compatible client: any provider, one code path (real HTTP, fake server)."""
from __future__ import annotations

from charta.core.config import AppConfig
from charta.core.llm import LLMClient, llm_ping


def _cfg(fake, **overrides) -> AppConfig:
    values = dict(llm_provider="custom", llm_base_url=fake.base_url, llm_api_key="test-key",
                  generation_model="fake-model", embedding_model="fake-embed",
                  llm_timeout=5, llm_retries=1)
    values.update(overrides)
    return AppConfig(**values)


def test_generate_uses_openai_route_and_auth(fake_provider):
    fake_provider.reply = lambda payload: "hello from the model"
    res = LLMClient(_cfg(fake_provider)).generate("hi there", system="be terse")
    assert res.ok and res.text == "hello from the model"
    assert fake_provider.paths == ["/v1/chat/completions"]
    assert fake_provider.requests[0][2] == "Bearer test-key"
    body = fake_provider.posts[0]
    assert body["model"] == "fake-model" and body["stream"] is False
    assert body["messages"][0] == {"role": "system", "content": "be terse"}
    assert body["messages"][1] == {"role": "user", "content": "hi there"}


def test_generate_json_mode_sets_response_format(fake_provider):
    fake_provider.reply = lambda payload: '{"dest_dir": "Invoices"}'
    res = LLMClient(_cfg(fake_provider)).generate("classify this", json_mode=True)
    assert res.ok and res.text.startswith("{")
    assert fake_provider.posts[0]["response_format"] == {"type": "json_object"}


def test_json_mode_retries_without_response_format_when_rejected(fake_provider):
    """Providers that 400 on response_format must still work (retry, no format)."""
    fake_provider.reject_json_format = True
    fake_provider.reply = lambda payload: "{}"
    res = LLMClient(_cfg(fake_provider)).generate("classify", json_mode=True)
    assert res.ok
    assert len(fake_provider.posts) == 2
    assert "response_format" in fake_provider.posts[0]
    assert "response_format" not in fake_provider.posts[1]


def test_embed_reads_data_array(fake_provider):
    vec = LLMClient(_cfg(fake_provider)).embed("abcd")
    assert vec == [4.0, 1.0]
    assert fake_provider.paths == ["/v1/embeddings"]
    assert fake_provider.posts[0]["input"] == "abcd"


def test_ping_ok_and_dead_port(fake_provider):
    client = LLMClient(_cfg(fake_provider))
    assert client.ping() is True
    assert fake_provider.paths == ["/v1/models"]
    assert llm_ping("http://127.0.0.1:9/v1") is False


def test_graceful_when_provider_down(fake_provider):
    fake_provider.fail_status = 500
    client = LLMClient(_cfg(fake_provider))
    res = client.generate("hi", json_mode=True)
    assert res.ok is False
    assert "custom" in res.error and "config.toml" in res.error
    assert client.embed("x") is None
    assert client.ping() is False


def test_vision_sends_data_uri(fake_provider, tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nfake-bytes")
    fake_provider.reply = lambda payload: "Invoice 42, total 12.00"
    client = LLMClient(_cfg(fake_provider))
    text = client.describe_image(img.read_bytes(), "image/png")
    assert "Invoice 42" in text
    content = fake_provider.posts[0]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    url = content[1]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")


def test_vision_disabled_returns_empty(fake_provider, tmp_path):
    img = tmp_path / "scan.png"
    img.write_bytes(b"bytes")
    client = LLMClient(_cfg(fake_provider, vision=False))
    assert client.describe_image(b"bytes", "image/png") == ""
    assert fake_provider.requests == []


def test_generate_with_image_attaches_content_parts(fake_provider, tmp_path):
    img = tmp_path / "page.jpg"
    img.write_bytes(b"jpeg-bytes")
    fake_provider.reply = lambda payload: "described"
    res = LLMClient(_cfg(fake_provider)).generate("what is this?", images=[img])
    assert res.ok
    content = fake_provider.posts[0]["messages"][-1]["content"]
    assert isinstance(content, list) and content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_generate_without_images_keeps_plain_string(fake_provider):
    fake_provider.reply = lambda payload: "ok"
    assert LLMClient(_cfg(fake_provider)).generate("plain").ok
    assert isinstance(fake_provider.posts[0]["messages"][-1]["content"], str)
