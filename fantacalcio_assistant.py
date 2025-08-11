import os
import json
import logging
import datetime as dt
from typing import Dict, Any, List, Optional

from openai import OpenAI  # openai>=1.0
from knowledge_manager import KnowledgeManager
from web_fallback import WebFallback

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SERIE_A_TEAMS = [
    "Atalanta", "Bologna", "Cagliari", "Como", "Empoli", "Fiorentina", "Genoa",
    "Inter", "Juventus", "Lazio", "Lecce", "Milan", "Monza", "Napoli", "Parma",
    "Roma", "Torino", "Udinese", "Venezia", "Verona", "Hellas Verona", "Frosinone",
]

def _load_prompt_json(path: str = "prompt.json") -> Dict[str, Any]:
    if not os.path.exists(path):
        logger.warning("[Assistant] prompt.json non trovato, uso defaults minimi.")
        return {
            "system": {
                "content": "Sei un assistente fantacalcio. Rispondi in italiano, citando le fonti quando presenti nel contesto.",
                "language": "it"
            }
        }
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "system" not in data or "content" not in data["system"]:
            raise ValueError("prompt.json deve contenere system.content")
        logger.info("[Assistant] prompt.json caricato correttamente")
        return data
    except Exception as e:
        logger.error("[Assistant] Errore caricamento prompt.json: %s", e)
        return {
            "system": {
                "content": "Sei un assistente fantacalcio. Rispondi in italiano, citando le fonti quando presenti nel contesto.",
                "language": "it"
            }
        }

def _extract_team_name(text: str) -> Optional[str]:
    low = text.lower()
    for t in SERIE_A_TEAMS:
        if t.lower() in low:
            # normalizza Hellas Verona → Verona
            if t.lower() in ("hellas verona", "verona"):
                return "Hellas Verona"
            return t
    return None

def _looks_like_transfer_question(text: str) -> bool:
    low = text.lower()
    keys = ["acquisti", "acquisto", "trasferimenti", "mercato", "arrivi", "nuovi giocatori"]
    return any(k in low for k in keys)


