"""Bucle de enriquecimiento IA en producción para personas y obras.

Lee las claves de `secrets/gemini.prod.key`, ejecuta los runners existentes de una
en una lote, aplica inmediatamente las respuestas a la BD de producción y, si la
API rechaza las claves o se agota la cuota, espera `--pause-hours` (24 h por
defecto) antes de reintentar el mismo lote.

Uso:
    .venv/bin/python scripts/ai_enrich_prod.py --once
    .venv/bin/python scripts/ai_enrich_prod.py
    .venv/bin/python scripts/ai_enrich_prod.py --persons-start 1477 --works-start 722
"""

from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCRIPTS = ROOT / "scripts"
KEY_FILE = ROOT / "secrets" / "gemini.prod.key"
LOG = DATA / "ai_enrich_prod.log"
LOCK = DATA / "ai_enrich_prod.lock"


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def keys() -> list[str]:
    found: list[str] = []
    if KEY_FILE.exists():
        for line in KEY_FILE.read_text(encoding="utf-8").splitlines():
            value = line.split("=", 1)[-1].strip() if "=" in line else line.strip()
            if value and value not in found:
                found.append(value)
    return found


def run(args: list[str], env: dict[str, str]) -> int:
    log("ejecutando: " + " ".join(args))
    try:
        result = subprocess.run(args, cwd=ROOT, env=env, text=True)
    except Exception as exc:  # noqa: BLE001
        log(f"error lanzando {args[0]}: {exc}")
        return 1
    log(f"salida: {result.returncode}")
    return result.returncode


def apply_persons(env: dict[str, str]) -> int:
    return run(
        [
            sys.executable,
            str(SCRIPTS / "apply_persons_ai_json.py"),
            "--dirs",
            str(DATA / "ai_out"),
            "--apply",
            "--allow-prod",
        ],
        env,
    )


def apply_works(env: dict[str, str]) -> int:
    return run(
        [
            sys.executable,
            str(SCRIPTS / "apply_works_ai_json.py"),
            "--dir",
            str(DATA / "works_ai_out"),
            "--apply",
            "--allow-prod",
        ],
        env,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persons-start", type=int, default=0)
    parser.add_argument("--works-start", type=int, default=0)
    parser.add_argument("--pause-hours", type=float, default=24.0)
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--once", action="store_true", help="procesa un lote de cada tipo y sale")
    args = parser.parse_args()

    available = keys()
    if not available:
        log("ERROR: no hay claves en secrets/gemini.prod.key")
        return 2
    env = os.environ.copy()
    env["GEMINI_API_KEYS"] = ",".join(available)

    DATA.mkdir(parents=True, exist_ok=True)
    lock = LOCK.open("w", encoding="utf-8")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("ya hay otro proceso de enriquecimiento activo")
        return 3

    def first_pending_person() -> int:
        n = 1
        while n <= 100000:
            name = f"json_personas_lote_{n:03d}.json"
            if (DATA / name).exists() and not (DATA / "ai_out" / name).exists():
                return n
            n += 1
        return n

    def first_pending_work() -> int:
        n = 1
        while n <= 1000000:
            if not (DATA / "works_ai_out" / f"json_works_lote_{n:05d}.json").exists():
                return n
            n += 1
        return n

    persons_n = args.persons_start or first_pending_person()
    works_n = args.works_start or first_pending_work()
    persons_done = works_done = False

    while True:
        changed = False
        if not persons_done:
            source = DATA / f"json_personas_lote_{persons_n:03d}.json"
            target = DATA / "ai_out" / source.name
            if source.exists():
                if target.exists():
                    log(f"personas {persons_n:03d}: ya existe; se omite")
                    persons_n += 1
                    changed = True
                    continue
                else:
                    rc = run(
                        [
                            sys.executable,
                            str(SCRIPTS / "persons_ai_runner.py"),
                            "--start", str(persons_n),
                            "--limit", "1",
                            "--sleep", str(args.sleep),
                        ],
                        env,
                    )
                    if rc != 0:
                        log(f"personas {persons_n:03d}: fallo de cuota/API; pausa {args.pause_hours} h")
                        time.sleep(max(60.0, args.pause_hours * 3600))
                        continue
                    changed = True
                rc = apply_persons(env)
                if rc != 0:
                    log("aplicación de personas falló; pausa")
                    time.sleep(max(60.0, args.pause_hours * 3600))
                    continue
                persons_n += 1
                changed = True
            else:
                persons_done = True

        if not works_done:
            target = DATA / "works_ai_out" / f"json_works_lote_{works_n:05d}.json"
            if target.exists():
                log(f"obras {works_n:05d}: ya existe; se omite")
                works_n += 1
                changed = True
                continue
            else:
                rc = run(
                    [
                        sys.executable,
                        str(SCRIPTS / "works_ai_runner.py"),
                        "--start", str(works_n),
                        "--limit", "1",
                        "--sleep", str(args.sleep),
                    ],
                    env,
                )
                if rc != 0:
                    log(f"obras {works_n:05d}: fallo de cuota/API; pausa {args.pause_hours} h")
                    time.sleep(max(60.0, args.pause_hours * 3600))
                    continue
                if not target.exists():
                    log("obras: no quedan lotes por generar")
                    works_done = True
                    if persons_done:
                        break
                    continue
                changed = True
            rc = apply_works(env)
            if rc != 0:
                log("aplicación de obras falló; pausa")
                time.sleep(max(60.0, args.pause_hours * 3600))
                continue
            works_n += 1
            changed = True

        if args.once and changed:
            break
        if persons_done and works_done:
            log("sin más lotes; proceso terminado")
            break
        if not changed:
            log("sin progreso; pausa para evitar bucle")
            time.sleep(max(60.0, args.pause_hours * 3600))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


