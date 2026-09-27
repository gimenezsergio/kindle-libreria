from __future__ import annotations

import json
import sqlite3
import unicodedata
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import connect_database


class ManualWorkError(RuntimeError):
    pass


def _normalize_name(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(without_marks.casefold().split())


def _clean_text(value: object, label: str, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ManualWorkError(f"{label} debe ser texto")
    text = value.strip()
    if required and not text:
        raise ManualWorkError(f"{label} no puede estar vacío")
    return text


def search_external_books(query: str, page: int = 1) -> list[dict]:
    clean_query = query.strip()
    if not clean_query:
        return []
    url = "https://openlibrary.org/search.json?" + urllib.parse.urlencode(
        {"q": clean_query, "limit": 10, "page": page}
    )
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "BibliotecaKindle/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.load(response)
    except Exception as exc:
        raise ManualWorkError("No se pudo conectar con el buscador externo") from exc

    results = []
    for doc in data.get("docs", []):
        cover_i = doc.get("cover_i")
        author_names = doc.get("author_name", [])
        if isinstance(author_names, str):
            author_names = [author_names]
        isbn_list = doc.get("isbn", [])
        isbn = isbn_list[0] if isinstance(isbn_list, list) and isbn_list else None
        results.append(
            {
                "key": doc.get("key"),
                "title": doc.get("title", "Sin título"),
                "authors": author_names,
                "first_publish_year": doc.get("first_publish_year"),
                "cover_i": cover_i,
                "cover_url": (
                    f"https://covers.openlibrary.org/b/id/{cover_i}-M.jpg"
                    if cover_i
                    else None
                ),
                "isbn": isbn,
            }
        )
    return results


def _download_cover(cover_i: int, work_id: str, covers_dir: Path) -> str | None:
    filename = f"user_{work_id[:8]}_ol-{cover_i}.jpg"
    target = covers_dir / filename
    if target.is_file():
        return filename
    try:
        covers_dir.mkdir(parents=True, exist_ok=True)
        img_req = urllib.request.Request(
            f"https://covers.openlibrary.org/b/id/{cover_i}-L.jpg",
            headers={"User-Agent": "BibliotecaKindle/1.0"},
        )
        with urllib.request.urlopen(img_req, timeout=15) as response:
            data = response.read()
        if len(data) >= 1500:
            target.write_bytes(data)
            return filename
    except Exception:
        pass
    return None


def create_manual_work(
    database: Path | str,
    *,
    title: object,
    author: object = "",
    display_title: object = None,
    publish_year: object = None,
    cover_i: object = None,
    covers_dir: Path | str | None = None,
) -> dict:
    clean_title_val = _clean_text(title, "El título", required=True)
    clean_author_val = _clean_text(author, "El autor") if author else ""
    clean_display = _clean_text(display_title, "El título mostrado") if display_title else None

    database_path = Path(database).expanduser().resolve()
    if not database_path.is_file():
        raise ManualWorkError("La base SQLite no existe")

    connection = connect_database(database_path)
    try:
        work_id = str(uuid.uuid4())
        edition_id = str(uuid.uuid4())

        with connection:
            connection.execute(
                """
                INSERT INTO works(id, preferred_title, display_title, merge_status)
                VALUES (?, ?, ?, 'normal')
                """,
                (work_id, clean_title_val, clean_display),
            )

            connection.execute(
                """
                INSERT INTO editions(id, work_id, title, format_hint)
                VALUES (?, ?, ?, 'MANUAL')
                """,
                (edition_id, work_id, clean_title_val),
            )

            if clean_author_val:
                contributor = connection.execute(

                    "SELECT id FROM contributors WHERE display_name = ? COLLATE NOCASE",
                    (clean_author_val,),
                ).fetchone()
                if contributor:
                    contributor_id = contributor["id"]
                else:
                    contributor_id = str(uuid.uuid4())
                    connection.execute(
                        "INSERT INTO contributors(id, display_name, normalized_name) VALUES (?, ?, ?)",
                        (contributor_id, clean_author_val, _normalize_name(clean_author_val)),
                    )

                connection.execute(
                    """
                    INSERT INTO edition_contributors(edition_id, contributor_id, role, display_order)
                    VALUES (?, ?, 'author', 0)
                    ON CONFLICT DO NOTHING
                    """,
                    (edition_id, contributor_id),
                )


            downloaded_cover = None
            if cover_i and covers_dir:
                try:
                    cover_num = int(cover_i)
                    downloaded_cover = _download_cover(cover_num, work_id, Path(covers_dir))
                    if downloaded_cover:
                        candidate_id = str(uuid.uuid4())
                        connection.execute(
                            """
                            INSERT INTO cover_candidates(
                                id, work_id, local_path, source_label, edition_label,
                                confidence, display_order, status, external_key
                            ) VALUES (?, ?, ?, 'Open Library', ?, 'high', 0, 'confirmed', ?)
                            """,
                            (
                                candidate_id,
                                work_id,
                                downloaded_cover,
                                str(publish_year) if publish_year else "Importado",
                                f"openlibrary:{cover_num}",
                            ),
                        )
                        connection.execute(
                            """
                            INSERT INTO work_cover_preferences(
                                id, work_id, review_status, selected_candidate_id, custom_relative_path
                            ) VALUES (?, ?, 'confirmed', ?, ?)
                            ON CONFLICT(work_id) DO UPDATE SET
                                review_status = 'confirmed',
                                selected_candidate_id = excluded.selected_candidate_id,
                                custom_relative_path = excluded.custom_relative_path,
                                updated_at = CURRENT_TIMESTAMP
                            """,
                            (str(uuid.uuid4()), work_id, candidate_id, downloaded_cover),
                        )
                except (ValueError, TypeError):
                    pass

        return {
            "id": work_id,
            "title": clean_display or clean_title_val,
            "author": clean_author_val,
            "cover_path": downloaded_cover,
        }
    finally:
        connection.close()


def delete_work(database: Path | str, work_id: str) -> None:
    database_path = Path(database).expanduser().resolve()
    if not database_path.is_file():
        raise ManualWorkError("La base SQLite no existe")

    connection = connect_database(database_path)
    try:
        connection.execute("PRAGMA foreign_keys = ON;")
        work = connection.execute("SELECT id FROM works WHERE id = ?", (work_id,)).fetchone()
        if work is None:
            raise ManualWorkError("La obra especificada no existe")

        edition_rows = connection.execute("SELECT id FROM editions WHERE work_id = ?", (work_id,)).fetchall()
        edition_ids = [row["id"] for row in edition_rows]

        with connection:
            if edition_ids:
                placeholders = ",".join("?" for _ in edition_ids)
                connection.execute(
                    f"""
                    DELETE FROM reading_states
                    WHERE kindle_delivery_id IN (
                        SELECT id FROM kindle_deliveries WHERE edition_id IN ({placeholders})
                    )
                    """,
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM kindle_deliveries WHERE edition_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"""
                    DELETE FROM annotation_occurrences
                    WHERE annotation_id IN (
                        SELECT id FROM annotations WHERE edition_id IN ({placeholders})
                    )
                    """,
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM annotations WHERE edition_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM edition_contributors WHERE edition_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM title_aliases WHERE edition_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM external_identifiers WHERE entity_type = 'edition' AND entity_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM personal_notes WHERE target_type = 'edition' AND target_id IN ({placeholders})",
                    tuple(edition_ids),
                )
                connection.execute(
                    f"DELETE FROM editions WHERE work_id = ?",
                    (work_id,),
                )

            connection.execute(
                "DELETE FROM external_identifiers WHERE entity_type = 'work' AND entity_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM personal_notes WHERE target_type = 'work' AND target_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM work_collections WHERE work_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM work_relations WHERE source_work_id = ? OR target_work_id = ?",
                (work_id, work_id),
            )
            connection.execute(
                "DELETE FROM cover_candidates WHERE work_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM work_cover_preferences WHERE work_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM conversation_message_sources WHERE work_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM reading_conversations WHERE work_id = ?",
                (work_id,),
            )
            connection.execute(
                "DELETE FROM works WHERE id = ?",
                (work_id,),
            )
    finally:
        connection.close()

