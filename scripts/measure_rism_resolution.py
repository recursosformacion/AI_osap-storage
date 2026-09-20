"""Medición comparativa: resolución de obras SIN y CON evidencia RISM (read-only).

Compara, sobre datos reales, el resultado del resolutor sin atribuciones y con las atribuciones
de `rism_sources`: cuántos grupos/mergers aporta, en qué estados, y una muestra para revisión
manual (incluidos posibles conflictos).

Requiere el índice `rism_sources` (si no existe, informa y sale sin romper).

    .venv\\Scripts\\python.exe scripts/measure_rism_resolution.py
    .venv\\Scripts\\python.exe scripts/measure_rism_resolution.py --out docsNew/medicion-rism-resolucion.md
    .venv\\Scripts\\python.exe scripts/measure_rism_resolution.py --sample 60
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from application.use_cases.resolution import _best_attribution  # noqa: E402
from domain.entities.composer_attribution import (  # noqa: E402
    ComposerAttribution,
    state_for_reliability,
)
from domain.entities.resolution import ResourceEvidence  # noqa: E402
from domain.services.composer_names import normalize_composer_name as norm  # noqa: E402
from domain.services.grouping_resolver import resolve  # noqa: E402
from domain.services.title_evidence import is_attributable_title  # noqa: E402


def _load_works(conn) -> tuple[list[dict], dict[int, list[str]]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT w.id, w.works_title, w.works_catalogue, c.person_id, p.persons_name "
            "FROM works w LEFT JOIN (SELECT works_person_roles_work_id wid, "
            "  MIN(works_person_roles_person_id) person_id FROM works_person_roles "
            "  WHERE works_person_roles_role_id=1 GROUP BY 1) c ON c.wid=w.id "
            "LEFT JOIN persons p ON p.persons_id=c.person_id"
        )
        works = cur.fetchall()
        cur.execute("SELECT person_id, person_aliases_normalized_alias a FROM persons_aliases")
        aliases: dict[int, list[str]] = defaultdict(list)
        for r in cur.fetchall():
            if r["a"]:
                aliases[r["person_id"]].append(r["a"])
    return works, aliases


def _load_rism(conn, titles: set[str]) -> dict[str, list[ComposerAttribution]]:
    out: dict[str, list[ComposerAttribution]] = defaultdict(list)
    values = [t for t in titles if t]
    if not values:
        return {}
    chunk = 500
    with conn.cursor() as cur:
        for i in range(0, len(values), chunk):
            part = values[i:i + chunk]
            ph = ", ".join(["%s"] * len(part))
            try:
                cur.execute(
                    "SELECT rism_uniform_title_norm u, rism_title_norm t, "
                    "       rism_composer_person_id pid, rism_composer_name pname, "
                    "       rism_reliability rel FROM rism_sources "
                    f"WHERE rism_composer_person_id IS NOT NULL AND "
                    f"(rism_uniform_title_norm IN ({ph}) OR rism_title_norm IN ({ph}))",
                    part + part,
                )
                rows = cur.fetchall()
            except Exception as exc:  # noqa: BLE001
                if "rism_sources" in str(exc).lower():
                    print("AVISO: el índice `rism_sources` no existe todavía; "
                          "ejecuta el importador antes de medir.")
                    return {}
                raise
            for r in rows:
                attr = ComposerAttribution(
                    person_id=r["pid"], person_name=r["pname"],
                    state=state_for_reliability(r["rel"]), reliability=r["rel"],
                    matched_title=None,
                )
                if r["u"] in titles:
                    out[r["u"]].append(attr)
                if r["t"] in titles:
                    out[r["t"]].append(attr)
    return dict(out)


def _works_map(resolution) -> dict[int, str]:
    return {wid: g.key for g in resolution.groups for wid in g.work_ids}


def run(out_path: Path | None, sample: int) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    works, aliases = _load_works(conn)

    # títulos atribuibles de obras sin compositor
    target_titles: set[str] = set()
    for w in works:
        if not w["person_id"] and w["works_title"] and is_attributable_title(w["works_title"]):
            target_titles.add(norm(w["works_title"]))
    by_title = _load_rism(conn, target_titles)
    conn.close()

    attributions_by_work: dict[int, ComposerAttribution] = {}
    for w in works:
        if w["person_id"] or not w["works_title"]:
            continue
        matches = by_title.get(norm(w["works_title"]))
        if matches:
            best = _best_attribution(matches)
            if best is not None:
                attributions_by_work[w["id"]] = best

    evidences: list[ResourceEvidence] = []
    for w in works:
        if not w["works_title"]:
            continue
        evidences.append(ResourceEvidence(
            resource_id=int(w["id"]), resource_type="MXL", representation_id=int(w["id"]),
            origin="synthetic", origin_id=str(w["id"]), license="", editors=(),
            work_id=int(w["id"]), title=w["works_title"], catalogue=w["works_catalogue"],
            composer=w["persons_name"], composer_id=w["person_id"],
            composer_aliases=tuple(aliases.get(w["person_id"] or "", [])),
        ))

    buckets: dict[str, list[ResourceEvidence]] = defaultdict(list)
    for ev in evidences:
        buckets[norm(ev.title)].append(ev)

    base_groups = rism_groups = 0
    works_candidates = 0
    rule_counts: Counter[str] = Counter()
    state_counts: Counter[str] = Counter()
    new_merges: list[str] = []
    conflicts: list[str] = []
    for members in buckets.values():
        if len(members) < 2:
            continue
        works_candidates += len(members)
        base = resolve(members)
        with_rism = resolve(members, attributions_by_work)
        base_groups += len(base.groups)
        rism_groups += len(with_rism.groups)
        for r in with_rism.applied + with_rism.review:
            if r.rule.startswith("rism_"):
                rule_counts[r.rule] += 1
                if r.rule == "rism_attribution":
                    state_counts[str(r.evidence.get("state"))] += 1

        before, after = _works_map(base), _works_map(with_rism)
        for wid, gkey in after.items():
            if before.get(wid) == gkey:
                continue
            peers = [p for p, k in after.items() if k == gkey and p != wid]
            if peers and len(new_merges) < sample:
                attr = attributions_by_work.get(wid)
                new_merges.append(
                    f"work {wid} ({next((e.title for e in evidences if e.work_id == wid), '')}) "
                    f"→ grupo con {peers[:4]}"
                    + (f" [RISM {attr.person_name}/{attr.state}/{attr.reliability}]" if attr else "")
                )
            # posible conflicto: el grupo mezcla nuestra persona y una atribución distinta
            group_ids = [wid, *peers]
            ours = {e.composer_id for e in evidences
                    if e.work_id in group_ids and e.composer_id}
            rism_ids = {attributions_by_work[p].person_id for p in group_ids
                        if p in attributions_by_work}
            if ours and rism_ids and not (ours & rism_ids) and len(conflicts) < sample:
                conflicts.append(f"grupo {gkey}: nuestras {sorted(ours)} vs RISM {sorted(rism_ids)}")

    lines: list[str] = []
    add = lines.append
    add("# Medición: resolución sin/con evidencia RISM\n")
    add("Generado por `scripts/measure_rism_resolution.py` (read-only).\n")
    add(f"- Obras candidatas (buckets >1): **{works_candidates}**")
    add(f"- Obras sin compositor con atribución RISM usable: **{len(attributions_by_work)}**\n")
    add("## Efecto en la agrupación\n")
    add("| | Grupos | Mergers (obras - grupos) |")
    add("|---|---|---|")
    add(f"| Sin RISM | {base_groups} | {works_candidates - base_groups} |")
    add(f"| Con RISM | {rism_groups} | {works_candidates - rism_groups} |")
    add(f"| Delta | {rism_groups - base_groups:+d} | {base_groups - rism_groups:+d} |")
    add("\n## Reglas RISM emitidas\n")
    add("| Regla | Casos |")
    add("|---|---|")
    for key, value in rule_counts.most_common():
        add(f"| {key} | {value} |")
    if state_counts:
        add("\nEstados de `rism_attribution`: " + ", ".join(f"{k}={v}" for k, v in state_counts.items()))
    add("\n## Muestra para revisión manual (mergers nuevos)\n")
    add("\n".join(f"- {e}" for e in new_merges) or "(sin muestras)")
    add("\n## Posibles conflictos (nuestra persona vs RISM distinta en el mismo grupo)\n")
    add("\n".join(f"- {e}" for e in conflicts) or "(sin conflictos detectados)")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print(f"candidatas={works_candidates} sin_rism={base_groups} con_rism={rism_groups} "
          f"delta={rism_groups - base_groups:+d} atribuciones={len(attributions_by_work)}")
    print("reglas:", dict(rule_counts), "estados:", dict(state_counts))


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sample", type=int, default=50)
    args = ap.parse_args()
    run(args.out, args.sample)


if __name__ == "__main__":
    main()
