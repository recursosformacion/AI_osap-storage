"""Análisis read-only de políticas de identidad de compositor y de compositor ausente.

NO modifica el resolutor ni la BBDD. Enumera los pares candidatos actuales (mismo título
normalizado), aplica cada política con union-find y produce un informe con métricas y ejemplos.

    .venv\\Scripts\\python.exe scripts/analyze_composer_identity.py
    .venv\\Scripts\\python.exe scripts/analyze_composer_identity.py --out docsNew/analisis-identidad-compositor.md
"""

from __future__ import annotations

import argparse
import contextlib
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402
from domain.services.composer_names import normalize_composer_name  # noqa: E402

PLACEHOLDERS = {
    "anonimo", "anonymous", "unknown", "desconocido", "tradicional", "traditional",
    "trad", "anon", "vvaa", "varios", "various", "sin autor", "auteur inconnu",
}

POLICY_NAMES = (
    "current",
    "A_strict",
    "B_tolerant",
    "P0_block",
    "P1_catalogue",
    "P2_sin_placeholders",
)


def _norm(value: str | None) -> str:
    return normalize_composer_name(value)


@dataclass(frozen=True)
class Work:
    id: int
    title: str | None
    catalogue: str | None
    person_id: str | None
    composer: str | None

    @property
    def title_key(self) -> str:
        return _norm(self.title)

    @property
    def catalogue_key(self) -> str:
        return _norm(self.catalogue)

    @property
    def composer_key(self) -> str:
        return _norm(self.composer)

    @property
    def placeholder(self) -> bool:
        return self.composer_key in PLACEHOLDERS


