# Contrato de la API privada para OpenClaw (v1)

## Alcance

Esta API permite que un OpenClaw ubicado en el mismo servidor converse sobre la
biblioteca sin acceder directamente a SQLite. Su prefijo estable es:

```text
/api/openclaw/v1
```

Todas las operaciones requieren:

```http
Authorization: Bearer <BIBLIOTECA_OPENCLAW_TOKEN>
```

El token es exclusivo de esta integración. No es una clave de un modelo ni el
token usado por el agente que sincroniza el Kindle. Si la variable no está
configurada, la API responde `503`; si la credencial falta o no coincide,
responde `401`.

## Operaciones

| Método y ruta | Uso |
| --- | --- |
| `GET /status` | Comprobar versión y disponibilidad. |
| `GET /works?q=...&limit=8` | Buscar por título o autor. |
| `GET /works/{work_id}` | Confirmar una obra estable. |
| `GET /profiles` | Listar perfiles activos sin exponer sus prompts. |
| `GET /works/{work_id}/conversations` | Listar conversaciones de una obra. |
| `POST /works/{work_id}/conversations` | Crear conversación con perfil. |
| `GET /conversations/{id}` | Recuperar historial y fuentes preservadas. |
| `GET /conversations/{id}/context` | Listar notas y anotaciones seleccionables. |
| `PUT /conversations/{id}/context` | Reemplazar la selección temporal. |
| `POST /conversations/{id}/library-search` | Previsualizar evidencia pertinente. |
| `POST /conversations/{id}/turns` | Guardar pregunta y preparar el paquete. |
| `POST /turns/{turn_id}/complete` | Guardar respuesta y fuentes del turno. |

Las rutas administrativas, las portadas y la sincronización USB no se exponen a
OpenClaw.

## Resolución de una obra

```http
GET /api/openclaw/v1/works?q=Byung-Chul%20Han&limit=8
```

La respuesta contiene identificadores estables, título visible, autoría y
cantidad de anotaciones. Se normalizan guiones y espacios para búsquedas
conversacionales. Si hay más de un candidato razonable, OpenClaw debe pedir una
elección; el orden de resultados no constituye autorización para adivinar.

## Crear una conversación

```json
{
  "profile_id": "companion",
  "title": "Conversación desde Telegram"
}
```

La conversación conserva una instantánea del nombre y las instrucciones del
perfil. `GET /profiles` no entrega el prompt: solo el servidor lo incorpora al
paquete de un turno preparado.

## Contexto explícito

`GET /conversations/{id}/context` devuelve las notas propias y anotaciones del
libro, con identificadores y referencias legibles. La selección se reemplaza
con:

```json
{
  "personal_note_ids": ["uuid-nota"],
  "annotation_ids": ["uuid-subrayado"]
}
```

La API valida que cada elemento pertenezca al libro de la conversación. Las
fuentes fijadas previamente se conservan.

## Turno en dos fases

OpenClaw es quien conversa y utiliza su proveedor de IA. Por eso esta API no
llama a DeepSeek ni a otro modelo. El turno se divide para preservar exactamente
la pregunta, el contexto y las fuentes usadas.

### 1. Preparar

```json
{
  "content": "Relacioná esta idea con otros libros de mi biblioteca",
  "search_library": true,
  "search_scope": "library",
  "personal_note_ids": [],
  "annotation_ids": ["uuid-subrayado"]
}
```

La respuesta incluye:

- `turn_id`, que identifica el trabajo pendiente;
- `user_message_id`, ya persistido;
- `prompt.instructions`, con el perfil y las salvaguardas;
- `prompt.input`, con historial y contexto vigente;
- `library_sources`, máximo ocho evidencias recuperadas.

El contexto devuelto puede contener material privado. OpenClaw no debe copiarlo
a registros generales ni enviarlo a herramientas ajenas a la conversación.

### 2. Completar

Después de generar la respuesta:

```json
{
  "content": "Podemos pensarlo como una tensión entre…"
}
```

se envía a `POST /turns/{turn_id}/complete`. La API guarda la respuesta y adjunta
las instantáneas de las fuentes preparadas. Repetir la misma solicitud no crea
otro mensaje: devuelve `created: false` y el identificador original.

No se aceptan fuentes suministradas por el cliente al completar. De ese modo,
OpenClaw no puede asociar accidentalmente una respuesta con evidencia diferente
de la que recibió al preparar el turno.

## Errores y reintentos

- `400`: datos inválidos, selección ajena al libro o conversación archivada.
- `401`: token ausente o incorrecto.
- `404`: recurso solicitado inexistente en operaciones de consulta.
- `503`: integración sin configurar.

Una preparación exitosa ya guarda el mensaje del usuario. Si OpenClaw falla
antes de completar, debe conservar el `turn_id`; no debe preparar la misma
pregunta de nuevo automáticamente. La finalización sí puede reintentarse.

## Límites actuales

- Mensaje del usuario: 20.000 caracteres.
- Respuesta del acompañante: 100.000 caracteres.
- Resultados de catálogo: máximo 20.
- Evidencia automática: máximo ocho fuentes.
- No se transmiten archivos de libros ni textos completos.
- La primera versión no expone escrituras de notas, relaciones o categorías.
