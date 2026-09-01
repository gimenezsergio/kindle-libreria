# Biblioteca Kindle

Biblioteca personal independiente que utiliza un Kindle como fuente de lectura,
pero conserva el catálogo, las anotaciones y la organización fuera del
ecosistema de Amazon.

## El problema

El Kindle es un excelente dispositivo para leer, subrayar y tomar notas, pero
no es suficiente como biblioteca personal de largo plazo.

Los libros enviados mediante Send to Kindle quedan distribuidos entre archivos
del dispositivo, manifiestos, directorios auxiliares y bases internas. Las
notas y los subrayados aparecen en fuentes diferentes, como `My Clippings.txt`,
KRDS y HAN. El progreso también utiliza posiciones y registros propios de
Kindle.

Además:

- la organización queda atada a Amazon y al dispositivo;
- las colecciones creadas en el Kindle no están expuestas de manera confiable
  mediante la conexión USB normal observada;
- los nombres de muchos documentos personales llegan como nombres de archivo,
  por ejemplo `Jugarse_la_piel`;
- resulta difícil conservar anotaciones históricas cuando un libro deja de
  estar en el dispositivo;
- el Kindle no ofrece un espacio adecuado para relacionar lecturas, desarrollar
  ideas o construir categorías personales;
- recuperar datos no equivale a poder explorarlos y utilizarlos para pensar.

El proyecto nació para que el Kindle pueda concentrarse en una tarea sencilla:
buscar un libro, abrirlo, leerlo, subrayarlo y anotar. La organización duradera
vive en otra parte.

## La solución

Biblioteca Kindle inspecciona el dispositivo en modo de solo lectura y guarda
los datos recuperados en una base SQLite local, fuera del Kindle.

Amazon y Send to Kindle continúan siendo el mecanismo para entregar y
sincronizar documentos. Esta aplicación no transfiere libros, no los convierte
y no intenta reemplazar a Amazon. Su función es construir un catálogo
independiente y acumulativo a partir de los datos que el Kindle expone.

La biblioteca local es la fuente de verdad para la organización personal. El
último Kindle sincronizado representa solamente el estado actual de presencia:
un libro puede quedar marcado como ausente sin que se eliminen su obra, sus
anotaciones ni las ideas asociadas.

## Principios

- El Kindle es siempre una fuente de solo lectura.
- Ninguna base de datos ni resultado se escribe dentro del dispositivo.
- Las sincronizaciones son idempotentes: repetirlas no duplica datos lógicos.
- Las fuentes se conservan con procedencia separada cuando existe incertidumbre.
- Una coincidencia ambigua no se fusiona automáticamente.
- Las notas, categorías y relaciones propias nunca se escriben en Amazon.
- Los textos privados permanecen fuera de Git.
- La aplicación diferencia datos observados, inferencias y decisiones humanas.

## Características actuales

### Recuperación desde Kindle

- Inventario seguro de libros y archivos auxiliares.
- Importación de manifiestos de documentos personales y libros de Amazon.
- Enriquecimiento desde `vocab.db` cuando está disponible.
- Recuperación de `My Clippings.txt`.
- Recuperación de subrayados, notas y marcadores desde KRDS y HAN.
- Importación de posiciones, historial y métricas nativas de lectura.
- Registro de libros presentes y ausentes sin borrar el historial.
- Reconciliación conservadora de títulos y fuentes.

### Catálogo local

- Obras, ediciones, autores y entregas Kindle.
- Búsqueda por título o autor.
- Filtros por presencia y existencia de anotaciones.
- Orden alfabético o por cantidad de anotaciones.
- Fichas con metadatos, progreso y procedencia.
- Títulos de presentación automáticos: `Jugarse_la_piel` se muestra como
  `Jugarse la piel`.
- Edición manual y reversible del título mostrado sin modificar el original.

### Lectura y anotaciones

- Consulta de subrayados, notas y marcadores por libro.
- Filtros por tipo y fuente.
- Paginación de bibliotecas y anotaciones extensas.
- Separación explícita entre Clippings, KRDS y HAN.
- El contenido privado solo aparece al abrir deliberadamente la ficha.

### Organización personal

- Categorías propias, independientes de las colecciones del Kindle.
- Asignación de una obra a una o varias categorías.
- Notas generales sobre una obra, separadas de las notas del Kindle.
- Relaciones manuales entre dos libros por tema, símbolo, conflicto, contraste u
  otro criterio.
- Explicación y dirección de cada relación.

### Interfaz

- Aplicación web local con HTML, CSS y JavaScript Vanilla.
- Servidor Python con Flask.
- Base SQLite.
- Panel general con el estado de la biblioteca.
- Catálogo navegable y adaptable a pantallas pequeñas.
- Acceso limitado actualmente a `127.0.0.1`.

