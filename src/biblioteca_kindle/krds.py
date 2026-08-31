"""Lector mínimo del contenedor Kindle Reader Data Store (KRDS).

Implementa únicamente las estructuras necesarias para progreso de lectura. La
descripción pública del formato está documentada en docs/sidecar-formats.md.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


class KRDSError(ValueError):
    pass


@dataclass
class _Buffer:
    data: bytes
    offset: int = 0

    def unpack(self, format_string: str, *, advance: bool = True) -> Any:
        try:
            value = struct.unpack_from(format_string, self.data, self.offset)[0]
        except struct.error as exc:
            raise KRDSError("Datos KRDS truncados") from exc
        if advance:
            self.offset += struct.calcsize(format_string)
        return value

    def take(self, size: int) -> bytes:
        end = self.offset + size
        if size < 0 or end > len(self.data):
            raise KRDSError("Datos KRDS truncados")
        value = self.data[self.offset:end]
        self.offset = end
        return value


def _timestamp(milliseconds: int) -> str | None:
    if milliseconds == -1:
        return None
    return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).isoformat()


class KRDSReader:
    SIGNATURE = b"\x00\x00\x00\x00\x00\x1a\xb1\x26"
    ANNOTATION_CLASSES = {
        0: "annotation.personal.bookmark",
        1: "annotation.personal.highlight",
        2: "annotation.personal.note",
        3: "annotation.personal.clip_article",
        10: "annotation.personal.handwritten_note",
        11: "annotation.personal.sticky_note",
        13: "annotation.personal.underline",
    }

    def __init__(self, data: bytes):
        self.buffer = _Buffer(data)
        self.warnings: list[str] = []

    def read(self) -> dict[str, Any]:
        if self.buffer.take(8) != self.SIGNATURE:
            raise KRDSError("Firma KRDS inválida")
        if self._value() != 1:
            raise KRDSError("Versión inicial KRDS desconocida")
        count = self._value()
        if not isinstance(count, int) or count < 0:
            raise KRDSError("Cantidad superior KRDS inválida")
        result: dict[str, Any] = {}
        for _ in range(count):
            value = self._value()
            if not isinstance(value, dict) or len(value) != 1:
                raise KRDSError("Objeto superior KRDS inválido")
            name, decoded = next(iter(value.items()))
            if name in result:
                raise KRDSError(f"Objeto KRDS duplicado: {name}")
            result[name] = decoded
        if self.buffer.offset != len(self.buffer.data):
            self.warnings.append(
                f"{len(self.buffer.data) - self.buffer.offset} bytes finales no interpretados"
            )
        return result

    def _value(self, tag: int | None = None) -> Any:
        tag = self.buffer.unpack("b") if tag is None else tag
        if tag == 0:
            value = self.buffer.unpack("b")
            if value not in (0, 1):
                raise KRDSError("Booleano KRDS inválido")
            return bool(value)
        if tag == 1:
            return self.buffer.unpack(">i")
        if tag == 2:
            return self.buffer.unpack(">q")
        if tag == 3:
            if self._value(0):
                return ""
            size = self.buffer.unpack(">H")
            try:
                return self.buffer.take(size).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise KRDSError("Texto KRDS inválido") from exc
        if tag == 4:
            return self.buffer.unpack(">d")
        if tag == 5:
            return self.buffer.unpack(">h")
        if tag == 6:
            return self.buffer.unpack(">f")
        if tag == 7:
            return self.buffer.unpack("b")
        if tag == 9:
            try:
                return self.buffer.take(1).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise KRDSError("Carácter KRDS inválido") from exc
        if tag == -2:
            name = self._value(3)
            values = []
            while self.buffer.unpack("b", advance=False) != -1:
                values.append(self._value())
            self.buffer.unpack("b")
            return {name: self._object(name, values)}
        raise KRDSError(f"Tipo KRDS desconocido: {tag}")

    def _object(self, name: str, values: list[Any]) -> Any:
        raw = list(values)
        try:
            decoded = self._known_object(name, values)
        except (IndexError, KeyError, TypeError, ValueError) as exc:
            self.warnings.append(f"{name}: estructura no reconocida ({type(exc).__name__})")
            return raw
        if values:
            self.warnings.append(f"{name}: {len(values)} valores adicionales")
        return decoded

    def _known_object(self, name: str, values: list[Any]) -> Any:
        if name == "lpr":
            version = values.pop(0)
            if isinstance(version, str):
                return {"position": version, "time": None}
            if version <= 2:
                return {
                    "position": values.pop(0),
                    "time": _timestamp(values.pop(0)),
                }
            raise ValueError("versión lpr")
        if name in {"fpr", "updated_lpr"}:
            return {
                "position": values.pop(0),
                "time": _timestamp(values.pop(0)),
                "time_zone_offset": values.pop(0),
                "country": values.pop(0),
                "device": values.pop(0),
            }
        if name == "timer.model":
            version = values.pop(0)
            total_time = values.pop(0)
            total_words = values.pop(0)
            total_percent = values.pop(0)
            average_value = values.pop(0)
            return {
                "version": version,
                "total_time": total_time,
                "total_words": total_words,
                "total_percent": total_percent,
                "average_calculator": average_value.get("timer.average.calculator")
                if isinstance(average_value, dict)
                else None,
            }
        if name == "timer.average.calculator":
            samples_1 = [values.pop(0) for _ in range(values.pop(0))]
            samples_2 = [values.pop(0) for _ in range(values.pop(0))]
            distributions = [values.pop(0) for _ in range(values.pop(0))]
            outliers = [values.pop(0) for _ in range(values.pop(0))]
            return {
                "samples_1": samples_1,
                "samples_2": samples_2,
                "distributions": distributions,
                "outliers": outliers,
            }
        if name == "timer.average.calculator.distribution.normal":
            return {
                "count": values.pop(0),
                "sum": values.pop(0),
                "sum_of_squares": values.pop(0),
            }
        if name == "timer.average.calculator.outliers":
            return [values.pop(0) for _ in range(values.pop(0))]
        if name == "book.info.store":
            return {
                "number_of_words": values.pop(0),
                "percent_of_book": values.pop(0),
            }
        if name == "page.history.store":
            return [
                values.pop(0)["page.history.record"]
                for _ in range(values.pop(0))
            ]
        if name == "page.history.record":
            return {
                "position": values.pop(0),
                "time": _timestamp(values.pop(0)),
            }
        if name == "annotation.cache.object":
            if not values:
                return {}
            result: dict[str, list[dict[str, Any]]] = {}
            for _ in range(values.pop(0)):
                annotation_type = values.pop(0)
                class_name = self.ANNOTATION_CLASSES.get(annotation_type)
                if class_name is None:
                    raise ValueError("tipo de anotación")
                tree = values.pop(0)["saved.avl.interval.tree"]
                annotations = []
                for item in tree:
                    annotations.append(item[class_name])
                result[class_name] = annotations
            return result
        if name == "saved.avl.interval.tree":
            return [values.pop(0) for _ in range(values.pop(0))]
        if name in self.ANNOTATION_CLASSES.values():
            result = {
                "start_position": values.pop(0),
                "end_position": values.pop(0),
                "creation_time": _timestamp(values.pop(0)),
                "modification_time": _timestamp(values.pop(0)),
                "template": values.pop(0),
            }
            if name == "annotation.personal.note":
                result["note"] = values.pop(0)
            elif name == "annotation.personal.handwritten_note":
                result["handwritten_note_ref"] = values.pop(0)
            elif name == "annotation.personal.sticky_note":
                result["sticky_note_ref"] = values.pop(0)
            return result
        return raw_object(values)


def raw_object(values: list[Any]) -> list[Any]:
    result = list(values)
    values.clear()
    return result


def read_krds(data: bytes) -> tuple[dict[str, Any], list[str]]:
    reader = KRDSReader(data)
    return reader.read(), reader.warnings
