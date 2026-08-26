import json

# Base de conocimiento ampliada con los compositores investigados
# Formato: nombre -> biography dict

BIOGRAPHIES = {
    "Clara Gottschalk-Peterson": {
        "summary": "Clara Gottschalk Peterson (1837–1910) fue una pianista, compositora y editora estadounidense.",
        "era": "Romántico",
        "nationality": "Estadounidense",
        "key_works": ["Creole Songs from New Orleans", "Notes of a Pianist"],
        "key_fact": "Fue hermana y protectora del legado de Louis Moreau Gottschalk."
    },
    "Francesco Turini": {
        "summary": "Francesco Turini (c. 1595 – 1656) fue un compositor y organista italiano del primer Barroco.",
        "era": "Barroco",
        "nationality": "Italiana",
        "key_works": ["Madrigali", "Motetti", "Messe da cappella"],
        "key_fact": "Fue el primer compositor en usar el término 'cantata' como designación de género."
    },
    "Léon Delafosse": {
        "summary": "Léon Delafosse (1874 – 1951) fue un compositor y pianista francés.",
        "era": "Romántico/Moderno",
        "nationality": "Francesa",
        "key_works": ["Soirée d'amour", "Quintette des fleurs", "Concerto for piano and orchestra"],
        "key_fact": "Se cree que inspiró el personaje de Charles Morel en 'En busca del tiempo perdido'."
    },
    "William James Kirkpatrick": {
        "summary": "William James Kirkpatrick (1838–1921) fue un himnólogo y editor musical estadounidense.",
        "era": "Siglo XIX",
        "nationality": "Estadounidense",
        "key_works": ["Away in a Manger", "A Wonderful Savior is Jesus My Lord"],
        "key_fact": "Cofundador de Praise Publishing Company."
    },
    "Joel Engel": {
        "summary": "Joel Engel (1868–1927) fue un compositor y crítico musical ruso.",
        "era": "Romántico/Contemporáneo",
        "nationality": "Rusa (judía)",
        "key_works": ["The Dybbuk Suite", "Adagio Mysterioso"],
        "key_fact": "Padre fundador de la música judía moderna."
    },
    "Artemy Vedel": {
        "summary": "Artemy Vedel (1767–1808) fue un compositor ucraniano-ruso.",
        "era": "Barroco/Clásico",
        "nationality": "Ucraniana",
        "key_works": ["Choral concertos", "On the Rivers of Babylon"],
        "key_fact": "Forma el 'Trío de Oro' de la música clásica ucraniana."
    },
    "Philippe Verdelot": {
        "summary": "Philippe Verdelot (c. 1480-1540) fue un compositor francés del Renacimiento.",
        "era": "Renacimiento",
        "nationality": "Francesa",
        "key_works": ["Madrigals (1520)", "Missa Philomna"],
        "key_fact": "Considerado el padre del madrigal italiano."
    },
    "Andreas Sicha": {
        "summary": "Andrei Osipovich Sychra (1773/76 – 1850) fue un guitarrista y compositor ruso.",
        "era": "Romántico",
        "nationality": "Rusa",
        "key_works": ["Praktičeskie pravila igrat' na gitare", "Peterburgskij žurnal dlja gitary"],
        "key_fact": "Patriarca de la guitarra de siete cuerdas en Rusia."
    },
    "William Marshall": {
        "summary": "William Marshall (1748–1833) fue un compositor escocés de música de violín.",
        "era": "Clásico/Romántico",
        "nationality": "Escocesa",
        "key_works": ["The Marchioness of Huntly", "Marshall's Scottish Airs"],
        "key_fact": "Robert Burns lo llamó 'el primer compositor de strathspeys de la época'."
    },
    "Șerban Nichifor": {
        "summary": "Șerban Nichifor (nacido 1954) es un compositor rumano.",
        "era": "Contemporáneo",
        "nationality": "Rumana",
        "key_works": ["Constellations for Orchestra", "Domnişoara Cristina"],
        "key_fact": "Ganó el Primer Premio Gaudeamus en 1977."
    },
    "George Botsford": {
        "summary": "George Botsford (1874–1949) fue un compositor estadounidense de ragtime.",
        "era": "Siglo XX",
        "nationality": "Estadounidense",
        "key_works": ["Black and White Rag", "Pride of the Prairie"],
        "key_fact": "Miembro fundador de ASCAP en 1914."
    },
    "Franz Schubert": {
        "summary": "Franz Schubert (1797–1828) fue un compositor austriaco del Romanticismo temprano.",
        "era": "Romántico",
        "nationality": "Austriaca",
        "key_works": ["Sinfonía No. 8 'Inacabada'", "Ave María", "Winterreise"],
        "key_fact": "Dejó más de 1,500 obras a pesar de morir a los 31 años."
    }
}

# Save to file
with open('composer_biographies.json', 'w', encoding='utf-8') as f:
    json.dump(BIOGRAPHIES, f, ensure_ascii=False, indent=2)

print(f"Saved {len(BIOGRAPHIES)} biographies to composer_biographies.json")
