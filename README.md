# OSAP Storage — Catalogue Data and Resource Storage

**OSAP Storage** is the data service for the [OSAP — Open Score Acquisition Platform](https://github.com/recursosformacion/AI_GAMEPC2) ecosystem. It serves catalogue data—including works, composers and their relationships—and manages resources and file locations. It is designed for authorized service-to-service access rather than direct access from the public web client.

The repository includes a Python API and CLI, a database layer with migrations, storage-provider abstractions, and operational documentation. The exact deployment and security status can change; consult the roadmap and deployment documentation before deploying.

## Architecture and status

- The roadmap describes the service as the authoritative catalogue-data server.
- Service authentication is designed around signed JWTs, JWKS verification and scopes.
- The roadmap tracks remaining deployment and verification work for protected access; do not assume every production security control is enabled without checking the current status.
- Storage locations and providers abstract where resource files are physically kept.

Useful repository documents:
- [Roadmap](ROADMAP.md) — responsibilities, status and remaining work.
- [Code structure](docs/structure.md) — architecture and modules.
- [OSAP Storage code audit](docs/auditoria-codigo-osap-storage.md) — recorded code review.

## Related OSAP repositories

- **[AI_GAMEPC2](https://github.com/recursosformacion/AI_GAMEPC2)** — OSAP core and resource-resolution engine.
- [ai-importacion](https://github.com/recursosformacion/ai-importacion) — independent discovery and review of music materials from Internet Archive.
- [ai_recogeYouTube](https://github.com/recursosformacion/ai_recogeYouTube) — discovery and review of YouTube recordings associated with musical works.
- [AI_osap-auth](https://github.com/recursosformacion/AI_osap-auth) — identity and authentication service.
- [AI_osap-support](https://github.com/recursosformacion/AI_osap-support) — donations, memberships and support services.
- Public catalogue: [openmusicrepository.com](https://openmusicrepository.com)
