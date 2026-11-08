# Exportación de partituras bajo demanda

`osap-storage` conserva **solo el fichero original** de cada recurso. Los formatos derivados
no se registran en `works_resources`, `representations` ni en ninguna tabla de recursos.

## Endpoint

```http
GET /api/v1/files/{file_id}/export?format=original|pdf|midi|svg|ly|mxl
```

- `original`: delega en `/api/v1/files/{id}/content`.
- `pdf`, `midi`, `svg`: se generan desde MXL/MusicXML o LilyPond.
- `ly`: se genera desde MXL/MusicXML con `musicxml2ly`; desde `.ly` devuelve el original.
- `mxl`: no se genera desde LilyPond; devuelve 406.

Los derivados se guardan en una caché temporal (`export.cache_dir`) con TTL. No son
recursos ni se exponen en listados. Si la caché se borra, se regeneran desde el original.

## Formatos

| Original | Salidas |
|---|---|
| `.mxl` / `.musicxml` | original, `.ly`, PDF, MIDI, SVG |
| `.ly` / `.lyi` | original, PDF, MIDI, SVG |
| `.pdf` | original |
| `.mid` / `.midi` | original |

## Seguridad

LilyPond y MuseScore procesan entrada no confiable. En producción deben ejecutarse en un
worker aislado (sin red, sin privilegios, con límites de CPU/memoria/tiempo). Este módulo
evita el shell, pero **no sustituye** el aislamiento del sistema operativo.
