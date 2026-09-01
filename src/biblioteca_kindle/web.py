from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .db import connect_database


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
        conditions.append("(w.preferred_title LIKE ? OR COALESCE(c.authors, '') LIKE ?)")
        pattern = f"%{query}%"
        parameters.extend((pattern, pattern))
    if presence in {"present", "absent"}:
        conditions.append("COALESCE(d.presence, 'absent') = ?")
        parameters.append(presence)
    if annotated:
        conditions.append("COALESCE(a.annotation_count, 0) > 0")
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    ordering = {
        "title": "w.preferred_title COLLATE NOCASE, w.id",
        "annotations": "annotation_count DESC, w.preferred_title COLLATE NOCASE",
    }.get(sort, "w.preferred_title COLLATE NOCASE, w.id")
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
        SELECT w.id, w.preferred_title AS title, w.merge_status,
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
    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


def create_app(database: Path | str) -> Flask:
    database_path = Path(database).expanduser().resolve()
    app = Flask(__name__)
    app.config["DATABASE"] = database_path

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

    @app.get("/library")
    def library() -> str:
        return render_template("library.html")

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
