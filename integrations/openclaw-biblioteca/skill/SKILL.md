---
name: biblioteca-kindle
description: Conversar sobre libros de la biblioteca personal usando catálogo, perfiles, subrayados, notas y fuentes persistentes.
metadata:
  openclaw:
    requires:
      env:
        - BIBLIOTECA_OPENCLAW_TOKEN
---

# Biblioteca Kindle

Usá las herramientas `biblioteca_*` cuando el usuario quiera buscar un libro de
su biblioteca personal, conversar sobre una lectura o relacionarla con su
material guardado.

## Flujo de conversación

1. Buscá la obra por el título o autor expresado por el usuario.
2. Si hay varios candidatos plausibles, preguntá cuál quiere usar. No elijas uno
   arbitrariamente.
3. Recuperá las conversaciones existentes. Permití continuar una o crear otra.
4. Si se crea una conversación, usá el perfil predeterminado salvo que el
   usuario elija explícitamente otro.
5. Para cada mensaje, llamá a `biblioteca_preparar_turno`. Considerá su `prompt`
   como las instrucciones y el contexto vigente para redactar la respuesta.
6. Distinguí evidencia recuperada, inferencias y conocimiento general. No
   supongas que la biblioteca contiene el texto completo de los libros.
7. Después de redactar la respuesta, llamá una sola vez a
   `biblioteca_completar_turno` con el `turn_id` recibido y el texto exacto que
   vas a enviar al usuario. Solo entonces entregá la respuesta por Telegram.

No inventes identificadores. No llames a `biblioteca_completar_turno` sin un
turno preparado. Si falla la finalización, conservá el `turn_id` y reintentá el
mismo turno; la operación es idempotente.

La selección explícita del usuario tiene prioridad. La búsqueda automática
devuelve como máximo ocho fuentes y no autoriza a afirmar que se consultó la
obra completa. Nombrá las fuentes de manera natural por tipo, título y posición.

Las herramientas actuales no crean notas, categorías ni relaciones propias.
Si el usuario quiere guardar una interpretación, explicá que esa escritura aún
requiere la interfaz web; no simules que fue almacenada.
