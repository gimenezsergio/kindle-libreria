# Biblioteca Kindle

Proyecto para construir una biblioteca personal independiente usando un Kindle
como fuente de datos de solo lectura.

## Principios

- Amazon y Send to Kindle siguen siendo el mecanismo de entrega y sincronización.
- Nunca se modifican, eliminan ni escriben archivos en el Kindle.
- Los datos derivados y las portadas propias viven fuera del dispositivo.
- Primero se documentan los datos realmente disponibles; el extractor se diseña después.

## Directorios

- `docs/`: hallazgos y decisiones del proyecto.
- `work/`: resultados locales temporales, excluidos de Git.

## Desarrollo local

El proyecto usa Python 3.11 o posterior y SQLite, sin dependencias de ejecución.

Para crear una base local durante el desarrollo:

```bash
PYTHONPATH=src python -m biblioteca_kindle init-db work/library.sqlite3
```

La base debe permanecer fuera del Kindle. `work/` está excluido de Git porque
puede contener datos privados derivados del dispositivo.

Para crear una instantánea de inventario de solo lectura:

```bash
PYTHONPATH=src python -m biblioteca_kindle inventory /media/usuario/Kindle \
  --database work/library.sqlite3
```

El comando rechaza una base ubicada dentro del Kindle y solo inventaría fuentes
relevantes; no interpreta todavía libros ni anotaciones.

Para importar manifiestos desde la última instantánea completa:

```bash
PYTHONPATH=src python -m biblioteca_kindle import-manifests \
  /media/usuario/Kindle --database work/library.sqlite3
```

Para enriquecer las entregas coincidentes con `vocab.db`:

```bash
PYTHONPATH=src python -m biblioteca_kindle import-vocabulary \
  /media/usuario/Kindle --database work/library.sqlite3
```

Para importar el historial de `My Clippings.txt`:

```bash
PYTHONPATH=src python -m biblioteca_kindle import-clippings \
  /media/usuario/Kindle --database work/library.sqlite3
```

Para importar posiciones y métricas nativas de lectura:

```bash
PYTHONPATH=src python -m biblioteca_kindle import-progress \
  /media/usuario/Kindle --database work/library.sqlite3
```

Para importar anotaciones locales KRDS y HAN como fuentes separadas:

```bash
PYTHONPATH=src python -m biblioteca_kindle import-annotations \
  /media/usuario/Kindle --database work/library.sqlite3
```

Para ejecutar el pipeline completo en el orden seguro:

```bash
PYTHONPATH=src python -m biblioteca_kindle sync /media/usuario/Kindle \
  --database work/library.sqlite3
```

## Organización personal

Las colecciones, notas y relaciones se guardan únicamente en la base local. No
se escriben ni se sincronizan al Kindle.

Para crear una colección local (puede anidarse usando el identificador de otra):

```bash
PYTHONPATH=src python -m biblioteca_kindle collection-add "Temas" \
  --database work/library.sqlite3

PYTHONPATH=src python -m biblioteca_kindle collection-add "Poder" \
  --parent ID_DE_TEMAS --database work/library.sqlite3
```

Para asignar una obra a una colección y añadir una nota propia:

```bash
PYTHONPATH=src python -m biblioteca_kindle collection-assign ID_OBRA ID_COLECCION \
  --database work/library.sqlite3

PYTHONPATH=src python -m biblioteca_kindle note-add ID_OBRA \
  "Esta escena cambia la lectura del conflicto." \
  --database work/library.sqlite3
```

Para relacionar obras por tema, símbolo, conflicto u otro criterio propio:

```bash
PYTHONPATH=src python -m biblioteca_kindle relation-add ID_ORIGEN ID_DESTINO simbolo \
  --label "El laberinto" --explanation "Opera de modo distinto en ambas obras." \
  --symmetric --database work/library.sqlite3
```
