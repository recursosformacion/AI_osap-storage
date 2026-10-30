# OSAP Storage — Catalogue Data and Resource Storage

**OSAP Storage** is the data service for the [OSAP — Open Score Acquisition Platform](https://github.com/recursosformacion/AI_GAMEPC2) ecosystem. It serves catalogue data—including works, composers and their relationships—and manages musical resources and their digital files. It is designed for authorized service-to-service access rather than direct access from the public web client.

The repository includes a Python API and CLI, a database layer with migrations, storage adapters and operational documentation. Consult the roadmap and deployment documentation before deploying; the implementation and production security status must be checked against the deployed version.

## Architecture and V6 direction

The target V6 catalogue model is **Work → Resource → File**. Representation, StorageLocation and StorageProvider as domain/catalogue entities are retired in V6. Physical objects already stored in Cloudflare R2 are to remain untouched; V6 reconstructs their database references directly on File. See the V6 documents below.

> **Transition warning:** the current codebase still contains the previous Representation / StorageLocation / StorageProvider implementation. The V6 documents describe the target and the required work; they do not mean that the code or production database has already been migrated.

## Essential documentation

- [V6 reconstruction, API, index and cutover plan](docs/v6-reconstruction-api-index-cutover.md) — exhaustive impact audit, data transformation, R2 preservation, Provider API, OSAP index, deployment, rollback, validation and pending decisions.
- [Roadmap](ROADMAP.md) — responsibilities, status and remaining work.
- [Code structure](docs/structure.md) — current repository architecture.
- [OSAP Storage code audit](docs/auditoria-codigo-osap-storage.md) — recorded code review.
- [Provider API contract (current implementation)](docs/provider-api-contract.md) — historical/current contract to be reconciled with V6; not by itself the V6 contract.

## Related OSAP repositories

- **[AI_GAMEPC2](https://github.com/recursosformacion/AI_GAMEPC2)** — OSAP core, API consumers and resource-resolution engine.
- [ai-importacion](https://github.com/recursosformacion/ai-importacion) — independent discovery and review of music materials from Internet Archive.
- [ai_recogeYouTube](https://github.com/recursosformacion/ai_recogeYouTube) — discovery and review of YouTube recordings associated with musical works.
- [AI_osap-auth](https://github.com/recursosformacion/AI_osap-auth) — identity and authentication service.
- [AI_osap-support](https://github.com/recursosformacion/AI_osap-support) — donations, memberships and support services.
- Public catalogue: [openmusicrepository.com](https://openmusicrepository.com)

## V6: área de trabajo personal y aportaciones

El alcance V6 incluye el espacio privado del usuario, los borradores y el flujo de aportación/revisión/publicación de nuevas piezas y Resources. Véase [la especificación funcional](docs/v6-user-workspace-contributions.md), coordinada con el plan de reconstrucción V6.
