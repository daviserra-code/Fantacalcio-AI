# age_index_cleaner.py
import os, json, time, unicodedata

AGE_INDEX_PATH = os.getenv("AGE_INDEX_PATH", "./data/age_index.json")
AGE_INDEX_CLEANED_PATH = os.getenv("AGE_INDEX_CLEANED_PATH", "./data/age_index.cleaned.json")
SERIE_A_TEAMS_PATH = os.getenv("SERIE_A_TEAMS_PATH", "./data/serie_a_teams_2025_26.json")

def norm(s: str) -> str:
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.split())

def parse_key(k: str):
    k = k.strip()
    if "@@" in k:
        name, team = k.split("@@", 1)
    elif "|" in k:
        name, team = k.split("|", 1)
    else:
        # niente separatore → prova a usare tutto come nome e team sconosciuto
        name, team = k, ""
    return norm(name), norm(team)

def load_serie_a(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        teams = set()
        if isinstance(data, list):
            for t in data:
                if isinstance(t, str):
                    teams.add(norm(t))
                elif isinstance(t, dict):
                    # supporta {"name":"Inter"} ecc.
                    teams.add(norm(t.get("name","")))
        return {x for x in teams if x}
    except Exception:
        return set()

def main():
    if not os.path.exists(AGE_INDEX_PATH):
        print(f"❌ file non trovato: {AGE_INDEX_PATH}")
        return
    cur_year = time.localtime().tm_year
    min_year = 1980
    max_year = cur_year - 15  # esclude “nati 2015+” che sono under 10, improbabile per Serie A

    serie_a = load_serie_a(SERIE_A_TEAMS_PATH)
    use_filter_teams = len(serie_a) > 0

    with open(AGE_INDEX_PATH, "r", encoding="utf-8") as f:
        src = json.load(f)

    cleaned = {}
    kept = dropped = 0
    for raw_k, v in src.items():
        name, team = parse_key(raw_k)
        # filtra team se disponibile la lista Serie A
        if use_filter_teams and team and team not in serie_a:
            dropped += 1
            continue
        by = None
        if isinstance(v, dict) and "birth_year" in v:
            by = v["birth_year"]
        elif isinstance(v, int):
            by = v
        # valida anno
        try:
            by = int(by)
        except Exception:
            dropped += 1
            continue
        if not (min_year <= by <= max_year):
            dropped += 1
            continue
        key = f"{name}@@{team}" if team else name
        cleaned[key] = by
        kept += 1

    os.makedirs(os.path.dirname(AGE_INDEX_CLEANED_PATH), exist_ok=True)
    with open(AGE_INDEX_CLEANED_PATH, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    print(f"✅ Pulizia completata: tenuti {kept}, scartati {dropped}.")
    print(f"➡️  Salvato in: {AGE_INDEX_CLEANED_PATH}")

if __name__ == "__main__":
    main()
