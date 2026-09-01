from __future__ import annotations

import re
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .db import connect_database, migrate_database
from .personal import (
    PersonalDataError,
    add_work_note,
    add_work_relation,
    assign_work_to_collection,
    create_collection,
    set_work_display_title,
)
from .profiles import ProfileError, create_profile, update_profile


DISPLAY_TITLE_SQL = (
    "COALESCE(NULLIF(TRIM(w.display_title), ''), "
    "REPLACE(w.preferred_title, '_', ' '))"
)

PILOT_COVERS = {
    "0090294e-4a8d-5ce8-a419-86465bb89c23": {"path": "12-reglas-para-vivir.webp", "source": "Planeta de Libros"},
    "8b1880ff-42f3-5872-a175-d0da6f27066b": {"path": "1984.jpg", "source": "Open Library"},
    "71cbf0f0-1a6e-5bd9-aa61-beb4522351b1": {"path": "50-clasicos.jpg", "source": "Open Library"},
    "aa83da8e-115e-50eb-bc38-81536ce04f14": {"path": "anna-karenina.jpg", "source": "Librería Nacional"},
    "44274922-c5b3-5b15-b7c1-6a1b12396145": {"path": "antifragil.jpg", "source": "Zivals"},
    "daa74900-192b-5894-a02c-f136b4842260": {"path": "gandhi.jpg", "source": "Editorial Océano"},
    "8731def6-8203-5e31-9dfc-2d672c98e958": {"path": "bartleby.jpg", "source": "Librotea"},
}
PILOT_COVER_CANDIDATES = {
    "0090294e-4a8d-5ce8-a419-86465bb89c23": [
        {"path": "12-reglas-para-vivir.webp", "source": "Planeta"},
        {"path": "12-reglas-candidato-2.webp", "source": "El Aleph"},
        {"path": "12-reglas-candidato-3.webp", "source": "Booket"},
    ]
}

PAGE_PATTERN = re.compile(r"\b(?:page|página)\s+(\d+)", re.IGNORECASE)
LOCATION_PATTERN = re.compile(
    r"\b(?:location|ubicación|posición)\s+(\d+)(?:\s*[-–]\s*(\d+))?",
    re.IGNORECASE,
)


def _readable_reference(position: str | None, date_text: str | None) -> dict | None:
    source = " · ".join(value for value in (position, date_text) if value)
    page_match = PAGE_PATTERN.search(source)
    location_match = LOCATION_PATTERN.search(source)
    if page_match is None and location_match is None:
        return None
    parts = []
    result: dict[str, object] = {}
    if page_match is not None:
        result["page"] = int(page_match.group(1))
        parts.append(f"Página {page_match.group(1)}")
    if location_match is not None:
        start, end = location_match.groups()
        result["location_start"] = int(start)
        result["location_end"] = int(end) if end else None
        parts.append(f"Ubicación {start}{f'–{end}' if end else ''}")
    result["label"] = " · ".join(parts)
    return result


def _count(connection, query: str, parameters: tuple = ()) -> int:
    return int(connection.execute(query, parameters).fetchone()[0])


def _summary(connection) -> dict:
    snapshot = connection.execute(
        """
        SELECT completed_at, warning_count,
               (SELECT COUNT(*) FROM source_observations so WHERE so.snapshot_id = ds.id)
                   AS source_count
        FROM device_snapshots ds
        WHERE status = 'completed'
        ORDER BY started_at DESC LIMIT 1
        """
    ).fetchone()
    annotation_counts = {
        row["kind"]: row["total"]
        for row in connection.execute(
            "SELECT kind, COUNT(*) AS total FROM annotations GROUP BY kind"
        )
    }
    return {
        "database_available": True,
        "last_sync": dict(snapshot) if snapshot is not None else None,
        "catalog": {
            "works": _count(connection, "SELECT COUNT(*) FROM works"),
            "editions": _count(connection, "SELECT COUNT(*) FROM editions"),
            "deliveries": _count(connection, "SELECT COUNT(*) FROM kindle_deliveries"),
            "present": _count(connection, "SELECT COUNT(*) FROM kindle_deliveries WHERE presence = 'present'"),
            "absent": _count(connection, "SELECT COUNT(*) FROM kindle_deliveries WHERE presence = 'absent'"),
            "provisional": _count(connection, "SELECT COUNT(*) FROM works WHERE merge_status = 'provisional'"),
            "review": _count(connection, "SELECT COUNT(*) FROM works WHERE merge_status = 'review'"),
        },
        "annotations": {
            "total": sum(annotation_counts.values()),
            "highlight": annotation_counts.get("highlight", 0),
            "note": annotation_counts.get("note", 0),
            "bookmark": annotation_counts.get("bookmark", 0),
        },
        "organization": {
            "collections": _count(connection, "SELECT COUNT(*) FROM collections"),
            "notes": _count(connection, "SELECT COUNT(*) FROM personal_notes"),
            "relations": _count(connection, "SELECT COUNT(*) FROM work_relations"),
        },
        "warnings": _count(connection, "SELECT COUNT(*) FROM source_observations WHERE parse_status IN ('warning', 'failed')"),
    }


