# -*- coding: utf-8 -*-
import json, os, re, unicodedata
from typing import Tuple

REF_YEAR = int(os.getenv("REF_YEAR", "2025"))
IN_PATH  = os.getenv("AGE_INDEX_PATH", "./data/age_index.json")
OUT_PATH = os.getenv("AGE_INDEX_CLEANED_PATH", "./data/age_index.cleaned.json")

def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))

def norm_text(s: str) -> str:
    if not s: return ""
    s = strip_accents(s).lower()
    s = re.sub(r"\b(f\.?c\.?|a\.?c\.?|u\.?s\.?|ssd|ss|ssc|ud|spa|calcio|club|1907|1913|1919|1927|1909|1905)\b"," ",s)
    s = s.replace(".", " ").replace("-", " ")
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    aliases = {
        "juventus fc":"juventus","juventus":"juventus","juve":"juventus",
        "inter":"inter","internazionale":"inter","inter milano":"inter",
        "milan":"milan","ac milan":"milan",
        "napoli":"napoli","ssc napoli":"napoli",
        "lazio":"lazio","ss lazio":"lazio",
        "roma":"roma","as roma":"roma",
        "atalanta bc":"atalanta","atalanta":"atalanta",
        "bologna fc":"bologna","bologna":"bologna",
        "udinese calcio":"udinese","udinese":"udinese",
        "acf fiorentina":"fiorentina","fiorentina":"fiorentina",
        "torino fc":"torino","torino":"torino",
        "hellas verona":"verona","verona":"verona",
        "genoa":"genoa","como":"como","monza":"monza",
        "sassuolo":"sassuolo","lecce":"lecce","empoli":"empoli",
        "cagliari":"cagliari","parma":"parma","venezia fc":"venezia","venezia":"venezia",
        "cremonese":"cremonese","bari":"bari",
        "como 1907":"como","pisa sporting club":"pisa",
        "football club torinese":"torino",
        "unione sportiva internazionale napoli":"napoli",
        "alba roma 1907":"roma",
    }
    return aliases.get(s, s)

def split_key(k: str) -> Tuple[str,str]:
    if "@@" in k:
        a,b = k.split("@@",1)
    elif "|" in k:
        a,b = k.split("|",1)
    else:
        a,b = k,""
    return norm_text(a), norm_text(b)

def valid_by(x) -> int|None:
    try:
        x = int(x)
    except:
        return None
    if x < 1900 or x > REF_YEAR: return None
    if x > REF_YEAR-14: return None
    return x

def main():
    if not os.path.exists(IN_PATH):
        print(f"❌ file non trovato: {IN_PATH}")
        return
    raw = json.load(open(IN_PATH,"r",encoding="utf-8"))
    if not isinstance(raw, dict):
        print("❌ age_index deve essere un dict { 'name@@team': birth_year | {'birth_year':...} }")
        return
    out = {}
    bad = 0
    for k, v in raw.items():
        by = v.get("birth_year") if isinstance(v, dict) else v
        by = valid_by(by)
        if by is None:
            bad += 1
            continue
        nn, tn = split_key(k)
        out[f"{nn}@@{tn}"] = by
    json.dump(out, open(OUT_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"✅ salvato {OUT_PATH} con {len(out)} righe pulite (scartate {bad})")

if __name__ == "__main__":
    main()
