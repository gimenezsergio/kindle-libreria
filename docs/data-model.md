# Modelo mínimo de datos

## Objetivos

El modelo debe:

- conservar los datos del Kindle sin modificarlos ni fingir precisión;
- distinguir obra intelectual, edición y entrega concreta al dispositivo;
- reconciliar varias fuentes sin perder contradicciones;
- soportar libros históricos que ya no estén descargados;
- permitir notas, categorías y relaciones propias independientes de Amazon;
- mantener trazabilidad hasta la observación original.

## Entidades principales

### `work`

Representa la obra conceptual que el usuario piensa y relaciona.

Campos mínimos:

- `id`: UUID interno e inmutable;
- `preferred_title`;
- `created_at`, `updated_at`;
- `merge_status`: normal, provisional o pendiente de revisión.

No contiene directamente ASIN, ruta ni progreso.

### `edition`

Representa una edición o manifestación concreta de una obra: idioma, traducción,
editorial o versión documental.

Campos mínimos:

- `id`;
- `work_id`;
- `title`, `subtitle` opcional;
- `language` opcional;
- `publication_date` y `publisher` opcionales;
- `format_hint` opcional.

Una obra puede tener varias ediciones. Inicialmente puede crearse una edición
provisional cuando no haya metadata editorial suficiente.

### `contributor`

Persona u organización vinculada a una edición.

Campos mínimos:

- `id`;
- `display_name`;
- `normalized_name`.

La tabla de relación `edition_contributor` guarda el rol —autor, traductor,
editor u otro— y el orden de presentación.

### `kindle_delivery`

Representa un archivo o entrega concreta observada en el Kindle.

Campos mínimos:

- `id` interno;
- `edition_id`;
- `kindle_content_id` opcional;
- `content_type`: `kindle.pdoc`, `kindle.ebook` u otro;
- `document_format`: KFX, AZW3, AZW/MOBI o PDF;
- `relative_path` observada;
- `sidecar_relative_path` opcional;
- `file_size`, `file_modified_at`;
- `first_seen_at`, `last_seen_at`;
- `presence`: presente, ausente o desconocida.

La ruta puede cambiar y no es identidad. Para los 173 manifiestos actuales, la
restricción única principal es `(content_type, kindle_content_id)`. Las entregas
sin manifiesto requieren una huella local y revisión posterior.

### `external_identifier`

Alias tipado asociado a una obra, edición o entrega.

Campos mínimos:

- `id`;
- `entity_type`, `entity_id`;
- `namespace`: `asin`, `kindle_content_id`, `kindle_vocab_id`,
  `kindle_vocab_guid`, `calibre_uuid` u otro;
- `value`;
- `source_observation_id`;
- `confidence`;
- `is_preferred`.

La unicidad se aplica dentro del espacio de nombres, no globalmente.

### `reading_state`

Instantánea del estado de una entrega Kindle.

Campos mínimos:

- `id`;
- `kindle_delivery_id`;
- `observed_at`;
- `last_position_native` y su tipo;
- `furthest_position_native` y su tipo, opcionales;
- fechas nativas de ambas posiciones, cuando existan;
- `progress_fraction` opcional;
- `progress_method` opcional;
- `reading_time_ms`, `words_read` opcionales;
- `source_observation_id`.

`progress_fraction` queda nulo salvo que exista un método validado. Las
instantáneas permiten historia sin sobrescribir estados anteriores.

### `annotation`

Identidad lógica de un subrayado, nota o marcador.

Campos mínimos:

- `id`;
- `edition_id`;
- `kind`: highlight, note, bookmark u otro;
- `text` opcional;
- `note_text` opcional;
- posiciones nativas de inicio y fin opcionales;
- fechas de creación y modificación opcionales;
- `status`: activa, histórica, eliminada o desconocida;
- `created_at`, `updated_at`.

### `annotation_occurrence`

Representa cada aparición de una anotación en una fuente concreta. Evita perder
diferencias entre `My Clippings.txt` y KRDS.

Campos mínimos:

- `id`;
- `annotation_id`;
- `source_observation_id`;
- `source_kind`: clippings, KRDS u otro;
- `source_record_key` o huella estable;
- campos originales de encabezado, posición y fecha;
- `raw_payload_ref` opcional y local;
- `observed_at`.

Una anotación lógica puede tener una ocurrencia en clippings, otra en KRDS o solo
una de ellas. La ausencia en KRDS no elimina automáticamente el registro histórico.

### `source_observation`

Registro de procedencia para cada inspección o sincronización.

Campos mínimos:

- `id`;
- `snapshot_id`;
- `source_type`: manifest, sidecar, clippings, vocab, fmcache, calibre u otro;
- `source_relative_path`;
- tamaño, fecha y huella del archivo observado;
- `observed_at`;
- `parser_name`, `parser_version`;
- `parse_status` y mensajes de advertencia no sensibles.

### `device_snapshot`

Describe una ejecución de sincronización de solo lectura.

Campos mínimos:

- `id`;
- identificador local pseudónimo del dispositivo;
- `started_at`, `completed_at`;
- punto de montaje observado;
- modo de montaje confirmado;
- resultado y contadores generales.

No necesita guardar el identificador de cuenta Amazon visible en nombres internos.

## Organización propia

### `collection`

Categoría creada en la aplicación, independiente de las colecciones Kindle.
Admite jerarquía mediante `parent_id` opcional.

### `work_collection`

Relación muchos-a-muchos entre obra y colección, con orden y nota opcionales.

### `personal_note`

Nota propia asociable a obra, edición, anotación o relación. Debe permanecer
separada de las notas importadas del Kindle.

### `work_relation`

Relación dirigida o simétrica entre dos obras.

Campos mínimos:

- `source_work_id`, `target_work_id`;
- `relation_type`: tema, símbolo, conflicto, influencia, contraste u otro;
- `label` y explicación opcionales;
- `is_symmetric`;
- fechas de creación y modificación.

## Confianza y resolución

Cada afirmación importada puede tener:

- `confidence`: exacta, alta, media, baja;
- `resolution_method`: identificador, ruta/base `.sdr`, metadata, título
  normalizado o confirmación manual;
- `source_observation_id`.

Orden inicial de confianza:

1. coincidencia de `content.id` entre manifiesto, archivo y `.sdr`;
2. identificador externo coincidente entre fuentes;
3. metadata embebida o `vocab.db` vinculada por identificador;
4. título y autor normalizados sin colisión;
5. título solo;
6. caché histórica de Calibre o miniatura huérfana.

Las coincidencias de baja confianza crean candidatos o registros provisionales;
no fusionan obras automáticamente.

## Datos deliberadamente separados

- Posición nativa y porcentaje calculado.
- Última posición y máxima posición alcanzada.
- Nota Kindle y nota personal de la aplicación.
- Colección Amazon, si alguna vez se recupera, y colección propia.
- Obra, edición y entrega Kindle.
- Estado actual e historial de observaciones.

