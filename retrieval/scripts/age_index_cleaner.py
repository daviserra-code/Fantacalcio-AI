# -*- coding: utf-8 -*-
import os, json, re, unicodedata, sys

IN_PATH = os.getenv("AGE_INDEX_PATH_RAW", "./data/age_index.json")
OUT_PATH = os.getenv("AGE_INDEX_CLEANED_PATH", "./data/age_index.cleaned.json")

def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

TEAM_ALIASES = {
    "como 1907": "como",
    "ss lazio": "lazio",
    "s.s. lazio": "lazio",
    "venezia fc": "venezia",
}

def norm_team(t: str) -> str:
    t = norm_text(t)
    t = re.sub(r"\b(football club|fc|ac|ss|usc|cfc|calcio|club)\b", "", t).strip()
    t = re.sub(r"\b(18|19|20)\d{2}\b", "", t).strip()
    t = re.sub(r"\s+", " ", t)
    if t in TEAM_ALIASES:
        t = TEAM_ALIASES[t]
    return t or norm_text(t)

def valid_by(v):
    try:
        v = int(v)
    except:
        return None
    return v if 1975 <= v <= 2010 else None

def main():
    if not os.path.exists(IN_PATH):
        print(f"❌ file non trovato: {IN_PATH}")
        sys.exit(1)
    with open(IN_PATH, "r", encoding="utf-8") as f:
        raw = json.load(f)

    out = {}
    if isinstance(raw, dict):
        items = raw.items()
    elif isinstance(raw, list):
        items = []
        for row in raw:
            if isinstance(row, dict):
                k = row.get("key") or row.get("k") or ""
                by = row.get("birth_year") or row.get("by")
                if k and by:
                    items.append((k, by))
    else:
        items = []

    for k, v in items:
        by = v.get("birth_year") if isinstance(v, dict) else v
        by = valid_by(by)
        if by is None:
            continue
        name, team = k, ""
        if "@@" in k:
            name, team = k.split("@@", 1)
        elif "|" in k:
            name, team = k.split("|", 1)
        name = norm_text(name)
        team = norm_team(team)
        out[f"{name}@@{team}"] = by

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"✅ cleaned -> {OUT_PATH} ({len(out)} chiavi)")

if __name__ == "__main__":
    main()