def _works_page(connection, *, query: str, presence: str, annotated: bool,
                sort: str, page: int, page_size: int) -> dict:
    conditions = []
    parameters: list[object] = []
    if query:
        conditions.append(f"({DISPLAY_TITLE_SQL} LIKE ? OR w.preferred_title LIKE ? OR COALESCE(c.authors, '') LIKE ?)")
        pattern = f"%{query}%"
        parameters.extend((pattern, pattern, pattern))
    if presence in {"present", "absent"}:
        conditions.append("COALESCE(d.presence, 'absent') = ?")
        parameters.append(presence)
    if annotated:
        conditions.append("COALESCE(a.annotation_count, 0) > 0")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    ordering = {
        "title": f"{DISPLAY_TITLE_SQL} COLLATE NOCASE, w.id",
        "annotations": f"annotation_count DESC, {DISPLAY_TITLE_SQL} COLLATE NOCASE",
    }.get(sort, f"{DISPLAY_TITLE_SQL} COLLATE NOCASE, w.id")
    common = """
        WITH a AS (
            SELECT e.work_id, COUNT(an.id) AS annotation_count
            FROM editions e LEFT JOIN annotations an ON an.edition_id = e.id
            GROUP BY e.work_id
        ), d AS (
            SELECT e.work_id,
                   CASE WHEN MAX(kd.presence = 'present') = 1 THEN 'present' ELSE 'absent' END AS presence
            FROM editions e LEFT JOIN kindle_deliveries kd ON kd.edition_id = e.id
            GROUP BY e.work_id
        ), c AS (
            SELECT e.work_id, GROUP_CONCAT(DISTINCT co.display_name) AS authors
            FROM editions e
            JOIN edition_contributors ec ON ec.edition_id = e.id
            JOIN contributors co ON co.id = ec.contributor_id
            WHERE ec.role = 'author'
            GROUP BY e.work_id
        )
    """
    total = _count(
        connection,
        common + f"SELECT COUNT(*) FROM works w LEFT JOIN a ON a.work_id = w.id LEFT JOIN d ON d.work_id = w.id LEFT JOIN c ON c.work_id = w.id {where}",
        tuple(parameters),
    )
    rows = connection.execute(
        common + f"""
        SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
               w.preferred_title AS original_title, w.display_title, w.merge_status,
               COALESCE(c.authors, '') AS authors,
               COALESCE(a.annotation_count, 0) AS annotation_count,
               COALESCE(d.presence, 'absent') AS presence
        FROM works w
        LEFT JOIN a ON a.work_id = w.id
        LEFT JOIN d ON d.work_id = w.id
        LEFT JOIN c ON c.work_id = w.id
        {where}
        ORDER BY {ordering}
        LIMIT ? OFFSET ?
        """,
        (*parameters, page_size, (page - 1) * page_size),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["cover"] = PILOT_COVERS.get(item["id"])
        preference = connection.execute(
            "SELECT selected_path, review_status FROM work_cover_preferences WHERE work_id = ?",
            (item["id"],),
        ).fetchone()
        if preference is not None:
            if preference["review_status"] == "none":
                item["cover"] = None
            elif preference["selected_path"]:
                item["cover"] = {"path": preference["selected_path"], "source": "Elegida por vos"}
        items.append(item)
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def _work_detail(connection, work_id: str) -> dict | None:
    work = connection.execute(
        f"""
        SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
               w.preferred_title AS original_title, w.display_title, w.merge_status,
               COALESCE(GROUP_CONCAT(DISTINCT co.display_name), '') AS authors
        FROM works w
        LEFT JOIN editions e ON e.work_id = w.id
        LEFT JOIN edition_contributors ec ON ec.edition_id = e.id AND ec.role = 'author'
        LEFT JOIN contributors co ON co.id = ec.contributor_id
        WHERE w.id = ? GROUP BY w.id
        """,
        (work_id,),
    ).fetchone()
    if work is None:
        return None
    editions = [
        dict(row) for row in connection.execute(
            """
            SELECT e.id, e.title, e.language, e.publisher, e.format_hint,
                   CASE WHEN MAX(kd.presence = 'present') = 1 THEN 'present' ELSE 'absent' END AS presence
            FROM editions e LEFT JOIN kindle_deliveries kd ON kd.edition_id = e.id
            WHERE e.work_id = ? GROUP BY e.id ORDER BY e.title COLLATE NOCASE
            """,
            (work_id,),
        )
    ]
    counts = {
        row["kind"]: row["total"] for row in connection.execute(
            """
            SELECT an.kind, COUNT(*) AS total FROM annotations an
            JOIN editions e ON e.id = an.edition_id
            WHERE e.work_id = ? GROUP BY an.kind
            """,
            (work_id,),
        )
    }
    progress = connection.execute(
        """
        SELECT rs.last_position_native, rs.last_position_type, rs.last_position_at,
               rs.furthest_position_native, rs.progress_fraction, rs.reading_time_ms,
               rs.words_read, rs.observed_at
        FROM reading_states rs
        JOIN kindle_deliveries kd ON kd.id = rs.kindle_delivery_id
        JOIN editions e ON e.id = kd.edition_id
        WHERE e.work_id = ? ORDER BY rs.observed_at DESC LIMIT 1
        """,
        (work_id,),
    ).fetchone()
    return {
        **dict(work),
        "editions": editions,
        "annotations": {
            "total": sum(counts.values()),
            "highlight": counts.get("highlight", 0),
            "note": counts.get("note", 0),
            "bookmark": counts.get("bookmark", 0),
        },
        "progress": dict(progress) if progress is not None else None,
        "personal": {
            "collections": _count(connection, "SELECT COUNT(*) FROM work_collections WHERE work_id = ?", (work_id,)),
            "notes": _count(connection, "SELECT COUNT(*) FROM personal_notes WHERE target_type = 'work' AND target_id = ?", (work_id,)),
            "relations": _count(connection, "SELECT COUNT(*) FROM work_relations WHERE source_work_id = ? OR target_work_id = ?", (work_id, work_id)),
        },
    }


def _annotation_page(connection, work_id: str, *, kind: str, source: str,
                     page: int, page_size: int) -> dict:
    conditions = ["e.work_id = ?"]
    parameters: list[object] = [work_id]
    if kind != "all":
        conditions.append("an.kind = ?")
        parameters.append(kind)
    if source != "all":
        conditions.append("EXISTS (SELECT 1 FROM annotation_occurrences ox WHERE ox.annotation_id = an.id AND ox.source_kind = ?)")
        parameters.append(source)
    where = " AND ".join(conditions)
    total = _count(connection, f"SELECT COUNT(*) FROM annotations an JOIN editions e ON e.id = an.edition_id WHERE {where}", tuple(parameters))
    rows = connection.execute(
        f"""
        SELECT an.id, an.kind, an.text, an.note_text, an.start_position_native,
               an.end_position_native, an.position_type, an.native_created_at,
               an.status, GROUP_CONCAT(DISTINCT ao.source_kind) AS sources,
               COALESCE(
                   MAX(CASE WHEN ao.source_kind = 'clippings' THEN ao.original_position END),
                   (SELECT ao2.original_position
                    FROM annotations an2
                    JOIN editions e2 ON e2.id = an2.edition_id
                    JOIN annotation_occurrences ao2 ON ao2.annotation_id = an2.id
                    WHERE e2.work_id = e.work_id AND ao2.source_kind = 'clippings'
                      AND an.text IS NOT NULL AND TRIM(an2.text) = TRIM(an.text)
                    LIMIT 1)
               ) AS clipping_position,
               COALESCE(
                   MAX(CASE WHEN ao.source_kind = 'clippings' THEN ao.original_date END),
                   (SELECT ao2.original_date
                    FROM annotations an2
                    JOIN editions e2 ON e2.id = an2.edition_id
                    JOIN annotation_occurrences ao2 ON ao2.annotation_id = an2.id
                    WHERE e2.work_id = e.work_id AND ao2.source_kind = 'clippings'
                      AND an.text IS NOT NULL AND TRIM(an2.text) = TRIM(an.text)
                    LIMIT 1)
               ) AS clipping_date
        FROM annotations an
        JOIN editions e ON e.id = an.edition_id
        LEFT JOIN annotation_occurrences ao ON ao.annotation_id = an.id
        WHERE {where}
        GROUP BY an.id
        ORDER BY COALESCE(an.native_created_at, an.created_at) DESC, an.id
        LIMIT ? OFFSET ?
        """,
        (*parameters, page_size, (page - 1) * page_size),
    ).fetchall()
    items = []
    for row in rows:
        item = dict(row)
        item["reference"] = _readable_reference(
            item.pop("clipping_position"), item.pop("clipping_date")
        )
        items.append(item)
    return {
        "items": items, "page": page, "page_size": page_size,
        "total": total, "pages": max(1, (total + page_size - 1) // page_size),
    }


def _personal_data(connection, work_id: str) -> dict:
    collections = [dict(row) for row in connection.execute(
        """
        SELECT c.id, c.name, c.description, wc.note, wc.display_order
        FROM work_collections wc JOIN collections c ON c.id = wc.collection_id
        WHERE wc.work_id = ? ORDER BY wc.display_order, c.name COLLATE NOCASE
        """,
        (work_id,),
    )]
    notes = [dict(row) for row in connection.execute(
        """
        SELECT id, body, created_at, updated_at FROM personal_notes
        WHERE target_type = 'work' AND target_id = ? ORDER BY created_at DESC, id
        """,
        (work_id,),
    )]
    relations = [dict(row) for row in connection.execute(
        """
        SELECT wr.id, wr.relation_type, wr.label, wr.explanation, wr.is_symmetric,
               CASE WHEN wr.source_work_id = ? THEN wr.target_work_id ELSE wr.source_work_id END AS other_work_id,
               COALESCE(NULLIF(TRIM(ow.display_title), ''), REPLACE(ow.preferred_title, '_', ' ')) AS other_title
        FROM work_relations wr
        JOIN works ow ON ow.id = CASE WHEN wr.source_work_id = ? THEN wr.target_work_id ELSE wr.source_work_id END
        WHERE wr.source_work_id = ? OR wr.target_work_id = ?
        ORDER BY wr.updated_at DESC, wr.id
        """,
        (work_id, work_id, work_id, work_id),
    )]
    return {"collections": collections, "notes": notes, "relations": relations}


def _json_body() -> dict:
    if not request.is_json or request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise PersonalDataError("La operación requiere una solicitud local JSON")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise PersonalDataError("El contenido enviado no es válido")
    return payload


def create_app(database: Path | str) -> Flask:
    database_path = Path(database).expanduser().resolve()
    if database_path.is_file():
        migrate_database(database_path)
    app = Flask(__name__)
    app.config["DATABASE"] = database_path

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/library")
    def library() -> str:
        return render_template("library.html")

    @app.get("/library/<work_id>")
    def book(work_id: str) -> str:
        return render_template("book.html", work_id=work_id)

    @app.get("/settings/ai-profiles")
    def ai_profiles_settings() -> str:
        return render_template("profiles.html")

    @app.get("/settings/covers")
    def cover_settings() -> str:
        return render_template("cover_setup.html")

    @app.get("/api/cover-setup")
    def cover_setup():
        connection = connect_database(database_path)
        try:
            items = []
            for work_id, candidates in PILOT_COVER_CANDIDATES.items():
                work = connection.execute(f"SELECT {DISPLAY_TITLE_SQL} AS title FROM works w WHERE w.id = ?", (work_id,)).fetchone()
                if work is None: continue
                pref = connection.execute("SELECT review_status, selected_path FROM work_cover_preferences WHERE work_id = ?", (work_id,)).fetchone()
                items.append({"id": work_id, "title": work["title"], "authors": "Jordan B. Peterson", "candidates": candidates, "status": pref["review_status"] if pref else "pending", "selected_path": pref["selected_path"] if pref else None})
            return jsonify(items=items)
        finally: connection.close()

    @app.patch("/api/cover-setup/<work_id>")
    def cover_setup_update(work_id: str):
        payload = _json_body()
        status = payload.get("review_status")
        path = payload.get("selected_path")
        allowed = {item["path"] for item in PILOT_COVER_CANDIDATES.get(work_id, [])}
        if status not in {"confirmed", "none"} or (status == "confirmed" and path not in allowed):
            return jsonify(error="Elección de portada inválida"), 400
        connection = connect_database(database_path)
        try:
            with connection:
                connection.execute("INSERT INTO work_cover_preferences(work_id, selected_path, review_status) VALUES (?, ?, ?) ON CONFLICT(work_id) DO UPDATE SET selected_path=excluded.selected_path, review_status=excluded.review_status, updated_at=CURRENT_TIMESTAMP", (work_id, path, status))
            return jsonify(saved=True)
        finally: connection.close()

    @app.get("/api/ai-profiles")
    def ai_profiles():
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                """SELECT id, name, description, prompt, is_default, created_at, updated_at
                   FROM ai_profiles WHERE is_archived = 0
                   ORDER BY is_default DESC, name COLLATE NOCASE"""
            ).fetchall()
            return jsonify(items=[dict(row) for row in rows])
        finally:
            connection.close()

    @app.post("/api/ai-profiles")
    def ai_profile_create():
        try:
            payload = _json_body()
            identifier = create_profile(
                database_path, name=payload.get("name"),
                description=payload.get("description", ""), prompt=payload.get("prompt"),
                is_default=bool(payload.get("is_default", False)),
            )
            return jsonify(id=identifier), 201
        except ProfileError as error:
            return jsonify(error=str(error)), 400

    @app.patch("/api/ai-profiles/<profile_id>")
    def ai_profile_update(profile_id: str):
        try:
            update_profile(database_path, profile_id, _json_body())
            return jsonify(id=profile_id)
        except ProfileError as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/status")
    def status():
        if not database_path.is_file():
            return jsonify(database_available=False, works=0)
        connection = connect_database(database_path)
        try:
            works = connection.execute("SELECT COUNT(*) FROM works").fetchone()[0]
        except Exception:
            app.logger.exception("No se pudo consultar la base local")
            return jsonify(database_available=False, works=0), 503
        finally:
            connection.close()
        return jsonify(database_available=True, works=works)

    @app.get("/api/summary")
    def summary():
        if not database_path.is_file():
            return jsonify(database_available=False), 404
        connection = connect_database(database_path)
        try:
            return jsonify(_summary(connection))
        except Exception:
            app.logger.exception("No se pudo construir el resumen local")
            return jsonify(database_available=False), 503
        finally:
            connection.close()

    @app.get("/api/works")
    def works():
        if not database_path.is_file():
            return jsonify(database_available=False), 404
        query = request.args.get("q", "").strip()[:200]
        presence = request.args.get("presence", "all")
        annotated = request.args.get("annotated", "false").lower() == "true"
        sort = request.args.get("sort", "title")
        try:
            page = max(1, int(request.args.get("page", "1")))
            page_size = min(100, max(1, int(request.args.get("page_size", "24"))))
        except ValueError:
            return jsonify(error="Parámetros de paginación inválidos"), 400
        if presence not in {"all", "present", "absent"}:
            return jsonify(error="Filtro de presencia inválido"), 400
        if sort not in {"title", "annotations"}:
            return jsonify(error="Orden inválido"), 400
        connection = connect_database(database_path)
        try:
            return jsonify(_works_page(
                connection, query=query, presence=presence, annotated=annotated,
                sort=sort, page=page, page_size=page_size,
            ))
        finally:
            connection.close()

    @app.get("/api/works/<work_id>")
    def work_detail(work_id: str):
        if not database_path.is_file():
            return jsonify(database_available=False), 404
        connection = connect_database(database_path)
        try:
            detail = _work_detail(connection, work_id)
            if detail is None:
                return jsonify(error="Obra inexistente"), 404
            return jsonify(detail)
        finally:
            connection.close()

    @app.patch("/api/works/<work_id>/display-title")
    def work_display_title_update(work_id: str):
        try:
            payload = _json_body()
            title = payload.get("title")
            if title is not None and not isinstance(title, str):
                raise PersonalDataError("El título debe ser texto")
            display_title = set_work_display_title(database_path, work_id, title)
            connection = connect_database(database_path)
            try:
                row = connection.execute(
                    f"SELECT {DISPLAY_TITLE_SQL} AS title, w.preferred_title AS original_title FROM works w WHERE w.id = ?",
                    (work_id,),
                ).fetchone()
            finally:
                connection.close()
            return jsonify(title=row["title"], original_title=row["original_title"], display_title=display_title)
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/works/<work_id>/annotations")
    def work_annotations(work_id: str):
        kind = request.args.get("kind", "all")
        source = request.args.get("source", "all")
        if kind not in {"all", "highlight", "note", "bookmark", "other"}:
            return jsonify(error="Tipo de anotación inválido"), 400
        if source not in {"all", "clippings", "krds", "han", "other"}:
            return jsonify(error="Fuente inválida"), 400
        try:
            page = max(1, int(request.args.get("page", "1")))
            page_size = min(100, max(1, int(request.args.get("page_size", "20"))))
        except ValueError:
            return jsonify(error="Parámetros de paginación inválidos"), 400
        connection = connect_database(database_path)
        try:
            if connection.execute("SELECT 1 FROM works WHERE id = ?", (work_id,)).fetchone() is None:
                return jsonify(error="Obra inexistente"), 404
            return jsonify(_annotation_page(connection, work_id, kind=kind, source=source, page=page, page_size=page_size))
        finally:
            connection.close()

    @app.get("/api/collections")
    def collections():
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                "SELECT id, parent_id, name, description FROM collections ORDER BY name COLLATE NOCASE"
            ).fetchall()
            return jsonify(items=[dict(row) for row in rows])
        finally:
            connection.close()

    @app.post("/api/collections")
    def collection_create():
        try:
            payload = _json_body()
            result = create_collection(
                database_path, str(payload.get("name", "")),
                parent_id=payload.get("parent_id"), description=payload.get("description"),
            )
            return jsonify(id=result.id, created=result.created), 201 if result.created else 200
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/work-options")
    def work_options():
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                f"SELECT id, {DISPLAY_TITLE_SQL} AS title FROM works w ORDER BY {DISPLAY_TITLE_SQL} COLLATE NOCASE"
            ).fetchall()
            return jsonify(items=[dict(row) for row in rows])
        finally:
            connection.close()

    @app.get("/api/works/<work_id>/personal")
    def work_personal(work_id: str):
        connection = connect_database(database_path)
        try:
            if connection.execute("SELECT 1 FROM works WHERE id = ?", (work_id,)).fetchone() is None:
                return jsonify(error="Obra inexistente"), 404
            return jsonify(_personal_data(connection, work_id))
        finally:
            connection.close()

    @app.post("/api/works/<work_id>/collections")
    def work_collection_assign(work_id: str):
        try:
            payload = _json_body()
            created = assign_work_to_collection(
                database_path, work_id, str(payload.get("collection_id", "")),
                note=payload.get("note"), display_order=int(payload.get("display_order", 0)),
            )
            return jsonify(created=created), 201 if created else 200
        except (PersonalDataError, TypeError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/works/<work_id>/notes")
    def work_note_create(work_id: str):
        try:
            payload = _json_body()
            identifier = add_work_note(database_path, work_id, str(payload.get("body", "")))
            return jsonify(id=identifier), 201
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/works/<work_id>/relations")
    def work_relation_create(work_id: str):
        try:
            payload = _json_body()
            result = add_work_relation(
                database_path, work_id, str(payload.get("target_work_id", "")),
                str(payload.get("relation_type", "")), label=payload.get("label"),
                explanation=payload.get("explanation"), symmetric=bool(payload.get("symmetric", False)),
            )
            return jsonify(id=result.id, created=result.created), 201 if result.created else 200
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    return app


def run_server(
    database: Path | str,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> None:
    if host != "127.0.0.1":
        raise ValueError("La interfaz local solo puede escuchar en 127.0.0.1")
    create_app(database).run(host=host, port=port, debug=False)
