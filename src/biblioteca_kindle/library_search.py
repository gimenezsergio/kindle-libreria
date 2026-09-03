from __future__ import annotations

import re
import sqlite3
import unicodedata
from pathlib import Path

from .db import connect_database


class LibrarySearchError(RuntimeError):
    pass


_STOP_WORDS = {
    "alguna", "como", "con", "cual", "cuando", "del", "desde", "donde",
    "esta", "este", "estos", "hacer", "las", "los", "para", "pero", "por",
    "que", "sobre", "sus", "una", "uno", "unos",
}


def _normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", "".join(ch for ch in value if not unicodedata.combining(ch))).split()
    )


def _terms(query: str) -> list[str]:
    return [term for term in _normalize(query).split() if len(term) > 2 and term not in _STOP_WORDS]


def _score(query: str, title: str, content: str, label: str) -> float:
    terms = _terms(query)
    if not terms:
        return 0
    normalized_title = _normalize(title)
    normalized_content = _normalize(content)
    normalized_label = _normalize(label)
    score = sum(5 for term in terms if term in normalized_title)
    score += sum(3 for term in terms if term in normalized_label)
    score += sum(1 for term in terms if term in normalized_content)
    phrase = _normalize(query)
    if phrase and phrase in normalized_content:
        score += 8
    return score / len(terms)


def _work_title_sql(alias: str = "w") -> str:
    return (
        f"COALESCE(NULLIF(TRIM({alias}.display_title), ''), "
        f"REPLACE({alias}.preferred_title, '_', ' '))"
    )


def search_library(
    database: Path | str,
    query: object,
    *,
    work_ids: list[str] | None = None,
    limit: int = 8,
) -> list[dict]:
    if not isinstance(query, str) or not query.strip():
        raise LibrarySearchError("Escribí una consulta para buscar en la biblioteca")
    query = query.strip()[:500]
    if not _terms(query):
        return []
    if work_ids is not None and not all(isinstance(item, str) for item in work_ids):
        raise LibrarySearchError("El alcance de libros no es válido")
    limit = min(20, max(1, int(limit)))
    selected = list(dict.fromkeys(work_ids or []))
    scope = ""
    parameters: list[object] = []
    if work_ids is not None:
        if not selected:
            return []
        scope = f" AND e.work_id IN ({','.join('?' for _ in selected)})"
        parameters.extend(selected)

    connection = connect_database(Path(database).expanduser().resolve())
    try:
        title_sql = _work_title_sql()
        results: list[dict] = []

        annotations = connection.execute(
            f"""
            SELECT an.id AS source_id, e.work_id, {title_sql} AS work_title,
                   an.kind, COALESCE(NULLIF(TRIM(an.text), ''),
                   NULLIF(TRIM(an.note_text), '')) AS content,
                   MAX(CASE WHEN ao.source_kind='clippings' THEN ao.original_position END) AS reference
            FROM annotations an
            JOIN editions e ON e.id=an.edition_id JOIN works w ON w.id=e.work_id
            LEFT JOIN annotation_occurrences ao ON ao.annotation_id=an.id
            WHERE COALESCE(NULLIF(TRIM(an.text), ''), NULLIF(TRIM(an.note_text), '')) IS NOT NULL
            {scope}
            GROUP BY an.id
            """,
            parameters,
        ).fetchall()
        for row in annotations:
            label = "Nota Kindle" if row["kind"] == "note" else "Subrayado"
            results.append(_result(row, "annotation", label, row["content"], row["reference"], query))

        note_scope = ""
        note_parameters: list[object] = []
        if work_ids is not None:
            note_scope = f" AND pn.target_id IN ({','.join('?' for _ in selected)})"
            note_parameters.extend(selected)
        notes = connection.execute(
            f"""
            SELECT pn.id AS source_id, pn.target_id AS work_id, {title_sql} AS work_title,
                   pn.body AS content
            FROM personal_notes pn JOIN works w ON w.id=pn.target_id
            WHERE pn.target_type='work' {note_scope}
            """,
            note_parameters,
        ).fetchall()
        for row in notes:
            results.append(_result(row, "personal_note", "Nota propia", row["content"], None, query))

        work_scope = ""
        work_parameters: list[object] = []
        if work_ids is not None:
            work_scope = f" WHERE w.id IN ({','.join('?' for _ in selected)})"
            work_parameters.extend(selected)
        works = connection.execute(
            f"""
            SELECT w.id AS source_id, w.id AS work_id, {_work_title_sql()} AS work_title,
                   COALESCE(GROUP_CONCAT(DISTINCT c.display_name), '') AS authors
            FROM works w
            LEFT JOIN editions e ON e.work_id=w.id
            LEFT JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
            LEFT JOIN contributors c ON c.id=ec.contributor_id
            {work_scope} GROUP BY w.id
            """,
            work_parameters,
        ).fetchall()
        for row in works:
            content = f"Título: {row['work_title']}"
            if row["authors"]:
                content += f". Autoría: {row['authors']}"
            results.append(_result(row, "work", "Ficha del libro", content, None, query))

        collection_scope = ""
        collection_parameters: list[object] = []
        if work_ids is not None:
            collection_scope = f" AND wc.work_id IN ({','.join('?' for _ in selected)})"
            collection_parameters.extend(selected)
        for row in connection.execute(
            f"""
            SELECT c.id || ':' || w.id AS source_id, w.id AS work_id,
                   {_work_title_sql()} AS work_title, c.name,
                   COALESCE(c.description, '') || CASE WHEN wc.note IS NULL THEN '' ELSE ' ' || wc.note END AS content
            FROM work_collections wc JOIN collections c ON c.id=wc.collection_id
            JOIN works w ON w.id=wc.work_id WHERE 1=1 {collection_scope}
            """,
            collection_parameters,
        ):
            results.append(_result(row, "collection", f"Categoría: {row['name']}", row["content"] or row["name"], None, query))

        relation_scope = ""
        relation_parameters: list[object] = []
        if work_ids is not None:
            relation_scope = f" AND wr.source_work_id IN ({','.join('?' for _ in selected)})"
            relation_parameters.extend(selected)
        for row in connection.execute(
            f"""
            SELECT wr.id AS source_id, wr.source_work_id AS work_id,
                   {_work_title_sql()} AS work_title, wr.relation_type,
                   COALESCE(wr.label, '') || ' ' || COALESCE(wr.explanation, '') ||
                   ' Relacionado con ' || {_work_title_sql('other')} AS content
            FROM work_relations wr JOIN works w ON w.id=wr.source_work_id
            JOIN works other ON other.id=wr.target_work_id
            WHERE 1=1 {relation_scope}
            """,
            relation_parameters,
        ):
            results.append(_result(row, "relation", f"Relación: {row['relation_type']}", row["content"], None, query))

        ranked = [item for item in results if item["score"] > 0]
        ranked.sort(key=lambda item: (-item["score"], item["work_title"].casefold(), item["key"]))
        return ranked[:limit]
    finally:
        connection.close()


def _result(row, source_type: str, label: str, content: str, reference: str | None, query: str) -> dict:
    work_title = row["work_title"]
    source_id = row["source_id"]
    return {
        "key": f"{source_type}:{source_id}",
        "source_type": source_type,
        "source_id": source_id,
        "work_id": row["work_id"],
        "work_title": work_title,
        "label": label,
        "content": content,
        "reference": reference,
        "score": round(_score(query, work_title, content, label), 3),
    }
