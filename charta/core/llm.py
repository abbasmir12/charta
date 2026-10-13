"""Ollama client: timeout + 1 retry + graceful fallback. No other network."""
from __future__ import annotations

import json
import urllib.request
import urllib.error
from dataclasses import dataclass

from .config import AppConfig


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    error: str = ""


def ollama_ping(host: str, timeout: float = 5.0) -> bool:
    try:
        with urllib.request.urlopen(host.rstrip("/") + "/", timeout=timeout) as r:
            return r.status < 500
    except Exception:
        return False


class OllamaClient:
    def __init__(self, cfg: AppConfig | None = None) -> None:
        self.cfg = cfg or AppConfig.load()

    def _post(self, path: str, payload: dict) -> dict:
        url = self.cfg.ollama_host.rstrip("/") + path
        data = json.dumps(payload).encode()
        last_err = ""
        attempts = 1 + max(0, self.cfg.llm_retries)
        for _ in range(attempts):
            try:
                req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(req, timeout=self.cfg.llm_timeout) as r:
                    return json.loads(r.read().decode())
            except Exception as e:  # noqa: BLE001
                last_err = str(e)
        raise RuntimeError(f"Ollama unreachable at {url}: {last_err}")

    def generate(self, prompt: str, system: str = "", json_mode: bool = False) -> LLMResult:
        try:
            payload: dict = {"model": self.cfg.generation_model, "prompt": prompt, "stream": False}
            if system:
                payload["system"] = system
            if json_mode:
                payload["format"] = "json"
            resp = self._post("/api/generate", payload)
            return LLMResult(ok=True, text=str(resp.get("response", "")))
        except Exception as e:  # noqa: BLE001
            return LLMResult(ok=False, error=f"Ollama not running ({e}). Start it with: ollama serve")

    def embed(self, text: str) -> list[float] | None:
        try:
            resp = self._post("/api/embeddings", {"model": self.cfg.embedding_model, "prompt": text})
            emb = resp.get("embedding")
            return list(emb) if emb else None
        except Exception:
            return None
