from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .clippings import normalize_title


@dataclass(frozen=True)
class ReconciliationResult:
    resolved_aliases: int
    moved_annotations: int
    unresolved_aliases: int
    removed_provisional_editions: int
    removed_provisional_works: int
    merged_annotations: int = 0


_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
    "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
    "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def _clipping_local_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    match = re.search(
        r"(?:Added on|Añadido el)\s+[^,]+,\s+(\d{1,2})\s+([A-Za-záéíóúñ]+)\s+(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})",
        value,
        re.IGNORECASE,
    )
    if not match:
        return None
    month = _MONTHS.get(match.group(2).casefold())
    if month is None:
        return None
    return datetime(
        int(match.group(3)), month, int(match.group(1)),
        int(match.group(4)), int(match.group(5)), int(match.group(6)),
    )


def _native_utc_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(microsecond=0)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)


def reconcile_annotation_sources(connection: sqlite3.Connection) -> int:
    """Unify exact cross-source matches while retaining every source occurrence."""
    clippings = connection.execute(
        """
        SELECT a.id, a.edition_id, a.kind, a.native_created_at
        FROM annotations a
        JOIN annotation_occurrences ao ON ao.annotation_id = a.id
        WHERE ao.source_kind = 'clippings'
        ORDER BY a.edition_id, a.kind, a.id
        """
    ).fetchall()
    native = connection.execute(
        """
        SELECT a.id, a.edition_id, a.kind, a.start_position_native,
               a.end_position_native, a.native_created_at, a.native_modified_at
        FROM annotations a
        JOIN annotation_occurrences ao ON ao.annotation_id = a.id
        WHERE ao.source_kind IN ('krds', 'han')
          AND NOT EXISTS (
              SELECT 1 FROM annotation_occurrences clipping_occurrence
              WHERE clipping_occurrence.annotation_id = a.id
                AND clipping_occurrence.source_kind = 'clippings'
          )
        ORDER BY a.edition_id, a.kind, a.id
        """
    ).fetchall()
    native_timestamps: list[tuple[sqlite3.Row, datetime]] = []
    for row in native:
        timestamp = _native_utc_timestamp(row["native_created_at"])
        if timestamp is not None:
            native_timestamps.append((row, timestamp))

    clipping_timestamps = [
        (row, timestamp)
        for row in clippings
        if (timestamp := _clipping_local_timestamp(row["native_created_at"])) is not None
    ]
    offsets = range(-12 * 60, 14 * 60 + 1, 15)
    scores: dict[int, int] = {}
    for offset_minutes in offsets:
        native_keys = {
            (row["edition_id"], row["kind"], timestamp + timedelta(minutes=offset_minutes))
            for row, timestamp in native_timestamps
        }
        scores[offset_minutes] = sum(
            (row["edition_id"], row["kind"], timestamp) in native_keys
            for row, timestamp in clipping_timestamps
        )
    best_score = max(scores.values(), default=0)
    best_offsets = [offset for offset, score in scores.items() if score == best_score]
    if best_score == 0 or len(best_offsets) != 1:
        return 0
    inferred_offset = best_offsets[0]

    candidates: dict[tuple[str, str, datetime], list[sqlite3.Row]] = {}
    for row, timestamp in native_timestamps:
        local = timestamp + timedelta(minutes=inferred_offset)
        candidates.setdefault((row["edition_id"], row["kind"], local), []).append(row)

    merged = 0
    used_native: set[str] = set()
    for clipping, timestamp in clipping_timestamps:
        matches: list[sqlite3.Row] = []
        for offset in (-1, 0, 1):
            probe = timestamp + timedelta(seconds=offset)
            matches.extend(candidates.get((clipping["edition_id"], clipping["kind"], probe), []))
        matches = [row for row in matches if row["id"] not in used_native]
        if len(matches) != 1:
            continue
        source = matches[0]
        used_native.add(source["id"])
        connection.execute(
            """
            UPDATE annotations SET
                start_position_native = COALESCE(start_position_native, ?),
                end_position_native = COALESCE(end_position_native, ?),
                native_modified_at = COALESCE(native_modified_at, ?),
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                source["start_position_native"], source["end_position_native"],
                source["native_modified_at"], clipping["id"],
            ),
        )
        connection.execute(
            "UPDATE annotation_occurrences SET annotation_id = ? WHERE annotation_id = ?",
            (clipping["id"], source["id"]),
        )
        connection.execute(
            "UPDATE personal_notes SET target_id = ? WHERE target_type = 'annotation' AND target_id = ?",
            (clipping["id"], source["id"]),
        )
        for context in connection.execute(
            "SELECT id, conversation_id FROM conversation_context_sources WHERE source_type = 'annotation' AND source_id = ?",
            (source["id"],),
        ).fetchall():
            duplicate = connection.execute(
                "SELECT 1 FROM conversation_context_sources WHERE conversation_id = ? AND source_type = 'annotation' AND source_id = ?",
                (context["conversation_id"], clipping["id"]),
            ).fetchone()
            if duplicate:
                connection.execute("DELETE FROM conversation_context_sources WHERE id = ?", (context["id"],))
            else:
                connection.execute(
                    "UPDATE conversation_context_sources SET source_id = ? WHERE id = ?",
                    (clipping["id"], context["id"]),
                )
        connection.execute("DELETE FROM annotations WHERE id = ?", (source["id"],))
        merged += 1
    return merged


def reconcile_provisional_titles(
    connection: sqlite3.Connection,
) -> ReconciliationResult:
    aliases = connection.execute(
        """
        SELECT ta.id, ta.edition_id, ta.original_title, ta.normalized_title,
               e.work_id
        FROM title_aliases AS ta
        JOIN editions AS e ON e.id = ta.edition_id
        WHERE ta.resolution_status IN ('provisional', 'conflict')
        ORDER BY ta.id
        """
    ).fetchall()
    editions = connection.execute("SELECT id, title FROM editions").fetchall()
    aliases_by_edition: dict[str, set[str]] = {}
    for row in connection.execute(
        "SELECT edition_id, normalized_title FROM title_aliases WHERE edition_id IS NOT NULL"
    ):
        aliases_by_edition.setdefault(row["edition_id"], set()).add(
            row["normalized_title"]
        )

    resolved = moved = unresolved = removed_editions = removed_works = 0
    for alias in aliases:
        normalized = alias["normalized_title"]
        heading_without_parenthetical = re.sub(
            r"\s*\([^()]*\)\s*$", "", alias["original_title"]
        ).strip()
        accepted_names = {normalized, normalize_title(heading_without_parenthetical)}
        accepted_names.discard("")
        candidates: set[str] = set()
        for edition in editions:
            if edition["id"] == alias["edition_id"]:
                continue
            names = {normalize_title(edition["title"])} | aliases_by_edition.get(
                edition["id"], set()
            )
            if accepted_names & names:
                candidates.add(edition["id"])
        if len(candidates) != 1:
            unresolved += 1
            continue
        target_edition = next(iter(candidates))
        cursor = connection.execute(
            "UPDATE annotations SET edition_id = ? WHERE edition_id = ?",
            (target_edition, alias["edition_id"]),
        )
        moved += cursor.rowcount
        connection.execute(
            """
            UPDATE title_aliases
            SET edition_id = ?, confidence = 'medium', resolution_status = 'resolved'
            WHERE id = ?
            """,
            (target_edition, alias["id"]),
        )
        resolved += 1

        edition_in_use = connection.execute(
            """
            SELECT
                EXISTS(SELECT 1 FROM kindle_deliveries WHERE edition_id = ?) OR
                EXISTS(SELECT 1 FROM annotations WHERE edition_id = ?) OR
                EXISTS(SELECT 1 FROM title_aliases WHERE edition_id = ?)
            """,
            (alias["edition_id"], alias["edition_id"], alias["edition_id"]),
        ).fetchone()[0]
        if not edition_in_use:
            connection.execute("DELETE FROM editions WHERE id = ?", (alias["edition_id"],))
            removed_editions += 1
            work_in_use = connection.execute(
                """
                SELECT
                    EXISTS(SELECT 1 FROM editions WHERE work_id = ?) OR
                    EXISTS(SELECT 1 FROM work_collections WHERE work_id = ?) OR
                    EXISTS(SELECT 1 FROM work_relations WHERE source_work_id = ? OR target_work_id = ?)
                """,
                (alias["work_id"], alias["work_id"], alias["work_id"], alias["work_id"]),
            ).fetchone()[0]
            if not work_in_use:
                connection.execute("DELETE FROM works WHERE id = ?", (alias["work_id"],))
                removed_works += 1

    merged_annotations = reconcile_annotation_sources(connection)
    return ReconciliationResult(
        resolved_aliases=resolved,
        moved_annotations=moved,
        unresolved_aliases=unresolved,
        removed_provisional_editions=removed_editions,
        removed_provisional_works=removed_works,
        merged_annotations=merged_annotations,
    )
