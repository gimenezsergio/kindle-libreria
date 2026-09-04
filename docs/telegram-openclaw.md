# Telegram como interfaz de conversación mediante OpenClaw

## Objetivo

Después de trasladar Biblioteca Kindle al servidor, una conversación de lectura
podrá comenzar y continuar desde Telegram sin abrir la interfaz web. Telegram no
reemplazará la biblioteca ni almacenará su lógica: será un canal atendido por
OpenClaw, que consultará una API privada y limitada de Biblioteca Kindle.

La experiencia buscada será natural:

```text
Usuario: Quiero hablar sobre 1984.
OpenClaw: Encontré 1984, de George Orwell. ¿Continuamos la conversación anterior
          o empezamos una nueva? ¿Qué te gustaría pensar?
Usuario: Relacioná la idea de la vidapropia con otros libros de mi biblioteca.
OpenClaw: [recupera evidencia, conversa y guarda el intercambio]
```

Los comandos de Telegram podrán existir como atajos, pero no serán obligatorios
para mantener una conversación normal.

## Arquitectura acordada

```text
Telegram
    │ mensaje y Telegram user ID
    ▼
OpenClaw
    │ herramienta autenticada, accesible solo en la red interna
    ▼
API privada de Biblioteca Kindle
    │
    ├── catálogo, autores y ediciones
    ├── notas, subrayados y referencias
    ├── perfiles del acompañante
    ├── recuperación de contexto
    └── conversaciones persistentes y sus fuentes
```

Biblioteca Kindle continúa siendo la fuente de verdad. OpenClaw interpreta la
intención, decide qué herramienta consultar y redacta la conversación. Telegram
solo transporta mensajes entre el usuario autorizado y OpenClaw.

OpenClaw no abrirá SQLite directamente. Esta separación permite validar cada
operación, limitar permisos, evolucionar el esquema de datos y registrar qué
información fue consultada sin acoplar el agente a las tablas internas.

## Responsabilidades

### Telegram

- Entregar el mensaje y la identidad de la cuenta remitente.
- Mostrar preguntas de desambiguación, respuestas y errores breves.
- Admitir lenguaje natural y, opcionalmente, atajos como `/libro`, `/perfil`,
  `/nueva`, `/contexto` y `/salir`.
- No recibir credenciales de Biblioteca Kindle ni acceder a SQLite.

### OpenClaw

- Rechazar identidades de Telegram no autorizadas.
- Mantener la sesión activa: libro, conversación y perfil elegidos.
- Preguntar cuando un título, autor o acción sean ambiguos.
- Llamar únicamente a herramientas publicadas por Biblioteca Kindle.
- Diferenciar evidencia bibliotecaria, memoria personal e hipótesis del modelo.
- Solicitar confirmación antes de crear una nota o relación propia.
- Devolver respuestas adecuadas al formato y longitud de Telegram.

### Biblioteca Kindle

- Buscar títulos y autores y devolver candidatos estables.
- Crear, recuperar y continuar conversaciones.
- Exponer perfiles activos y material seleccionable.
- Ejecutar la recuperación bibliotecaria ya existente.
- Conservar mensajes, contexto y fuentes legibles en SQLite.
- Aplicar autorización y validación independientemente de OpenClaw.
- No entregar el texto completo de los libros: actualmente no está almacenado.

## Estado de conversación

La sesión de Telegram necesita asociar, como mínimo:

- `telegram_user_id`: identidad externa autorizada;
- `work_id`: obra elegida;
- `conversation_id`: conversación persistente;
- `profile_id`: perfil del acompañante;
- fecha de la última actividad.

La identidad real de obras y conversaciones siempre será la de Biblioteca
Kindle. OpenClaw puede conservar estos identificadores como estado de sesión,
pero debe volver a validarlos mediante la API antes de usarlos.

Si el usuario escribe «quiero hablar sobre 1984», el flujo será:

