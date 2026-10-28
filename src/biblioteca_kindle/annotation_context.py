from __future__ import annotations

import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .db import connect_database


class ContextExtractionError(Exception):
    pass


@dataclass(frozen=True)
class ContextExtractionResult:
    books_scanned: int
    books_matched: int
    annotations_scanned: int
    annotations_matched: int
    annotations_extracted: int
    annotations_skipped: int


_HEADING_RE = re.compile(
    r"^(?:cap[íi]tulo\b|parte\b|libro\b|secci[óo]n\b|acto\b|escena\b|pr[óo]logo\b|prefacio\b|introducci[óo]n\b|ep[íi]logo\b|conclusi[óo]n\b|[ivxlcdm]+\b|\d+[\.\s])",
    re.IGNORECASE,
)


def _read_varuint(data: bytes, p: int) -> tuple[int, int]:
    res = 0
    n = len(data)
    while p < n:
        b = data[p]
        p += 1
        res = (res << 7) | (b & 0x7F)
        if b & 0x80:
            break
    return res, p


def extract_kfx_paragraphs(file_bytes: bytes) -> list[str]:
    """Extrae las cadenas de texto (párrafos) de un contenedor Amazon KFX en orden secuencial."""
    strings: list[str] = []
    pos = 0
    n = len(file_bytes)
    while pos < n:
        b = file_bytes[pos]
        # Tipo 8 en Amazon Ion = String UTF-8
        if (b & 0xF0) == 0x80:
            ln = b & 0x0F
            p = pos + 1
            if ln == 0x0E:
                ln, p = _read_varuint(file_bytes, p)
            if 0 < ln < 200_000 and p + ln <= n:
                raw = file_bytes[p : p + ln]
                try:
                    s = raw.decode("utf-8")
                    if not any(ord(c) < 32 and c not in "\n\r\t" for c in s):
                        st = s.strip()
                        if st:
                            strings.append(st)
                except UnicodeDecodeError:
                    pass
        pos += 1
    return strings


def extract_paragraphs_from_file(file_path: Path) -> list[str]:
    """Detecta el tipo de archivo y extrae los párrafos de texto secuenciales."""
    data = file_path.read_bytes()
    if data.startswith(b"CONT") or file_path.suffix.lower() == ".kfx":
        return extract_kfx_paragraphs(data)
    # Fallback para archivos de texto plano o derivados
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = data.decode("latin1", errors="replace")
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    return paras


