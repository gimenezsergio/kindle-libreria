from __future__ import annotations

import sqlite3
import struct
from pathlib import Path

import pytest

from biblioteca_kindle.annotation_context import (
    extract_kfx_paragraphs,
    extract_paragraphs_from_file,
    find_chapter_title,
    find_surrounding_context,
    normalize_text,
    extract_annotation_contexts,
    ContextExtractionError,
)
from biblioteca_kindle.cli import build_parser, main
from biblioteca_kindle.conversations import build_prompt_packet
from biblioteca_kindle.db import migrate_database


def _encode_ion_string(text: str) -> bytes:
    encoded = text.encode("utf-8")
    length = len(encoded)
    if length < 14:
        return bytes([0x80 | length]) + encoded
    # VarUInt
    varuint = bytearray()
    n = length
    while True:
        b = n & 0x7F
        n >>= 7
        if not varuint:
            b |= 0x80
        varuint.insert(0, b)
        if n == 0:
            break
    return bytes([0x8E]) + bytes(varuint) + encoded


def test_extract_kfx_paragraphs():
    p1 = "Primer párrafo de prueba con contenido relevante."
    p2 = "Segundo párrafo con información contextual."
    p3 = "Tercer párrafo final del capítulo."

    data = (
        b"CONT\x02\x00\x00\x00"
        + _encode_ion_string(p1)
        + b"\x01\x02\x03"  # binary noise
        + _encode_ion_string(p2)
        + _encode_ion_string(p3)
    )

    paragraphs = extract_kfx_paragraphs(data)
    assert paragraphs == [p1, p2, p3]


def test_normalize_text():
    raw = "«Texto   con  “comillas” y ‘apóstrofes’—guiones»"
    normalized = normalize_text(raw)
    assert normalized == '"Texto con "comillas" y \'apóstrofes\'-guiones"'


def test_find_chapter_title():
    paras = [
        "PARTE PRIMERA",
        "CAPÍTULO I",
        "Párrafo inicial del libro.",
        "Otro párrafo más.",
    ]
    assert find_chapter_title(paras, 2) == "PARTE PRIMERA · CAPÍTULO I"
    assert find_chapter_title(paras, 1) == "PARTE PRIMERA · CAPÍTULO I"


def test_find_surrounding_context_single_para():
    paras = [
        "CAPÍTULO II",
        "El sol caía sobre la colina mientras caminábamos en silencio.",
        "De pronto vimos la cabaña abandonada en el claro del bosque. Las ventanas estaban rotas.",
        "Nadie había entrado allí en más de cincuenta años.",
    ]
    quote = "vimos la cabaña abandonada en el claro del bosque"
    chapter, before, after = find_surrounding_context(paras, quote)

    assert chapter == "CAPÍTULO II"
    assert "El sol caía sobre la colina" in before
    assert "De pronto" in before
    assert "Las ventanas estaban rotas." in after
    assert "Nadie había entrado allí" in after


def test_find_surrounding_context_across_paras():
    paras = [
        "El primer párrafo terminaba con una frase inconclusa sobre",
        "el destino que aguardaba a los exploradores al llegar a la costa.",
        "Más adelante el camino se bifurcaba.",
    ]
    quote = "inconclusa sobre el destino que aguardaba"
    chapter, before, after = find_surrounding_context(paras, quote)

    assert "primer párrafo terminaba con una frase" in before
    assert "a los exploradores al llegar a la costa." in after
    assert "Más adelante el camino se bifurcaba." in after


