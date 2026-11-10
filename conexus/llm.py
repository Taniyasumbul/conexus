"""Pluggable LLM layer.

- AnthropicLLM: Claude via the official SDK, JSON-schema structured outputs.
- OllamaLLM:   local models via Ollama's HTTP API (free, private - good for the
               data-sovereignty angle discussed in MA-RAG).
- None:        "offline" mode. Every agent has a deterministic fallback, so the
               full pipeline and the evaluation run without any model.
"""
from __future__ import annotations

import copy
import json
import urllib.request
from typing import Protocol, TypeVar

from pydantic import BaseModel

from .config import Settings

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


class LLM(Protocol):
    name: str

    def structured(self, system: str, prompt: str, schema: type[T]) -> T: ...

    def text(self, system: str, prompt: str) -> str: ...


def strict_json_schema(model: type[BaseModel]) -> dict:
    """Pydantic schema -> strict schema (all props required, no extras)."""
    schema = copy.deepcopy(model.model_json_schema())

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                node["additionalProperties"] = False
                node["required"] = list(node["properties"].keys())
            for key in ("title", "default"):
                node.pop(key, None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(schema)
    return schema


class AnthropicLLM:
    def __init__(self, model: str = "claude-opus-5-5", effort: str = "low"):
        import anthropic

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.name = f"anthropic:{model}"

    def _create(self, system: str, prompt: str, fmt: dict | None):
        output_config: dict = {"effort": self.effort}
        if fmt:
            output_config["format"] = fmt
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=system,
                messages=[{"role": "user", "content": prompt}],
                output_config=output_config,
                # On a safety decline, the API retries on a fallback model in the same call.
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except self._anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}: {e.message}") from e
        except self._anthropic.APIConnectionError as e:
            raise LLMError(f"Could not reach Claude API: {e}") from e
        if resp.stop_reason == "refusal":
            raise LLMError("Model declined the request")
        return "".join(b.text for b in resp.content if b.type == "text")

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        raw = self._create(system, prompt, {"type": "json_schema", "schema": strict_json_schema(schema)})
        return schema.model_validate_json(raw)

    def text(self, system: str, prompt: str) -> str:
        return self._create(system, prompt, None)


class OllamaLLM:
    def __init__(self, model: str, host: str):
        self.model = model
        self.host = host.rstrip("/")
        self.name = f"ollama:{model}"

    def _chat(self, system: str, prompt: str, fmt) -> str:
        body = {
            "model": self.model,
            "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "options": {"temperature": 0},
        }
        if fmt is not None:
            body["format"] = fmt
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read())["message"]["content"]
        except OSError as e:
            raise LLMError(f"Ollama call failed ({self.host}): {e}") from e

    def structured(self, system: str, prompt: str, schema: type[T]) -> T:
        raw = self._chat(system, prompt, strict_json_schema(schema))
        return schema.model_validate_json(raw)

    def text(self, system: str, prompt: str) -> str:
        return self._chat(system, prompt, None)


def build_llm(settings: Settings) -> LLM | None:
    p = settings.llm_provider.lower()
    if p == "offline":
        return None
    if p == "anthropic":
        return AnthropicLLM(settings.anthropic_model, settings.effort)
    if p == "ollama":
        return OllamaLLM(settings.ollama_model, settings.ollama_host)
    raise ValueError(f"Unknown CONEXUS_LLM provider: {settings.llm_provider}")
