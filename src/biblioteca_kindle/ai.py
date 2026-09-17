from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


class AIError(RuntimeError):
    pass


def load_environment_file(path: Path) -> None:
    """Carga pares simples CLAVE=VALOR sin reemplazar variables ya exportadas."""
    if not path.is_file():
        return
    for number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key.replace("_", "").isalnum() or not key[0].isalpha():
            raise AIError(f"Línea inválida en {path.name}: {number}")
        os.environ.setdefault(key, value.strip())


def save_environment_config(path: Path, updates: dict[str, str]) -> None:
    """Actualiza o agrega variables en el archivo .env especificado y sincroniza os.environ."""
    existing_lines = []
    if path.is_file():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    seen_keys = set()
    new_lines = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in updates:
                seen_keys.add(key)
                val = updates[key]
                new_lines.append(f"{key}={val}")
                continue
        new_lines.append(line)

    for key, val in updates.items():
        if key not in seen_keys:
            new_lines.append(f"{key}={val}")
            seen_keys.add(key)

    content = "\n".join(new_lines) + ("\n" if new_lines else "")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    for key, val in updates.items():
        os.environ[key] = val



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


PRESET_PROVIDERS = {
    "draft": {
        "id": "draft",
        "name": "Draft (Borrador / Desconectado)",
        "base_url": "",
        "model": "",
        "protocol": "chat_completions",
    },
    "openrouter": {
        "id": "openrouter",
        "name": "OpenRouter.ai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-2.5-flash",
        "protocol": "chat_completions",
    },
    "gemini": {
        "id": "gemini",
        "name": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.5-flash",
        "protocol": "chat_completions",
    },
    "openai": {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-5-mini",
        "protocol": "chat_completions",
    },
    "deepseek": {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "protocol": "responses",
    },
    "openclaw": {
        "id": "openclaw",
        "name": "OpenClaw (Local)",
        "base_url": "http://127.0.0.1:18789/v1",
        "model": "openclaw",
        "protocol": "responses",
    },
}


class ResponsesProvider:
    ready = True

    def __init__(self, *, name: str, base_url: str, api_key: str, model: str, protocol: str = "auto") -> None:
        if not api_key:
            raise AIError("Falta la credencial del proveedor de IA")
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model

        if protocol == "auto":
            if name == "openclaw" or self.base_url.endswith("/responses"):
                self.protocol = "responses"
            else:
                self.protocol = "chat_completions"
        else:
            self.protocol = protocol

    @property
    def url(self) -> str:
        if self.protocol == "responses":
            return self.base_url if self.base_url.endswith("/responses") else f"{self.base_url}/responses"
        return self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"

    def respond(self, packet: PromptPacket) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if "openrouter" in self.base_url.lower() or self.name == "openrouter":
            headers["HTTP-Referer"] = "http://localhost:5000"
            headers["X-Title"] = "Biblioteca Kindle"

        if self.protocol == "responses":
            url = self.base_url if self.base_url.endswith("/responses") else f"{self.base_url}/responses"
            body_dict = {
                "model": self.model,
                "instructions": packet.instructions,
                "input": packet.input,
                "store": False,
            }
        else:
            url = self.base_url if self.base_url.endswith("/chat/completions") else f"{self.base_url}/chat/completions"
            user_parts = []
            for item in packet.input:
                content = item.get("content", "")
                if content:
                    user_parts.append(content)
            user_text = "\n\n".join(user_parts) if user_parts else "Hola"

            body_dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": packet.instructions},
                    {"role": "user", "content": user_text},
                ],
            }

        body = json.dumps(body_dict).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers=headers, method="POST")

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

        text = None
        if isinstance(data, dict) and "choices" in data and isinstance(data["choices"], list) and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if isinstance(choice, dict):
                if "message" in choice and isinstance(choice["message"], dict):
                    text = choice["message"].get("content")
                elif "text" in choice:
                    text = choice.get("text")

        if not text and isinstance(data, dict):
            text = data.get("output_text")
        if not text and isinstance(data, dict):
            pieces = [part.get("text", "") for item in data.get("output", []) if isinstance(item, dict) for part in item.get("content", []) if isinstance(part, dict) and part.get("type") == "output_text"]
            text = "".join(pieces)

        if not isinstance(text, str) or not text.strip():
            raise AIError("El proveedor no devolvió una respuesta de texto")
        return text.strip()


def resolve_provider_for_profile(provider_id: str | None = None, model_override: str | None = None) -> AIProvider:
    if not provider_id or provider_id == "global":
        provider = provider_from_environment()
        if model_override and isinstance(provider, ResponsesProvider):
            return ResponsesProvider(
                name=provider.name,
                base_url=provider.base_url,
                api_key=provider.api_key,
                model=model_override,
                protocol=provider.protocol,
            )
        return provider

    kind = provider_id.strip().lower()
    if kind == "draft":
        return DraftProvider()

    preset = PRESET_PROVIDERS.get(kind, {})
    default_url = preset.get("base_url", "https://api.openai.com/v1")
    default_model = model_override or preset.get("model", "")
    default_protocol = preset.get("protocol", "chat_completions")

    key = os.getenv("BIBLIOTECA_AI_API_KEY", "")
    if not key or kind != os.getenv("BIBLIOTECA_AI_PROVIDER", "draft").strip().lower():
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        if kind in env_key_map:
            key = os.getenv(env_key_map[kind], "") or key

    url = preset.get("base_url", default_url)
    if kind == os.getenv("BIBLIOTECA_AI_PROVIDER", "draft").strip().lower():
        url = os.getenv("BIBLIOTECA_AI_BASE_URL", url)

    protocol = preset.get("protocol", default_protocol)

    try:
        return ResponsesProvider(
            name=kind,
            base_url=url,
            api_key=key,
            model=default_model,
            protocol=protocol,
        )
    except AIError:
        return DraftProvider()


def provider_from_environment() -> AIProvider:
    kind = os.getenv("BIBLIOTECA_AI_PROVIDER", "draft").strip().lower()
    if kind == "draft":
        return DraftProvider()

    preset = PRESET_PROVIDERS.get(kind, {})
    default_url = preset.get("base_url", "https://api.openai.com/v1")
    default_model = preset.get("model", "")
    default_protocol = preset.get("protocol", "chat_completions")

    key = os.getenv("BIBLIOTECA_AI_API_KEY", "")
    if not key:
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }
        if kind in env_key_map:
            key = os.getenv(env_key_map[kind], "")

    url = os.getenv("BIBLIOTECA_AI_BASE_URL", default_url)
    model = os.getenv("BIBLIOTECA_AI_MODEL", default_model)
    protocol = os.getenv("BIBLIOTECA_AI_PROTOCOL", default_protocol)

    try:
        return ResponsesProvider(
            name=kind,
            base_url=url,
            api_key=key,
            model=model,
            protocol=protocol,
        )
    except AIError:
        return DraftProvider()

