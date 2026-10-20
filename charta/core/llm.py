"""Provider-agnostic LLM client speaking the *OpenAI-compatible* HTTP API.

One client, any provider. Anything that exposes these three routes works:

    POST {base_url}/chat/completions
    POST {base_url}/embeddings
    GET  {base_url}/models

That covers Ollama (``http://localhost:11434/v1``), LM Studio
(``http://localhost:1234/v1``), llama.cpp/vLLM servers, OpenAI, OpenRouter,
Groq, Together, and friends. The provider only changes ``[llm] provider`` /
``base_url`` / ``api_key`` in ``config.toml`` — no code changes.

Every call: timeout + retries + a graceful fallback message (never raises).
No network beyond the configured base_url.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import pathlib
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Sequence

from .config import AppConfig

VISION_PROMPT = (
    "Transcribe every piece of text in this file and list the key fields "
    "(dates, names, amounts, totals). Be terse and factual. No commentary."
)


@dataclass
class LLMResult:
    ok: bool
    text: str = ""
    error: str = ""


def _data_uri(data: bytes, mime: str | None = None) -> str:
    mime = mime or "image/png"
    return f"data:{mime};base64,{base64.b64encode(data).decode()}"


def _guess_mime(path: str | pathlib.Path) -> str:
    return mimetypes.guess_type(str(path))[0] or "application/octet-stream"


class LLMClient:
    """OpenAI-compatible chat + embeddings client (no third-party deps)."""

    def __init__(self, cfg: AppConfig | None = None) -> None:
        self.cfg = cfg or AppConfig.load()

    # -- transport ---------------------------------------------------------
    @property
    def base_url(self) -> str:
        return self.cfg.llm_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.cfg.llm_api_key:
            headers["Authorization"] = f"Bearer {self.cfg.llm_api_key}"
        return headers

    def _request(self, method: str, path: str, payload: dict | None = None,
                 timeout: float | None = None) -> dict:
        """One HTTP call with timeout + retries. Raises RuntimeError on failure."""
        url = self.base_url + path
        data = json.dumps(payload).encode() if payload is not None else None
        last_err = ""
        attempts = 1 + max(0, self.cfg.llm_retries)
        for _ in range(attempts):
            try:
                req = urllib.request.Request(url, data=data, headers=self._headers(), method=method)
                with urllib.request.urlopen(req, timeout=timeout or self.cfg.llm_timeout) as resp:
                    body = resp.read().decode(errors="replace")
                    return json.loads(body) if body.strip() else {}
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                last_err = f"HTTP {e.code}: {detail}"
                # Client errors (bad model, bad schema) won't fix themselves.
                if 400 <= e.code < 500 and e.code != 429:
                    break
            except Exception as e:  # noqa: BLE001 — URLError, timeouts, bad JSON
                last_err = str(e)
        raise RuntimeError(f"{url} unavailable ({last_err})")

    # -- health ------------------------------------------------------------
    def ping(self, timeout: float = 2.0) -> bool:
        """True if the provider answers on /models (used by `charta status`)."""
        try:
            req = urllib.request.Request(self.base_url + "/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status < 500
        except Exception:  # noqa: BLE001
            return False

    def models(self, timeout: float = 2.0) -> list[str] | None:
        """Model ids the endpoint advertises, or None if it cannot list them."""
        try:
            req = urllib.request.Request(self.base_url + "/models", headers=self._headers())
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # noqa: BLE001
            return None
        items = data.get("data") if isinstance(data, dict) else None
        ids = [str(i["id"]) for i in items or [] if isinstance(i, dict) and i.get("id")]
        return ids or None

    # -- generation --------------------------------------------------------
    def generate(self, prompt: str, system: str = "", json_mode: bool = False,
                 images: Sequence[str | pathlib.Path] | None = None,
                 model: str | None = None, timeout: float | None = None) -> LLMResult:
        """Chat completion. ``images`` = paths to attach for vision models."""
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": self._user_content(prompt, images)})

        # Some providers reject response_format; retry once without it.
        variants = [True, False] if json_mode else [False]
        last_err = ""
        for use_json_format in variants:
            payload: dict = {
                "model": model or self.cfg.generation_model,
                "messages": messages,
                "stream": False,
            }
            if use_json_format:
                payload["response_format"] = {"type": "json_object"}
            try:
                resp = self._request("POST", "/chat/completions", payload, timeout)
            except RuntimeError as e:
                last_err = str(e)
                # A transport/auth failure won't be fixed by dropping response_format.
                if "HTTP 400" not in last_err and "HTTP 422" not in last_err:
                    break
                continue
            text = self._first_message(resp)
            if text:
                return LLMResult(ok=True, text=text)
            last_err = "empty response"
        hint = ""
        if "HTTP 404" in last_err:
            hint = (f" The model '{model or self.cfg.generation_model}' may not be "
                    f"installed; see {self.base_url}/models.")
        return LLMResult(ok=False, error=(
            f"{self.cfg.llm_provider} at {self.base_url} failed ({last_err}). "
            "Check [llm] in config.toml — for the local default run: ollama serve"
            + hint
        ))

    def embed(self, text: str) -> list[float] | None:
        """Embedding vector, or None when the provider has no embedding model."""
        try:
            resp = self._request("POST", "/embeddings",
                                 {"model": self.cfg.embedding_model, "input": text or ""})
        except Exception:  # noqa: BLE001
            return None
        data = resp.get("data") or []
        if data and isinstance(data[0], dict) and data[0].get("embedding"):
            return [float(x) for x in data[0]["embedding"]]
        return None

    # -- vision ------------------------------------------------------------
    def describe_image(self, data: bytes, mime: str = "image/png",
                       prompt: str = VISION_PROMPT) -> str:
        """Read text out of an image/rendered page via a vision model.

        Signature (bytes, mime) fits ``charta.core.extract``'s vision hook.
        Returns "" when vision is unavailable so callers degrade gracefully.
        """
        if not self.cfg.vision:
            return ""
        model = self.cfg.vision_model or self.cfg.generation_model
        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": _data_uri(data, mime)}},
        ]}]
        try:
            resp = self._request("POST", "/chat/completions",
                                 {"model": model, "messages": messages, "stream": False})
        except Exception:  # noqa: BLE001
            return ""
        return (self._first_message(resp) or "").strip()

    def describe_file(self, path: str | pathlib.Path) -> str:
        """Convenience wrapper: read a local image file and transcribe it."""
        p = pathlib.Path(path)
        try:
            return self.describe_image(p.read_bytes(), _guess_mime(p))
        except OSError:
            return ""

    # -- helpers -----------------------------------------------------------
    def _user_content(self, prompt: str, images: Sequence[str | pathlib.Path] | None
                      ) -> str | list[dict]:
        if not images:
            return prompt
        content: list[dict] = [{"type": "text", "text": prompt}]
        for path in images:
            p = pathlib.Path(path)
            try:
                content.append({"type": "image_url",
                                "image_url": {"url": _data_uri(p.read_bytes(), _guess_mime(p))}})
            except OSError:
                continue
        return content

    @staticmethod
    def _first_message(resp: dict) -> str | None:
        try:
            message = resp["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            return None
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):  # some providers split content into parts
            content = "".join(str(p.get("text", "")) for p in content if isinstance(p, dict))
        text = str(content) if content else ""
        return text or None


def llm_ping(base_url: str, api_key: str = "", timeout: float = 2.0) -> bool:
    """Standalone health check for a base_url without building a full client."""
    cfg = AppConfig(llm_base_url=base_url, llm_api_key=api_key)
    return LLMClient(cfg).ping(timeout=timeout)