class FantacalcioAssistant:
    """
    - Usa KnowledgeManager per RAG
    - Se RAG non copre i trasferimenti recenti, usa WebFallback (Wikipedia)
    - Salva i risultati del fallback nel KB per le prossime volte
    """

    def __init__(self):
        # OpenAI client
        self.client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

        # Prompt
        self.prompt = _load_prompt_json()

        # Knowledge
        self.km = KnowledgeManager(
            collection_name=os.environ.get("CHROMA_COLLECTION", "fantacalcio_knowledge"),
            persist_dir=os.environ.get("CHROMA_DIR", "./chroma_db"),
            embed_model_name=os.environ.get("EMBED_MODEL", "all-MiniLM-L6-v2"),
        )

        # Web fallback
        self.web = WebFallback(timeout_s=float(os.environ.get("WEB_TIMEOUT", "6.5")))

        # Semplice cache in memoria (per non ripetere scraping a ruota)
        self._memory_cache: Dict[str, Any] = {}

        logger.info("[Assistant] Inizializzazione completata")

    # -------------------------------------------------
    # Public API (usata da web_interface)
    # -------------------------------------------------
    def get_response(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        context = context or {}

        # 1) Intent basic: trasferimenti di una squadra?
        if _looks_like_transfer_question(message):
            team = _extract_team_name(message) or context.get("team")
            if team:
                return self._answer_team_transfers(team, message)

        # 2) RAG generico: prova a costruire contesto e chiamare LLM
        return self._answer_generic(message, context)

    def reset_conversation(self) -> str:
        self._memory_cache.clear()
        return "Conversazione resettata."

    def get_cache_stats(self) -> Dict[str, Any]:
        return {
            "cache_size": len(self._memory_cache),
            "cache_keys": list(self._memory_cache.keys())[:10],
        }

    # -------------------------------------------------
    # Internal: risposte specifiche
    # -------------------------------------------------
    def _answer_team_transfers(self, team: str, user_query: str) -> str:
        """
        1) Cerca nel KB (type=transfer, team=team)
        2) Se pochi/vecchi → fallback web sincrono
        3) Salva nel KB gli acquisti trovati, rispondi con elenco + fonti
        """
        today = dt.date.today().isoformat()

        # 1) Prova KB
        where = {"$and": [
            {"type": {"$eq": "transfer"}},
            {"team": {"$eq": team}},
        ]}
        kb_hits = self.km.search_knowledge(
            query_text=user_query,
            n_results=8,
            where=where
        )

        acquisti_from_kb = []
        sources_kb = set()
        for h in kb_hits:
            md = h.get("metadata", {})
            if md.get("direction") == "in":  # solo acquisti
                name = md.get("player") or md.get("name")
                if name:
                    acquisti_from_kb.append(name)
            src = md.get("source")
            if src:
                sources_kb.add(src)

        # Se abbiamo almeno 2 nomi dal KB, rispondi subito
        if len(set(acquisti_from_kb)) >= 2:
            elenco = "\n".join(f"- {n}" for n in sorted(set(acquisti_from_kb)))
            fonti = ", ".join(sorted(sources_kb)) if sources_kb else "KB interno"
            return f"Ultimi acquisti {team} (dal mio database):\n{elenco}\n\nFonti: {fonti}"

        # 2) Fallback web (sincrono, subito)
        cache_key = f"transfers:{team.lower()}"
        if cache_key in self._memory_cache:
            web_result = self._memory_cache[cache_key]
        else:
            web_result = self.web.fetch_team_transfers(team)
            self._memory_cache[cache_key] = web_result

        acquisti = [a for a in web_result.get("acquisti", []) if a]
        sources = web_result.get("sources", [])
        elapsed = web_result.get("elapsed", 0)

        if not acquisti:
            # Nessun dato affidabile
            return (
                f"Non ho trovato dati affidabili sugli acquisti recenti del {team} nelle fonti pubbliche controllate "
                f"(Wikipedia). Prova a specificare un periodo (es. 'luglio 2025') oppure carichiamo una fonte ufficiale "
                f"(es. RSS del club) nel KB per evitare incertezze."
            )

        # 3) Salva nel KB i risultati trovati (best-effort)
        for name in acquisti:
            try:
                self.km.add_knowledge(
                    text=f"{name} è stato acquistato dal {team}.",
                    metadata={
                        "type": "transfer",
                        "team": team,
                        "player": name,
                        "direction": "in",
                        "season": "2025-26",
                        "source": "Wikipedia",
                        "source_url": ", ".join(sources) if sources else "Wikipedia",
                        "source_date": today,
                        "updated_at": today,
                    }
                )
            except Exception as e:
                logger.warning("[Assistant] Impossibile salvare in KB '%s': %s", name, e)

        elenco = "\n".join(f"- {n}" for n in acquisti[:6])
        src_str = ", ".join(sources) if sources else "Wikipedia"
        return (
            f"Ultimi **acquisti** del {team} (best-effort, via web, {elapsed}s):\n{elenco}\n\n"
            f"Fonti: {src_str}\n"
            f"Nota: il parsing da Wikipedia può essere incompleto. Se vuoi, posso aggiungere una fonte più affidabile "
            f"(RSS del club) al KB per aggiornamenti automatici."
        )

    def _answer_generic(self, message: str, context: Dict[str, Any]) -> str:
        # Costruisci un contesto ampio dal KB
        ctx = self.km.get_context_for_query(
            query_text=message,
            n_results=8,
            max_context_length=1400,
            where=None
        )

        system_prompt = self.prompt["system"]["content"]
        messages = [
            {"role": "system", "content": system_prompt},
        ]

        if ctx:
            messages.append({"role": "system", "content": f"[Contesto KB]\n{ctx}"})

        messages.append({"role": "user", "content": message})

        try:
            model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
            resp = self.client.chat.completions.create(
                model=model,
                temperature=float(os.environ.get("OPENAI_TEMPERATURE", "0.2")),
                max_tokens=int(os.environ.get("OPENAI_MAX_TOKENS", "500")),
                messages=messages,
            )
            answer = (resp.choices[0].message.content or "").strip()
            if not answer:
                return "Non ho trovato abbastanza dati nel mio KB. Se vuoi, posso provare a cercare online."
            return answer
        except Exception as e:
            logger.error("[Assistant] Errore LLM: %s", e)
            return "⚠️ Servizio momentaneamente non disponibile. Riprova tra poco."