## Uso local

El proyecto requiere Python 3.11 o posterior. Para instalarlo en modo de
desarrollo:

```bash
python3 -m pip install -e .
```

Para crear o actualizar la base:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle init-db work/library.sqlite3
```

Para sincronizar un Kindle montado:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle sync /media/usuario/Kindle \
  --database work/library.sqlite3
```

La base debe estar fuera del Kindle. El directorio `work/` está excluido de Git
porque contiene información privada derivada de las lecturas.

Para iniciar la interfaz:

```bash
PYTHONPATH=src python3 -m biblioteca_kindle serve \
  --database work/library.sqlite3
```

Después se abre [http://127.0.0.1:8000](http://127.0.0.1:8000). El Kindle no
necesita estar conectado para consultar una base ya sincronizada.

Los importadores individuales y las decisiones sobre formatos están
documentados en `docs/`.

## Acompañante de lectura y OpenClaw

El acompañante ya permite crear conversaciones por libro, elegir perfiles,
seleccionar el contexto y revisar el paquete exacto antes de enviarlo. Por
defecto trabaja en modo borrador: guarda los mensajes localmente y no envía
información fuera de la computadora.

La dirección elegida para el despliegue definitivo es utilizar OpenClaw como
capa de conversación y razonamiento. El adaptador también admite una conexión
directa opcional con OpenAI para probar el flujo antes de la mudanza.

La configuración se realiza exclusivamente mediante variables de entorno; las
credenciales no se guardan en SQLite ni en Git. Véase `.env.example`. Para
OpenClaw será necesario habilitar su endpoint Responses y definir la URL y el
token del Gateway.

La arquitectura prevista es:

```text
Biblioteca Kindle
    │
    │ herramientas y contexto seleccionado
    ▼
OpenClaw
    │
    ├── proveedor de modelo configurado en OpenClaw
    ├── memoria personal relevante
    └── conversación con el usuario
```

Biblioteca Kindle seguirá siendo la fuente de verdad para libros, subrayados,
notas, categorías, relaciones y progreso. OpenClaw funcionará como interlocutor:
podrá consultar la biblioteca, comparar fragmentos, encontrar patrones,
formular preguntas y sugerir relaciones.

La experiencia buscada no es una IA que declare interpretaciones definitivas,
sino alguien con quien continuar pensando una lectura. Sus propuestas deberán
presentarse como hipótesis, preguntas o caminos posibles.

### Herramientas previstas

- buscar libros;
- obtener la ficha de una obra;
- consultar y buscar subrayados;
- recuperar notas personales;
- comparar dos o más lecturas;
- detectar temas recurrentes;
- proponer relaciones y preguntas;
- guardar una relación o nota únicamente después de la confirmación humana.

### Salvaguardas necesarias

La integración deberá mantener separadas y visibles tres fuentes de contexto:

1. Evidencia de la biblioteca: subrayados, notas y categorías reales.
2. Memoria personal recuperada por OpenClaw, que puede estar incompleta o
   desactualizada.
3. Conocimiento general o inferencias del modelo.

OpenClaw no será una autoridad sobre el usuario ni sobre las obras. Una
sugerencia no se convertirá automáticamente en una relación, nota o recuerdo.
El usuario podrá examinarla, pedir evidencia, editarla, descartarla o aprobarla.

También deberá controlarse qué fragmentos privados se entregan al modelo. Si el
proveedor configurado en OpenClaw es externo, los textos seleccionados pueden
salir del servidor. Una alternativa futura será utilizar un modelo local cuando
la privacidad o el costo lo justifiquen.

### Despliegue futuro

La aplicación puede trasladarse al mismo servidor que OpenClaw y permanecer
accesible solo mediante `localhost` para sus herramientas. Eso no equivale a
publicar la interfaz actual en Internet.

Antes de permitir acceso remoto deberán incorporarse:

- autenticación;
- HTTPS o una red privada;
- un servidor web de producción;
- copias de seguridad de SQLite;
- permisos separados para lectura y escritura;
- protección específica de anotaciones y notas privadas.

La opción elegida es, por lo tanto: **Biblioteca Kindle administra los datos y
OpenClaw ayuda a conversar y razonar sobre ellos.**

## Estructura del repositorio

- `src/biblioteca_kindle/`: aplicación, importadores, API e interfaz web.
- `src/biblioteca_kindle/migrations/`: evolución reproducible de SQLite.
- `tests/`: pruebas unitarias y de integración.
- `docs/`: inspecciones, formatos y decisiones de diseño.
- `work/`: base y resultados privados locales, excluidos de Git.
