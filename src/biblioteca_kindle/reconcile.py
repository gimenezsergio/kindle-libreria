from __future__ import annotations

import sqlite3
import re
from dataclasses import dataclass

from .clippings import normalize_title


@dataclass(frozen=True)
class ReconciliationResult:
    resolved_aliases: int
    moved_annotations: int
    unresolved_aliases: int
    removed_provisional_editions: int
    removed_provisional_works: int


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

    return ReconciliationResult(
        resolved_aliases=resolved,
        moved_annotations=moved,
        unresolved_aliases=unresolved,
        removed_provisional_editions=removed_editions,
        removed_provisional_works=removed_works,
    )