1. OpenClaw busca `1984` por título o autor.
2. Si hay un único resultado confiable, lo propone; si hay varios, pregunta.
3. Consulta conversaciones previas de esa obra.
4. El usuario continúa una o crea otra con el perfil elegido o predeterminado.
5. Cada pregunta pasa por la recuperación de contexto de Biblioteca Kindle.
6. La respuesta y las fuentes utilizadas quedan en la conversación persistente.
7. Una conversación iniciada en Telegram puede revisarse luego desde la web.

## Escrituras y confirmación humana

Conversar, buscar y leer contexto son operaciones de consulta. En cambio,
crear categorías, notas o relaciones modifica la biblioteca. OpenClaw nunca
debe interpretar una sugerencia como autorización para guardarla.

```text
OpenClaw: Podríamos relacionar 1984 con La sociedad del cansancio por las formas
          externas e internas de control. ¿Querés guardar esa relación?
Usuario: Sí, guardala.
```

Solo después de esa confirmación se llamará a la operación de escritura. La API
debe distinguir credenciales de solo lectura de credenciales con escrituras
personales permitidas.

## Seguridad y privacidad

- La primera instalación autorizará únicamente el Telegram user ID del dueño.
- El bot no se autoriza por nombre de usuario, porque puede cambiar.
- Telegram no llamará directamente a Biblioteca Kindle.
- La API se mantendrá en `localhost` o en una red privada compartida con
  OpenClaw; no se publicará como una API anónima de Internet.
- OpenClaw usará un token propio, diferente del token del agente de
  sincronización del Kindle.
- Los secretos vivirán en el entorno del servidor y nunca en SQLite o Git.
- Los fragmentos enviados al proveedor de IA se limitarán a la selección y a la
  evidencia recuperada. Si el modelo es externo, esos fragmentos salen del
  servidor y esa condición deberá permanecer documentada.
- Los registros técnicos no deben copiar el contenido íntegro de notas o
  subrayados salvo que resulte imprescindible para diagnosticar un fallo.

## Qué se reutiliza y qué falta

Ya existen el catálogo, la búsqueda por autor y título, los perfiles, las
conversaciones persistentes, la selección de material, la recuperación textual,
las fuentes legibles y el adaptador configurable de IA. La interfaz web seguirá
sirviendo para tareas visuales y administrativas, pero no será obligatoria para
conversar.

Estado de las etapas:

1. Definir el contrato concreto de la API privada: terminado.
2. Autenticar las llamadas con un token independiente: terminado.
3. Exponer búsqueda de obras y resolución de ambigüedades: terminado.
4. Exponer perfiles y apertura de conversaciones: terminado.
5. Exponer contexto, notas y subrayados de manera limitada: terminado.
6. Exponer el flujo conversacional reutilizando la recuperación actual:
   terminado, con preparación y finalización idempotente.
7. Preparar las herramientas que OpenClaw podrá invocar: plugin construido y
   validado localmente; instalación en el servidor pendiente.
8. Configurar el bot y autorizar el Telegram user ID: pendiente de credenciales
   y acceso al servidor.
9. Probar el recorrido completo en el servidor: pendiente del punto anterior;
   procedimiento y recuperación ante fallos documentados.

Los puntos 1 a 7 quedaron preparados en este repositorio. Los puntos 8 y 9
requieren la instalación real de OpenClaw, Telegram y sus credenciales.

## Fuera de alcance inicial

- Acceso de varios usuarios a una biblioteca compartida.
- Permisos diferentes por libro o colección.
- Envío de EPUB, KFX, AZW o PDF al modelo.
- Sincronización del Kindle a través de Telegram.
- Administración completa de portadas o grandes selecciones desde el chat.
- Reemplazo de la interfaz web para mantenimiento y configuración.

Si en el futuro se habilitan más personas, deberá incorporarse un modelo de
propiedad y aislamiento de datos antes de agregarlas a la lista autorizada.
