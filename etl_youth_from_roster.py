#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Fallback: costruisce la cache U23/U21 dal season_roster.json.
Utile se i metadati/doc di Chroma non contengono l'anno.

ENV:
  ROSTER_JSON_PATH=./season_roster.json
  EXTERNAL_YOUTH_CACHE=./cache/under21_cache.json
  REF_YEAR=2025
  AGE_CUTOFF=23
"""

import os
import re
import json
import math
import logging

LOG = logging.getLogger("etl_youth_from_roster")
logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

REF_YEAR = int(os.getenv("REF_YEAR", "2025"))
AGE_CUTOFF = int(os.getenv("AGE_CUTOFF", "23"))
ROSTER_PATH = os.getenv("ROSTER_JSON_PATH", "./season_roster.json")
OUT_PATH = os.getenv("EXTERNAL_YOUTH_CACHE", "./cache/under21_cache.json")

YEAR_RE = re.compile(r"\b(20\d{2}|19\d{2})\b")

def _to_int(x):
    try:
        return int(x)
    except Exception:
        return None

def norm_role(role: str) -> str:
    if not role: return ""
    r = role.strip().upper()
    if r in {"P","POR","GK","PORTIERE"}: return "P"
    if r in {"D","DEF","DC","TD","TS","BR","CB","RB","LB"}: return "D"
    if r in {"C","CC","MED","CM","MD","ME","EST","M"}: return "C"
    if r in {"A","ATT","ATTACCANTE","F","FW","SS","PUNTA"}: return "A"
    return r[:1]

def age_from_year(by: int) -> int | None:
    try: return REF_YEAR - int(by)
    except Exception: return None

def guess_year(obj: dict) -> int | None:
    for k in ("birth_year","year_of_birth","born_year","anno_nascita"):
        y=_to_int(obj.get(k))
        if y and (REF_YEAR-AGE_CUTOFF) <= y <= REF_YEAR:  # plausibile U23
            return y
    # eventualmente prova a estrarre numeri da eventuali campi descrittivi
    for k in ("bio","notes","extra"):
        val=obj.get(k)
        if isinstance(val,str):
            m=YEAR_RE.search(val)
            if m:
                y=_to_int(m.group(1))
                if y and (REF_YEAR-AGE_CUTOFF) <= y <= REF_YEAR:
                    return y
    return None

def safe_float(x):
    try: return float(x)
    except Exception: return None

def main():
    if not os.path.exists(ROSTER_PATH):
        LOG.warning("[ETL-Y-ROSTER] roster non trovato: %s", ROSTER_PATH)
        return

    try:
        data=json.load(open(ROSTER_PATH,encoding="utf-8"))
    except Exception as e:
        LOG.error("[ETL-Y-ROSTER] errore lettura roster: %s", e)
        return

    if not isinstance(data,list):
        LOG.warning("[ETL-Y-ROSTER] roster non è una lista, stop")
        return

    out=[]
    for r in data:
        if not isinstance(r,dict): continue
        name=(r.get("name") or r.get("player") or "").strip()
        if not name: continue
        role=norm_role(r.get("role") or r.get("position") or "")
        team=(r.get("team") or r.get("club") or "").strip()
        by = guess_year(r)
        if not by: continue
        age = age_from_year(by)
        if age is None or age > AGE_CUTOFF: continue

        fm = safe_float(r.get("fantamedia") or r.get("avg"))
        price = safe_float(r.get("price") or r.get("cost"))

        out.append({
            "name": name,
            "role": role,
            "team": team,
            "birth_year": by,
            "age": age,
            "fantamedia": fm,
            "price": price,
            "source": "roster"
        })

    # dedup per (name, team), preferisci FM maggiore poi prezzo minore
    dedup={}
    for p in out:
        key=(p["name"].lower(), (p.get("team") or "").lower())
        prev=dedup.get(key)
        if not prev:
            dedup[key]=p
        else:
            pfm = prev.get("fantamedia") or -math.inf
            nfm = p.get("fantamedia") or -math.inf
            if nfm > pfm:
                dedup[key]=p
            elif nfm == pfm:
                ppr = p.get("price") or math.inf
                pprev = prev.get("price") or math.inf
                if ppr < pprev:
                    dedup[key]=p

    out=list(dedup.values())
    out.sort(key=lambda x: (-(x.get("fantamedia") or 0.0), x.get("price") or 1e9, x["name"]))

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    json.dump(out, open(OUT_PATH,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

    n_u23=sum(1 for x in out if x.get("age") is not None and x["age"]<=23)
    n_u21=sum(1 for x in out if x.get("age") is not None and x["age"]<=21)

    LOG.info("[ETL-Y-ROSTER] Salvato %s con %d profili U23 (di cui %d U21).", OUT_PATH, n_u23, n_u21)

if __name__=="__main__":
    main()
