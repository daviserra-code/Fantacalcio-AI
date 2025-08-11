# fantacalcio_assistant.py
import os
import json
import time
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

# Config opzionale (se presente)
try:
    from config import app_config
except Exception:
    app_config = {}

# OpenAI client (SDK >= 1.0)
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # verrà gestito più sotto

# Knowledge base locale
try:
    from knowledge_manager import KnowledgeManager
except Exception as e:
    KnowledgeManager = None

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ------------------------------------------------------------
# Utility
# ------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now().isoformat()

def _safe_get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    val = os.environ.get(name, default)
    return val if (val is not None and str(val).strip() != "") else default

# ------------------------------------------------------------
# FantacalcioAssistant
# ------------------------------------------------------------
class FantacalcioAssistant:
    """
    Assistente principale:
    - Carica prompt.json (schema: system + intents + anti_hallucination)
    - Integra KnowledgeManager per il contesto RAG
    - Usa OpenAI ChatCompletions (SDK v1) per generare risposte
    - Espone metodi richiesti dalla tua UI
    """

    _init_lock = threading.Lock()
    _initialized_once = False

    def __init__(self,
                 prompt_path: str = "./prompt.json",
                 collection_name: Optional[str] = None):
        with FantacalcioAssistant._init_lock:
            # Evita doppi init in race condition
            if getattr(self, "_is_initialized", False):
                return

            # 1) Prompt
            self.prompt_path = prompt_path
            self.prompt_spec = self._load_prompt(prompt_path)

            # 2) OpenAI
            self.client = self._init_openai()

            # 3) Knowledge Manager (RAG locale)
            self.km = None
            if KnowledgeManager is not None:
                try:
                    # Se hai una collection specifica, passala; altrimenti default interno del KM
                    self.km = KnowledgeManager(collection_name=collection_name or "fantacalcio_knowledge")
                    logger.info("[Assistant] KnowledgeManager attivo")
                except Exception as e:
                    logger.error(f"[Assistant] Errore init KnowledgeManager: {e}")
                    self.km = None
            else:
                logger.warning("[Assistant] KnowledgeManager non disponibile (import fallito)")

            # 4) Stato conversazione / cache
            self.history: List[Dict[str, str]] = []
            self.cache_hits = 0
            self.cache_misses = 0
            self._response_cache: Dict[str, str] = {}
            self._cache_max = int(app_config.get("assistant_cache_max", 64))
            self._corrections: List[Dict[str, Any]] = []

            # 5) Parametri LLM
            self.model = app_config.get("openai_model_primary") or _safe_get_env("OPENAI_MODEL", "gpt-4o-mini")
            self.temperature = float(app_config.get("temperature", 0.3))
            self.max_tokens = int(app_config.get("max_tokens", 600))

            self._is_initialized = True
            FantacalcioAssistant._initialized_once = True
            logger.info("[Assistant] Inizializzazione completata")

    # --------------------------------------------------------
    # Init helpers
    # --------------------------------------------------------
    def _load_prompt(self, path: str) -> Dict[str, Any]:
        """
        Carica prompt.json e valida struttura (system/intents/anti_hallucination).
        NON richiede chiave 'prompt' semplice: usa 'system.content' + sezioni.
        """
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Validazione minima
            if "system" not in data or "content" not in data["system"]:
                raise ValueError("prompt.json deve avere 'system.content'")

            # Campi opzionali
            data.setdefault("intents", {})
            data.setdefault("anti_hallucination", [])

            logger.info("[Assistant] prompt.json caricato correttamente")
            return data
        except Exception as e:
            logger.error(f"[Assistant] Errore caricamento prompt: {e}")
            # Fallback minimale
            return {
                "system": {
                    "name": "fantacalcio_fallback",
                    "content": (
                        "Sei un assistente fantacalcio. Rispondi in italiano e non inventare. "
                        "Se non hai fonti, dichiaralo e proponi di aggiornare i dati."
                    )
                },
                "intents": {},
                "anti_hallucination": [
                    "Non inventare nomi/squadre se non presenti nel contesto.",
                    "Se il contesto è vuoto, proponi l'aggiornamento dati."
                ]
            }

    def _init_openai(self):
        """
        Inizializza client OpenAI (SDK v1). Se non disponibile, ritorna None.
        """
        api_key = _safe_get_env("OPENAI_API_KEY") or app_config.get("openai_api_key")
        if not api_key:
            logger.warning("[Assistant] OPENAI_API_KEY mancante: lavorerò in modalità degradata.")
            return None

        if OpenAI is None:
            logger.error("[Assistant] SDK openai>=1.0 non installato. Installa 'openai>=1.0'.")
            return None

        try:
            client = OpenAI(api_key=api_key)
            return client
        except Exception as e:
            logger.error(f"[Assistant] Errore init OpenAI client: {e}")
            return None

    # --------------------------------------------------------
    # Public API (usata dalla tua web_interface.py)
    # --------------------------------------------------------
    def reset_conversation(self) -> str:
        self.history.clear()
        self._response_cache.clear()
        return "Conversazione resettata!"

    def get_cache_stats(self) -> Dict[str, Any]:
        hit_rate = 0.0
        total = self.cache_hits + self.cache_misses
        if total > 0:
            hit_rate = round(100.0 * self.cache_hits / total, 2)
        return {
            "cache_hits": self.cache_hits,
            "cache_misses": self.cache_misses,
            "hit_rate_percentage": hit_rate,
            "cache_size": len(self._response_cache),
            "max_cache_size": self._cache_max
        }

    def get_corrections_summary(self) -> Dict[str, Any]:
        return {
            "total_corrections": len(self._corrections),
            "corrections": self._corrections[-20:]
        }

    def _handle_correction_command(self, text: str) -> Dict[str, Any]:
        """
        Salva una correzione dell'utente anche in KB (se KM attivo).
        Formato atteso: "Correggi: X -> Y"
        """
        wrong = ""
        correct = ""
        if "->" in text:
            parts = text.split("->", 1)
            wrong = parts[0].replace("Correggi:", "").strip()
            correct = parts[1].strip()

        meta = {
            "type": "correction",
            "wrong": wrong,
            "correct": correct,
            "created_at": _now_iso()
        }
        entry = {"text": f"CORREZIONE: {wrong} -> {correct}", "metadata": meta}
        self._corrections.append(entry)

        # Salva anche in KB come documento "correction"
        if self.km:
            try:
                self.km.add_knowledge(
                    text=entry["text"],
                    metadata=meta
                )
            except Exception as e:
                logger.error(f"[Assistant] Errore salvataggio correzione in KB: {e}")

        return {"saved": True, "wrong": wrong, "correct": correct}

    # --------------------------------------------------------
    # Core: get_response
    # --------------------------------------------------------
    def get_response(self, message: str, context: Optional[Dict[str, Any]] = None) -> str:
        """
        - Recupera contesto dal KB (se disponibile)
        - Costruisce messaggi (system + user)
        - Chiama OpenAI (se configurato), altrimenti risposta statica di fallback
        """
        context = context or {}
        mode = context.get("mode", "classic")

        # Cache semplice (chiave: messaggio + mode)
        cache_key = f"{mode}::{message.strip().lower()}"
        if cache_key in self._response_cache:
            self.cache_hits += 1
            return self._response_cache[cache_key]
        self.cache_misses += 1

        # 1) Estrai intent (semplice euristica su parole chiave)
        intent_key = self._detect_intent(message)

        # 2) Recupera contesto dal KB
        rag_context, citations = self._build_context(message, intent_key=intent_key)

        # 3) Costruisci system prompt
        system_prompt = self._compose_system_prompt(intent_key=intent_key)

        # 4) Costruisci user content
        user_payload = self._compose_user_block(message, rag_context, citations, mode)

        # 5) Se client assente -> fallback
        if self.client is None:
            reply = self._fallback_reply(rag_context, message)
            self._maybe_cache(cache_key, reply)
            return reply

        # 6) Chiama OpenAI ChatCompletions (SDK v1)
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                messages=[
                    {"role": "system", "content": system_prompt},
                    *self.history[-6:],  # breve memoria (se la mantieni)
                    {"role": "user", "content": user_payload},
                ]
            )
            answer = completion.choices[0].message.content.strip()

            # Aggiorna history minima
            self.history.append({"role": "user", "content": message})
            self.history.append({"role": "assistant", "content": answer})

            # Cache
            self._maybe_cache(cache_key, answer)
            return answer

        except Exception as e:
            logger.error(f"[Assistant] Errore OpenAI: {e}")
            reply = self._fallback_reply(rag_context, message)
            self._maybe_cache(cache_key, reply)
            return reply

    # --------------------------------------------------------
    # Builders
    # --------------------------------------------------------
    def _detect_intent(self, message: str) -> Optional[str]:
        m = message.lower()
        # euristiche semplici
        if any(k in m for k in ["infortun", "out", "squalifica", "rientro"]):
            return "injury"
        if any(k in m for k in ["trasfer", "squadra", "gioca oggi", "ha cambiato"]):
            return "transfer"
        if any(k in m for k in ["asta", "conviene", "budget", "crediti", "prezzo"]):
            return "value"
        if any(k in m for k in ["prossime partite", "calendario", "forma", "fixtures"]):
            return "fixtures"
        return None

    def _build_context(self, query: str, intent_key: Optional[str]) -> (str, List[Dict[str, str]]):
        """
        Recupera contesto dal KB. Ritorna:
        - context_text (stringa pronta per il prompt)
        - citations (lista di dict per eventuale uso nel rendering)
        """
        if not self.km:
            return "", []

        # numero di passaggi RAG
        n = 8
        results = []
        try:
            results = self.km.search_knowledge(query, n_results=n)
        except Exception as e:
            logger.error(f"[Assistant] Errore search_knowledge: {e}")
            results = []

        if not results:
            return "", []

        parts = []
        citations = []
        for r in results[:n]:
            txt = r.get("text", "")
            meta = r.get("metadata", {})
            score = r.get("cosine_similarity", 0.0)
            date = meta.get("date") or meta.get("source_date") or meta.get("valid_to") or meta.get("valid_from") or "ND"
            title = meta.get("title") or meta.get("player") or meta.get("team") or "Interno KB"
            parts.append(f"- {txt} [sim={score:.3f}]")
            citations.append({
                "title": str(title),
                "date": str(date),
                "source": "Interno KB"
            })

        context_text = "Contesto dal KB:\n" + "\n".join(parts)
        return context_text, citations

    def _compose_system_prompt(self, intent_key: Optional[str]) -> str:
        system = self.prompt_spec.get("system", {})
        content = system.get("content", "").strip()

        ah_rules = self.prompt_spec.get("anti_hallucination", [])
        ah_text = ""
        if ah_rules:
            bullets = "\n".join([f"- {r}" for r in ah_rules])
            ah_text = "\n\nRegole anti-hallucination:\n" + bullets

        # Se esiste un intent specifico, aggiungi le sue istruzioni
        intent_text = ""
        if intent_key and intent_key in self.prompt_spec.get("intents", {}):
            intent_def = self.prompt_spec["intents"][intent_key]
            inst = intent_def.get("instruction", "")
            if inst:
                intent_text = f"\n\nIstruzioni per intento '{intent_key}':\n{inst}"

        return f"{content}{intent_text}{ah_text}"

    def _compose_user_block(self, message: str, rag_context: str, citations: List[Dict[str, str]], mode: str) -> str:
        # Template: se esiste un intento con template, usalo
        intent_key = self._detect_intent(message)
        intent_template = None
        if intent_key and intent_key in self.prompt_spec.get("intents", {}):
            intent_template = self.prompt_spec["intents"][intent_key].get("template")

        base = f"Modalità: {mode}\nDomanda utente: {message}".strip()
        ctx = rag_context or "(nessun contesto trovabile nel KB)"

        if intent_template:
            # Sostituzioni semplici
            user_block = intent_template.replace("{query}", message).replace("{context}", ctx)
        else:
            user_block = f"{base}\n\n{ctx}\n\nCita sempre le fonti disponibili (titolo + data)."

        # Aggiungi elenco fonti (testo) come hint
        if citations:
            fonti = "; ".join([f"[{c['title']} — {c['date']}]" for c in citations[:5]])
            user_block += f"\n\nFonti KB (se rilevanti): {fonti}"

        return user_block

    def _fallback_reply(self, rag_context: str, message: str) -> str:
        """
        Risposta di riserva quando OpenAI non è disponibile o fallisce.
        Onesta e allineata alle regole anti-hallucination.
        """
        if not rag_context:
            return "Non ho fonti nel mio database. Puoi aggiornare i dati o specificare meglio la domanda?"
        # Se almeno abbiamo del contesto, restituiamo un riassunto minimale
        lines = [ln.strip("- ").strip() for ln in rag_context.splitlines() if ln.startswith("- ")]
        snippet = lines[0] if lines else "Ho pochi dati nel KB."
        return f"In base alle informazioni presenti nel KB: {snippet}"

    def _maybe_cache(self, key: str, value: str):
        try:
            if len(self._response_cache) >= self._cache_max:
                # drop FIFO
                oldest = next(iter(self._response_cache.keys()))
                self._response_cache.pop(oldest, None)
            self._response_cache[key] = value
        except Exception:
            pass
