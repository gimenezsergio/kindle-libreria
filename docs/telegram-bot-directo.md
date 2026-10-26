# Bot Directo de Telegram para Biblioteca Kindle

## Descripción

Permite interactuar con el Acompañante de Lectura de la biblioteca directamente desde Telegram, sin necesidad de agentes intermediarios ni pasarelas externas.

- **Canal exclusivo**: Ventana de chat independiente en Telegram para tus lecturas.
- **Interactivo**: Botoneras táctiles (*Inline Keyboards*) para elegir libros, perfiles pedagógicos o retomar charlas anteriores.
- **Persistente**: Todos los mensajes, hilos y síntesis se registran en la base SQLite local (`work/library.sqlite3`), reflejándose en tiempo real en la interfaz web.
- **Seguro**: Lista blanca estricta por `TELEGRAM_ALLOWED_USER_ID` numérico.

---

## Configuración

En `work/.env` (o variables de entorno del sistema):

```bash
# Token obtenido desde @BotFather en Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxYZ

# Tu Telegram User ID numérico (obtenible hablando con @userinfobot en Telegram)
TELEGRAM_ALLOWED_USER_ID=123456789
```

---

## Ejecución

### Desde la terminal

```bash
.venv/bin/python -m biblioteca_kindle telegram-bot --database work/library.sqlite3
```

El bot verificará las credenciales con Telegram y comenzará el sondeo mediante *Long Polling*:
```text
Bot autenticado: @MiBibliotecaBot (Biblioteca Kindle)
Seguridad activa: aceptando exclusivamente al usuario 123456789
```

---

## Comandos y Flujo de Uso

| Comando / Acción | Descripción |
| --- | --- |
| `/start` o `/menu` | Menú principal con estado de la charla activa y accesos rápidos. |
| `/libros` | Lista paginada de libros en el catálogo con botones para seleccionar. |
| `/nueva` | Inicia una nueva charla eligiendo un libro o perfil. |
| `/historial` | Envía el historial completo de la conversación activa mensaje por mensaje. |
| `/buscar <título>` | Busca libros que coincidan con el texto y muestra botones directos. |
| `/charla` | Muestra la conversación activa, el perfil y el último intercambio sin recortes. |
| `/sintesis` | Pide al modelo de IA un resumen estructurado y lo guarda en la base. |
| `/cerrar` | Sale de la conversación activa y vuelve al catálogo. |
| *Texto libre* | Si hay una conversación activa, dialoga con la IA. Si no hay charla activa, busca libros en la biblioteca con ese texto. |

---

## Selección de Perfiles y Charlas Previas

1. Al tocar un libro, el bot muestra sus datos y lista las charlas anteriores junto con el botón `[➕ Iniciar nueva charla]`.
2. Si elegís `[➕ Iniciar nueva charla]`, muestra los perfiles activos (*Socrático*, *Crítico*, *Síntesis*, *Filosófico*, etc.). Al tocar uno, el hilo se crea y queda activo.
3. Si tocás una charla anterior, recupera la ficha de la conversación y envía el último intercambio completo (pregunta del usuario y respuesta de la IA sin recortar). Además, ofrece el botón táctil `[📜 Leer charla completa]` (o comando `/historial`) para enviar el hilo íntegro turnos por turnos. Cualquier mensaje que envíes a continuación continuará ese diálogo.
