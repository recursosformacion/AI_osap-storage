"""
Auditoria y canonicalizacion de la tabla `ensembles` (BD osap-storage, SOLO LECTURA).

Reglas implementadas (enunciado de la tarea):
  a) mayusculas + limpieza de espacios/caracteres de control
  b) normalizacion de notacion de voces (BAR/BARB/BRB/BARITONE -> B ; MEZZO/MZ -> A ;
     SOPRANO/ALTO/TENOR/BASS -> S/A/T/B)
  c) modificadores de ejecucion ignorados (SOLO, SOLI, CHOIR, VERSE, A CAPPELLA, ...)
  d) firma canonica = frecuencias de voz en el orden S -> A -> T -> B -> C
  e) codigos no vocales (transposicion, claves, textos incompletos) -> INVALID_OR_INSTRUMENTAL

Salidas (todas dentro de _externo/):
  resultado.md            tabla Markdown exigida (3 columnas)
  auditoria_detalle.csv   traza completa de auditoria (diagnostico adicional)
  INFORME.md              nota metodologica

La conexion es estrictamente de lectura: solo se ejecutan SELECT.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

import pymysql
import yaml

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
INVALID = "INVALID_OR_INSTRUMENTAL"
VOICE_ORDER = ("S", "A", "T", "B", "C")

# --------------------------------------------------------------------------
# 1. Lexicon
# --------------------------------------------------------------------------

# b) Sustituciones de notacion dentro de un mismo token (pegado: SATBARB, SMZATB...)
SUBSTRING_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"MEZZOSOPRANOS?"), "A"),
    (re.compile(r"BARITON[EO]?S?"), "B"),
    (re.compile(r"BARYTON[EO]?S?"), "B"),
    (re.compile(r"BARBAR"), "BB"),
    (re.compile(r"BRBAR"), "BB"),
    (re.compile(r"BARB"), "B"),
    (re.compile(r"BRB"), "B"),
    (re.compile(r"BAR"), "B"),
    (re.compile(r"MEZZO"), "A"),
    (re.compile(r"MEZ"), "A"),
    (re.compile(r"MZ"), "A"),
]

# b) Palabras de voz completas -> iniciales (token exacto)
WORD_MAP: dict[str, str] = {
    # soprano
    "SOPRANO": "S", "SOPRANOS": "S", "SOPRAN": "S", "SOP": "S",
    "SOPRANIST": "S", "SOPRANISTS": "S", "SOPRANISTA": "S", "SUPERANUS": "S",
    # alto / mezzo
    "ALTO": "A", "ALTI": "A", "ALTS": "A", "MEZZO": "A", "MEZZOS": "A",
    "MEZ": "A", "MZ": "A", "MEZZA": "A", "MEDIUS": "A",
    # tenor
    "TENOR": "T", "TENORS": "T", "TENORE": "T", "TENORIS": "T",
    "TENORIST": "T", "TENORISTS": "T", "TINN": "T",
    # bajo / baritono
    "BASS": "B", "BASSES": "B", "BASSO": "B", "BASSI": "B", "BASSUS": "B",
    "BASSUSES": "B", "BARITONE": "B", "BARITON": "B", "BARITONO": "B",
    "BARITONES": "B", "BARYTON": "B", "BARB": "B", "BAR": "B",
    # contratenor / contralto: categoria C del orden canonico (se anade a S,A,T,B)
    "CONTRA": "C", "CONTRALT": "C", "CONTRALTO": "C", "CONTRALTIST": "C",
    "COUNTERTENOR": "C", "COUNTERTENEUR": "C", "CTR": "CT",
}

# c) Modificadores de ejecucion: permiten que una letra suelta sea voz
QUALIFIERS = {
    "SOLO", "SOLOS", "SOLOIST", "SOLOISTS", "SOLISTA", "SOLISTAS", "SOLIST",
    "SOLI", "SOLE", "VERSE", "VERSES", "CHORUS", "CHOIR", "CHOIRS", "CHORAL",
    "DUET", "DUETS", "DUO", "DUOS", "TRIO", "TRIOS", "QUARTET", "QUARTETS",
    "OCTET", "UNISON", "UNISONO", "DIV", "DIVI", "DIVISI", "DIVISIONS",
    "DIVISION", "DIVISI", "DIVSI", "DIVIDES", "SPLITTING", "PARTS", "PART",
    "ANTI", "ANTIPHONAL", "ANTIPHONALLY", "RIPIENI", "RIPIENO", "RECIT",
    "COLLATO", "SING", "SINGS", "SINGING", "FULL", "PLAIN", "REDUCED",
    "SECTION", "SECTIONS", "DESCANT", "DESCANTS", "FOLD", "MEZZO",
}

# Palabras funcionales: si son el unico contenido restante, la letra suelta es voz
FUNCTION_WORDS = {
    "AND", "OR", "WITH", "IN", "OF", "FOR", "THE", "TO", "IS", "ARE", "WAS",
    "PLUS", "ALSO", "NOT", "UNLESS", "OTHERWISE", "AS", "IF", "THEN", "ONLY",
    "BOTH", "SAME", "SUCH", "THAN", "THAT", "THIS", "THESE", "THOSE",
}

# Antecedentes que invalidan una letra suelta ("each of S" -> no es un soprano)
SUPPRESSORS = {"OF", "EACH", "EVERY", "ONE", "TWO", "THREE", "SOME", "LOWEST",
               "HIGHEST", "ONLY", "PART"}

# Conectores explicitos entre grupos de voces
CONNECTOR_WORDS = {"AND", "OR", "Y", "E"}
CONNECTOR_CHARS = "&+/.,"

# Tokens que solo usan letras SATBC pero NO son voces ("AS"=preposicion inglesa)
SKIP_TOKENS = {"AS"}
# Fragmentos de clave/altura sin valor de conjunto vocal
FORCE_INVALID_TOKENS = {"BC"}

# Notacion pegada con un prefijo alfabetico no resolved: se conserva solo el
# grupo de voces inequivoco (queda registrado en la traza de auditoria).
GLUED_OVERRIDES = {"DDATB": "ATB", "CAQATB": "ATB"}

# Interpretaciones curadas sobre el codigo completo (a partir de su glosa).
CODE_OVERRIDES = {
    # "CT2 are sopranist and alto" -> 2 contratenores + sopranista + alto
    "CT2 ARE SOPRANIST AND ALTO": "SACC",
}

# c) Modificadores plurifrasicos: se eliminan antes de tokenizar
PHRASE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bA[\s_\-]*CAPP[A-Z]*\b"), " "),        # a cappella, a capp.
    (re.compile(r"\bA[\s_\-]*CAPELL?[A-Z]*\b"), " "),    # a capella
    (re.compile(r"\bSEMI[\s_\-]*CHOR(US|E|USES)\b"), " "),
    (re.compile(r"\bCOUNTER[\s_\-]*TENORS?\b"), "CT"),
    # "mezzi-soprano" es UNA voz: la regla b) la equipara al alto
    (re.compile(r"\bMEZZO[\s_\-]*SOPRANOS?\b"), "A"),
    (re.compile(r"\bSOP[\s_\-]*TENORS?\b"), "ST"),
]

DASHES = {"\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212", "_"}
QUOTES = {"\u2018", "\u2019", "\u201c", "\u201d", "\u00ab", "\u00bb", "\u00b7",
          "\u00d7", "\u2026"}
# Nota musical: letra + prima de octava (C', A', D', F', G' ...)
NOTE_PAIR = re.compile(r"(?<![A-Z])'?[A-G]'?\s*-\s*'?[A-G]'?(?![A-Z])")
# Nota/ambitus suelto: C2, C3, C4, F3, F4, C' ...
NOTE_ALONE = re.compile(r"^\s*'?[A-G]'?[0-9]+\s*$")


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def clean(raw: str) -> str:
    """a) Normalizacion tipografica: mayusculas, sin controles, espacios colapsados."""
    text = unicodedata.normalize("NFC", raw).upper()
    text = "".join("-" if ch in DASHES else ch for ch in text)
    text = "".join("'" if ch in QUOTES else ch for ch in text)
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    text = strip_accents(text)
    text = text.replace("'", "")  # la prima se conserva solo para la deteccion e)
    return re.sub(r"\s+", " ", text).strip()


def apply_phrases(text: str) -> str:
    for pattern, replacement in PHRASE_RULES:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


TOKEN_RE = re.compile(r"[A-Z]+|[0-9]+")
TRAILING_NUMBER = re.compile(r"([A-Z]+)([0-9]+)")
NUMBER_WORDS = {
    "TWO": 2, "THREE": 3, "FOUR": 4, "FIVE": 5, "SIX": 6, "SEVEN": 7,
    "EIGHT": 8, "NINE": 9, "TEN": 10, "ELEVEN": 11, "TWELVE": 12,
}


def tokenize(text: str) -> list[tuple[str, str]]:
    """Devuelve [(token, separador_previo)]; los digitos se conservan."""
    tokens: list[tuple[str, str]] = []
    pos = 0
    for match in TOKEN_RE.finditer(text):
        tokens.append((match.group(0), text[pos:match.start()]))
        pos = match.end()
    return tokens


def split_multiplier(token: str) -> tuple[str, int]:
    """'CT2' -> ('CT', 2); 'CA5A6TB' -> ('CAATB', 1)."""
    match = TRAILING_NUMBER.fullmatch(token)
    if match:
        factor = int(match.group(2))
        return match.group(1), min(factor, 20)
    return re.sub(r"[0-9]+", "", token), 1


def expand_token(token: str) -> str:
    for pattern, replacement in SUBSTRING_RULES:
        token = pattern.sub(replacement, token)
    return token


def voice_counts(text: str) -> Counter:
    return Counter(ch for ch in text if ch in VOICE_ORDER)


def classify(token: str) -> tuple[Counter | None, str | None, str]:
    """Clasifica un token. Devuelve (recuento, tipo, letra_aislada)."""
    if token in GLUED_OVERRIDES:
        return voice_counts(GLUED_OVERRIDES[token]), "OVERRIDE", ""
    expanded = expand_token(token)
    if expanded in WORD_MAP:
        return Counter(WORD_MAP[expanded]), "WORD", ""
    if len(expanded) > 1 and set(expanded) <= set(VOICE_ORDER):
        return voice_counts(expanded), "RUN", ""
    stripped = "".join(ch for ch in expanded if ch not in "MR")
    if stripped != expanded:
        if stripped in WORD_MAP:
            return Counter(WORD_MAP[stripped]), "WORD", ""
        if len(stripped) > 1 and set(stripped) <= set(VOICE_ORDER):
            return voice_counts(stripped), "PREFIX", ""
    if len(expanded) == 1 and expanded in VOICE_ORDER:
        return Counter(expanded), "LONE", expanded
    return None, None, ""


def family_label(counts: Counter) -> str:
    n_s, n_a, n_b, n_c = counts["S"], counts["A"], counts["B"], counts["C"]
    if n_s and n_b:
        return "MIXED_CT" if n_c else "MIXED"
    if n_s:
        return "FEMALE"
    if n_b and n_a:
        return "ALT_MALE"
    if n_b:
        return "MALE_CT" if n_c else "MALE"
    if n_a:
        return "INNER_CT" if n_c else "INNER"
    if n_c:
        return "COUNTERTENOR"
    return "TENOR"


def canonicalize(raw: str) -> dict:
    text = clean(raw)
    notes: list[str] = []
    invalid = False

    override = CODE_OVERRIDES.get(text)
    if override:
        counts = voice_counts(override)
        ordered = "".join(v * counts[v] for v in VOICE_ORDER)
        return {
            "id_canonico": ordered,
            "counts": counts,
            "counts_txt": "".join(f"{v}{counts[v]}" for v in VOICE_ORDER if counts[v]),
            "family": f"{ordered}_{family_label(counts)}_{sum(counts.values())}V",
            "total": sum(counts.values()),
            "notas": f"REGLA_CURADA:{text}->{override}",
        }

    # e) Deteccion de notacion de transposicion / claves sobre el texto original
    if NOTE_PAIR.search(text):
        notes.append("TRANSPOSICION_PAR_DE_NOTAS")
        invalid = True
    if NOTE_ALONE.match(text):
        notes.append("NOTA_AMBITO_SUELTA")
        invalid = True

    body = apply_phrases(text)
    if body != text:
        notes.append("MODIFICADOR_ELIMINADO")

    tokens = tokenize(body)
    total: Counter = Counter()
    lone: list[tuple[int, str]] = []
    evidence: list[str] = []
    unexplained: list[str] = []

    pending = 0  # multiplicador numerico pendiente ("2 TENORS", "THREE BASSES")
    for index, (token, _gap) in enumerate(tokens):
        if token.isdigit():
            pending = int(token) if 1 <= int(token) <= 20 else 0
            continue
        if token in NUMBER_WORDS:
            pending = NUMBER_WORDS[token]
            continue
        if token in SKIP_TOKENS:
            notes.append(f"TOKEN_OMITIDO:{token}")
            pending = 0
            continue
        if token in FORCE_INVALID_TOKENS:
            notes.append(f"FRAGMENTO_NO_VOCAL:{token}")
            invalid = True
            pending = 0
            continue
        base, factor = split_multiplier(token)
        counts, kind, letter = classify(base)
        # un modificador ("SOLO", "SOLOISTS"...) no anula el multiplicador
        inherited, pending = pending, 0
        if token in QUALIFIERS:
            pending = inherited
        if counts is None:
            unexplained.append(token)
            continue
        if kind == "OVERRIDE":
            notes.append(f"REGLA_CURADA:{token}->{GLUED_OVERRIDES[base]}")
        if kind == "LONE":
            lone.append((index, letter))
            pending = 0
            continue
        # "2 TENORS", "3 BASSES": el numeral solo multiplica a una voz escrita
        if inherited and kind == "WORD" and factor == 1:
            notes.append(f"MULTIPLICADOR:{inherited}x{base}")
            counts = Counter({k: v * inherited for k, v in counts.items()})
            pending = 0
        elif factor > 1:
            notes.append(f"MULTIPLICADOR:{factor}x{base}")
            counts = Counter({k: v * factor for k, v in counts.items()})
        total.update(counts)
        evidence.append(kind)

    # c) Regla de contexto para las letras sueltas (S, A, T, B, C aisladas)
    text_tokens = [t for t, _ in tokens]
    has_qualifier = any(t in QUALIFIERS for t in text_tokens)
    others_all_functional = all(
        t in FUNCTION_WORDS or t in QUALIFIERS for t in unexplained
    )
    for index, letter in lone:
        previous = text_tokens[index - 1] if index > 0 else None
        right_word = (
            text_tokens[index + 1] if index + 1 < len(text_tokens) else None
        )
        left_gap = tokens[index][1]
        right_gap = tokens[index + 1][1] if index + 1 < len(tokens) else ""
        connected = (
            previous in CONNECTOR_WORDS
            or right_word in CONNECTOR_WORDS
            or any(ch in CONNECTOR_CHARS for ch in left_gap)
            or any(ch in CONNECTOR_CHARS for ch in right_gap)
        )
        if previous in SUPPRESSORS:
            notes.append(f"LETRA_DESCARTADA:{letter}:precedida por {previous}")
            continue
        if evidence or has_qualifier or connected or others_all_functional:
            total[letter] += 1
            notes.append(f"LETRA_ACEPTADA:{letter}")
        else:
            notes.append(f"LETRA_DESCARTADA:{letter}:sin contexto de voces")

    # e) Sin voces identificables -> no es un conjunto vocal
    if invalid or not total:
        if not total and not notes:
            notes.append("SIN_VOZES_IDENTIFICABLES")
        return {
            "id_canonico": INVALID,
            "counts": Counter(),
            "counts_txt": "-",
            "family": "-",
            "total": 0,
            "notas": "; ".join(notes),
        }

    ordered = "".join(v * total[v] for v in VOICE_ORDER)
    counts_txt = "".join(
        f"{v}{total[v]}" for v in VOICE_ORDER if total[v]
    )
    return {
        "id_canonico": ordered,
        "counts": total,
        "counts_txt": counts_txt,
        "family": f"{ordered}_{family_label(total)}_{sum(total.values())}V",
        "total": sum(total.values()),
        "notas": "; ".join(notes) if notes else "-",
    }


# --------------------------------------------------------------------------
# 2. Lectura de la base de datos (solo lectura)
# --------------------------------------------------------------------------

def read_rows() -> list[dict]:
    with (ROOT / "config.yaml").open(encoding="utf-8") as handle:
        db = yaml.safe_load(handle)["db"]
    connection = pymysql.connect(
        host=db["host"],
        port=int(db["port"]),
        user=db["user"],
        password=db["password"],
        database=db["name"],
        charset="utf8mb4",
        autocommit=False,          # solo lectura: nunca se confirma nada
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with connection.cursor() as cursor:      # unico tipo de sentencia usada
            cursor.execute(
                "SELECT id, ensembles_name, ensembles_code, ensembles_description "
                "FROM ensembles ORDER BY id"
            )
            return list(cursor.fetchall())
    finally:
        connection.rollback()
        connection.close()


def main() -> None:
    rows = read_rows()
    existing_codes = {row["ensembles_code"] for row in rows}

    results = []
    for row in rows:
        info = canonicalize(row["ensembles_code"])
        code = info["id_canonico"]
        info["existe"] = 1 if code in existing_codes else 0
        results.append((row, info))

    # --- resultado.md (unicamente la tabla) -------------------------------
    lines = [
        "| ensembles_code | ID_Canonico | Existe_en_Tabla (0/1) |",
        "|---|---|---|",
    ]
    for row, info in results:
        code = str(row["ensembles_code"]).replace("|", "\\|")
        lines.append(f"| {code} | {info['id_canonico']} | {info['existe']} |")
    (BASE / "resultado.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # --- auditoria_detalle.csv (traza diagnosticable) ---------------------
    with (BASE / "auditoria_detalle.csv").open("w", encoding="utf-8-sig",
                                               newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow([
            "id", "ensembles_name", "ensembles_code", "ID_Canonico",
            "Existe_en_Tabla", "conteo_S", "conteo_A", "conteo_T", "conteo_B",
            "conteo_C", "total_voces", "firma_frecuencias", "etiqueta_familia",
            "notas_reglas",
        ])
        for row, info in results:
            counts = info["counts"]
            writer.writerow([
                row["id"], row["ensembles_name"], row["ensembles_code"],
                info["id_canonico"], info["existe"],
                counts["S"], counts["A"], counts["T"], counts["B"], counts["C"],
                info["total"], info["counts_txt"], info["family"], info["notas"],
            ])

    # --- resumen por consola ---------------------------------------------
    nuevos = [(r, i) for r, i in results if i["existe"] == 0]
    invalidos = [(r, i) for r, i in results if i["id_canonico"] == INVALID]
    ya_existentes = [(r, i) for r, i in results if i["existe"] == 1]
    nuevos_ids = sorted({i["id_canonico"] for _, i in nuevos
                      if i["id_canonico"] != INVALID})
    familias = Counter(i["family"] for _, i in results if i["id_canonico"] != INVALID)

    print(f"registros leidos        : {len(rows)}")
    print(f"ID_Canonico == INVALID  : {len(invalidos)}")
    print(f"Existe_en_Tabla = 1     : {len(ya_existentes)}")
    print(f"Existe_en_Tabla = 0     : {len(nuevos)}")
    print(f"IDs canonicos distintos : "
          f"{len({i['id_canonico'] for _, i in results})}")
    print(f"IDs canonicos nuevos    : {len(nuevos_ids)}")
    print("\nIDS canonicos mas frecuentes:")
    for code, n in Counter(i["id_canonico"] for _, i in results).most_common(15):
        print(f"  {n:5d}  {code}")
    print("\nFAMILIAS mas frecuentes:")
    for name, n in familias.most_common(10):
        print(f"  {n:5d}  {name}")
    print("\ncodigos marcados INVALID_OR_INSTRUMENTAL:")
    for row, _info in invalidos:
        print(f"  {row['ensembles_code']}")
    print("\nIDs canonicos nuevos (no figuran como ensembles_code):")
    print("  " + ", ".join(nuevos_ids))


if __name__ == "__main__":
    main()
