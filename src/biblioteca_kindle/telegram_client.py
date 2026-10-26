import html
import logging
import re
from typing import Any
import requests

logger = logging.getLogger(__name__)


def markdown_to_telegram_html(text: str) -> str:
    """Convierte Markdown estándar de LLMs a HTML admitido por Telegram."""
    if not text:
        return ""

    # 1. Proteger bloques de código
    code_blocks: list[str] = []

    def _save_code_block(match: re.Match[str]) -> str:
        code_blocks.append(match.group(1))
        return f"@@@CODEBLOCK{len(code_blocks) - 1}@@@"

    text = re.sub(r"```(?:[a-zA-Z0-9_-]+)?\n?(.*?)```", _save_code_block, text, flags=re.DOTALL)

    # 2. Proteger código inline
    inline_codes: list[str] = []

    def _save_inline_code(match: re.Match[str]) -> str:
        inline_codes.append(match.group(1))
        return f"@@@INLINECODE{len(inline_codes) - 1}@@@"

    text = re.sub(r"`([^`\n]+)`", _save_inline_code, text)

    # 3. Escapar caracteres HTML en el texto general
    text = html.escape(text, quote=False)

    # 4. Encabezados (# Título) a negrita
    text = re.sub(r"^[ \t]*#{1,6}[ \t]+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # 5. Negrita: **texto** o __texto__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)

    # 6. Cursiva: *texto* o _texto_
    text = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)

    # 7. Citas: > texto
    lines = text.split("\n")
    in_quote = False
    new_lines: list[str] = []
    quote_acc: list[str] = []
    for line in lines:
        if line.startswith("&gt;"):
            quote_acc.append(line[4:].strip())
            in_quote = True
        else:
            if in_quote:
                new_lines.append(f"<blockquote>{chr(10).join(quote_acc)}</blockquote>")
                quote_acc = []
                in_quote = False
            new_lines.append(line)
    if in_quote:
        new_lines.append(f"<blockquote>{chr(10).join(quote_acc)}</blockquote>")
    text = "\n".join(new_lines)

    # 8. Restaurar bloques y código inline escapados correctamente
    for i, code in enumerate(inline_codes):
        text = text.replace(f"@@@INLINECODE{i}@@@", f"<code>{html.escape(code, quote=False)}</code>")
    for i, code in enumerate(code_blocks):
        text = text.replace(f"@@@CODEBLOCK{i}@@@", f"<pre><code>{html.escape(code, quote=False)}</code></pre>")

    return text


def split_message_text(text: str, max_length: int = 4000) -> list[str]:
    """Divide un texto largo respetando párrafos o saltos de línea para Telegram."""
    if len(text) <= max_length:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        split_pos = remaining.rfind("\n\n", 0, max_length)
        if split_pos == -1:
            split_pos = remaining.rfind("\n", 0, max_length)
        if split_pos == -1:
            split_pos = remaining.rfind(" ", 0, max_length)
        if split_pos == -1 or split_pos < max_length // 2:
            split_pos = max_length

        chunk = remaining[:split_pos].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_pos:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


class TelegramAPIError(Exception):
    """Error al comunicarse con Telegram Bot API."""


class TelegramClient:
    def __init__(self, token: str, base_url: str = "https://api.telegram.org", timeout: int = 40) -> None:
        if not token:
            raise ValueError("El token de Telegram no puede estar vacío.")
        self.token = token
        self.api_url = f"{base_url.rstrip('/')}/bot{token}"
        self.session = requests.Session()
        self.timeout = timeout

    def _post(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.api_url}/{method}"
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise TelegramAPIError(f"Fallo de red en {method}: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise TelegramAPIError(f"Respuesta no JSON de Telegram en {method} ({response.status_code})") from exc

        if not data.get("ok"):
            description = data.get("description", "Error desconocido")
            error_code = data.get("error_code")
            raise TelegramAPIError(f"Error {error_code} en {method}: {description}")

        return data.get("result", {})

    def get_me(self) -> dict[str, Any]:
        url = f"{self.api_url}/getMe"
        try:
            response = self.session.get(url, timeout=15)
            data = response.json()
            if not data.get("ok"):
                raise TelegramAPIError(f"Error en getMe: {data.get('description')}")
            return data.get("result", {})
        except requests.RequestException as exc:
            raise TelegramAPIError(f"Fallo de red en getMe: {exc}") from exc

    def set_my_commands(self, commands: list[dict[str, str]]) -> bool:
        try:
            self._post("setMyCommands", {"commands": commands})
            return True
        except TelegramAPIError as exc:
            logger.warning("Error al configurar comandos de Telegram: %s", exc)
            return False

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        try:
            # timeout del request debe ser mayor al timeout de long-polling
            url = f"{self.api_url}/getUpdates"
            response = self.session.post(url, json=payload, timeout=timeout + 15)
            data = response.json()
            if not data.get("ok"):
                raise TelegramAPIError(f"Error en getUpdates: {data.get('description')}")
            return data.get("result", [])
        except requests.RequestException as exc:
            raise TelegramAPIError(f"Fallo de red en getUpdates: {exc}") from exc

    def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        chunks = split_message_text(text)
        result: dict[str, Any] = {}
        for index, chunk in enumerate(chunks):
            is_last = index == len(chunks) - 1
            payload: dict[str, Any] = {
                "chat_id": chat_id,
                "text": chunk,
            }
            if is_last and reply_markup:
                payload["reply_markup"] = reply_markup
            if parse_mode:
                payload["parse_mode"] = parse_mode

            try:
                result = self._post("sendMessage", payload)
            except TelegramAPIError as exc:
                # Si falló por formato (Markdown/HTML), reintentar sin parse_mode
                if parse_mode and "can't parse entities" in str(exc).lower():
                    payload.pop("parse_mode", None)
                    result = self._post("sendMessage", payload)
                else:
                    raise exc
        return result

    def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            return self._post("editMessageText", payload)
        except TelegramAPIError as exc:
            # Si el texto es idéntico Telegram retorna error; podemos ignorarlo
            if "message is not modified" in str(exc).lower():
                return {}
            if parse_mode and "can't parse entities" in str(exc).lower():
                payload.pop("parse_mode", None)
                return self._post("editMessageText", payload)
            raise exc

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> bool:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        if show_alert:
            payload["show_alert"] = show_alert
        try:
            self._post("answerCallbackQuery", payload)
            return True
        except TelegramAPIError as exc:
            logger.warning("Error al responder callback query: %s", exc)
            return False
