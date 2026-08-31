from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template

from .db import connect_database


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