def test_extract_annotation_contexts_end_to_end(tmp_path: Path):
    db_path = tmp_path / "test_library.sqlite3"
    migrate_database(db_path)

    # Crear libro simulado
    kindle_dir = tmp_path / "kindle"
    items_dir = kindle_dir / "documents" / "Downloads" / "Items01"
    items_dir.mkdir(parents=True)

    book_file = items_dir / "test_book.kfx"
    p0 = "CAPÍTULO I"
    p1 = "Esta es la introducción del relato con varios detalles previos."
    p2 = "El pasaje principal contiene la frase que el lector decide subrayar con gran esmero."
    p3 = "Y esta es la conclusión posterior con información de cierre."
    book_file.write_bytes(
        b"CONT\x02\x00"
        + _encode_ion_string(p0)
        + _encode_ion_string(p1)
        + _encode_ion_string(p2)
        + _encode_ion_string(p3)
    )

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            "INSERT INTO works (id, preferred_title) VALUES ('w1', 'Libro de Prueba')"
        )
        conn.execute(
            "INSERT INTO editions (id, work_id, title) VALUES ('e1', 'w1', 'Libro de Prueba')"
        )
        conn.execute(
            """
            INSERT INTO kindle_deliveries (
                id, edition_id, relative_path, file_size, document_format, presence,
                first_seen_at, last_seen_at
            ) VALUES ('kd1', 'e1', 'documents/Downloads/Items01/test_book.kfx', 100, 'KFX', 'present', '2026-01-01', '2026-01-01')
            """
        )
        conn.execute(
            """
            INSERT INTO annotations (
                id, edition_id, kind, text, start_position_native
            ) VALUES ('a1', 'e1', 'highlight', 'frase que el lector decide subrayar', 10)
            """
        )
    conn.close()

    result = extract_annotation_contexts(db_path, kindle_dir)
    assert result.books_scanned == 1
    assert result.books_matched == 1
    assert result.annotations_extracted == 1

    # Verificar datos guardados en annotation_contexts
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT chapter_title, surrounding_before, surrounding_after FROM annotation_contexts WHERE annotation_id = 'a1'"
    ).fetchone()
    conn.close()

    assert row is not None
    ch, before, after = row
    assert ch == "CAPÍTULO I"
    assert "detalles previos" in before
    assert "con gran esmero" in after or "información de cierre" in after


def test_build_prompt_packet_with_annotation_context(tmp_path: Path):
    db_path = tmp_path / "test_conv.sqlite3"
    migrate_database(db_path)

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute(
            "INSERT INTO works (id, preferred_title) VALUES ('w1', 'Obra Filosófica')"
        )
        conn.execute("INSERT INTO editions (id, work_id, title) VALUES ('e1', 'w1', 'Edición 1')")
        conn.execute(
            "INSERT INTO annotations (id, edition_id, kind, text) VALUES ('ann1', 'e1', 'highlight', 'El hombre es la medida de todas las cosas')"
        )
        conn.execute(
            """
            INSERT INTO annotation_contexts (annotation_id, chapter_title, surrounding_before, surrounding_after)
            VALUES ('ann1', 'Libro IV', 'Protágoras argumentaba lo siguiente en el ágora.', 'Esta doctrina causó gran controversia.')
            """
        )
        conn.execute(
            """
            INSERT INTO reading_conversations (
                id, work_id, profile_id, profile_name_snapshot, profile_prompt_snapshot,
                title, title_origin, status
            ) VALUES ('c1', 'w1', 'mentor_clasico', 'Mentor Clásico', 'Eres un mentor.', 'Diálogo', 'manual', 'active')
            """
        )
        conn.execute(
            """
            INSERT INTO conversation_context_sources (
                id, conversation_id, source_type, source_id, label_snapshot, content_snapshot
            ) VALUES ('cs1', 'c1', 'annotation', 'ann1', 'Subrayado', 'El hombre es la medida de todas las cosas')
            """
        )
        conn.execute(
            """
            INSERT INTO conversation_messages (
                id, conversation_id, sequence, role, content
            ) VALUES ('m1', 'c1', 1, 'user', '¿Qué opinas de esta frase?')
            """
        )
    conn.close()

    packet = build_prompt_packet(db_path, "c1")
    context_msg = [m for m in packet.input if "CONTEXTO VIGENTE" in m.get("content", "")][0]
    content = context_msg["content"]

    assert "Libro IV" in content
    assert "Protágoras argumentaba" in content
    assert "El hombre es la medida de todas las cosas" in content
    assert "Esta doctrina causó gran controversia" in content


def test_cli_extract_contexts_parser():
    parser = build_parser()
    args = parser.parse_args(["extract-contexts", "/media/kindle", "--database", "test.db", "--limit", "10"])
    assert args.command == "extract-contexts"
    assert args.mount == Path("/media/kindle")
    assert args.database == Path("test.db")
    assert args.limit == 10