def normalize_text(text: str) -> str:
    """Normaliza texto para comparaciones resistentes a diferencias tipográficas."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\u2018\u2019\u201a\u201b\u2032\u2035]", "'", text)
    text = re.sub(r"[\u201c\u201d\u201e\u201f\u2033\u2036«»]", '"', text)
    text = re.sub(r"[\u2010\u2011\u2012\u2013\u2014\u2015]", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def find_chapter_title(paragraphs: list[str], match_idx: int) -> str | None:
    """Busca hacia atrás desde la posición del subrayado el título de capítulo o sección más cercano."""
    for k in range(match_idx, max(-1, match_idx - 120), -1):
        cand = paragraphs[k].strip()
        if len(cand) > 75 or len(cand) < 2:
            continue
        if cand.isupper() and any(c.isalpha() for c in cand):
            if k > 0 and _HEADING_RE.match(paragraphs[k - 1].strip()) and len(paragraphs[k - 1].strip()) < 60:
                return f"{paragraphs[k - 1].strip()} · {cand}"
            return cand
        if _HEADING_RE.match(cand):
            if k > 0 and _HEADING_RE.match(paragraphs[k - 1].strip()) and len(paragraphs[k - 1].strip()) < 60:
                return f"{paragraphs[k - 1].strip()} · {cand}"
            return cand
    return None


def find_surrounding_context(
    paragraphs: list[str],
    quote: str,
    *,
    max_chars: int = 400,
) -> tuple[str | None, str | None, str | None]:
    """
    Encuentra el contexto circundante de una cita en la lista de párrafos.
    Retorna (chapter_title, surrounding_before, surrounding_after).
    """
    norm_quote = normalize_text(quote)
    if not norm_quote:
        return None, None, None

    # Ancla de búsqueda
    anchor = norm_quote if len(norm_quote) <= 45 else norm_quote[:45]

    # 1. Búsqueda en un solo párrafo
    match_start = -1
    match_end = -1
    for i, p in enumerate(paragraphs):
        np = normalize_text(p)
        if norm_quote in np or anchor in np:
            match_start = i
            match_end = i
            break

    # 2. Búsqueda en 2 párrafos consecutivos
    if match_start == -1:
        for i in range(len(paragraphs) - 1):
            np = normalize_text(paragraphs[i] + " " + paragraphs[i + 1])
            if anchor in np:
                match_start = i
                match_end = i + 1
                break

    # 3. Búsqueda con ancla intermedia si la cita es larga
    if match_start == -1 and len(norm_quote) > 60:
        mid_anchor = norm_quote[20:65]
        for i, p in enumerate(paragraphs):
            np = normalize_text(p)
            if mid_anchor in np:
                match_start = i
                match_end = i
                break

    if match_start == -1:
        return None, None, None

    chapter = find_chapter_title(paragraphs, match_start)

    # Construir surrounding_before
    p_first = paragraphs[match_start]
    norm_first = normalize_text(p_first)
    idx_in_first = -1
    if norm_quote in norm_first:
        idx_in_first = norm_first.find(norm_quote)
    elif anchor in norm_first:
        idx_in_first = norm_first.find(anchor)
    else:
        words = norm_quote.split()
        for count in (3, 2, 1):
            if len(words) >= count:
                lead = " ".join(words[:count])
                idx_in_first = norm_first.find(lead)
                if idx_in_first != -1:
                    break

    prefix = p_first[:idx_in_first].strip() if idx_in_first > 0 else ""

    before_parts = []
    if match_start > 0:
        before_parts.append(paragraphs[match_start - 1])
    if prefix:
        before_parts.append(prefix)
    before = " ".join(before_parts).strip()
    if len(before) > max_chars:
        before = before[-max_chars:].lstrip()
        if " " in before:
            before = before.split(" ", 1)[1]

    # Construir surrounding_after
    p_last = paragraphs[match_end]
    norm_last = normalize_text(p_last)
    suffix = ""
    if norm_quote in norm_last:
        pos = norm_last.find(norm_quote) + len(norm_quote)
        suffix = p_last[pos:].strip()
    else:
        words = norm_quote.split()
        for count in (4, 3, 2, 1):
            if len(words) >= count:
                tail = " ".join(words[-count:])
                pos = norm_last.find(tail)
                if pos != -1:
                    suffix = p_last[pos + len(tail) :].strip()
                    break

    after_parts = []
    if suffix:
        after_parts.append(suffix)
    if match_end < len(paragraphs) - 1:
        after_parts.append(paragraphs[match_end + 1])
    after = " ".join(after_parts).strip()
    if len(after) > max_chars:
        after = after[:max_chars].rstrip()
        if " " in after:
            after = after.rsplit(" ", 1)[0]

    return chapter, before or None, after or None


def extract_annotation_contexts(
    database: Path | str,
    kindle_root: Path | str,
    *,
    work_id: str | None = None,
    limit: int | None = None,
    overwrite: bool = False,
) -> ContextExtractionResult:
    """
    Recorre las anotaciones vinculadas a entregas presentes en el Kindle y extrae
    los párrafos circundantes y títulos de capítulo en `annotation_contexts`.
    """
    database_path = Path(database).expanduser().resolve()
    kindle_path = Path(kindle_root).expanduser().resolve()

    if not kindle_path.exists():
        raise ContextExtractionError(f"El punto de montaje no existe: {kindle_path}")

    connection = connect_database(database_path)
    try:
        where_clauses = [
            "a.text IS NOT NULL",
            "TRIM(a.text) != ''",
            "a.text NOT LIKE '%clipping limit%'",
            "kd.relative_path IS NOT NULL",
        ]
        params: list[object] = []

        if not overwrite:
            where_clauses.append(
                "NOT EXISTS (SELECT 1 FROM annotation_contexts ac WHERE ac.annotation_id = a.id)"
            )

        if work_id:
            where_clauses.append("e.work_id = ?")
            params.append(work_id)

        query = f"""
            SELECT a.id, a.text, e.id AS edition_id, e.title AS edition_title,
                   kd.relative_path
            FROM annotations a
            JOIN editions e ON e.id = a.edition_id
            JOIN kindle_deliveries kd ON kd.edition_id = e.id
            WHERE {" AND ".join(where_clauses)}
            ORDER BY kd.relative_path, a.start_position_native ASC, a.created_at ASC
        """
        if limit and limit > 0:
            query += f" LIMIT {int(limit)}"

        rows = connection.execute(query, tuple(params)).fetchall()

        # Agrupar por archivo relativo para parsear cada libro solo una vez
        files_map: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            files_map.setdefault(row["relative_path"], []).append(row)

        books_scanned = len(files_map)
        books_matched = 0
        annotations_scanned = len(rows)
        annotations_matched = 0
        annotations_extracted = 0
        annotations_skipped = 0

        for rel_path, ann_list in files_map.items():
            book_file = kindle_path / rel_path
            if not book_file.exists():
                annotations_skipped += len(ann_list)
                continue

            try:
                paragraphs = extract_paragraphs_from_file(book_file)
            except Exception:
                annotations_skipped += len(ann_list)
                continue

            if not paragraphs:
                annotations_skipped += len(ann_list)
                continue

            book_matched = False
            for ann in ann_list:
                quote = ann["text"]
                chapter, before, after = find_surrounding_context(paragraphs, quote)
                if before or after or chapter:
                    with connection:
                        connection.execute(
                            """
                            INSERT INTO annotation_contexts (
                                annotation_id, chapter_title, surrounding_before,
                                surrounding_after, extracted_at
                            ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                            ON CONFLICT(annotation_id) DO UPDATE SET
                                chapter_title = excluded.chapter_title,
                                surrounding_before = excluded.surrounding_before,
                                surrounding_after = excluded.surrounding_after,
                                extracted_at = CURRENT_TIMESTAMP
                            """,
                            (ann["id"], chapter, before, after),
                        )
                    annotations_matched += 1
                    annotations_extracted += 1
                    book_matched = True
                else:
                    annotations_skipped += 1

            if book_matched:
                books_matched += 1

        return ContextExtractionResult(
            books_scanned=books_scanned,
            books_matched=books_matched,
            annotations_scanned=annotations_scanned,
            annotations_matched=annotations_matched,
            annotations_extracted=annotations_extracted,
            annotations_skipped=annotations_skipped,
        )
    finally:
        connection.close()
