"""Corrige los roles de autoría de una obra leyendo el MusicXML de su recurso.

Los registros con varios nombres pegados (`: Hans Sitt (1850-1922) Paul Klengel (1854-1935)`)
suelen ser **arreglistas/intérpretes/editores** de una obra de otro compositor. El MusicXML trae
`<creator type="...">`, así que este script:

1. lee `<creator type="composer|arranger|editor|lyricist|performer">`,
2. limpia el nombre (años, instrumentos, `door …`) y descarta textos que no son nombres,
3. resuelve la persona existente (nombre normalizado, apellido+año, apellido+iniciales),
   creándola solo si no existe,
4. **deja el compositor en el rol 1** y a los demás con SU rol (3 arreglista, 6 editor,
   10 intérprete, 2 letrista):
   - compositores que falten -> se añaden al rol 1,
   - un rol 1 revisado (p. ej. Bach) **se conserva**,
   - el rol 1 basura (`not_reviewed_2/3`) -> se **re-asigna** a su rol real si el XML lo nombra,
     o se desvincula.

    .venv\\Scripts\\python.exe scripts/fix_person_from_score.py --work-id 192729 --work-id 153478
    .venv\\Scripts\\python.exe scripts/fix_person_from_score.py --person-like 'Ferdinand David'
    .venv\\Scripts\\python.exe scripts/fix_person_from_score.py --work-id 192729 --apply
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import unicodedata
import uuid
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import requests  # noqa: E402
import yaml  # noqa: E402

_UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "*/*",
}
_ANON = re.compile(r"(?i)anonym|unknown|traditional|trad\.|unattributed|desconocido")
_YEARS = re.compile(r"[([]\s*(\d{3,4})\s*[-–—/]?\s*(\d{3,4})?\s*[)\]]")
_LABEL = re.compile(r"(?i)^\(?\s*(?:attributed to|atribuida a|by|door|de)\s*\)?\s*[:.-]?\s*")
_INSTR = re.compile(
    r"(?i)[,\s]+(violin|viola|violoncello|cello|piano|klavier|flute|flöte|oboe|clarinet|"
    r"harpsichord|cembalo|organ|soprano|alto|tenor|bass|voice|gesang|continuo)\b.*$"
)
_INSTR_ONLY = re.compile(
    r"(?i)^(violin|viola|cello|piano|flute|oboe|clarinet|organ|soprano|alto|tenor|bass|"
    r"voice|continuo|klavier|harpsichord)s?$"
)
_NOT_A_NAME = re.compile(
    r"(?i)\b(bwv|hwv|kv|opus|sonata|suite|concerto|symphony|handschrift|bibliotheek|"
    r"geschreven|serie|ausgabe|transcription|transcript|arrangement|instrumentalmusik|"
    r"orchestermusik|kammer)\b|\bin [a-g] (major|minor)\b"
)
_DOOR = re.compile(
    r"(?i)\b(?:geschreven\s+door|door|by|von)\s+"
    r"([A-ZÀ-Þ][\w'’.\-]+(?:\s+[A-ZÀ-Þ][\w'’.\-]+){0,3})"
)
_ROLE_BY_TYPE = {
    "composer": 1, "lyricist": 2, "poet": 2, "arranger": 3, "orchestrator": 4,
    "transcriber": 5, "editor": 6, "performer": 10,
}
_ROLE_NAME = {1: "Compositor/a", 2: "Letrista", 3: "Arreglista", 6: "Editor/a", 10: "Intérprete"}


def _db() -> dict:
    with open(ROOT / "config.yaml", encoding="utf-8") as handle:
        conf = (yaml.safe_load(handle) or {}).get("db") or {}
    return {
        "host": conf.get("host", "127.0.0.1"),
        "port": int(conf.get("port", 3306)),
        "user": conf.get("user"),
        "password": conf.get("password"),
        "database": conf.get("name") or conf.get("database"),
    }


def _norm(text: str) -> str:
    flat = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", flat)).strip()


def _clean_person(raw: str) -> tuple[str, str]:
    """Devuelve (nombre, año). Vacío si el texto no es un nombre de persona."""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw or "")).strip()
    door = list(_DOOR.finditer(text))
    if door:
        text = door[-1].group(1)
    text = _LABEL.sub("", text)
    text = _INSTR.sub("", text).strip(" ,;/")
    year = ""
    match = _YEARS.search(text)
    if match:
        year = match.group(1)
        text = (text[: match.start()] + " " + text[match.end() :]).strip(" ,;/")
    text = re.sub(r"\s+", " ", text).strip(" ,;/.")
    if not text or _ANON.search(text) or _NOT_A_NAME.search(text) or _INSTR_ONLY.match(text):
        return "", ""
    if text[0].islower():
        return "", ""
    tokens = re.findall(r"[^\W\d_][\w'’.\-]*", text, re.UNICODE)
    if not 1 <= len(tokens) <= 5:
        return "", ""
    return text, year


def _xml_of(file_id: int) -> str:
    resp = requests.get(f"http://127.0.0.1:8000/api/download/{file_id}", headers=_UA, timeout=60)
    if resp.status_code != 200 or resp.content[:2] != b"PK":
        return ""
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml") and "META-INF" not in n]
        return zf.read(names[0]).decode("utf-8", "replace") if names else ""


class People:
    def __init__(self, rows: list[dict]) -> None:
        self.by_name: dict[str, str] = {}
        self.by_surname_year: dict[tuple[str, str], str] = {}
        self.by_surname: dict[str, list[dict]] = {}
        for row in rows:
            norm = _norm(str(row["persons_name"] or ""))
            self.by_name.setdefault(norm, str(row["persons_id"]))
            tokens = norm.split()
            if tokens:
                self.by_surname.setdefault(tokens[-1], []).append(row)
                year = str(row["persons_birth_year"] or "")
                if year:
                    self.by_surname_year.setdefault((tokens[-1], year), str(row["persons_id"]))

    def find(self, name: str, year: str = "") -> tuple[str | None, str]:
        norm = _norm(name)
        if norm in self.by_name:
            return self.by_name[norm], "nombre"
        tokens = norm.split()
        if len(tokens) >= 2:
            surname, given = tokens[-1], tokens[0]
            if year and (surname, year) in self.by_surname_year:
                return self.by_surname_year[(surname, year)], "apellido+año"
            for row in self.by_surname.get(surname, []):
                if str(row.get("persons_review_status") or "") not in ("reviewed", "correct"):
                    continue
                existing = _norm(str(row["persons_name"] or "")).split()
                if len(existing) < 2 or len(set(existing)) != len(existing):
                    continue
                if existing[0].startswith(given) or given.startswith(existing[0]):
                    return str(row["persons_id"]), "apellido+nombre"
        return None, ""


def _reuse_role1(cur1: dict[str, dict], name: str, year: str) -> tuple[str | None, str]:
    """Si la obra ya tiene un rol 1 equivalente (mismo apellido/iniciales), reutilizarlo."""
    tokens = _norm(name).split()
    if not tokens:
        return None, ""
    surname = tokens[-1]
    for pid, row in cur1.items():
        existing = _norm(str(row["persons_name"] or "")).split()
        if len(existing) < 2 or existing[-1] != surname:
            continue
        year_existing = str(row.get("persons_birth_year") or "")
        if year and year_existing and year == year_existing:
            return pid, "rol 1 existente (mismo apellido+año)"
        if existing[0].startswith(tokens[0]) or tokens[0].startswith(existing[0]):
            return pid, "rol 1 existente (mismo apellido+nombre)"
    return None, ""


def _composer_from_title(title: str) -> str:
    head = re.split(r"[_–—-]", str(title or ""))[0].strip()
    return head if re.search(r"(?i)\b[A-Z][a-zà-ÿ]+\s+[A-Z]\.", head) else ""


def _creators(xml: str) -> list[tuple[str, str]]:
    found = re.findall(r'<creator[^>]*type="([^"]+)"[^>]*>(.*?)</creator>', xml, re.S)
    if not found:
        found = [("composer", c) for c in re.findall(r"<creator[^>]*>(.*?)</creator>", xml, re.S)]
    return [(t.strip().lower(), re.sub(r"\s+", " ", c).strip()) for t, c in found]


def _plan(creators: list[tuple[str, str]]) -> list[tuple[int, str, str]]:
    """[(role_id, nombre, año)] deducido del XML."""
    out: list[tuple[int, str, str]] = []
    for raw_type, raw_text in creators:
        role = _ROLE_BY_TYPE.get(raw_type)
        if not role:
            continue
        pieces = [p for p in re.split(r",|/|\band\b|\by\b|\bund\b", raw_text)]
        cleaned = [_clean_person(p) for p in pieces]
        cleaned = [c for c in cleaned if c[0]]
        if len(cleaned) == 2 and not any(year for _, year in cleaned) and all(
                len(name.split()) <= 2 for name, _ in cleaned):
            # "Apellido, Nombre" -> una sola persona
            whole = _clean_person(raw_text.replace(",", " "))
            if whole[0]:
                out.append((role, whole[0], whole[1]))
                continue
        if len(cleaned) >= 2:
            out.extend((role, name, year) for name, year in cleaned)
            continue
        whole = _clean_person(raw_text)
        if whole[0]:
            out.append((role, whole[0], whole[1]))
    return out


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-id", type=int, action="append", default=[])
    parser.add_argument("--person-like", default=None)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    conn = pymysql.connect(**_db(), charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor,
                           autocommit=True)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT persons_id, persons_name, persons_birth_year, persons_review_status FROM persons")
            people = People(cur.fetchall())

            if args.work_id:
                marks = ",".join(["%s"] * len(args.work_id))
                cur.execute(
                    "SELECT id AS work_id, works_title AS work_title FROM works"
                    f" WHERE id IN ({marks}) ORDER BY id",
                    args.work_id,
                )
            else:
                where = ["r.works_person_roles_role_id = 1",
                         "p.persons_review_status IN ('not_reviewed_2','not_reviewed_3')"]
                params: list[object] = []
                if args.person_like:
                    where.append("p.persons_name LIKE %s")
                    params.append(f"%{args.person_like}%")
                cur.execute(
                    "SELECT DISTINCT w.id AS work_id, w.works_title AS work_title FROM works w"
                    " JOIN works_person_roles r ON r.works_person_roles_work_id=w.id"
                    " JOIN persons p ON p.persons_id=r.works_person_roles_person_id"
                    f" WHERE {' AND '.join(where)} ORDER BY w.id LIMIT {int(args.limit)}",
                    params,
                )
            works = cur.fetchall()

            for work in works:
                wid = int(work["work_id"])
                print(f"obra {wid}  {str(work['work_title'])[:52]!r}")
                cur.execute(
                    "SELECT r.works_person_roles_role_id AS role_id, r.works_person_roles_person_id"
                    " AS person_id, p.persons_name, p.persons_review_status, p.persons_birth_year"
                    " FROM works_person_roles r"
                    " JOIN persons p ON p.persons_id=r.works_person_roles_person_id"
                    " WHERE r.works_person_roles_work_id=%s",
                    (wid,),
                )
                current = cur.fetchall()
                cur1 = {str(c["person_id"]): c for c in current if int(c["role_id"]) == 1}
                print("   rol 1 actual: " + " | ".join(
                    f"{c['persons_name'][:38]}[{c['persons_review_status']}]" for c in cur1.values()))
                cur.execute(
                    "SELECT works_resources_file_id AS file_id FROM works_resources"
                    " WHERE works_resources_work_id=%s LIMIT 1",
                    (wid,),
                )
                res = cur.fetchone()
                if not res or not res["file_id"]:
                    print("   sin recurso MXL -> se omite")
                    continue
                plan = _plan(_creators(_xml_of(int(res["file_id"]))))
                if not plan:
                    guess = _composer_from_title(str(work["work_title"]))
                    if guess:
                        name, year = _clean_person(guess)
                        if name:
                            plan = [(1, name, year)]
                if not plan:
                    print("   XML sin nombres utilizables -> no se toca")
                    continue
                for role, name, year in plan:
                    pid, via = people.find(name, year)
                    if role == 1:
                        reuse, note = _reuse_role1(cur1, name, year)
                        if reuse:
                            pid, via = reuse, note
                    print(f"   -> rol {role} ({_ROLE_NAME.get(role, role)}): {name!r} {year}"
                          f" = {pid or 'CREAR'}{' [' + via + ']' if via else ''}")

                if not args.apply:
                    continue

                resolved: list[tuple[int, str, str]] = []
                for role, name, year in plan:
                    pid, _ = people.find(name, year)
                    if role == 1:
                        reuse, _note = _reuse_role1(cur1, name, year)
                        if reuse:
                            pid = reuse
                    if not pid:
                        pid = str(uuid.uuid4())
                        cur.execute(
                            "INSERT INTO persons (persons_id, persons_name, persons_visible,"
                            " persons_birth_year, persons_status, persons_review_status,"
                            " persons_source_system) VALUES (%s,%s,1,%s,'active','reviewed','score')",
                            (pid, name, year or None),
                        )
                        people.by_name[_norm(name)] = pid
                        print(f"   + persona creada {name!r}")
                    resolved.append((role, pid, name))
                by_person: dict[str, set[int]] = {}
                for c in current:
                    by_person.setdefault(str(c["person_id"]), set()).add(int(c["role_id"]))
                for role, pid, name in resolved:
                    roles_of = by_person.get(pid, set())
                    if role in roles_of:
                        continue
                    if role != 1 and roles_of == {1}:
                        cur.execute(
                            "UPDATE works_person_roles SET works_person_roles_role_id=%s"
                            " WHERE works_person_roles_work_id=%s AND works_person_roles_person_id=%s",
                            (role, wid, pid),
                        )
                        print(f"   ~ rol 1 -> {role} ({name!r})")
                        continue
                    cur.execute(
                        "INSERT INTO works_person_roles (works_person_roles_work_id,"
                        " works_person_roles_person_id, works_person_roles_role_id)"
                        " VALUES (%s,%s,%s)",
                        (wid, pid, role),
                    )
                    print(f"   + rol {role} ({name!r})")
                keep = {pid for _, pid, _ in resolved}
                for pid, row in cur1.items():
                    if pid in keep:
                        continue
                    if str(row["persons_review_status"]) in ("not_reviewed_2", "not_reviewed_3"):
                        cur.execute(
                            "DELETE FROM works_person_roles WHERE works_person_roles_work_id=%s"
                            " AND works_person_roles_person_id=%s AND works_person_roles_role_id=1",
                            (wid, pid),
                        )
                        print(f"   - rol 1 basura desvinculado: {row['persons_name'][:40]!r}")
        if not args.apply:
            print("DRY-RUN: usa --apply para escribir.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
