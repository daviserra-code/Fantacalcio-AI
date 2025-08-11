import os
import json
import time
import logging
from typing import Dict, Any, List, Optional, Tuple

from knowledge_manager import KnowledgeManager
from retrieval.rag_pipeline import RAGPipeline  # se non lo usi più, puoi rimuoverlo
from web_fallback import WebFallback, FallbackResult

# OpenAI SDK >=1.0
try:
    from openai import OpenAI
except Exception:  # pragma: no cover
    OpenAI = None  # gestito sotto

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def _load_app_config() -> Dict[str, Any]:
    path = os.path.join(os.getcwd(), "app_config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[Assistant] Impossibile leggere app_config.json: {e}")
        return {}


def _build_system_prompt_from_json(prompt_path: str) -> Tuple[str, Dict[str, Any]]:
    """
    Supporta sia:
    - formato vecchio: {"prompt": "..."}
    - formato nuovo (quello che mi hai mostrato): {"system": {...}, "intents": {...}, ...}
    """
    if not os.path.exists(prompt_path):
        return (
            "Sei un assistente fantacalcio. Rispondi in italiano, sintetico, cita fonti quando disponibili.",
            {},
        )

    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"[Assistant] Errore caricamento prompt.json: {e}")
        return (
            "Sei un assistente fantacalcio. Rispondi in italiano, sintetico, cita fonti quando disponibili.",
            {},
        )

    # Caso legacy
    if isinstance(data, dict) and "prompt" in data and isinstance(data["prompt"], str):
        return data["prompt"], {}

    # Nuovo formato (come il tuo esempio)
    system = data.get("system", {})
    system_content = system.get("content")
    if not isinstance(system_content, str):
        logger.error("[Assistant] Errore caricamento prompt: prompt.json deve contenere una chiave stringa 'prompt' oppure 'system.content'")
        # fallback minimale
        system_content = "Sei un assistente fantacalcio. Usa prima il KB, poi segnala quando fai web fallback."

    return system_content, data  # restituisco anche l'intero JSON per intents/few-shot


def _detect_intent(query: str) -> str:
    q = (query or "").lower()
    if any(w in q for w in ["infortun", "squalific"]):
        return "injury"
    if any(w in q for w in ["trasfer", "gioca oggi", "squadra", "team attuale"]):
        return "transfer"
    if any(w in q for w in ["asta", "conviene", "budget", "credito", "consigliare", "under 21", "u21"]):
        return "value"
    if any(w in q for w in ["prossime partite", "calendario", "forma", "turni", "gameweek"]):
        return "fixtures"
    return "general"