def _load(conn) -> tuple[dict[int, Work], dict[str, set[str]], dict[str, str], dict[str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT w.id, w.works_title, w.works_catalogue, c.person_id, p.persons_name "
            "FROM works w "
            "LEFT JOIN (SELECT works_person_roles_work_id wid, "
            "                  MIN(works_person_roles_person_id) person_id "
            "           FROM works_person_roles WHERE works_person_roles_role_id=1 "
            "           GROUP BY 1) c ON c.wid = w.id "
            "LEFT JOIN persons p ON p.persons_id = c.person_id"
        )
        works = {
            int(r["id"]): Work(int(r["id"]), r["works_title"], r["works_catalogue"],
                               r["person_id"], r["persons_name"])
            for r in cur.fetchall()
        }
        cur.execute(
            "SELECT person_id, person_aliases_normalized_alias FROM persons_aliases"
        )
        aliases: dict[str, set[str]] = defaultdict(set)
        raw_aliases: dict[str, set[str]] = defaultdict(set)
        for r in cur.fetchall():
            aliases[r["person_id"]].add(r["person_aliases_normalized_alias"])
            raw_aliases[r["person_id"]].add(r["person_aliases_normalized_alias"])
        cur.execute(
            "SELECT persons_id, persons_merged_into FROM persons "
            "WHERE persons_merged_into IS NOT NULL"
        )
        merged = {r["persons_id"]: r["persons_merged_into"] for r in cur.fetchall()}
        cur.execute("SELECT persons_id, persons_name FROM persons")
        names = {r["persons_id"]: _norm(r["persons_name"]) for r in cur.fetchall()}
    return works, aliases, merged, names


def _canonical(pid: str | None, merged: dict[str, str]) -> str | None:
    seen: set[str] = set()
    while pid is not None and pid in merged and pid not in seen:
        seen.add(pid)
        pid = merged[pid]
    return pid


def _provably_same(a: Work, b: Work, aliases: dict[str, set[str]],
                   merged: dict[str, str], names: dict[str, str]) -> bool:
    ca, cb = _canonical(a.person_id, merged), _canonical(b.person_id, merged)
    if ca is not None and ca == cb:
        return True
    if not a.person_id or not b.person_id:
        return False
    # alias no-propio de uno que coincide con nombre o alias no-propio del otro
    def non_self(pid: str) -> set[str]:
        own = names.get(pid)
        return {x for x in aliases.get(pid, set()) if x and x != own}
    na, nb = names.get(a.person_id), names.get(b.person_id)
    ea, eb = non_self(a.person_id), non_self(b.person_id)
    if na and na in eb:
        return True
    if nb and nb in ea:
        return True
    return bool(ea & eb)


def _catalogue_ok(a: Work, b: Work) -> bool:
    if not a.catalogue_key or not b.catalogue_key:
        return True  # sin catálogo no hay conflicto
    return a.catalogue_key == b.catalogue_key


def _present(w: Work, treat_placeholder_as_missing: bool) -> bool:
    if not w.composer_key or not w.person_id:
        return False
    return not (treat_placeholder_as_missing and w.placeholder)


def _mergeable(policy: str, a: Work, b: Work, aliases, merged, names) -> bool:
    if not _catalogue_ok(a, b):
        return False
    if policy == "current":
        return bool(a.composer_key) and a.composer_key == b.composer_key
    if policy in ("A_strict", "P0_block"):
        return bool(a.person_id and b.person_id) and (
            _canonical(a.person_id, merged) == _canonical(b.person_id, merged)
        )
    if policy == "B_tolerant":
        return bool(a.person_id and b.person_id) and _provably_same(a, b, aliases, merged, names)
    if policy == "P1_catalogue":
        if a.composer_key and b.composer_key:
            return _provably_same(a, b, aliases, merged, names)
        return bool(a.catalogue_key) and a.catalogue_key == b.catalogue_key
    if policy == "P2_sin_placeholders":
        if _present(a, True) and _present(b, True):
            return _provably_same(a, b, aliases, merged, names)
        return bool(a.catalogue_key) and a.catalogue_key == b.catalogue_key
    raise ValueError(policy)


class _Find:
    def __init__(self, ids: list[int]) -> None:
        self.parent = {i: i for i in ids}

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        self.parent[rb] = ra
        return True


def _identity(a: Work, b: Work, aliases, merged, names) -> str:
    if not a.composer_key and not b.composer_key:
        return "missing_both"
    if not a.composer_key or not b.composer_key:
        return "missing_one"
    if a.person_id and a.person_id == b.person_id:
        return "same_person"
    if a.composer_key == b.composer_key:
        return "same_name_diff_person"
    if _provably_same(a, b, aliases, merged, names):
        return "alias_variant"
    return "different"


def _decision(policy: str, a: Work, b: Work, aliases, merged, names) -> str:
    if not _catalogue_ok(a, b):
        return "blocked_catalogue"
    return "merge" if _mergeable(policy, a, b, aliases, merged, names) else "no_union"


def run(out_path: Path | None) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    works, aliases, merged, names = _load(conn)
    conn.close()

    buckets: dict[str, list[Work]] = defaultdict(list)
    for work in works.values():
        buckets[work.title_key].append(work)

    groups: dict[str, int] = {p: 0 for p in POLICY_NAMES}
    works_in_pairs = 0
    buckets_multi = 0
    pair_reasons: Counter[str] = Counter()
    blocked: Counter[str] = Counter()
    focus: Counter[str] = Counter()
    new_merges: dict[str, list[tuple[Work, Work]]] = {p: [] for p in POLICY_NAMES}
    pair_samples: list[tuple[Work, Work]] = []

    for _title_key, members in buckets.items():
        if len(members) < 2:
            continue
        buckets_multi += 1
        works_in_pairs += len(members)
        for policy in POLICY_NAMES:
            find = _Find([m.id for m in members])
            for i in range(len(members)):
                for j in range(i + 1, len(members)):
                    a, b = members[i], members[j]
                    if find.find(a.id) == find.find(b.id):
                        continue
                    if _mergeable(policy, a, b, aliases, merged, names):
                        find.union(a.id, b.id)
            roots = {find.find(m.id) for m in members}
            groups[policy] += len(roots)

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                ident = _identity(a, b, aliases, merged, names)
                if not _catalogue_ok(a, b):
                    blocked["catalogue_conflict"] += 1
                elif ident in ("missing_one", "missing_both"):
                    blocked["composer_absent"] += 1
                elif ident == "different":
                    blocked["composer_distinto"] += 1
                current = _mergeable("current", a, b, aliases, merged, names)
                b_merge = _mergeable("B_tolerant", a, b, aliases, merged, names)
                p1_merge = _mergeable("P1_catalogue", a, b, aliases, merged, names)
                p2_merge = _mergeable("P2_sin_placeholders", a, b, aliases, merged, names)
                if a.composer_key and b.composer_key:
                    focus["present_pairs"] += 1
                    for pol in ("current", "A_strict", "B_tolerant"):
                        if _mergeable(pol, a, b, aliases, merged, names):
                            focus[f"present_merge_{pol}"] += 1
                else:
                    focus["missing_pairs"] += 1
                    for pol in ("P0_block", "P1_catalogue", "P2_sin_placeholders"):
                        if _mergeable(pol, a, b, aliases, merged, names):
                            focus[f"missing_merge_{pol}"] += 1
                if current and ident in ("same_person", "same_name_diff_person"):
                    pair_reasons["current_compositor_inequivoco"] += 1
                if not current and b_merge:
                    pair_reasons["B_nuevos_por_alias"] += 1
                if not current and p1_merge and ident in ("missing_one", "missing_both"):
                    pair_reasons["P1_nuevos_por_catalogo"] += 1
                if not current and p2_merge and ident in ("missing_one", "missing_both"):
                    pair_reasons["P2_nuevos_por_catalogo"] += 1
                if (not current and b_merge and ident in ("alias_variant", "same_person")
                        and len(new_merges["B_tolerant"]) < 12):
                    new_merges["B_tolerant"].append((a, b))
                if (not current and p1_merge and ident in ("missing_one", "missing_both")
                        and len(new_merges["P1_catalogue"]) < 12):
                    new_merges["P1_catalogue"].append((a, b))
                if (not current and p2_merge and ident in ("missing_one", "missing_both")
                        and len(new_merges["P2_sin_placeholders"]) < 12):
                    new_merges["P2_sin_placeholders"].append((a, b))
                if len(pair_samples) < 200 and ident in ("different", "alias_variant",
                                                         "same_name_diff_person"):
                    pair_samples.append((a, b))

    lines: list[str] = []
    add = lines.append
    with_composer = sum(1 for w in works.values() if w.composer_key)
    add("# Análisis de identidad de compositor y compositor ausente\n")
    add("Generado por `scripts/analyze_composer_identity.py` (read-only). No modifica el motor.\n")
    add("## Contexto\n")
    add(f"- Obras totales: **{len(works)}**")
    add(f"- Con compositor resuelto (rol 1): **{with_composer}** "
        f"({with_composer * 100 // len(works)}%)")
    add(f"- Sin compositor: **{len(works) - with_composer}**")
    add(f"- Buckets por título normalizado con >1 obra: **{buckets_multi}** "
        f"(obras implicadas: **{works_in_pairs}**)")
    add("\n## Grupos antes / después por política\n")
    add("| Política | Grupos después | Mergers (obras - grupos) | Grupos vs current |")
    add("|---|---|---|---|")
    base = groups["current"]
    for policy in POLICY_NAMES:
        add(f"| {policy} | {groups[policy]} | {works_in_pairs - groups[policy]} | "
            f"{base - groups[policy]:+d} |")
    add("\n## Motivos y bloqueos (pares)\n")
    add("| Métrica | Pares |")
    add("|---|---|")
    for key in ("current_compositor_inequivoco", "B_nuevos_por_alias",
                "P1_nuevos_por_catalogo", "P2_nuevos_por_catalogo",
                "composer_distinto", "composer_absent", "catalogue_conflict"):
        value = pair_reasons.get(key, 0) if key in pair_reasons else blocked.get(key, 0)
        add(f"| {key} | {value} |")

    add("\n## Análisis 1 — compositor presente (pares): current vs A vs B\n")
    add("| Política | Pares fusionados |")
    add("|---|---|")
    add(f"| pares con ambos compositores presentes | {focus['present_pairs']} |")
    for pol in ("current", "A_strict", "B_tolerant"):
        add(f"| {pol} | {focus[f'present_merge_{pol}']} |")

    add("\n## Análisis 2 — compositor ausente (pares): P0 vs P1 vs P2\n")
    add("| Política | Pares fusionados |")
    add("|---|---|")
    add(f"| pares con compositor ausente | {focus['missing_pairs']} |")
    for pol in ("P0_block", "P1_catalogue", "P2_sin_placeholders"):
        add(f"| {pol} | {focus[f'missing_merge_{pol}']} |")

    add("\n## Muestra de mergers nuevos (merge bajo la política, no bajo current)\n")
    for policy in ("B_tolerant", "P1_catalogue", "P2_sin_placeholders"):
        examples = new_merges[policy]
        add(f"\n### {policy} — {len(examples)} ejemplos\n")
        if not examples:
            add("(sin ejemplos)")
            continue
        add("| título | work_a | work_b | compositor_a | compositor_b | id | cat_a | cat_b |")
        add("|---|---|---|---|---|---|---|---|")
        for a, b in examples[:12]:
            ident = _identity(a, b, aliases, merged, names)
            add(f"| {a.title} | {a.id} | {b.id} | {a.composer} | {b.composer} | {ident} | "
                f"{a.catalogue} | {b.catalogue} |")

    add("\n## Muestra `candidate_pair` (decisiones por política)\n")
    add("| título | work_a | work_b | comp_a | comp_b | identidad | cat_a | cat_b | "
        "current | A | B | P1 | P2 |")
    add("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for a, b in pair_samples[:40]:
        ident = _identity(a, b, aliases, merged, names)
        cols = [_decision(p, a, b, aliases, merged, names) for p in POLICY_NAMES]
        add(f"| {a.title} | {a.id} | {b.id} | {a.composer} | {b.composer} | {ident} | "
            f"{a.catalogue} | {b.catalogue} | " + " | ".join(cols) + " |")

    report = "\n".join(lines) + "\n"
    if out_path is not None:
        out_path.write_text(report, encoding="utf-8")
        print(f"informe: {out_path}")
    print(f"obras={len(works)} con_compositor={with_composer} "
          f"buckets={buckets_multi} obras_candidatas={works_in_pairs}")
    for policy in POLICY_NAMES:
        print(f"  {policy:22s} grupos={groups[policy]:6d} "
              f"mergers={works_in_pairs - groups[policy]:6d}")
    print("  pares:", dict(pair_reasons), dict(blocked))
    print("  focus:", dict(focus))


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    run(args.out)


if __name__ == "__main__":
    main()
