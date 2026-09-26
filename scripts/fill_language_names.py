#!/usr/bin/env python
"""Rellena `languages.languages_name` a partir de `languages_code` (BCP-47).

Solo escribe las filas con nombre vacío/NULL (idempotente). Los nombres van en inglés,
coherentes con los ya presentes en la tabla ("Icelandic", "Lithuanian", "Serbian"...).
No toca `languages_code` ni ninguna otra tabla.

Uso (en osap-storage, con su venv):
    .venv\\Scripts\\python.exe scripts/fill_language_names.py --dry-run
    .venv\\Scripts\\python.exe scripts/fill_language_names.py
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from infrastructure.config import Settings
from infrastructure.db.connection import Database

# Código BCP-47 -> nombre. Cubre los 60 códigos que estaban sin nombre.
NAMES: dict[str, str] = {
    "ar": "Arabic",
    "ar_EG": "Arabic (Egypt)",
    "az_Arab": "Azerbaijani (Arabic)",
    "be": "Belarusian",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "cs": "Czech",
    "da_DK": "Danish (Denmark)",
    "de": "German",
    "de_DE": "German (Germany)",
    "el": "Greek",
    "en": "English",
    "en_AU": "English (Australia)",
    "en_PH": "English (Philippines)",
    "en_US": "English (United States)",
    "es": "Spanish",
    "fa": "Persian",
    "fa_IR": "Persian (Iran)",
    "fr": "French",
    "ga": "Irish",
    "gu": "Gujarati",
    "he": "Hebrew",
    "he_IL": "Hebrew (Israel)",
    "hi": "Hindi",
    "hy": "Armenian",
    "is": "Icelandic",
    "it": "Italian",
    "it_IT": "Italian (Italy)",
    "ja": "Japanese",
    "ja_JP": "Japanese (Japan)",
    "ka": "Georgian",
    "km": "Khmer",
    "ko": "Korean",
    "ku": "Kurdish",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "mai": "Maithili",
    "mk": "Macedonian",
    "ml": "Malayalam",
    "nl": "Dutch",
    "pa": "Punjabi",
    "pl": "Polish",
    "pt_BR": "Portuguese (Brazil)",
    "ru": "Russian",
    "ru_RU": "Russian (Russia)",
    "shi_Latn": "Tachelhit (Latin)",
    "sr_Cyrl": "Serbian (Cyrillic)",
    "sr_Cyrl_RS": "Serbian (Cyrillic, Serbia)",
    "sr_Latn_RS": "Serbian (Latin, Serbia)",
    "sv": "Swedish",
    "sv_SE": "Swedish (Sweden)",
    "th": "Thai",
    "uk": "Ukrainian",
    "uk_UA": "Ukrainian (Ukraine)",
    "zh": "Chinese",
    "zh_Hans": "Chinese (Simplified)",
    "zh_Hans_HK": "Chinese (Simplified, Hong Kong)",
    "zh_Hant": "Chinese (Traditional)",
    "zh_Latn": "Chinese (Latin)",
}


async def run(dry_run: bool) -> int:
    db = Database(Settings())  # type: ignore[call-arg]
    async with db.connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT id, languages_code FROM languages "
            "WHERE languages_name IS NULL OR TRIM(languages_name) = ''"
        )
        rows = await cur.fetchall()
    unknown: list[str] = []
    updates: list[tuple[str, int]] = []
    for row in rows:
        code = str(row["languages_code"] or "")
        name = NAMES.get(code)
        if name is None:
            unknown.append(code)
            continue
        updates.append((name, int(row["id"])))
    if not dry_run and updates:
        async with db.transaction() as conn, conn.cursor() as cur:
            for name, lang_id in updates:
                await cur.execute(
                    "UPDATE languages SET languages_name = %s WHERE id = %s", (name, lang_id)
                )
    print(
        f"sin nombre: {len(rows)} | rellenados: {len(updates)} | sin mapear: {len(unknown)}"
    )
    if unknown:
        print("  sin mapear:", unknown)
    await db.close()
    return len(updates)


def main() -> int:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    return asyncio.run(run(args.dry_run))


if __name__ == "__main__":
    sys.exit(main())
