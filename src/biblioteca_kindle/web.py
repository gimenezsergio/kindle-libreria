from __future__ import annotations

import json
import re
import hmac
import os
import sqlite3
import uuid
from pathlib import Path

from flask import Flask, jsonify, redirect, render_template, request, send_from_directory
from werkzeug.utils import secure_filename

from .db import connect_database, migrate_database
from .personal import (
    PersonalDataError,
    add_work_note,
    add_work_relation,
    assign_work_to_collection,
    bulk_assign_works_to_collection,
    create_collection,
    delete_collection,
    set_work_display_title,
    update_collection,
)
from .profiles import ProfileError, create_profile, update_profile
from .cover_search import CoverSearchError, search_covers
from .conversations import (
    ConversationError,
    add_message,
    create_conversation,
    context_options,
    get_conversation,
    list_work_conversations,
    update_conversation_title,
    update_context,
    build_prompt_packet,
    attach_library_sources,
    pin_library_sources,
    resolve_turn_context_sources,
)
from .ai import AIError, DraftProvider, PRESET_PROVIDERS, load_environment_file, provider_from_environment, resolve_provider_for_profile, save_environment_config
from .companion_actions import get_companion_action, list_companion_actions
from .library_search import LibrarySearchError
from .retrieval import requested_library_sources as retrieve_library_sources
from .openclaw_api import create_openclaw_blueprint
from .remote_sync import SyncPackageError
from .sync_receiver import apply_sync_package


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
INITIAL_COVER_CANDIDATES = {
    "0090294e-4a8d-5ce8-a419-86465bb89c23": [
        {"path": "12-reglas-para-vivir.webp", "source": "Planeta"},
        {"path": "12-reglas-candidato-2.webp", "source": "El Aleph"},
        {"path": "12-reglas-candidato-3.webp", "source": "Booket"},
    ]
}


