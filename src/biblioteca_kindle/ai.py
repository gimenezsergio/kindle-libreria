from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Protocol


class AIError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptPacket:
    instructions: str
    input: list[dict]

    def as_dict(self) -> dict:
        return {"instructions": self.instructions, "input": self.input}


class AIProvider(Protocol):
    name: str
    ready: bool

    def respond(self, packet: PromptPacket) -> str: ...


class DraftProvider:
    name = "draft"
    ready = False

    def respond(self, packet: PromptPacket) -> str:
        raise AIError("El modo borrador no envía información a una IA")


class ResponsesProvider:
    ready = True

    def __init__(self, *, name: str, base_url: str, api_key: str, model: str) -> None:
        if not api_key:
            raise AIError("Falta la credencial del proveedor de IA")
        self.name = name
        self.url = f"{base_url.rstrip('/')}/responses"
        self.api_key = api_key
        self.model = model

    def respond(self, packet: PromptPacket) -> str:
        body = json.dumps({
            "model": self.model,
            "instructions": packet.instructions,
            "input": packet.input,
            "store": False,
        }).encode("utf-8")
        request = urllib.request.Request(
            self.url,
            data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error)["error"]["message"]
            except Exception:
                detail = f"HTTP {error.code}"
            raise AIError(f"El proveedor rechazó la solicitud: {detail}") from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise AIError("No se pudo conectar con el proveedor de IA") from error
        text = data.get("output_text")
        if not text:
            pieces = [part.get("text", "") for item in data.get("output", []) for part in item.get("content", []) if part.get("type") == "output_text"]
            text = "".join(pieces)
        if not isinstance(text, str) or not text.strip():
            raise AIError("El proveedor no devolvió una respuesta de texto")
        return text.strip()


def provider_from_environment() -> AIProvider:
    kind = os.getenv("BIBLIOTECA_AI_PROVIDER", "draft").strip().lower()
    if kind == "draft":
        return DraftProvider()
    if kind not in {"openai", "deepseek", "openclaw"}:
        raise AIError("BIBLIOTECA_AI_PROVIDER debe ser draft, openai, deepseek u openclaw")
    default_urls = {
        "openai": "https://api.openai.com/v1",
        "deepseek": "https://api.deepseek.com",
        "openclaw": "http://127.0.0.1:18789/v1",
    }
    key = os.getenv("BIBLIOTECA_AI_API_KEY", "")
    if kind == "openai" and not key:
        key = os.getenv("OPENAI_API_KEY", "")
    if kind == "deepseek" and not key:
        key = os.getenv("DEEPSEEK_API_KEY", "")
    default_models = {"openai": "gpt-5-mini", "deepseek": "deepseek-v4-flash", "openclaw": "openclaw"}
    model = os.getenv("BIBLIOTECA_AI_MODEL", default_models[kind])
    try:
        return ResponsesProvider(name=kind, base_url=os.getenv("BIBLIOTECA_AI_BASE_URL", default_urls[kind]), api_key=key, model=model)
    except AIError:
        return DraftProvider()
