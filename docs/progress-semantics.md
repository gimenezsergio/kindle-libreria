# Semántica del progreso de lectura

## Posiciones nativas

Los 185 sidecars de progreso contienen `lpr` (última posición leída), pero su
representación depende del formato:

| Formato | Representación observada de `lpr.position` |
| --- | --- |
| AZW3 (`.azw3f`) | entero decimal expresado como texto |
| KFX (`.yjf`) | token estructural opaco seguido por un desplazamiento numérico |
| PDF (`.pdt`) | cuatro u ocho enteros separados por espacios |
| AZW/MOBI (`.mbs`) | estructura codificada compleja y multilínea |

Estas posiciones son comparables dentro del mismo libro y formato, pero no entre
formatos. Deben conservarse íntegramente como valor nativo junto con su tipo.

## Última y máxima posición

- `lpr`: última posición leída; está disponible en los 185 archivos.
- `fpr`: máxima posición alcanzada; está disponible en 84 archivos.

`fpr` no sustituye a `lpr`: si el lector retrocede, ambas expresan hechos distintos.
El modelo debe guardar las dos cuando existan.

## `timer.model.totalPercent`

No es un porcentaje fiable del progreso actual. En los datos observados aparecen
valores superiores a `1.0`, con máximos de `1,9495` en KFX y `3,0` en AZW/MOBI.
Por lo tanto no se debe multiplicar por cien ni mostrarlo como avance del libro.
Representa una métrica del modelo acumulativo de palabras y tiempo del Kindle.

## Historial

Hay 84 sidecars con `page.history.store`, de los cuales 56 tienen registros. Los
historiales son muy cortos en este dispositivo: entre cero y tres registros por
archivo. Pueden aportar una pequeña línea temporal reciente, pero no una historia
completa de sesiones.

## Decisión para la primera versión

1. Guardar `lpr` y `fpr` como posiciones nativas opacas, con formato y fecha.
2. No producir un porcentaje universal por heurística.
3. Mostrar estado cualitativo solo si puede inferirse con evidencia independiente.
4. Calcular porcentaje por formato únicamente cuando exista un denominador
   validado: mapa de páginas, extensión de posiciones o metadata equivalente.
5. Mantener separado el tiempo/ritmo del progreso posicional.
6. Conservar el historial disponible sin prometer que es exhaustivo.

