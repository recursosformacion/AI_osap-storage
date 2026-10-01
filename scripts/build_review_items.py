"""Construye la cola de revisión humana (`review_items`) desde el staging saneado.

NO aplica nada al catálogo: solo materializa la **unidad humana de decisión** con claves lógicas.

Unidades (paso a paso, según la auditoría del artefacto):
  identity_cluster    una PERSONA (no una cadena): se agrupa por la clave de identidad del catálogo
                      y se separa cuando esa clave colapsa nombres distintos (Neil vs Nathaniel Gow).
  ambiguous_identity  un NOMBRE con varios candidatos (antes: un item por obra) + obras afectadas.
  work_attribution    una OBRA y su propuesta de atribución (la clave incluye la propuesta, para que
                      `anonymous` y `traditional` no se pisen).

Cada item lleva candidatos enriquecidos (ancla, alias, obras, relaciones, si fue la resolución) y
contexto suficiente para decidir sin abrir obra por obra. Los solapamientos obra↔identidad↔atribución
se marcan explícitamente (`conflicto`).

Uso:
    python -m scripts.build_review_items             # dry-run: solo métricas
    python -m scripts.build_review_items --apply     # refresca review_items (derivada)
    python -m scripts.build_review_items --json out.json
    python -m scripts.build_review_items --export-dir dir   # detalle completo de obras por clúster
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

from application.services.import_person_parser import canonical_name_key
from domain.services.composer_names import normalize_composer_name
from infrastructure.config import Settings
from infrastructure.db.connection import Database

_EXCEPCIONES = ("review_target_contaminated", "resolved_sanitized", "ambiguous", "needs_review")
_MAX_OBRAS_EN_ITEM = 200


def build_work_key(origin: str | None, origin_id: str | None, works_key: str | None) -> str | None:
    """Clave lógica de obra, estable entre entornos (o None si no se puede construir)."""
    origen = canonical_name_key(origin).upper()
    identificador = canonical_name_key(origin_id)
    hash_pdmx = canonical_name_key(works_key)
    if origen == "CPDL" and identificador:
        return f"CPDL:{identificador}"
    if hash_pdmx:
        return f"PDMX:{hash_pdmx}"
    if identificador:
        return f"{origen or 'OTRO'}:{identificador}"
    return None


_EQUIVALENCIAS = str.maketrans({
    "ß": "ss", "ſ": "s", "ø": "o", "Ø": "o", "ł": "l", "Ł": "l", "đ": "d", "Đ": "d",
    "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe", "þ": "th", "Þ": "th",
})


def collation_key(texto: str | None) -> str:
    """Clave con la misma semántica que la colación utf8mb4_unicode_ci: sin acentos ni mayúsculas
    y con las equivalencias que la colación aplica (`ß`≡`ss`, `ø`≡`o`, `ſ`≡`s`…).

    Evita emitir dos claves lógicas que la base de datos considere iguales, que romperían el
    índice único del artefacto.
    """
    base = canonical_name_key(texto).translate(_EQUIVALENCIAS)
    plano = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", plano).strip().lower()


def build_item_key(item_type: str, work_key: str | None, person_key: str | None, extra: str | None = None) -> str:
    """Clave canónica del item (no nula), para idempotencia del refresco."""
    return "|".join(
        [item_type, canonical_name_key(work_key), canonical_name_key(person_key), canonical_name_key(extra)]
    )


def build_decision_key(
    decision_type: str, work_key: str | None, person_key: str | None, role_key: str | None = None
) -> str:
    """Clave canónica de una decisión humana (misma forma que el item cuando aplica)."""
    return "|".join(
        [decision_type, canonical_name_key(work_key), canonical_name_key(person_key), canonical_name_key(role_key)]
    )


def full_name_key(nombre: str) -> str:
    """Clave nominal COMPLETA (sin colapsar nombres de pila a iniciales).

    Es la que evita que `Neil Gow` y `Nathaniel Gow` caigan en la misma identidad.
    """
    texto = normalize_composer_name(canonical_name_key(nombre))
    return canonical_name_key(texto)


def compatible_names(uno: str, otro: str) -> bool:
    """True si dos claves nominales pueden ser la misma persona (p. ej. `j s bach` vs `johann sebastian bach`).

    Compatibles si tienen el mismo número de palabras, el mismo último apellido y el resto son
    iguales o iniciales de la otra (una palabra de 1-2 caracteres que empieza la otra).
    """
    a, b = uno.split(), otro.split()
    if not a or not b or len(a) != len(b) or a[-1] != b[-1]:
        return False
    for x, y in zip(a[:-1], b[:-1], strict=True):
        if x == y:
            continue
        if len(x) <= 2 and y.startswith(x[0]):
            continue
        if len(y) <= 2 and x.startswith(y[0]):
            continue
        return False
    return True


_CONECTOR_ROL = re.compile(r"^(attr\.?|attributed to|atribuido a|after|from|by)\s+", re.I)
_TITULO = re.compile(r"\s-\s.*|\b(in|op|no|bwv|kv|hwv|buxwv)\b.*\b[a-z]\b", re.I)
_CONCATENACION = re.compile(r"[a-z]{3,}[A-Z][a-z]{2,}")
_TRUNCADO = re.compile(r"\b(befo|before|after|sir|rev|ed|arr|adap|transcr)\.?$", re.I)


def clasificar_artefacto(nombre: str) -> str | None:
    """Clasifica un nombre como posible artefacto textual (no identidad de persona).

    `posible_artefacto` ≠ `new_person`: aquí no hay evidencia de que sea una persona real, así que
    no debe entrar en la unidad de identidad ni alimentar una futura decisión `create_person`.
    """
    texto = canonical_name_key(nombre)
    if not texto:
        return "vacio"
    if _CONECTOR_ROL.match(texto):
        return "prefijo_atribucion"
    if _TITULO.search(texto):
        return "posible_titulo"
    if _CONCATENACION.search(texto):
        return "concatenacion"
    if _TRUNCADO.search(texto):
        return "texto_truncado"
    if len(texto.split()) > 6:
        return "demasiado_largo"
    return None


def _persona_evidencia(pid: str, meta: dict[str, dict[str, Any]]) -> tuple[set[str], set[str]]:
    datos = meta.get(pid, {})
    anclas = set(datos.get("anchors", []))
    alias = {full_name_key(a) for a in datos.get("aliases", []) if a}
    nombre = full_name_key(str(datos.get("name", "")))
    if nombre:
        alias.add(nombre)
    return anclas, alias


def unir_por_evidencia(
    grupos: list[dict[str, Any]], meta: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Une grupos de identidad siguiendo el orden: ancla > alias > nombre compatible.

    Deja constancia de la evidencia usada (`evidencia_union`), para poder auditar después qué
    uniones no se apoyan en ancla ni alias.
    """
    for grupo in grupos:
        anclas: set[str] = set()
        alias: set[str] = set()
        for pid in grupo["candidatos"]:
            a, al = _persona_evidencia(pid, meta)
            anclas |= a
            alias |= al
        grupo["anclas"] = anclas
        grupo["alias"] = alias

    padre = {i: i for i in range(len(grupos))}
    evidencia: list[set[str]] = [set() for _ in grupos]

    def raiz(i: int) -> int:
        while padre[i] != i:
            padre[i] = padre[padre[i]]
            i = padre[i]
        return i

    for i, uno in enumerate(grupos):
        for j in range(i + 1, len(grupos)):
            otro = grupos[j]
            razones: set[str] = set()
            if uno["anclas"] & otro["anclas"]:
                razones.add("ancla_comun")
            if uno["alias"] & otro["alias"]:
                razones.add("alias_comun")
            if not razones:
                # compatibilidad fuerte de nombre, siempre que no haya anclas en conflicto
                conflicto = bool(uno["anclas"] and otro["anclas"] and not (uno["anclas"] & otro["anclas"]))
                if not conflicto and any(
                    compatible_names(a, b) for a in uno["nombres"] for b in otro["nombres"]
                ):
                    razones.add("nombre_compatible")
            if razones:
                ri, rj = raiz(i), raiz(j)
                if ri != rj:
                    padre[rj] = ri
                    evidencia[ri] |= razones | evidencia[rj]
                    evidencia[rj] = set()

    unidos: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for i, grupo in enumerate(grupos):
        unidos[raiz(i)].append(grupo)
    resultado: list[dict[str, Any]] = []
    for indice, miembros in unidos.items():
        resultado.append({
            "miembros": miembros,
            "evidencia_union": sorted(evidencia[indice]),
        })
    return resultado