class FantacalcioAssistant:
    """
    Assistant con:
    - prompt.json (nuovo formato)
    - KB locale tramite KnowledgeManager
    - fallback web (Wikipedia/Wikidata, opzionale Transfermarkt) dietro flag
    - OpenAI SDK >= 1.0
    """

    def __init__(self):
        self.config = _load_app_config()

        # Prompt
        prompt_path = os.path.join(os.getcwd(), "prompt.json")
        self.system_prompt, self.prompt_json = _build_system_prompt_from_json(prompt_path)
        logger.info("[Assistant] prompt.json caricato correttamente")

        # KM (autorigenerante)
        self.knowledge_manager = KnowledgeManager(collection_name=self.config.get("chroma_collection", "fantacalcio_knowledge"))
        logger.info("[Assistant] KnowledgeManager attivo")

        # (Opzionale) RAG pipeline – se l’hai rimossa puoi togliere tutto
        self.rag = None
        try:
            # Solo se usi davvero RAGPipeline con Chroma collection già pronta
            # Altrimenti commenta queste 3 righe.
            self.rag = RAGPipeline(chroma_collection=self.knowledge_manager.collection)
        except Exception as e:
            logger.error(f"[RAG] Inizializzazione RAG legacy fallita: {e}. Uso dummy.")
            self.rag = None

        # Web fallback
        self.web_fb = WebFallback(
            enabled=bool(self.config.get("web_fallback_enabled", False)),
            sources=self.config.get("web_fallback_sources", ["wikipedia"]),
            timeout_s=int(self.config.get("web_fallback_timeout_s", 6)),
            ttl_s=int(self.config.get("web_fallback_ttl_s", 86400)),
        )

        # OpenAI client (sdk >= 1.0)
        self.openai_client = None
        api_key = os.environ.get("OPENAI_API_KEY") or self.config.get("openai_api_key")
        if OpenAI and api_key:
            try:
                self.openai_client = OpenAI(api_key=api_key)
            except Exception as e:
                logger.error(f"[Assistant] OpenAI client init failed: {e}")

        self.model = self.config.get("openai_model_primary", "gpt-4o-mini")  # scegli tu
        self.temperature = float(self.config.get("temperature", 0.3))
        self.max_tokens = int(self.config.get("max_tokens", 600))

        # cache basica per risposte
        self._resp_cache: Dict[str, str] = {}
        self._hits = 0
        self._miss = 0

        logger.info("[Assistant] Inizializzazione completata")

    # ----------------- API PUBBLICHE (usate dalla webapp) -----------------

    def get_cache_stats(self) -> Dict[str, Any]:
        total = self._hits + self._miss
        return {
            "cache_hits": self._hits,
            "cache_misses": self._miss,
            "hit_rate_percentage": round((self._hits / total * 100), 2) if total else 0.0,
            "cache_size": len(self._resp_cache),
            "max_cache_size": 128,
        }

    def reset_conversation(self) -> str:
        self._resp_cache.clear()
        self._hits = 0
        self._miss = 0
        return "Conversazione resettata!"

    def get_response(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        Flusso:
        1) controlla cache
        2) cerca nel KB locale
        3) se risultati scarsi → web fallback (se abilitato) → scrive nel KB
        4) genera risposta con OpenAI (sistema + context dal KB)
        """
        key = f"{message.strip().lower()}::{(context or {}).get('mode','')}"
        if key in self._resp_cache:
            self._hits += 1
            return self._resp_cache[key]
        self._miss += 1

        intent = _detect_intent(message)
        today = time.strftime("%Y-%m-%d")

        # 1) query KB (elastico: nessun where aggressivo qui; lasciamo semantica libera)
        km_results = []
        try:
            km_results = self.knowledge_manager.search_knowledge(message, n_results=12)
        except Exception as e:
            logger.error(f"[Assistant] Errore search_knowledge: {e}")

        max_sim = max((r.get("cosine_similarity", 0.0) for r in km_results), default=0.0)
        has_sufficient = len(km_results) >= 2 and max_sim >= 0.28

        # 2) se scarsi → fallback web condizionato
        added_from_web: List[Dict[str, Any]] = []
        if not has_sufficient and self.web_fb.enabled:
            try:
                fb: Optional[FallbackResult] = self.web_fb.enrich_query(message, intent=intent)
                if fb and fb.items:
                    # Normalizza -> scrive nel KB
                    for item in fb.items:
                        text = item.get("text_snippet") or item.get("summary") or item.get("title", "")
                        meta = item.get("metadata", {})
                        # guard rails minimi:
                        if not isinstance(meta, dict):
                            meta = {}
                        meta.setdefault("type", item.get("type", "external"))
                        meta.setdefault("source", item.get("source", "web"))
                        meta.setdefault("source_url", item.get("source_url", ""))
                        meta.setdefault("source_date", item.get("source_date", today))
                        # TTL: per transfer/injury 7 giorni, altrimenti 30
                        ttl_days = 7 if intent in ("transfer", "injury") else 30
                        meta.setdefault("valid_to", self.web_fb.valid_to_days(ttl_days))
                        meta.setdefault("created_at", today)

                        self.knowledge_manager.add_knowledge(text=text, metadata=meta)
                        added_from_web.append({"text": text, "meta": meta})
                    # rifai una query KB leggera dopo ingest
                    km_results = self.knowledge_manager.search_knowledge(message, n_results=12)
                    max_sim = max((r.get("cosine_similarity", 0.0) for r in km_results), default=0.0)
            except Exception as e:
                logger.error(f"[Assistant] Fallback web error: {e}")

        # 3) comporre il contesto da KM
        kb_context = self.knowledge_manager.get_context_for_query(message, max_context_length=1200)

        # 4) generare risposta
        reply = self._llm_answer(message, kb_context, intent=intent, added_from_web=added_from_web)
        # cache (limit)
        if len(self._resp_cache) > 128:
            self._resp_cache.pop(next(iter(self._resp_cache)))
        self._resp_cache[key] = reply
        return reply

    # ----------------- INTERNO -----------------

    def _render_citations(self, added_from_web: List[Dict[str, Any]]) -> str:
        if not added_from_web:
            return ""
        # mostriamo max 3 fonti
        parts = []
        for it in added_from_web[:3]:
            m = it.get("meta", {})
            src = m.get("source", "web")
            url = m.get("source_url", "")
            date = m.get("source_date", "")
            title = m.get("title") or m.get("source_title") or src.capitalize()
            parts.append(f"[{title} — {date}]")
        return "Fonti: " + " | ".join(parts)

    def _llm_answer(self, user_msg: str, kb_context: str, intent: str, added_from_web: List[Dict[str, Any]]) -> str:
        """
        Crea messaggi per OpenAI. Se client assente, fornisce un fallback testuale.
        """
        # Messaggio sistema
        system_msg = self.system_prompt

        # Template intent-driven (se presenti in prompt.json)
        tmpl = None
        if isinstance(self.prompt_json, dict):
            intents = self.prompt_json.get("intents", {})
            if isinstance(intents, dict) and intent in intents:
                intent_obj = intents[intent] or {}
                tmpl = intent_obj.get("template")

        # Costruzione del contenuto utente
        if tmpl:
            user_content = tmpl.replace("{query}", user_msg).replace("{context}", kb_context or "(vuoto)")
        else:
            user_content = f"Domanda: {user_msg}\n\nContesto KB:\n{kb_context or '(vuoto)'}\n\n"

        # Anti-hallucination dall’esempio
        anti = []
        if isinstance(self.prompt_json, dict):
            anti = self.prompt_json.get("anti_hallucination", [])
        hints = "\n".join(f"- {x}" for x in anti[:5])

        assistant_guidelines = (
            "Linee guida anti-allucinazione:\n"
            f"{hints}\n\n"
            "Se mancano fonti recenti, indica cosa manca e proponi aggiornamento.\n"
        )

        # Se non ho client OpenAI, ritorno un fallback testuale
        if not self.openai_client:
            base = "Non ho accesso al modello di generazione in questo momento."
            cites = self._render_citations(added_from_web)
            return base + ("\n" + cites if cites else "")

        messages = [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_content},
            {"role": "system", "content": assistant_guidelines},
        ]

        try:
            resp = self.openai_client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=messages,
            )
            out = (resp.choices[0].message.content or "").strip()
            # aggiungo citazioni web se presenti
            cites = self._render_citations(added_from_web)
            if cites:
                out = out.rstrip() + "\n\n" + cites
            return out or "Non ho trovato abbastanza informazioni per rispondere."
        except Exception as e:
            logger.error(f"[Assistant] Errore OpenAI: {e}")
            cites = self._render_citations(added_from_web)
            return "Servizio momentaneamente non disponibile. Riprova tra poco." + ("\n" + cites if cites else "")

    # ----------------- Correzioni inline (opzionale compat) -----------------

    def _handle_correction_command(self, text: str) -> Dict[str, Any]:
        """
        Supporta l’endpoint /api/inline-correction della tua UI.
        Salva nel KB una mini nota di correzione con TTL breve (7 giorni).
        """
        meta = {
            "type": "correction",
            "source": "user_inline",
            "source_date": time.strftime("%Y-%m-%d"),
            "valid_to": self.web_fb.valid_to_days(7),
            "created_at": time.strftime("%Y-%m-%d"),
        }
        doc_id = self.knowledge_manager.add_knowledge(text=text, metadata=meta)
        return {"saved": True, "id": doc_id, "meta": meta}

    def get_corrections_summary(self) -> Dict[str, Any]:
        # qui potresti interrogare il KM filtrando type='correction' se vuoi
        return {"corrections": [], "total_corrections": 0}
