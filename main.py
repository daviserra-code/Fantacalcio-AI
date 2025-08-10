import os
import re
import traceback
from typing import List, Optional, Dict, Any

from knowledge_manager import KnowledgeManager
from retrieval.helpers import dump_chroma_texts_ids
from retrieval.rag_pipeline import RAGPipeline

# ====== opzionale: OpenAI per la generazione ======
def openai_chat(system_prompt: str, user_prompt: str) -> str:
    """
    Usa OpenAI se OPENAI_API_KEY e' presente; altrimenti risponde con un fallback
    che riporta solo parte del contesto per evitare allucinazioni.
    Sostituisci con la tua funzione se vuoi.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return ("[No LLM configurato] Riassunto contesto:\n\n" + user_prompt[:1200])
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=700,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"[Errore generazione] {e}"


class ChatAssistant:
    """
    Assistente principale. Espone:
    - answer(msg) -> dict {ok, message, citations}
    - get_response(msg, *args, **kwargs) -> str   (retro-compat)
    - get_cache_stats() -> dict
    - clear_cache() -> bool
    """
    def __init__(self, collection_name: Optional[str] = None, season_default: Optional[str] = None):
        self.collection_name = collection_name or os.environ.get("CHROMA_COLLECTION", "fantacalcio_knowledge")
        self.season_default  = season_default  or os.environ.get("SEASON_DEFAULT", "2025-26")

        # Inizializza KnowledgeManager e Chroma collection
        self.knowledge_manager = KnowledgeManager(collection_name=self.collection_name)

        # Costruisci RAGPipeline
        try:
            texts, ids = dump_chroma_texts_ids(self.knowledge_manager.collection)
            self.rag = RAGPipeline(self.knowledge_manager.collection, texts, ids)
            print(f"[RAG] Pipeline inizializzata. Collection='{self.collection_name}', documenti indicizzati: {len(ids)}")
        except Exception as e:
            print("[RAG] Init fallita:", e)
            traceback.print_exc()
            self.rag = None

    @staticmethod
    def _build_prompts(user_message: str, context_chunks: List[str]):
        context = "\n\n---\n\n".join(chunk.strip() for chunk in context_chunks if chunk and chunk.strip())
        system_rules = (
            "Sei un assistente per il fantacalcio. "
            "Rispondi SOLO usando il contesto fornito. "
            "Se il contesto non basta, di che non lo sai. "
            "Rispondi in modo conciso, poi aggiungi esattamente due motivi (bullet). "
            "Non inventare dati o trasferimenti. "
            "Chiudi con 2-3 fonti tra parentesi quadre nel formato: [Titolo — AAAA-MM-GG]."
        )
        user_prompt = (
            "Contesto:\n" + (context if context else "(nessun contesto)") + "\n\n"
            "Domanda: " + user_message + "\n"
            "Fornisci una risposta concisa e due motivi in elenco puntato."
        )
        return system_rules, user_prompt

    def _maybe_player_query(self, q: str) -> bool:
        # euristica minimale: almeno una parola con iniziale maiuscola -> probabile entita'
        toks = [t for t in re.split(r"[^A-Za-zÀ-ÿ']", q) if t]
        caps = [t for t in toks if t[:1].isupper()]
        return len(caps) >= 1

    def _covers_entity(self, user_message: str, items: list) -> bool:
        """
        Considera "grounded" solo se almeno uno dei documenti recuperati
        contiene l'entita' nominata nella query (nel testo o nei metadati).
        """
        toks = [t for t in re.findall(r"[A-Za-zÀ-ÿ']+", user_message) if t[:1].isupper()]
        if not toks:
            return True  # domanda generica
        qnames = set(t.lower() for t in toks)
        for it in items or []:
            meta = (it.get("metadata") or {})
            text = (it.get("text") or "")
            fields = " ".join(str(meta.get(k, "")) for k in ("player", "title", "team", "type"))
            blob = (text + " " + fields).lower()
            if any(n in blob for n in qnames):
                return True
        return False

    def _fallback_live_player(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Usa Wikipedia/Wikidata per ricavare squadra attuale se la KB non copre l'entita'.
        Ritorna un "documento" temporaneo {text, metadata} o None.
        """
        try:
            from live_sources import fetch_player_current_team
        except Exception:
            return None

        name_guess = " ".join([w for w in re.findall(r"[A-Za-zÀ-ÿ']+", user_message) if w[:1].isupper()]) or user_message
        try:
            live = fetch_player_current_team(name_guess, lang="it")
        except Exception:
            live = None
        if live and live.get("team"):
            txt = f"{name_guess} attualmente gioca nel {live['team']}."
            meta = {
                "title": f"Profilo {name_guess}",
                "date": live.get("date"),
                "source": live.get("source_url") or "internal://live",
                "team": live["team"],
                "player": name_guess,
                "type": "live_web",
            }
            return {"text": txt, "metadata": meta}
        return None

    def answer(self, user_message: str) -> dict:
        # SEASON permissiva: se env e' "*" o vuota, niente filtro
        season_env = (self.season_default or "").strip()
        season_arg = season_env if season_env and season_env != "*" else None

        top_docs, citations = [], []
        rag_out = None

        # 0) Retrieval RAG interno
        if self.rag is not None:
            rag_out = self.rag.retrieve(user_message, season=season_arg, final_k=8)
            # grounded solo se ci sono fonti e coprono l'entita' richiesta
            if rag_out.get("grounded", False) and self._covers_entity(user_message, rag_out.get("results", [])):
                top_docs = rag_out.get("results", [])
                citations = rag_out.get("citations", [])

        # 1) Fallback live se il RAG non e' grounded o non ha trovato nulla di pertinente
        if not top_docs and self._maybe_player_query(user_message):
            live_doc = self._fallback_live_player(user_message)
            if live_doc:
                top_docs = [live_doc]
                citations.append({
                    "title": live_doc["metadata"].get("title", "Profilo"),
                    "date":  live_doc["metadata"].get("date"),
                    "url":   live_doc["metadata"].get("source", "internal://live"),
                })

        # 2) Se ancora vuoto, risposta onesta
        if not top_docs:
            return {
                "ok": False,
                "message": ("Non ho fonti sufficienti. Vuoi che provi una ricerca web mirata (Wikipedia/Wikidata) "
                            "o che aggiorniamo la base di conoscenza?"),
                "citations": citations,
                "conflicts": rag_out.get("conflicts", {}) if rag_out else {}
            }

        # 3) Costruisci prompt + genera
        context_chunks = [d.get("text") or "" for d in top_docs]
        system_rules, user_prompt = self._build_prompts(user_message, context_chunks)
        text = openai_chat(system_rules, user_prompt)

        if citations:
            cites_str = " | ".join("[{} — {}]".format(c["title"], c["date"]) for c in citations[:3])
            text = text.rstrip() + "\n\nFonti: " + cites_str

        return {"ok": True, "message": text, "citations": citations}

    # Retro-compat: alcune UI chiamano get_response(msg, session_id, ...)
    def get_response(self, user_message: str, *args, **kwargs) -> str:
        out = self.answer(user_message)
        return out.get("message", "")

    # Statistiche per la tua UI
    def get_cache_stats(self) -> dict:
        """
        Ritorna statistiche utili:
        - chroma_docs: numero di documenti nella collection
        - bm25_docs:   numero di doc indicizzati in BM25 (se presente)
        - embed_cache_entries: righe nella cache SQLite degli embeddings (se disponibile)
        - embed_model: nome modello per embeddings
        """
        stats = {
            "chroma_docs": 0,
            "bm25_docs": 0,
            "embed_cache_entries": 0,
            "embed_model": None,
        }
        try:
            stats["chroma_docs"] = self.knowledge_manager.count()
        except Exception:
            pass

        try:
            if getattr(self, "rag", None) and getattr(self.rag, "bm25", None):
                stats["bm25_docs"] = len(self.rag.bm25.doc_ids or [])
        except Exception:
            pass

        try:
            if getattr(self, "rag", None) and getattr(self.rag, "embedder", None):
                stats["embed_model"] = getattr(self.rag.embedder, "model", None)
                cache = getattr(self.rag.embedder, "cache", None)
                if cache and hasattr(cache, "conn"):
                    cur = cache.conn.execute("SELECT COUNT(*) FROM cache")
                    stats["embed_cache_entries"] = int(cur.fetchone()[0])
        except Exception:
            pass

        return stats

    def clear_cache(self) -> bool:
        """
        Svuota la cache SQLite degli embeddings (HFEmbedder).
        Non tocca Chroma ne' BM25.
        """
        try:
            if getattr(self, "rag", None) and getattr(self.rag, "embedder", None):
                cache = getattr(self.rag.embedder, "cache", None)
                if cache and hasattr(cache, "conn"):
                    cache.conn.execute("DELETE FROM cache")
                    cache.conn.commit()
                    try:
                        cache.conn.execute("VACUUM")
                    except Exception:
                        pass
            return True
        except Exception:
            return False


# --- Back-compat per web_interface: mantiene il vecchio nome classe ---
class FantacalcioAssistant(ChatAssistant):
    pass


# Factory comoda per web_interface
def get_assistant(collection_name: Optional[str] = None, season_default: Optional[str] = None) -> ChatAssistant:
    return ChatAssistant(collection_name=collection_name, season_default=season_default)