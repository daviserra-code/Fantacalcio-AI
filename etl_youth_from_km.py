# etl_youth_from_km.py
# -*- coding: utf-8 -*-
import os, re, json, math, logging
from knowledge_manager import KnowledgeManager

LOG = logging.getLogger("etl_youth_from_km")
logging.basicConfig(level=os.environ.get("LOG_LEVEL","INFO"),
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")

REF_YEAR  = int(os.getenv("REF_YEAR","2025"))
AGE_CUTOFF= int(os.getenv("AGE_CUTOFF","23"))
OUT_PATH  = os.getenv("EXTERNAL_YOUTH_CACHE","./cache/under21_cache.json")

MIN_YEAR = REF_YEAR - AGE_CUTOFF     # 23 anni → 2002
MAX_YEAR = REF_YEAR - 15             # 10–15 anni come filtro superiore
ITALIAN_MONTHS = r"(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)"

# Più pattern: anno esplicito (ampi), '03, (2004), * 2005, "X anni"
RE_ANNI = [
    re.compile(r"nato(?:\s+il)?\s+\d{1,2}[\/\-\.\s](?:\d{1,2}|" + ITALIAN_MONTHS + r")[\/\-\.\s](20\d{2}|19\d{2})", re.I),
    re.compile(r"\b\d{1,2}\s+" + ITALIAN_MONTHS + r"\s+(20\d{2}|19\d{2})\b", re.I),
    re.compile(r"\bclasse\s+('?|’)?0?(\d{2}|\d{4})\b", re.I),   # classe '03, classe 2004
    re.compile(r"\bnato\s+nel\s+(20\d{2}|19\d{2})\b", re.I),
    re.compile(r"\(\s*(20\d{2}|19\d{2})\s*\)"),               # (2004)
    re.compile(r"[*]\s*(20\d{2}|19\d{2})"),                   # * 2004
    re.compile(r"\b(20\d{2}|19\d{2})\b"),                     # anno isolato (filtriamo dopo)
]
RE_AGE = re.compile(r"\b(\d{1,2})\s+anni\b", re.I)            # “19 anni”

def _to_int(x):
    try: return int(x)
    except: return None

def norm_role(r: str) -> str:
    if not r: return ""
    r=r.strip().upper()
    if r in {"P","POR","GK","PORTIERE"}: return "P"
    if r in {"D","DEF","DC","TD","TS","BR","CB","RB","LB"}: return "D"
    if r in {"C","CC","MED","CM","MD","ME","EST","M"}: return "C"
    if r in {"A","ATT","ATTACCANTE","F","FW","SS","PUNTA"}: return "A"
    return r[:1]

def age_from_year(by: int) -> int | None:
    try: return REF_YEAR - int(by)
    except: return None

def clamp_birth_year(y: int | None) -> int | None:
    if not y: return None
    if y < 1980 or y > REF_YEAR: return None
    return y

def extract_years(txt: str):
    """Restituisce (best_birth_year, fallback_year_from_age)"""
    if not txt: return (None, None)
    clean = txt.replace("–","-")
    # rimuovi pattern stagione “2025-26” → 2025
    clean = re.sub(r"\b(20\d{2})\s*[-/]\s*(\d{2})\b", r"\1", clean)

    # 1) prova anni espliciti
    for pat in RE_ANNI:
        for m in pat.finditer(clean):
            groups = [g for g in m.groups() if g]
            # normalizza '03 → 2003
            cand = None
            for g in groups[::-1]:
                g = g.strip("’'")
                y = _to_int(g)
                if y is None: continue
                if y < 100: y += 2000
                cand = clamp_birth_year(y)
                if cand: break
            if cand and MIN_YEAR <= cand <= MAX_YEAR:
                return (cand, None)

    # 2) prova età “X anni” → REF_YEAR - X (fallback)
    m = RE_AGE.search(clean)
    if m:
        age = _to_int(m.group(1))
        if age is not None and 15 <= age <= AGE_CUTOFF:
            y = REF_YEAR - age
            if MIN_YEAR <= y <= MAX_YEAR:
                return (None, y)

    return (None, None)

def safe_float(x):
    try: return float(x)
    except: return None

def main():
    km = KnowledgeManager()
    raw = km.collection.get(include=["metadatas","documents"])
    metas = raw.get("metadatas") or []
    docs  = raw.get("documents") or []
    LOG.info("[YOUTH] records: %d", len(metas))

    out=[]
    for m,doc in zip(metas, docs):
        if not isinstance(m, dict): continue
        name = (m.get("name") or m.get("player") or "").strip()
        if not name: continue
        role = norm_role(m.get("role") or m.get("position") or "")
        team = (m.get("team") or m.get("club") or "").strip()

        # hard fields first
        for key in ("birth_year","year_of_birth","anno_nascita","born_year"):
            by = _to_int(m.get(key))
            if by and MIN_YEAR <= by <= MAX_YEAR:
                age = age_from_year(by)
                out.append({"name":name,"role":role,"team":team,"birth_year":by,"age":age,
                            "fantamedia":safe_float(m.get("fantamedia")),
                            "price":safe_float(m.get("price") or m.get("cost")),
                            "source":"km-meta"})
                break
        else:
            # extract dal testo
            best, fallback = extract_years(doc or "")
            by = best or fallback
            if by and MIN_YEAR <= by <= MAX_YEAR:
                age = age_from_year(by)
                out.append({"name":name,"role":role,"team":team,"birth_year":by,"age":age,
                            "fantamedia":safe_float(m.get("fantamedia")),
                            "price":safe_float(m.get("price") or m.get("cost")),
                            "source":"km-text" if best else "km-age"})

    # dedup (name, team)
    dedup={}
    for p in out:
        key=(p["name"].lower(), (p.get("team") or "").lower())
        prev=dedup.get(key)
        if not prev: dedup[key]=p
        else:
            # preferisci chi ha birth_year “best” da testo/metadati (km-meta/ km-text) rispetto “km-age”
            rank = {"km-meta":2,"km-text":2,"km-age":1}
            if rank.get(p["source"],0) > rank.get(prev.get("source"),0):
                dedup[key]=p
            elif rank.get(p["source"],0) == rank.get(prev.get("source"),0):
                # pari: FM maggiore → prezzo minore
                pfm = (prev.get("fantamedia") or -math.inf)
                nfm = (p.get("fantamedia") or -math.inf)
                if nfm > pfm: dedup[key]=p
                elif nfm == pfm:
                    ppr = p.get("price") or math.inf
                    pprev= prev.get("price") or math.inf
                    if ppr < pprev: dedup[key]=p

    out=list(dedup.values())
    out.sort(key=lambda x: (-(x.get("fantamedia") or 0.0), x.get("price") or 1e9, x["name"]))

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    json.dump(out, open(OUT_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

    n_u23=sum(1 for x in out if x.get("age") is not None and x["age"]<=23)
    n_u21=sum(1 for x in out if x.get("age") is not None and x["age"]<=21)
    LOG.info("[YOUTH] salvato %s con %d profili U23 (di cui %d U21).", OUT_PATH, n_u23, n_u21)

if __name__=="__main__":
    main()
