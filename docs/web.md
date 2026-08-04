# Web pública — Open Music Repository

> Plan de la landing y las páginas del servicio público en `storage.openmusicrepository.com`.
> La web es un cliente de la API: **nunca** accede a MariaDB ni contiene lógica de negocio.
>
> **Multiidioma**: la web debe estar disponible en castellano, catalán, inglés, francés, italiano
> y alemán (`es, ca, en, fr, it, de`), con selector de idioma y detección por `Accept-Language`.
> Las traducciones viven en la capa web (cliente de la API), nunca en el dominio (ver `docs/v2.md`).

## Página principal

**Título**
> The Open Music Repository

**Subtítulo (mensaje de propósito)**
> A permanent home for open MusicXML resources.

**Texto principal**
> Open Music Repository preserves and distributes public-domain and openly licensed musical scores
> through a stable API designed for software, education and research.

Botones:
- **API Documentation**
- **Search scores** (`/search`)
- **Statistics** (`/statistics`)

**Cifras (reales, cercanas a lo que representa el proyecto)**:

| Etiqueta | Valor |
|---|---|
| MusicXML resources | 254,035 |
| Collections | 1 |
| Repository size | 54 GB |
| API availability | Online |

Sin menciones a GitHub por ahora. Cloudflare queda **invisible** (es infraestructura).

## Qué es Open Music Repository

> Open Music Repository nació para resolver un problema sencillo: encontrar partituras abiertas
> en un único lugar, independientemente de dónde se encuentren.

Dejar claro que **no pretende sustituir a IMSLP ni a PDMX**: al contrario, los integra.

## Filosofía

> - Open Standards
> - Public Domain
> - Open Source
> - Music First
> - No vendor lock-in
> - Long-term preservation

## Qué contiene

Explicar las fuentes y que **cada fuente mantiene sus derechos**:

| Fuente | Tipo |
|---|---|
| PDMX | MusicXML |
| IMSLP | PDF |
| Local Collections | MusicXML |
| OpenScore | cuando exista |

## Búsqueda

Página con ejemplos. Buscar por: compositor, título, catálogo, instrumento, género,
tonalidad, duración, dominio público.
No importa que todavía no esté todo implementado: la web debe enseñar hacia dónde va.

## API

Página completa con ejemplos:

- `GET /works`
- `GET /works/{id}`
- `GET /download/{id}`
- `GET /search?composer=Mozart`

Ejemplos en: **curl**, **Python**, **JavaScript**.

## Mirror

Explicar algo muy importante. No se dice "tenemos PDMX", se dice:

> Open Music Repository maintains its own verified mirror of the PDMX collection to provide
> stable and permanent access.

Eso transmite confianza (mirror propio verificado = acceso estable y permanente).

## Estadísticas

- 254 035 MusicXML
- 254 035 PDF
- 254 035 MIDI
- 54 GB
- 1 mirror
- XXX composers
- XXX works
- Un gráfico creciendo.

Datos disponibles vía la API (`/api/v1/statistics`).

## Estado del sistema

Estilo GitHub Status: API, Storage, Mirror, Database, Search → *Everything is OK*.
Se puede reutilizar literalmente el comando `doctor`.

## Licencias

Explicar: dominio público, CC0, licencias originales, qué almacena el proyecto, qué no almacena.

## Arquitectura (en la landing)

Simplificada, sin infraestructura visible (Cloudflare queda invisible):

```
Clients
  ↓
Open Music Repository API
  ↓
Verified Repository
```

## Para desarrolladores

Explicar OSAP, **no como producto comercial**, sino como cliente oficial:

```
OSAP
  ↓
Open Music Repository
  ↓
Storage
  ↓
Music Providers
```

## Blog

No subestimar. Cada hito merece entrada: nuevo mirror PDMX, nueva API, 100 000 obras,
nuevo buscador, nueva versión. (También muy valorado por SEO.)

## Roadmap

- **Version 1** ✔ MusicXML · API · Mirror
- **Version 2**: User accounts · Collections · Favorites · Uploads
- **Version 3**: Community · Collaborative editing · Analysis · Donaciones

**Support the project** → discreto, al final de la página, no al principio.

## Contacto

Muy sencillo: email, documentación.

## Sobre el creador

**Recomendado (frase resumen, no CV):**

> Desarrollador de software, arquitecto de sistemas y formador con más de 40 años de experiencia,
> construyendo herramientas abiertas para facilitar el acceso al conocimiento y a la música.

(El visitante no necesita el historial laboral completo: distrae del objetivo del proyecto.
La frase transmite confianza y mantiene el foco en Open Music Repository.)

---

### Material de referencia para "Sobre el creador"

> Open Music Repository no nace de una empresa.
> Nace del trabajo de un ingeniero y desarrollador que lleva más de cuatro décadas diseñando
> software y formando a profesionales.
> Durante su carrera ha trabajado en banca, industria, administración pública, consultoría y
> formación tecnológica, ocupando desde puestos de programador hasta director de sistemas de
> información.
> En los últimos años su actividad se ha centrado en la formación especializada y el desarrollo
> de herramientas para desarrolladores y profesionales de la informática, impartiendo miles de
> horas de formación en tecnologías como Java, Spring, MySQL, MongoDB, React, Angular, Node.js,
> PHP o Flutter.

**¿Por qué Open Music Repository?**

> Después de muchos años desarrollando software para empresas, decidí dedicar parte de mi tiempo
> a construir herramientas abiertas que resuelvan problemas reales.
> Como músico aficionado descubrí un problema evidente: encontrar una partitura concreta en
> formato MusicXML sigue siendo sorprendentemente difícil.
> Existen magníficos repositorios de PDF, grandes colecciones para investigación y numerosos
> proyectos musicales, pero ninguno ofrece una forma sencilla de localizar, unificar y servir
> partituras editables desde una única interfaz.
> Open Music Repository nace para cubrir ese hueco.

**La filosofía**

> No pretendo construir "otro repositorio de partituras". El objetivo es construir una
> infraestructura abierta que permita: localizar obras musicales, unificar múltiples fuentes,
> preservar los metadatos originales, facilitar el acceso a formatos editables y servir como
> base para futuras aplicaciones musicales.

**Tecnología** (íntegramente software libre)

> Python · FastAPI · MariaDB · Cloudflare R2 · Docker · Linux · Git · IA aplicada al desarrollo.
> Todo el proyecto se desarrolla siguiendo arquitectura limpia y principios de mantenibilidad.

**Experiencia**

> Mi trayectoria combina dos perfiles que rara vez aparecen juntos: desarrollo profesional de
> software desde finales de los años 80 y miles de horas formando desarrolladores y
> profesionales IT. He trabajado con tecnologías que abarcan desde sistemas bancarios y grandes
> corporaciones hasta aplicaciones web modernas, móviles e inteligencia artificial.

**Formación**

> Además de la experiencia profesional, durante años he desarrollado material docente y cursos
> especializados sobre tecnologías web, HTML5, CSS, JavaScript y desarrollo de aplicaciones.

**Open Source**

> Open Music Repository es un proyecto personal. No depende de financiación externa ni de
> ninguna empresa. La prioridad siempre será: mantener una API abierta, facilitar el acceso a
> los datos, respetar las licencias originales y colaborar con la comunidad.

## Separación de proyectos (recordatorio)

- **Open Music Repository (OMR)** → servicio público: web, API y almacenamiento.
- **OSAP** → cliente inteligente que consulta OMR (y otras fuentes) para encontrar y obtener
  partituras.
- Otras aplicaciones pueden consumir OMR sin depender de OSAP.
