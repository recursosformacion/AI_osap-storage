"""Dry-run (read-only) de derivación de URLs CPDL para `works_resources`.

Genera `Special:FilePath/<name>` URL-encoded para los recursos CPDL, valida localmente y comprueba
una muestra REAL contra CPDL (incluyendo espacios, paréntesis y acentos). No escribe ni descarga.

    .venv\\Scripts\\python.exe scripts/derive_cpdl_urls.py
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pymysql  # noqa: E402
import yaml  # noqa: E402

BASE = "https://www.cpdl.org/wiki/index.php/Special:FilePath/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) osap-migration/1.0"


def derive(name: str) -> str:
    return BASE + urllib.parse.quote(name, safe="")


def run(out_csv: Path, out_md: Path, check: bool, sample: int) -> None:
    with open(ROOT / "config.yaml", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)["db"]
    conn = pymysql.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                           password=cfg["password"], database=cfg["name"], charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT r.id, r.works_resources_name n, r.works_resources_type t "
            "FROM works_resources r JOIN representations rep "
            "ON rep.id = r.works_resources_representation_id "
            "WHERE rep.representations_origin='cpdl'")
        rows = cur.fetchall()
    conn.close()

    stats = Counter()
    special = {"con_espacio": 0, "con_parentesis": 0, "con_acento": 0, "con_apostrofo": 0,
               "no_ascii": 0}
    urls = Counter()
    with open(out_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["resource_id", "name", "type", "url"])
        for r in rows:
            stats["total"] += 1
            name = r["n"] or ""
            if not name:
                stats["sin_nombre"] += 1
                continue
            if "." in name:
                stats["con_extension"] += 1
            if " " in name:
                special["con_espacio"] += 1
            if "(" in name or ")" in name:
                special["con_parentesis"] += 1
            if "'" in name:
                special["con_apostrofo"] += 1
            if any(ord(c) > 127 for c in name):
                special["no_ascii"] += 1
            if any(c in "áéíóúàèìòùâêîôûäëïöüñçÁÉÍÓÚÑÇ" for c in name):
                special["con_acento"] += 1
            url = derive(name)
            urls[url] += 1
            writer.writerow([r["id"], name, r["t"], url])
    stats["urls_distintas"] = len(urls)
    stats["urls_duplicadas"] = sum(1 for v in urls.values() if v > 1)

    # muestra real
    checks = []
    if check:
        picks: list[str] = []
        wanted = (" ", "(", ")", "'")
        for want in wanted:
            picks += [r["n"] for r in rows if r["n"] and want in r["n"]][:3]
        picks += [r["n"] for r in rows if r["n"] and any(ord(c) > 127 for c in r["n"])][:3]
        picks += [r["n"] for r in rows if r["n"] and "." in r["n"]][:3]
        seen = set()
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        for name in picks:
            if name in seen:
                continue
            seen.add(name)
            if len(seen) > sample:
                break
            req = urllib.request.Request(derive(name), headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                    checks.append((name, resp.status, resp.geturl()))
            except urllib.error.HTTPError as exc:
                checks.append((name, exc.code, ""))
            except Exception as exc:  # noqa: BLE001
                checks.append((name, "ERR", str(exc)[:80]))

    lines = ["# Dry-run: derivación de URLs CPDL (read-only)\n",
             f"- Recursos CPDL: **{stats['total']}** · con nombre: {stats['total'] - stats['sin_nombre']} "
             f"· con extensión: {stats['con_extension']}",
             f"- URLs distintas: {stats['urls_distintas']} · duplicadas: {stats['urls_duplicadas']}",
             f"- Nombres especiales: {dict(special)}\n"]
    if checks:
        ok = sum(1 for _, s, _ in checks if s in (200, 301, 302, 303, 307, 308))
        lines += [f"## Verificación real contra CPDL ({ok}/{len(checks)} resueltos)\n",
                  "| nombre | status | destino |", "|---|---|---|"]
        for name, status, dest in checks:
            lines.append(f"| `{name}` | {status} | {dest[:90]} |")
    else:
        lines.append("\n(verificación real no ejecutada o sin red)")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("recursos CPDL:", stats["total"], "| URLs distintas:", stats["urls_distintas"],
          "| especiales:", dict(special))
    if checks:
        ok = sum(1 for _, s, _ in checks if s in (200, 301, 302, 303, 307, 308))
        print(f"verificación real: {ok}/{len(checks)} resueltos")
        for name, status, _dest in checks[:12]:
            print(f"  {status}  {name}")
    print("csv:", out_csv, "| informe:", out_md)


def main() -> None:
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, default=Path(r"G:\rism\cpdl_url_derivation.csv"))
    ap.add_argument("--md", type=Path, default=ROOT / "docsNew" / "dry-run-cpdl-urls.md")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--sample", type=int, default=15)
    args = ap.parse_args()
    run(args.csv, args.md, not args.no_check, args.sample)


if __name__ == "__main__":
    main()