def _seed_cover_candidates(connection) -> None:
    with connection:
        for work_id, candidates in INITIAL_COVER_CANDIDATES.items():
            if connection.execute("SELECT 1 FROM works WHERE id = ?", (work_id,)).fetchone() is None:
                continue
            for order, candidate in enumerate(candidates):
                connection.execute(
                    """INSERT INTO cover_candidates(
                           id, work_id, local_path, source_label, confidence, display_order)
                       VALUES (?, ?, ?, ?, 'high', ?)
                       ON CONFLICT(work_id, local_path) DO NOTHING""",
                    (f"{work_id}:{order}", work_id, candidate["path"], candidate["source"], order),
                )

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
                collection: str | None = None, sort: str, page: int, page_size: int) -> dict:
    conditions = []
    parameters: list[object] = []
    if collection:
        if collection == "uncategorized":
            conditions.append("w.id NOT IN (SELECT work_id FROM work_collections)")
        else:
            conditions.append("w.id IN (SELECT work_id FROM work_collections WHERE collection_id = ?)")
            parameters.append(collection)
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
        preference = connection.execute(
            "SELECT selected_path, review_status FROM work_cover_preferences WHERE work_id = ?",
            (item["id"],),
        ).fetchone()
        if preference is not None:
            if preference["review_status"] == "none":
                item["cover"] = None
            elif preference["selected_path"]:
                item["cover"] = {"path": preference["selected_path"], "source": "Elegida por vos"}
        else:
            candidate = connection.execute(
                "SELECT local_path, source_label FROM cover_candidates WHERE work_id = ? AND status = 'available' ORDER BY display_order LIMIT 1",
                (item["id"],),
            ).fetchone()
            if candidate is not None:
                item["cover"] = {"path": candidate["local_path"], "source": candidate["source_label"]}
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
    cover = PILOT_COVERS.get(work_id)
    cover_preference = connection.execute(
        "SELECT selected_path, review_status FROM work_cover_preferences WHERE work_id = ?",
        (work_id,),
    ).fetchone()
    if cover_preference is not None:
        if cover_preference["review_status"] == "none":
            cover = None
        elif cover_preference["selected_path"]:
            cover = {"path": cover_preference["selected_path"], "source": "Elegida por vos"}
    return {
        **dict(work),
        "cover": cover,
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


def create_app(database: Path | str, ai_provider=None) -> Flask:
    database_path = Path(database).expanduser().resolve()
    load_environment_file(database_path.parent / ".env")
    if database_path.is_file():
        migrate_database(database_path)
        connection = connect_database(database_path)
        try:
            _seed_cover_candidates(connection)
        finally:
            connection.close()
    app = Flask(__name__)
    app.config["DATABASE"] = database_path
    app.config["MAX_CONTENT_LENGTH"] = int(
        os.environ.get("BIBLIOTECA_SYNC_MAX_BYTES", str(32 * 1024 * 1024))
    )
    sync_token = os.environ.get("BIBLIOTECA_SYNC_TOKEN", "")
    openclaw_token = os.environ.get("BIBLIOTECA_OPENCLAW_TOKEN", "")
    provider = ai_provider or provider_from_environment()
    app.register_blueprint(create_openclaw_blueprint(database_path, openclaw_token))

    @app.route("/static/covers/<path:filename>")
    def serve_cover(filename: str):
        static_covers = Path(app.static_folder) / "covers" / filename
        if static_covers.is_file():
            return send_from_directory(Path(app.static_folder) / "covers", filename)
        work_covers = database_path.parent / "covers" / filename
        if work_covers.is_file():
            return send_from_directory(database_path.parent / "covers", filename)
        return ("Cover image not found", 404)

    def requested_library_sources(
        conversation_id: str, payload: dict, *, conversation: dict | None = None
    ) -> list[dict]:
        return retrieve_library_sources(
            database_path, conversation_id, payload, conversation=conversation
        )

    def prepare_companion_turn(conversation_id: str, payload: dict) -> dict:
        """Normaliza un borrador una sola vez para preview y envío real.

        La vista previa usa el mismo paquete que después recibe el proveedor.
        No persiste ni el borrador ni la selección de material.
        """
        try:
            action = get_companion_action(payload.get("companion_action_id"))
        except ValueError as error:
            raise ConversationError(str(error)) from error
        has_context_update = "personal_note_ids" in payload or "annotation_ids" in payload
        context_sources = resolve_turn_context_sources(
            database_path,
            conversation_id,
            personal_note_ids=payload.get("personal_note_ids") if has_context_update else None,
            annotation_ids=payload.get("annotation_ids") if has_context_update else None,
        )
        conversation = get_conversation(database_path, conversation_id)
        if conversation["status"] != "active":
            raise ConversationError("La conversación está archivada")
        conversation["context_sources"] = context_sources
        library_sources = requested_library_sources(
            conversation_id, payload, conversation=conversation
        )
        packet = build_prompt_packet(
            database_path,
            conversation_id,
            library_sources=library_sources,
            context_sources=context_sources,
            draft_content=payload.get("content"),
        )
        return {
            "action": action,
            "context_sources": context_sources,
            "has_context_update": has_context_update,
            "library_sources": library_sources,
            "packet": packet,
            "conversation": conversation,
        }

    def resolve_conversation_provider(conversation_id: str) -> AIProvider:
        connection = connect_database(database_path)
        try:
            row = connection.execute(
                """SELECT p.provider_id, p.model_override
                   FROM reading_conversations c
                   JOIN ai_profiles p ON c.profile_id = p.id
                   WHERE c.id = ?""",
                (conversation_id,)
            ).fetchone()
            if row and (row["provider_id"] or row["model_override"]):
                return resolve_provider_for_profile(row["provider_id"], row["model_override"])
        finally:
            connection.close()
        return provider

    def companion_turn_preview(turn: dict, payload: dict) -> dict:
        action = turn["action"]
        context_sources = turn["context_sources"]
        material = [
            item for item in context_sources
            if item["source_type"] in {"personal_note", "annotation"}
        ]
        conv_provider = resolve_conversation_provider(turn["conversation"]["id"])
        return {
            "profile": {"name": turn["conversation"]["profile_name_snapshot"]},
            "provider": {"name": conv_provider.name, "ready": conv_provider.ready},
            "action": (
                {"id": action.id, "label": action.label} if action is not None else None
            ),
            "draft": {"content": turn["packet"].input[-1]["content"]},
            "scope": {
                "search_library": bool(payload.get("search_library", False)),
                "search_scope": payload.get("search_scope", "library"),
                "search_work_ids": payload.get("search_work_ids", []),
            },
            "material": {
                "count": len(material),
                "items": [
                    {"type": item["source_type"], "label": item["label_snapshot"]}
                    for item in material
                ],
                "contains_full_text": False,
            },
            "library_sources": turn["library_sources"],
            "packet": turn["packet"].as_dict(),
        }

    @app.errorhandler(413)
    def sync_payload_too_large(_error):
        return jsonify(error="El paquete supera el límite de sincronización"), 413

    @app.post("/api/sync/v1/packages")
    def receive_sync_package():
        authorization = request.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not sync_token or not hmac.compare_digest(supplied, sync_token):
            return jsonify(error="Autenticación de sincronización inválida"), 401
        if not request.is_json:
            return jsonify(error="El paquete debe enviarse como JSON"), 415
        try:
            response = apply_sync_package(database_path, request.get_json(silent=True))
            return jsonify(response), 200 if response["status"] == "already_applied" else 201
        except (SyncPackageError, sqlite3.IntegrityError, KeyError, TypeError) as error:
            return jsonify(error=str(error)), 400

    @app.get("/")
    def index():
        return redirect("/library")

    @app.get("/library")
    def library() -> str:
        return render_template("library.html")

    @app.get("/library/<work_id>")
    def book(work_id: str) -> str:
        return render_template("book.html", work_id=work_id)

    @app.get("/settings")
    @app.get("/settings/ai-profiles")
    @app.get("/settings/covers")
    @app.get("/settings/status")
    def settings_page():
        return render_template("settings.html")

    def _load_custom_providers():
        config_file = database_path.parent / "ai_providers.json"
        if not config_file.is_file():
            return {}
        try:
            return json.loads(config_file.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_custom_providers(data: dict):
        config_file = database_path.parent / "ai_providers.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @app.get("/api/ai-config")
    @app.get("/api/ai-providers")
    def get_ai_config():
        custom = _load_custom_providers()
        all_providers = dict(PRESET_PROVIDERS)
        all_providers.update(custom)

        active_id = os.getenv("BIBLIOTECA_AI_PROVIDER", "draft").strip().lower()

        items = []
        for provider_id, pdata in all_providers.items():
            env_key_name = f"{provider_id.upper()}_API_KEY"
            key = ""
            if provider_id == active_id:
                key = os.getenv("BIBLIOTECA_AI_API_KEY", "")
            if not key:
                key = os.getenv(env_key_name, "")
            if not key and provider_id == "openai":
                key = os.getenv("OPENAI_API_KEY", "")
            if not key and provider_id == "deepseek":
                key = os.getenv("DEEPSEEK_API_KEY", "")
            if not key and provider_id == "gemini":
                key = os.getenv("GEMINI_API_KEY", "")
            if not key and provider_id == "openrouter":
                key = os.getenv("OPENROUTER_API_KEY", "")

            has_key = bool(key) or provider_id == "draft"
            masked_key = f"{key[:4]}...{key[-4:]}" if len(key) >= 10 else ("****" if key else "")

            base_url = pdata.get("base_url", "")
            model = pdata.get("model", "")
            protocol = pdata.get("protocol", "chat_completions")

            if provider_id == active_id:
                base_url = os.getenv("BIBLIOTECA_AI_BASE_URL", base_url)
                model = os.getenv("BIBLIOTECA_AI_MODEL", model)
                protocol = os.getenv("BIBLIOTECA_AI_PROTOCOL", protocol)

            items.append({
                "id": provider_id,
                "name": pdata.get("name", provider_id),
                "base_url": base_url,
                "model": model,
                "protocol": protocol,
                "models": pdata.get("models", []),
                "is_preset": provider_id in PRESET_PROVIDERS,
                "is_active": provider_id == active_id,
                "has_api_key": has_key,
                "masked_api_key": masked_key,
            })

        # Backwards compatible format + new providers list
        active_pdata = all_providers.get(active_id, PRESET_PROVIDERS["draft"])
        active_key = os.getenv("BIBLIOTECA_AI_API_KEY", "")
        masked_active = f"{active_key[:4]}...{active_key[-4:]}" if len(active_key) >= 10 else ("****" if active_key else "")

        return jsonify(
            provider=active_id,
            active_provider_id=active_id,
            model=os.getenv("BIBLIOTECA_AI_MODEL", active_pdata.get("model", "")),
            base_url=os.getenv("BIBLIOTECA_AI_BASE_URL", active_pdata.get("base_url", "")),
            has_api_key=bool(active_key) or active_id == "draft",
            masked_api_key=masked_active,
            providers=items,
        )

    @app.post("/api/ai-config")
    @app.post("/api/ai-providers")
    def set_ai_config():
        data = request.get_json(silent=True) or {}
        provider_id = str(data.get("id") or data.get("provider", "draft")).strip().lower()
        if not provider_id:
            return jsonify(error="El identificador de proveedor no puede estar vacío."), 400

        custom = _load_custom_providers()
        all_providers = dict(PRESET_PROVIDERS)
        all_providers.update(custom)

        existing = all_providers.get(provider_id, {})

        name = str(data.get("name", existing.get("name", provider_id.title()))).strip()
        base_url = str(data.get("base_url", existing.get("base_url", ""))).strip()
        model = str(data.get("model", existing.get("model", ""))).strip()
        protocol = str(data.get("protocol", existing.get("protocol", "chat_completions"))).strip()
        api_key = str(data.get("api_key", "")).strip()

        if provider_id not in PRESET_PROVIDERS:
            custom[provider_id] = {
                "id": provider_id,
                "name": name,
                "base_url": base_url,
                "model": model,
                "protocol": protocol,
            }
            _save_custom_providers(custom)

        updates = {
            "BIBLIOTECA_AI_PROVIDER": provider_id,
            "BIBLIOTECA_AI_BASE_URL": base_url,
            "BIBLIOTECA_AI_MODEL": model,
            "BIBLIOTECA_AI_PROTOCOL": protocol,
        }

        if api_key:
            updates["BIBLIOTECA_AI_API_KEY"] = api_key
            updates[f"{provider_id.upper()}_API_KEY"] = api_key

        env_path = database_path.parent / ".env"
        save_environment_config(env_path, updates)

        try:
            active_provider = provider_from_environment()
            app.config["AI_PROVIDER"] = active_provider
        except AIError as err:
            return jsonify(error=f"Configuración guardada en .env, pero el proveedor falló al inicializar: {err}"), 400

        return jsonify(
            message="Configuración de IA actualizada correctamente",
            provider=active_provider.name,
            ready=active_provider.ready,
        )

    @app.delete("/api/ai-providers/<provider_id>")
    def delete_ai_provider(provider_id: str):
        provider_id = provider_id.strip().lower()
        if provider_id in PRESET_PROVIDERS:
            return jsonify(error="No se pueden eliminar los proveedores predefinidos del sistema."), 400

        custom = _load_custom_providers()
        if provider_id in custom:
            del custom[provider_id]
            _save_custom_providers(custom)

        return jsonify(message="Proveedor eliminado correctamente.")



    @app.get("/api/cover-setup")
    def cover_setup():
        connection = connect_database(database_path)
        try:
            items = []
            work_ids = connection.execute("SELECT DISTINCT work_id FROM cover_candidates ORDER BY work_id").fetchall()
            for work_row in work_ids:
                work_id = work_row["work_id"]
                work = connection.execute(f"SELECT {DISPLAY_TITLE_SQL} AS title FROM works w WHERE w.id = ?", (work_id,)).fetchone()
                candidates = [dict(row) for row in connection.execute(
                    """SELECT id, local_path AS path, source_label AS source, isbn,
                              edition_label, confidence, status, search_round
                       FROM cover_candidates WHERE work_id = ?
                       ORDER BY display_order, created_at""", (work_id,)
                )]
                pref = connection.execute("SELECT review_status, selected_path FROM work_cover_preferences WHERE work_id = ?", (work_id,)).fetchone()
                items.append({"id": work_id, "title": work["title"], "authors": "Jordan B. Peterson", "candidates": candidates, "status": pref["review_status"] if pref else "pending", "selected_path": pref["selected_path"] if pref else None})
            return jsonify(items=items)
        finally: connection.close()

    @app.get("/api/cover-setup/<work_id>")
    def cover_setup_detail(work_id: str):
        connection = connect_database(database_path)
        try:
            candidates = [dict(row) for row in connection.execute(
                """SELECT id, local_path AS path, source_label AS source, isbn,
                           edition_label, confidence, status, search_round
                    FROM cover_candidates WHERE work_id = ?
                    ORDER BY display_order, created_at""", (work_id,)
            )]
            pref = connection.execute("SELECT review_status, selected_path FROM work_cover_preferences WHERE work_id = ?", (work_id,)).fetchone()
            return jsonify(
                work_id=work_id,
                candidates=candidates,
                status=pref["review_status"] if pref else "pending",
                selected_path=pref["selected_path"] if pref else None
            )
        finally: connection.close()

    @app.patch("/api/cover-setup/<work_id>")
    def cover_setup_update(work_id: str):
        payload = _json_body()
        status = payload.get("review_status")
        path = payload.get("selected_path")
        connection = connect_database(database_path)
        allowed = {row["local_path"] for row in connection.execute("SELECT local_path FROM cover_candidates WHERE work_id = ?", (work_id,))}
        if status not in {"confirmed", "none"} or (status == "confirmed" and path not in allowed):
            connection.close()
            return jsonify(error="Elección de portada inválida"), 400
        try:
            with connection:
                connection.execute("INSERT INTO work_cover_preferences(work_id, selected_path, review_status) VALUES (?, ?, ?) ON CONFLICT(work_id) DO UPDATE SET selected_path=excluded.selected_path, review_status=excluded.review_status, updated_at=CURRENT_TIMESTAMP", (work_id, path, status))
                if status == "none":
                    connection.execute("UPDATE cover_candidates SET status = 'rejected', updated_at = CURRENT_TIMESTAMP WHERE work_id = ?", (work_id,))
                else:
                    connection.execute("UPDATE cover_candidates SET status = 'available', updated_at = CURRENT_TIMESTAMP WHERE work_id = ? AND local_path = ?", (work_id, path))
            return jsonify(saved=True)
        finally: connection.close()

    @app.post("/api/cover-setup/<work_id>/search")
    def cover_setup_search(work_id: str):
        try:
            _json_body()
            added = search_covers(database_path, work_id, Path(app.static_folder) / "covers")
            return jsonify(added=added), 201
        except CoverSearchError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/cover-setup/<work_id>/upload")
    def cover_setup_upload(work_id: str):
        if "file" not in request.files:
            return jsonify(error="No se envió ninguna imagen."), 400
        file = request.files["file"]
        if not file or not file.filename:
            return jsonify(error="Archivo de imagen inválido."), 400

        filename = secure_filename(file.filename)
        ext = Path(filename).suffix.lower()
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}:
            return jsonify(error="Formato de imagen no soportado. Usá JPG, PNG, WEBP o GIF."), 400

        candidate_id = f"custom-{uuid.uuid4().hex[:8]}"
        local_filename = f"user_{work_id}_{candidate_id}{ext}"
        covers_dir = Path(app.static_folder) / "covers"
        covers_dir.mkdir(parents=True, exist_ok=True)
        file.save(covers_dir / local_filename)

        connection = connect_database(database_path)
        try:
            with connection:
                connection.execute(
                    """INSERT INTO cover_candidates (id, work_id, local_path, source_label, confidence, status)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (candidate_id, work_id, local_filename, "Subida local", "high", "available")
                )
                connection.execute(
                    """INSERT INTO work_cover_preferences (work_id, selected_path, review_status)
                       VALUES (?, ?, 'confirmed')
                       ON CONFLICT(work_id) DO UPDATE SET selected_path=excluded.selected_path, review_status=excluded.review_status, updated_at=CURRENT_TIMESTAMP""",
                    (work_id, local_filename)
                )
            return jsonify(saved=True, path=local_filename), 201
        finally:
            connection.close()

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

    @app.get("/api/works/<work_id>/conversations")
    def work_conversations(work_id: str):
        try:
            return jsonify(items=list_work_conversations(database_path, work_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @app.post("/api/works/<work_id>/conversations")
    def work_conversation_create(work_id: str):
        try:
            payload = _json_body()
            identifier = create_conversation(
                database_path,
                work_id=work_id,
                profile_id=str(payload.get("profile_id", "")),
                title=payload.get("title", ""),
            )
            return jsonify(id=identifier), 201
        except (ConversationError, PersonalDataError) as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/conversations/<conversation_id>")
    def conversation_detail(conversation_id: str):
        try:
            return jsonify(get_conversation(database_path, conversation_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @app.patch("/api/conversations/<conversation_id>/title")
    def conversation_title_update(conversation_id: str):
        try:
            payload = _json_body()
            update_conversation_title(
                database_path, conversation_id=conversation_id, title=payload.get("title")
            )
            return jsonify(get_conversation(database_path, conversation_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/conversations/<conversation_id>/messages")
    def conversation_message_create(conversation_id: str):
        try:
            payload = _json_body()
            identifier = add_message(
                database_path,
                conversation_id=conversation_id,
                role="user",
                content=payload.get("content"),
                companion_action_id=payload.get("companion_action_id"),
            )
            return jsonify(id=identifier), 201
        except (ConversationError, PersonalDataError) as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/ai/status")
    def ai_status():
        return jsonify(provider=provider.name, ready=provider.ready)

    @app.get("/api/companion-actions")
    def companion_actions():
        """Recetas de interfaz; no dependen del proveedor de IA activo."""
        return jsonify(items=list_companion_actions())

    @app.get("/api/conversations/<conversation_id>/prompt-preview")
    def conversation_prompt_preview(conversation_id: str):
        try:
            return jsonify(build_prompt_packet(database_path, conversation_id).as_dict())
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @app.post("/api/conversations/<conversation_id>/prompt-preview")
    def conversation_prompt_preview_draft(conversation_id: str):
        try:
            payload = _json_body()
            turn = prepare_companion_turn(conversation_id, payload)
            return jsonify(companion_turn_preview(turn, payload))
        except (ConversationError, PersonalDataError, LibrarySearchError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/conversations/<conversation_id>/library-search")
    def conversation_library_search(conversation_id: str):
        try:
            payload = _json_body()
            payload["search_library"] = True
            return jsonify(items=requested_library_sources(conversation_id, payload))
        except (ConversationError, PersonalDataError, LibrarySearchError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/conversations/<conversation_id>/library-context/pin")
    def conversation_library_context_pin(conversation_id: str):
        try:
            payload = _json_body()
            payload["search_library"] = True
            sources = requested_library_sources(conversation_id, payload)
            count = pin_library_sources(database_path, conversation_id, sources)
            return jsonify(pinned=count)
        except (ConversationError, PersonalDataError, LibrarySearchError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @app.post("/api/conversations/<conversation_id>/respond")
    def conversation_respond(conversation_id: str):
        try:
            payload = _json_body()
            turn = prepare_companion_turn(conversation_id, payload)
            if turn["has_context_update"]:
                update_context(
                    database_path,
                    conversation_id,
                    personal_note_ids=payload.get("personal_note_ids", []),
                    annotation_ids=payload.get("annotation_ids", []),
                )
            add_message(
                database_path,
                conversation_id=conversation_id,
                role="user",
                content=payload.get("content"),
                companion_action_id=payload.get("companion_action_id"),
            )
            library_sources = turn["library_sources"]
            packet = turn["packet"]
            conv_provider = resolve_conversation_provider(conversation_id)
            if not conv_provider.ready:
                return jsonify(mode="draft", prompt=packet.as_dict(), library_sources=library_sources), 202
            answer = conv_provider.respond(packet)
            message_id = add_message(database_path, conversation_id=conversation_id, role="assistant", content=answer)
            attach_library_sources(database_path, message_id, library_sources)
            return jsonify(mode=conv_provider.name, answer=answer, library_sources=library_sources)
        except (ConversationError, PersonalDataError, LibrarySearchError, AIError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/conversations/<conversation_id>/context")
    def conversation_context(conversation_id: str):
        try:
            return jsonify(context_options(database_path, conversation_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @app.put("/api/conversations/<conversation_id>/context")
    def conversation_context_update(conversation_id: str):
        try:
            payload = _json_body()
            update_context(
                database_path,
                conversation_id,
                personal_note_ids=payload.get("personal_note_ids", []),
                annotation_ids=payload.get("annotation_ids", []),
            )
            return jsonify(saved=True)
        except (ConversationError, PersonalDataError) as error:
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
        collection = request.args.get("collection", "").strip() or None
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
                collection=collection, sort=sort, page=page, page_size=page_size,
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
                """
                SELECT c.id, c.parent_id, c.name, c.description,
                       COUNT(wc.work_id) AS works_count
                FROM collections c
                LEFT JOIN work_collections wc ON wc.collection_id = c.id
                GROUP BY c.id
                ORDER BY c.name COLLATE NOCASE
                """
            ).fetchall()
            items = [dict(row) for row in rows]
            uncategorized_count = connection.execute(
                """
                SELECT COUNT(*) FROM works w
                WHERE NOT EXISTS (
                    SELECT 1 FROM work_collections wc WHERE wc.work_id = w.id
                )
                """
            ).fetchone()[0]
            uncategorized = {
                "id": "uncategorized",
                "parent_id": None,
                "name": "Sin categoría",
                "description": "Obras que no pertenecen a ninguna colección",
                "works_count": uncategorized_count,
                "is_system": True,
            }
            return jsonify(items=[uncategorized] + items)
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

    @app.put("/api/collections/<collection_id>")
    def collection_update(collection_id: str):
        try:
            payload = _json_body()
            update_collection(
                database_path, collection_id, str(payload.get("name", "")),
                description=payload.get("description"),
            )
            return jsonify(success=True)
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    @app.delete("/api/collections/<collection_id>")
    def collection_delete(collection_id: str):
        try:
            delete_collection(database_path, collection_id)
            return jsonify(success=True)
        except PersonalDataError as error:
            return jsonify(error=str(error)), 400

    @app.get("/api/collections/<collection_id>/works")
    def collection_works(collection_id: str):
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                "SELECT work_id FROM work_collections WHERE collection_id = ?",
                (collection_id,),
            ).fetchall()
            return jsonify(work_ids=[row["work_id"] for row in rows])
        finally:
            connection.close()

    @app.post("/api/collections/<collection_id>/works")
    def collection_works_bulk_update(collection_id: str):
        try:
            payload = _json_body()
            work_ids = payload.get("work_ids", [])
            if not isinstance(work_ids, list):
                raise PersonalDataError("work_ids debe ser una lista")
            bulk_assign_works_to_collection(database_path, collection_id, [str(wid) for wid in work_ids])
            return jsonify(success=True)
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