def agrupar_por_persona(filas: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Parte las filas de una misma clave de identidad en sub-clústeres que son UNA persona.

    Une variantes compatibles (`j s bach` + `johann sebastian bach`) y separa nombres distintos que
    la clave colapsó (`n gow` → `neil gow` y `nathaniel gow`).
    """
    nombres = sorted({f["full_key"] for f in filas})
    padre = {n: n for n in nombres}

    def raiz(n: str) -> str:
        while padre[n] != n:
            padre[n] = padre[padre[n]]
            n = padre[n]
        return n

    for i, uno in enumerate(nombres):
        for otro in nombres[i + 1:]:
            if compatible_names(uno, otro):
                padre[raiz(otro)] = raiz(uno)
    grupos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for fila in filas:
        grupos[raiz(fila["full_key"])].append(fila)
    return list(grupos.values())


async def _catalogo(db: Database) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, str]]]]:
    """Metadatos por persona (nombre, anclas, alias, clave de identidad) y candidatos por nombre."""
    meta: dict[str, dict[str, Any]] = {}
    candidatos: dict[str, list[dict[str, str]]] = defaultdict(list)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT persons_id, persons_name FROM persons WHERE persons_status='active' AND persons_merged_into IS NULL"
        )
        for row in await cur.fetchall():
            pid = str(row["persons_id"])
            meta[pid] = {"name": str(row["persons_name"]), "anchors": [], "aliases": [], "identity_key": ""}
            key = full_name_key(str(row["persons_name"]))
            if key:
                candidatos[key].append({"id": pid, "name": str(row["persons_name"])})
        await cur.execute(
            "SELECT person_id, person_aliases_alias, person_aliases_normalized_alias FROM persons_aliases"
        )
        for row in await cur.fetchall():
            pid = str(row["person_id"])
            if pid in meta:
                meta[pid]["aliases"].append(str(row["person_aliases_alias"]))
            key = canonical_name_key(str(row["person_aliases_normalized_alias"] or ""))
            if key:
                candidatos[key].append({"id": pid, "name": str(row["person_aliases_alias"] or "")})
        await cur.execute(
            "SELECT persons_id, identity_type, identity_value, identity_name_norm FROM persons_identity "
            "WHERE identity_is_anchor = 1"
        )
        for row in await cur.fetchall():
            pid = str(row["persons_id"])
            if pid not in meta:
                continue
            tipo = str(row["identity_type"] or "").strip().lower()
            valor = canonical_name_key(str(row["identity_value"] or ""))
            if tipo in ("viaf", "musicbrainz", "mbid", "isni") and valor:
                meta[pid]["anchors"].append(f"{tipo}:{valor}")
            elif not meta[pid]["identity_key"] and row["identity_name_norm"]:
                meta[pid]["identity_key"] = canonical_name_key(str(row["identity_name_norm"]))
        await cur.execute(
            "SELECT works_person_roles_person_id AS pid, COUNT(*) AS n FROM works_person_roles GROUP BY pid"
        )
        rel = {str(r["pid"]): int(r["n"]) for r in await cur.fetchall()}
        for pid, datos in meta.items():
            datos["relaciones"] = rel.get(pid, 0)
    return meta, candidatos


def _candidato(pid: str, meta: dict[str, dict[str, Any]], es_resolucion: bool) -> dict[str, Any]:
    datos = meta.get(pid, {})
    return {
        "person_key": (datos.get("anchors") or [f"name:{datos.get('identity_key') or ''}"])[0],
        "nombre": datos.get("name", ""),
        "anchors": datos.get("anchors", []),
        "alias": datos.get("aliases", [])[:10],
        "obras": datos.get("obras", 0),
        "relaciones": datos.get("relaciones", 0),
        "es_resolucion_parser": es_resolucion,
    }


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="refresca review_items (derivada)")
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--export-dir", type=Path, default=None, help="detalle completo de obras por clúster")
    args = parser.parse_args()

    settings = Settings()  # type: ignore[call-arg]
    db = Database(settings)
    meta, candidatos = await _catalogo(db)
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT s.id, s.kind, s.person_key, s.person_name_raw, s.person_name_clean, s.person_name_norm, "
            "s.role_key, s.attribution_status, s.person_id, s.status, s.sanitize_flags, s.works_id, "
            "w.works_title, w.works_origin, w.works_origin_id, w.works_key, "
            "(SELECT GROUP_CONCAT(g.name) FROM work_genres wg JOIN genres g ON g.id = wg.genres_id "
            " WHERE wg.works_id = w.id) AS generos, "
            "w.works_instrumentation, w.works_attr_type, w.works_attribution_note "
            "FROM import_person_parse s JOIN works w ON w.id = s.works_id"
        )
        rows = [dict(r) for r in await cur.fetchall()]
        await cur.execute("SELECT works_person_roles_work_id AS w, COUNT(*) AS n FROM works_person_roles GROUP BY w")
        relaciones_obra = {int(r["w"]): int(r["n"]) for r in await cur.fetchall()}
    # obras por persona (para enriquecer candidatos)
    obras_por_persona: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        if row["kind"] == "person" and row["person_id"]:
            obras_por_persona[str(row["person_id"])].add(int(row["works_id"]))
    for pid, obras_persona in obras_por_persona.items():
        if pid in meta:
            meta[pid]["obras"] = len(obras_persona)

    # --- clasificación de artefactos textuales y agrupación por identidad (paso 1)
    artefactos: dict[str, list[dict[str, Any]]] = defaultdict(list)
    por_identidad: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["kind"] != "person":
            continue
        limpio = str(row["person_name_clean"] or "")
        pid = str(row["person_id"]) if row["person_id"] else ""
        ident = (meta.get(pid, {}).get("identity_key") or "") or canonical_name_key(
            normalize_composer_name(limpio or str(row["person_name_norm"] or ""))
        )
        fila = {**row, "full_key": full_name_key(limpio), "ident": ident or "?"}
        motivo = clasificar_artefacto(limpio)
        if motivo:
            artefactos[f"{motivo}|{canonical_name_key(limpio)}"].append({**fila, "motivo": motivo})
        else:
            por_identidad[ident or "?"].append(fila)

    grupos_iniciales = [
        {
            "ident": ident,
            "filas": filas,
            "candidatos": sorted({str(f["person_id"]) for f in filas if f["person_id"]}),
            "nombres": sorted({f["full_key"] for f in filas if f["full_key"]}),
        }
        for ident, filas in por_identidad.items()
    ]
    grupos_unidos = unir_por_evidencia(grupos_iniciales, meta)

    items: list[dict[str, Any]] = []
    export: dict[str, Any] = {}
    obras_por_cluster: dict[str, set[str]] = defaultdict(set)
    obras_en_persona: set[str] = set()
    # Se acumulan por `person_key`: dos sub-clústeres que resuelven a la MISMA persona son uno solo.
    acumulado: dict[str, dict[str, Any]] = {}
    for grupo in grupos_unidos:
        filas_grupo = [f for miembro in grupo["miembros"] for f in miembro["filas"]]
        fichas = len({m["ident"] for m in grupo["miembros"]})
        for sub in agrupar_por_persona(filas_grupo):
            nombres = sorted({f["full_key"] for f in sub if f["full_key"]})
            candidatos_ids = {str(f["person_id"]) for f in sub if f["person_id"]}
            anclas = {a for pid in candidatos_ids for a in meta.get(pid, {}).get("anchors", [])}
            colision = len(agrupar_por_persona(filas_grupo)) > 1
            if colision and nombres:
                person_key = f"name:{nombres[0]}"
            elif len(candidatos_ids) == 1 and len(anclas) == 1:
                person_key = next(iter(anclas))
            else:
                person_key = f"name:{sorted({f['ident'] for f in sub})[0]}"
            entrada = acumulado.setdefault(
                collation_key(person_key),
                {
                    "filas": [], "ident": sorted({f["ident"] for f in sub})[0], "colision": colision,
                    "nombres": set(), "person_key": person_key, "evidencia": set(),
                    "fichas": fichas,
                },
            )
            entrada["filas"].extend(sub)
            entrada["nombres"].update(nombres)
            entrada["colision"] = entrada["colision"] or colision
            entrada["evidencia"] |= set(grupo["evidencia_union"])
            entrada["fichas"] = max(int(entrada["fichas"]), fichas)

    for entrada in acumulado.values():
        sub = entrada["filas"]
        ident = entrada["ident"]
        colision = entrada["colision"]
        person_key = entrada["person_key"]
        evidencia = sorted(entrada.get("evidencia", []))
        fichas = int(entrada.get("fichas", 1))
        nombres = sorted(entrada["nombres"])
        candidatos_ids = {str(f["person_id"]) for f in sub if f["person_id"]}
        obras = {
            build_work_key(f["works_origin"], f["works_origin_id"], f["works_key"])
            or f"work:{f['works_id']}"
            for f in sub
        }
        estados = sorted({str(f["status"]) for f in sub})
        roles = sorted({str(f["role_key"]) for f in sub if f["role_key"]})
        patrones: dict[str, int] = defaultdict(int)
        for f in sub:
            patrones[canonical_name_key(str(f["person_name_raw"]))[:120]] += 1
        item = {
            "item_key": build_item_key("identity_cluster", None, person_key),
            "item_type": "identity_cluster", "person_key": person_key, "work_key": None,
            "role_key": None, "attribution_status": None,
            "filas": len(sub), "obras": len(obras), "roles": ",".join(roles)[:255],
            "estados": ",".join(estados)[:255],
            "candidatos_json": json.dumps(
                [_candidato(pid, meta, True) for pid in sorted(candidatos_ids)]
                + [
                    {**_candidato(c["id"], meta, False), "nombre": c["name"]}
                    for nombre in nombres for c in candidatos.get(nombre, [])
                    if c["id"] not in candidatos_ids
                ],
                ensure_ascii=False,
            ),
            "contexto_json": json.dumps({
                "colision_de_clave": colision,
                "clave_identidad_colapsada": ident,
                "nombres_vistos": nombres,
                "evidencia_union": evidencia,
                "fichas_unidas": fichas,
                "union_solo_por_nombre": evidencia == ["nombre_compatible"] and len(candidatos_ids) > 1,
                "por_estado": {e: sum(1 for f in sub if str(f["status"]) == e) for e in estados},
                "por_rol": {r: sum(1 for f in sub if str(f["role_key"]) == r) for r in roles},
                "patrones_origen": [
                    {"patron": patron, "n": total}
                    for patron, total in sorted(patrones.items(), key=lambda kv: -kv[1])[:15]
                ],
                "obras": sorted(obras)[:_MAX_OBRAS_EN_ITEM],
                "obras_total": len(obras),
                "muestras": [
                    {"texto_origen": f["person_name_raw"], "nombre_limpio": f["person_name_clean"],
                     "flags": f["sanitize_flags"], "obra": f["works_title"], "estado": f["status"]}
                    for f in sub[:5]
                ],
            }, ensure_ascii=False),
            "_obras": obras,
            "_filas": sub,
        }
        items.append(item)
        obras_por_cluster[item["item_key"]] = obras
        obras_en_persona |= obras
        if len(obras) > _MAX_OBRAS_EN_ITEM or args.export_dir:
            export[item["item_key"]] = sorted(obras)

    # --- posible artefacto textual: fuera de la unidad de identidad (paso 2)
    for clave, filas in artefactos.items():
        motivo, _, nombre = clave.partition("|")
        obras = {
            build_work_key(f["works_origin"], f["works_origin_id"], f["works_key"]) or f"work:{f['works_id']}"
            for f in filas
        }
        items.append({
            "item_key": build_item_key("posible_artefacto", None, nombre),
            "item_type": "posible_artefacto", "person_key": f"name:{nombre}", "work_key": None,
            "role_key": filas[0]["role_key"], "attribution_status": None,
            "filas": len(filas), "obras": len(obras),
            "roles": ",".join(sorted({str(f["role_key"]) for f in filas if f["role_key"]}))[:255],
            "estados": motivo,
            "candidatos_json": None,
            "contexto_json": json.dumps({
                "motivo": motivo,
                "textos_origen": sorted({canonical_name_key(str(f["person_name_raw"])) for f in filas})[:15],
                "obras": sorted(obras)[:_MAX_OBRAS_EN_ITEM],
                "obras_total": len(obras),
                "person_id_casado": sorted({str(f["person_id"]) for f in filas if f["person_id"]}),
            }, ensure_ascii=False),
        })

    # --- ambiguas por identidad (paso 2): un item por persona, no por obra
    _ambiguas_vistas: set[str] = set()
    for item in items:
        if item["item_type"] != "identity_cluster" or "ambiguous" not in str(item["estados"]):
            continue
        if collation_key(item["person_key"]) in _ambiguas_vistas:
            continue
        _ambiguas_vistas.add(collation_key(item["person_key"]))
        filas_amb = [f for f in item["_filas"] if str(f["status"]) == "ambiguous"]
        if not filas_amb:
            continue
        nombres = sorted({f["full_key"] for f in filas_amb if f["full_key"]})
        obras = {
            build_work_key(f["works_origin"], f["works_origin_id"], f["works_key"]) or f"work:{f['works_id']}"
            for f in filas_amb
        }
        candidatos_amb = [
            {**_candidato(c["id"], meta, False), "nombre": c["name"]}
            for nombre in nombres for c in candidatos.get(nombre, [])
        ]
        items.append({
            "item_key": build_item_key("ambiguous_identity", None, item["person_key"]),
            "item_type": "ambiguous_identity", "person_key": item["person_key"], "work_key": None,
            "role_key": filas_amb[0]["role_key"], "attribution_status": None,
            "filas": len(filas_amb), "obras": len(obras),
            "roles": ",".join(sorted({str(f["role_key"]) for f in filas_amb}))[:255],
            "estados": "ambiguous",
            "candidatos_json": json.dumps(candidatos_amb, ensure_ascii=False),
            "contexto_json": json.dumps({
                "nombres_vistos": nombres,
                "obras": sorted(obras)[:_MAX_OBRAS_EN_ITEM],
                "obras_total": len(obras),
                "textos_origen": sorted({canonical_name_key(str(f["person_name_raw"])) for f in filas_amb})[:15],
            }, ensure_ascii=False),
        })

    # --- atribuciones por obra (paso 4) y conflictos (paso 5)
    por_obra_attr: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["kind"] == "attribution":
            work_key = (
                build_work_key(row["works_origin"], row["works_origin_id"], row["works_key"])
                or f"work:{row['works_id']}"
            )
            por_obra_attr[work_key].append(row)
    clusters_por_obra: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if item["item_type"] != "identity_cluster":
            continue
        for obra in item["_obras"]:
            clusters_por_obra[obra].append(item["item_key"])
    for work_key, filas in por_obra_attr.items():
        for estado in sorted({str(f["attribution_status"]) for f in filas}):
            conflicto = work_key in obras_en_persona
            items.append({
                "item_key": build_item_key("work_attribution", work_key, None, estado),
                "item_type": "work_attribution", "person_key": None, "work_key": work_key,
                "role_key": None, "attribution_status": estado,
                "filas": sum(1 for f in filas if str(f["attribution_status"]) == estado), "obras": 1,
                "roles": None, "estados": estado,
                "candidatos_json": None,
                "contexto_json": json.dumps({
                    "titulo": filas[0]["works_title"],
                    "origen": filas[0]["works_origin"],
                    "source_id": filas[0]["works_origin_id"] or filas[0]["works_key"],
                    "genero": filas[0]["generos"],
                    "instrumentacion": filas[0]["works_instrumentation"],
                    "attr_type": filas[0]["works_attr_type"],
                    "attribution_note": filas[0]["works_attribution_note"],
                    "textos_origen": sorted({canonical_name_key(str(f["person_name_raw"])) for f in filas})[:10],
                    "relaciones_actuales": relaciones_obra.get(int(filas[0]["works_id"]), 0),
                    "clusters_identidad_relacionados": sorted(set(clusters_por_obra.get(work_key, []))),
                    "conflicto_persona_atribucion": conflicto,
                }, ensure_ascii=False),
            })

    # Red de seguridad: si dos items acaban con claves que la colación de la BD considera iguales,
    # se fusionan (misma unidad humana) en lugar de romper el índice único.
    unicos: dict[str, dict[str, Any]] = {}
    for item in items:
        clave = collation_key(item["item_key"])
        previo = unicos.get(clave)
        if previo is None:
            unicos[clave] = item
            continue
        previo["filas"] += item["filas"]
        previo["_obras"] = set(previo.get("_obras", set())) | set(item.get("_obras", set()))
        previo["obras"] = len(previo["_obras"])
        previo["_filas"] = list(previo.get("_filas", [])) + list(item.get("_filas", []))
        estados = sorted(set(str(previo["estados"]).split(",")) | set(str(item["estados"]).split(",")) - {""})
        previo["estados"] = ",".join(estados)[:255]
    items = list(unicos.values())

    # limpieza de campos internos
    for item in items:
        item.pop("_obras", None)
        item.pop("_filas", None)

    informe = {
        "filas_staging_leidas": len(rows),
        "items_total": len(items),
        "items_por_tipo": {
            tipo: sum(1 for i in items if i["item_type"] == tipo)
            for tipo in ("identity_cluster", "ambiguous_identity", "work_attribution", "posible_artefacto")
        },
        "clusters_unidos_solo_por_nombre": sum(
            1
            for i in items
            if i["item_type"] == "identity_cluster"
            and '"union_solo_por_nombre": true' in str(i["contexto_json"])
        ),
        "clusters_con_colision": sum(
            1
            for i in items
            if i["item_type"] == "identity_cluster" and '"colision_de_clave": true' in str(i["contexto_json"])
        ),
        "clusters_con_excepcion": sum(
            1 for i in items if i["item_type"] == "identity_cluster"
            and any(e in str(i["estados"]) for e in _EXCEPCIONES)
        ),
        "obras_con_conflicto": sum(
            1 for i in items if i["item_type"] == "work_attribution"
            and '"conflicto_persona_atribucion": true' in str(i["contexto_json"])
        ),
        "aplicado": False,
    }

    if args.export_dir:
        args.export_dir.mkdir(parents=True, exist_ok=True)
        (args.export_dir / "obras_por_cluster.json").write_text(
            json.dumps(export, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        informe["export"] = str(args.export_dir / "obras_por_cluster.json")

    if args.apply:
        columnas = ("item_key", "item_type", "person_key", "work_key", "role_key", "attribution_status",
                    "filas", "obras", "roles", "estados", "candidatos_json", "contexto_json")
        sql = (
            "INSERT INTO review_items (" + ",".join(f"`{c}`" for c in columnas) + ") "
            "VALUES (" + ",".join(["%s"] * len(columnas)) + ")"
        )
        params = [tuple(item.get(c) for c in columnas) for item in items]
        async with db.transaction() as conn, conn.cursor() as cur:
            await cur.execute("DELETE FROM review_items")
            for start in range(0, len(params), 500):
                await cur.executemany(sql, params[start: start + 500])
        informe["aplicado"] = True

    if args.json:
        args.json.write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(informe, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
