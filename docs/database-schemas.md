# Esquemas de bases de datos

La inspección se realizó con SQLite en modo explícito de solo lectura y se limitó
a objetos del esquema y columnas. No se consultaron filas de datos.

## `readingstreams.db`

Contiene solamente `pendingmessages`, una cola con identificador de perfil,
fecha, estado y un `payload` binario. No parece ser por sí sola un historial de
lectura directamente consultable.

## `fmcache.db`

Contiene:

- `app_sessions`: sesiones de aplicación serializadas como texto.
- `reading_sessions`: sesiones de lectura serializadas como texto.
- `records`: eventos con esquema, versión, secuencia, fecha, prioridad y un
  registro serializado como texto.

Es una fuente candidata para actividad y sesiones de lectura. Será necesario
identificar el formato de los campos serializados antes de atribuirles una
semántica precisa.

## `vocab.db`

Contiene:

- `BOOK_INFO`: identificador, ASIN, GUID, idioma, título y autores.
- `DICT_INFO`: diccionario e idiomas de entrada y salida.
- `WORDS`: palabra, raíz, idioma, categoría, fecha y perfil.
- `LOOKUPS`: relación entre palabra, libro y diccionario, con posición, contexto
  de uso y fecha.
- `METADATA` y `VERSION`: control interno de sincronización y versión.

Puede enriquecer el catálogo y relacionar consultas de vocabulario con libros,
pero no debe confundirse con una fuente general de subrayados o notas.

## `isd.db`

Contiene `DEVICE_USAGE` e `ISD_TABLE`. Ambas registran día, horas, minutos,
segundos y fecha de inserción. Parece representar uso agregado del dispositivo,
no progreso individual por libro.

## Evaluación inicial

| Base | Uso potencial | Confianza inicial |
| --- | --- | --- |
| `readingstreams.db` | Cola de sincronización pendiente | Media |
| `fmcache.db` | Sesiones y actividad de lectura | Alta como candidata; formato pendiente |
| `vocab.db` | Catálogo parcial y consultas de vocabulario | Alta |
| `isd.db` | Tiempo agregado de uso | Media |

