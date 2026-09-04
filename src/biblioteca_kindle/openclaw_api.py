from __future__ import annotations

import hmac
from pathlib import Path

from flask import Blueprint, jsonify, request

from .conversations import (
    ConversationError,
    build_prompt_packet,
    complete_external_turn,
    context_options,
    create_conversation,
    get_conversation,
    list_work_conversations,
    prepare_external_turn,
    update_context,
)
from .db import connect_database
from .library_search import LibrarySearchError
from .personal import PersonalDataError
from .retrieval import requested_library_sources


DISPLAY_TITLE_SQL = (
    "COALESCE(NULLIF(TRIM(w.display_title), ''), "
    "REPLACE(w.preferred_title, '_', ' '))"
)


def create_openclaw_blueprint(database: Path | str, token: str) -> Blueprint:
    database_path = Path(database).expanduser().resolve()
    api = Blueprint("openclaw_api", __name__, url_prefix="/api/openclaw/v1")

    @api.before_request
    def authenticate():
        if not token:
            return jsonify(error="La integración con OpenClaw no está configurada"), 503
        authorization = request.headers.get("Authorization", "")
        supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not hmac.compare_digest(supplied, token):
            return jsonify(error="Autenticación de OpenClaw inválida"), 401, {
                "WWW-Authenticate": "Bearer"
            }
        return None

    def body() -> dict:
        if not request.is_json:
            raise PersonalDataError("La solicitud debe usar JSON")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            raise PersonalDataError("El contenido enviado no es válido")
        return payload

    def limited_text(value: object, label: str, limit: int = 20_000) -> str:
        if not isinstance(value, str) or not value.strip():
            raise PersonalDataError(f"{label} no puede estar vacío")
        text = value.strip()
        if len(text) > limit:
            raise PersonalDataError(f"{label} supera el máximo de {limit} caracteres")
        return text

    @api.get("/status")
    def status():
        return jsonify(service="biblioteca-kindle", api_version=1, ready=database_path.is_file())

    @api.get("/works")
    def works():
        query = request.args.get("q", "").strip()[:200]
        try:
            limit = min(20, max(1, int(request.args.get("limit", "8"))))
        except ValueError:
            return jsonify(error="El límite no es válido"), 400
        normalized_query = " ".join(query.replace("-", " ").replace("_", " ").split())
        pattern = f"%{normalized_query}%"
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                f"""
                WITH authors AS (
                    SELECT e.work_id, GROUP_CONCAT(DISTINCT c.display_name) AS names
                    FROM editions e
                    JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
                    JOIN contributors c ON c.id=ec.contributor_id
                    GROUP BY e.work_id
                ), annotation_counts AS (
                    SELECT e.work_id, COUNT(a.id) AS total
                    FROM editions e LEFT JOIN annotations a ON a.edition_id=e.id
                    GROUP BY e.work_id
                )
                SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
                       COALESCE(authors.names, '') AS authors,
                       COALESCE(annotation_counts.total, 0) AS annotation_count
                FROM works w
                LEFT JOIN authors ON authors.work_id=w.id
                LEFT JOIN annotation_counts ON annotation_counts.work_id=w.id
                WHERE ?='' OR REPLACE({DISPLAY_TITLE_SQL}, '-', ' ') LIKE ?
                      OR REPLACE(REPLACE(w.preferred_title, '_', ' '), '-', ' ') LIKE ?
                      OR REPLACE(COALESCE(authors.names, ''), '-', ' ') LIKE ?
                ORDER BY CASE WHEN LOWER({DISPLAY_TITLE_SQL})=LOWER(?) THEN 0 ELSE 1 END,
                         {DISPLAY_TITLE_SQL} COLLATE NOCASE, w.id
                LIMIT ?
                """,
                (normalized_query, pattern, pattern, pattern, normalized_query, limit),
            ).fetchall()
            return jsonify(items=[dict(row) for row in rows])
        finally:
            connection.close()

    @api.get("/works/<work_id>")
    def work_detail(work_id: str):
        connection = connect_database(database_path)
        try:
            row = connection.execute(
                f"""
                SELECT w.id, {DISPLAY_TITLE_SQL} AS title,
                       COALESCE(GROUP_CONCAT(DISTINCT c.display_name), '') AS authors,
                       (SELECT COUNT(a.id) FROM editions ea LEFT JOIN annotations a ON a.edition_id=ea.id
                        WHERE ea.work_id=w.id) AS annotation_count
                FROM works w
                LEFT JOIN editions e ON e.work_id=w.id
                LEFT JOIN edition_contributors ec ON ec.edition_id=e.id AND ec.role='author'
                LEFT JOIN contributors c ON c.id=ec.contributor_id
                WHERE w.id=? GROUP BY w.id
                """,
                (work_id,),
            ).fetchone()
            if row is None:
                return jsonify(error="Obra inexistente"), 404
            return jsonify(dict(row))
        finally:
            connection.close()

    @api.get("/profiles")
    def profiles():
        connection = connect_database(database_path)
        try:
            rows = connection.execute(
                """SELECT id,name,description,is_default FROM ai_profiles
                   WHERE is_archived=0 ORDER BY is_default DESC,name COLLATE NOCASE"""
            ).fetchall()
            return jsonify(items=[dict(row) for row in rows])
        finally:
            connection.close()

    @api.get("/works/<work_id>/conversations")
    def work_conversations(work_id: str):
        try:
            return jsonify(items=list_work_conversations(database_path, work_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @api.post("/works/<work_id>/conversations")
    def work_conversation_create(work_id: str):
        try:
            payload = body()
            identifier = create_conversation(
                database_path,
                work_id=work_id,
                profile_id=str(payload.get("profile_id", "")),
                title=payload.get("title", ""),
            )
            return jsonify(id=identifier), 201
        except (ConversationError, PersonalDataError) as error:
            return jsonify(error=str(error)), 400

    @api.get("/conversations/<conversation_id>")
    def conversation_detail(conversation_id: str):
        try:
            conversation = get_conversation(database_path, conversation_id)
            allowed = {
                "id", "work_id", "profile_id", "profile_name_snapshot", "title",
                "status", "created_at", "updated_at", "messages", "context_sources",
            }
            return jsonify({key: value for key, value in conversation.items() if key in allowed})
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @api.get("/conversations/<conversation_id>/context")
    def conversation_context(conversation_id: str):
        try:
            return jsonify(context_options(database_path, conversation_id))
        except ConversationError as error:
            return jsonify(error=str(error)), 404

    @api.put("/conversations/<conversation_id>/context")
    def conversation_context_update(conversation_id: str):
        try:
            payload = body()
            update_context(
                database_path,
                conversation_id,
                personal_note_ids=payload.get("personal_note_ids", []),
                annotation_ids=payload.get("annotation_ids", []),
            )
            return jsonify(saved=True)
        except (ConversationError, PersonalDataError) as error:
            return jsonify(error=str(error)), 400

    @api.post("/conversations/<conversation_id>/library-search")
    def conversation_library_search(conversation_id: str):
        try:
            payload = body()
            payload["search_library"] = True
            return jsonify(items=requested_library_sources(database_path, conversation_id, payload))
        except (ConversationError, PersonalDataError, LibrarySearchError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @api.post("/conversations/<conversation_id>/turns")
    def prepare_turn(conversation_id: str):
        try:
            payload = body()
            content = limited_text(payload.get("content"), "El mensaje")
            if "personal_note_ids" in payload or "annotation_ids" in payload:
                update_context(
                    database_path,
                    conversation_id,
                    personal_note_ids=payload.get("personal_note_ids", []),
                    annotation_ids=payload.get("annotation_ids", []),
                )
            sources = requested_library_sources(database_path, conversation_id, payload)
            turn_id, user_message_id = prepare_external_turn(
                database_path,
                conversation_id=conversation_id,
                content=content,
                library_sources=sources,
            )
            packet = build_prompt_packet(database_path, conversation_id, library_sources=sources)
            return jsonify(
                turn_id=turn_id,
                user_message_id=user_message_id,
                prompt=packet.as_dict(),
                library_sources=sources,
            ), 201
        except (ConversationError, PersonalDataError, LibrarySearchError, ValueError) as error:
            return jsonify(error=str(error)), 400

    @api.post("/turns/<turn_id>/complete")
    def complete_turn(turn_id: str):
        try:
            payload = body()
            answer = limited_text(payload.get("content"), "La respuesta", limit=100_000)
            message_id, created = complete_external_turn(
                database_path, turn_id=turn_id, content=answer
            )
            return jsonify(message_id=message_id, created=created), 201 if created else 200
        except (ConversationError, PersonalDataError, ValueError) as error:
            return jsonify(error=str(error)), 400

    return api
