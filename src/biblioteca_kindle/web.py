from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template

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


def create_app(database: Path | str) -> Flask:
    database_path = Path(database).expanduser().resolve()
    app = Flask(__name__)
    app.config["DATABASE"] = database_path

    @app.get("/")
    def index() -> str:
        return render_template("index.html")

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
