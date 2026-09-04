from __future__ import annotations

from pathlib import Path

from .conversations import ConversationError, get_conversation
from .library_search import LibrarySearchError, mentioned_works, search_library


def requested_library_sources(
    database: Path | str, conversation_id: str, payload: dict
) -> list[dict]:
    """Resolve a bounded, traceable set of library evidence for one question."""
    if not bool(payload.get("search_library", False)):
        return []
    scope = payload.get("search_scope", "library")
    if scope not in {"library", "current", "selected"}:
        raise ConversationError("El alcance de búsqueda no es válido")
    conversation = get_conversation(database, conversation_id)
    selected_context = [
        item for item in conversation["context_sources"]
        if item["source_type"] in {"personal_note", "annotation"}
    ]
    question = payload.get("search_query", payload.get("content"))
    if not isinstance(question, str):
        raise LibrarySearchError("Escribí una consulta para buscar en la biblioteca")
    seed = " ".join(item["content_snapshot"] for item in selected_context)[:2000]
    work_ids = None
    if scope == "current":
        work_ids = [conversation["work_id"]]
    elif scope == "selected":
        supplied = payload.get("search_work_ids", [])
        if not isinstance(supplied, list):
            raise ConversationError("La selección de libros no es válida")
        work_ids = supplied
    direct = mentioned_works(database, question, work_ids=work_ids, limit=3)
    direct_ids = [item["work_id"] for item in direct]
    targeted = []
    if direct_ids:
        targeted_query = f"{question} {seed}".strip()
        targeted = [
            item for item in search_library(
                database, targeted_query, work_ids=direct_ids, limit=12,
            )
            if item["source_type"] != "work"
        ][:3]
        for item in targeted:
            item["reason"] = "Evidencia de obra mencionada"
    thematic_query = f"{question} {seed}".strip()
    thematic = search_library(database, thematic_query, work_ids=work_ids, limit=20)
    for item in thematic:
        item["reason"] = "Coincidencia temática"
    selected_context_keys = {
        f"{item['source_type']}:{item['source_id']}" for item in selected_context
    }
    results = []
    seen = set(selected_context_keys)
    for item in [*direct, *targeted, *thematic]:
        if item["key"] in seen:
            continue
        seen.add(item["key"])
        results.append(item)
    results = results[:8]
    selected_keys = payload.get("library_source_keys")
    if selected_keys is None:
        return results
    if not isinstance(selected_keys, list) or not all(isinstance(key, str) for key in selected_keys):
        raise ConversationError("La selección de resultados no es válida")
    allowed = set(selected_keys) | {item["key"] for item in direct}
    return [item for item in results if item["key"] in allowed][:8]
