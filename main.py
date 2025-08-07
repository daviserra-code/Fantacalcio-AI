import openai
import os
import sys
import json
import logging
from datetime import datetime
from knowledge_manager import KnowledgeManager
from corrections_manager import CorrectionsManager

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

openai.api_key = os.environ.get('OPENAI_API_KEY', '')

if not openai.api_key:
    sys.stderr.write("""
    Devi configurare la tua API key OpenAI.

    Vai su: https://platform.openai.com/signup
    1. Crea un account o accedi
    2. Clicca "View API Keys" 
    3. Clicca "Create new secret key"

    Poi apri il tool Secrets e aggiungi OPENAI_API_KEY come secret.
    """)
    exit(1)

class FantacalcioAssistant:
    def __init__(self):
        try:
            # Initialize knowledge manager for RAG
            print("🔄 Initializing knowledge manager...")
            self.knowledge_manager = KnowledgeManager()
            print("✅ Knowledge manager initialized")

            # Initialize corrections manager (using ChromaDB)
            print("🔄 Initializing corrections manager...")
            self.corrections_manager = KnowledgeManager(collection_name="corrections")
            print("✅ Corrections manager initialized")
        except Exception as e:
            print(f"❌ Failed to initialize managers: {e}")
            # Create minimal fallback managers
            self.knowledge_manager = None
            self.corrections_manager = None

        # Load training data once at startup
        self._load_training_data()
        
        # Skip model verification in production for faster startup
        
        # Response cache with TTL (Time To Live)
        self.response_cache = {}
        self.cache_ttl = {}
        self.cache_max_size = 50
        self.cache_duration = 180
        self.cache_stats = {'hits': 0, 'misses': 0}

        self.system_prompt = """
        Sei un assistente virtuale per fantacalcio Serie A. Il tuo nome è Fantacalcio AI.
        
        REGOLE FONDAMENTALI:
        1. PRIMA prova sempre a rispondere usando le informazioni dal database quando disponibili
        2. SE hai dati specifici dal database, usali con fiducia e precisione
        3. SE non hai dati specifici ma hai informazioni correlate, utilizzale come base per dare consigli utili
        4. SOLO se non hai proprio nessuna informazione rilevante, specifica che non hai dati aggiornati
        5. NON inventare mai statistiche precise, prezzi esatti o trasferimenti confermati

        APPROCCIO PREFERITO:
        - Usa sempre i dati dal database quando presenti (fantamedia, prezzi, presenze)
        - Fornisci consigli strategici basati sui principi del fantacalcio
        - Combina dati disponibili con logiche di gioco consolidate
        - Aiuta sempre l'utente con strategie pratiche

        QUANDO NON HAI DATI SPECIFICI:
        - Fornisci comunque consigli strategici generali utili
        - Spiega criteri di valutazione e principi del fantacalcio
        - Suggerisci approcci per budget e formazioni
        - Dai indicazioni su ruoli e tattiche

        COMPITI PRINCIPALI:
        - Consigli per aste e gestione rose
        - Assistenza su regole e strategie
        - Suggerimenti su budget e formazioni
        - Supporto per tutte le modalità (Classic, Mantra, Draft, Superscudetto)

        STILE: Utile e pratico, sempre pronto ad aiutare con consigli concreti.
        """

        self.conversation_history = []

    def _load_training_data(self):
        """Load training data once at startup"""
        if not self.knowledge_manager:
            print("⚠️ Knowledge manager not available, skipping training data load")
            return
            
        training_loaded = False

        # Try loading main training data
        try:
            self.knowledge_manager.load_from_jsonl("training_data.jsonl")
            training_loaded = True
            print("✅ Main training data loaded")
        except Exception as e:
            print(f"⚠️ Could not load training_data.jsonl: {e}")

        # Try loading extended training data as fallback
        try:
            self.knowledge_manager.load_from_jsonl("extended_training_data.jsonl")
            print("✅ Extended training data loaded")
        except Exception as e:
            print(f"⚠️ Could not load extended_training_data.jsonl: {e}")
            if not training_loaded:
                print("⚠️ Running with limited knowledge base")

    def get_response(self, user_message, context=None):
        """Get AI response for fantasy football queries with RAG"""

        # Check if this is a correction command
        if user_message.lower().startswith("correggi:") or user_message.lower().startswith("correzione:"):
            return self._handle_correction_command(user_message)

        # TTL-based response cache for better performance
        cache_key = f"{user_message.lower().strip()}_{json.dumps(context, sort_keys=True) if context else ''}"
        current_time = datetime.now().timestamp()

        # Check if cache entry exists and is still valid
        if cache_key in self.response_cache and cache_key in self.cache_ttl:
            if current_time - self.cache_ttl[cache_key] < self.cache_duration:
                self.cache_stats['hits'] += 1
                return self.response_cache[cache_key]
            else:
                # Cache expired, remove it
                del self.response_cache[cache_key]
                del self.cache_ttl[cache_key]

        messages = [{"role": "system", "content": self.system_prompt}]

        # Get relevant knowledge from vector database (data already loaded at startup)
        print(f"\n🔍 QUERY: {user_message}")
        relevant_context = None
        if self.knowledge_manager:
            try:
                relevant_context = self.knowledge_manager.get_context_for_query(user_message)
            except Exception as e:
                print(f"⚠️ Knowledge search failed: {e}")
                relevant_context = None
        
        if relevant_context:
            # Provide context but allow strategic reasoning
            validated_context = f"""
            INFORMAZIONI DISPONIBILI DAL DATABASE:
            {relevant_context}
            
            ISTRUZIONI: Usa queste informazioni come base per la tua risposta. 
            Se i dati sono sufficienti, fornisci consigli dettagliati.
            Se i dati sono parziali, integra con principi strategici del fantacalcio.
            Aiuta sempre l'utente con consigli pratici e utili.
            """
            messages.append({"role": "system", "content": validated_context})
        else:
            # Even without specific data, provide helpful strategic advice
            fallback_context = """
            MODALITÀ STRATEGICA: Non hai dati specifici dal database per questa query.
            Fornisci comunque consigli strategici utili basati sui principi del fantacalcio,
            criteri di valutazione generali, e best practices per aste e gestione rosa.
            Sii sempre utile e pratico nelle tue risposte.
            """
            messages.append({"role": "system", "content": fallback_context})

        # Add context if provided (league info, budget, etc.)
        if context:
            context_msg = f"Contesto attuale: {json.dumps(context, ensure_ascii=False)}"
            messages.append({"role": "system", "content": context_msg})

        # Add conversation history (last 6 messages to manage token usage)
        messages.extend(self.conversation_history[-6:])

        # Add current user message
        messages.append({"role": "user", "content": user_message})

        try:
            # Always use gpt-4o-mini for faster responses
            model = "gpt-4o-mini"

            response = openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.05,  # Lower temperature for more factual responses
                max_tokens=400,    # Slightly increased for complete answers
                timeout=15,
                stream=False,
                # Add system-level constraints
                frequency_penalty=0.1,  # Reduce repetition
                presence_penalty=0.1    # Encourage diverse vocabulary
            )

            ai_response = response.choices[0].message.content

            # Apply corrections from ChromaDB
            ai_response = self._apply_corrections_from_chromadb(ai_response)

            # Cache response with TTL
            self.cache_stats['misses'] += 1

            # Manage cache size - remove oldest entries if cache is full
            if len(self.response_cache) >= self.cache_max_size:
                oldest_key = min(self.cache_ttl.keys(), key=lambda k: self.cache_ttl[k])
                del self.response_cache[oldest_key]
                del self.cache_ttl[oldest_key]

            # Store in cache with timestamp
            self.response_cache[cache_key] = ai_response
            self.cache_ttl[cache_key] = current_time

            # Update conversation history
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": ai_response})

            return ai_response

        except Exception as e:
            return f"Errore nel processare la richiesta: {str(e)}"

    def reset_conversation(self):
        """Reset conversation history"""
        self.conversation_history = []
        return "Conversazione resettata. Pronto per nuove domande sul fantacalcio."

    def get_cache_stats(self):
        """Get cache performance statistics"""
        total_requests = self.cache_stats['hits'] + self.cache_stats['misses']
        hit_rate = (self.cache_stats['hits'] / total_requests * 100) if total_requests > 0 else 0

        return {
            'cache_hits': self.cache_stats['hits'],
            'cache_misses': self.cache_stats['misses'],
            'hit_rate_percentage': round(hit_rate, 2),
            'cache_size': len(self.response_cache),
            'max_cache_size': self.cache_max_size
        }

    def add_correction(self, incorrect_info: str, correct_info: str, 
                      correction_type: str = "general", context: str = None):
        """Add a new correction to the persistent system"""
        return self.corrections_manager.add_correction(
            correction_type, incorrect_info, correct_info, context
        )

    def add_player_correction(self, player_name: str, field_name: str, 
                            old_value: str, new_value: str, reason: str = None):
        """Add a player data correction"""
        return self.corrections_manager.add_player_correction(
            player_name, field_name, old_value, new_value, reason
        )

    def _handle_correction_command(self, message):
        """Handle correction commands from chat"""
        # Format: "Correggi: [wrong info] -> [correct info]"
        try:
            if "->" in message:
                parts = message.split(":", 1)[1].split("->")
                if len(parts) == 2:
                    wrong_info = parts[0].strip()
                    correct_info = parts[1].strip()

                    # Store correction in ChromaDB
                    correction_text = f"CORREZIONE: Sostituisci '{wrong_info}' con '{correct_info}'"
                    correction_id = self.corrections_manager.add_knowledge(
                        correction_text,
                        {
                            "type": "correction",
                            "wrong": wrong_info,
                            "correct": correct_info,
                            "created_at": datetime.now().isoformat()
                        }
                    )

                    return f"✅ Correzione aggiunta con successo! ID: {correction_id[:8]}...\nDa ora in poi sostituirò '{wrong_info}' con '{correct_info}'"

            return "❌ Formato correzione non valido. Usa: 'Correggi: [info errata] -> [info corretta]'"

        except Exception as e:
            return f"❌ Errore nell'aggiungere la correzione: {str(e)}"

    def _apply_corrections_from_chromadb(self, text):
        """Apply corrections stored in ChromaDB"""
        if not self.corrections_manager:
            return text
            
        try:
            # Search for relevant corrections
            corrections = self.corrections_manager.search_knowledge("CORREZIONE", n_results=10)

            corrected_text = text
            applied_count = 0

            for correction in corrections:
                if correction['metadata'].get('type') == 'correction':
                    wrong = correction['metadata'].get('wrong', '')
                    correct = correction['metadata'].get('correct', '')

                    if wrong and correct and wrong.lower() in corrected_text.lower():
                        # Case insensitive replacement
                        import re
                        corrected_text = re.sub(re.escape(wrong), correct, corrected_text, flags=re.IGNORECASE)
                        applied_count += 1

            if applied_count > 0:
                print(f"📝 Applied {applied_count} corrections to response")

            return corrected_text

        except Exception as e:
            print(f"⚠️ Error applying corrections: {e}")
            return text

    def get_corrections_summary(self):
        """Get corrections system summary"""
        try:
            corrections = self.corrections_manager.search_knowledge("CORREZIONE", n_results=50)
            correction_corrections = [c for c in corrections if c['metadata'].get('type') == 'correction']

            return {
                'total_corrections': len(correction_corrections),
                'corrections': correction_corrections[:10]  # Return first 10
            }
        except:
            return {'total_corrections': 0, 'corrections': []}

    def reset_and_rebuild_database(self):
        """Reset ChromaDB and rebuild from JSONL files"""
        print("🔄 STARTING DATABASE RESET AND REBUILD...")
        
        # Reset main knowledge database
        if self.knowledge_manager.reset_database():
            # Rebuild from JSONL files
            jsonl_files = ["training_data.jsonl", "extended_training_data.jsonl"]
            total_loaded = self.knowledge_manager.rebuild_database_from_jsonl(jsonl_files)
            
            # Reset corrections database
            if self.corrections_manager.reset_database():
                print("✅ Corrections database also reset")
            
            # Verify the rebuild worked
            print("\n🔍 VERIFYING REBUILD...")
            self.knowledge_manager.verify_embedding_consistency()
            
            return f"✅ Database reset and rebuild complete! Loaded {total_loaded} entries from JSONL files."
        else:
            return "❌ Database reset failed"

def main():
    assistant = FantacalcioAssistant()

    print("🏆 ASSISTENTE FANTACALCIO PROFESSIONALE")
    print("=" * 50)
    print("Supporto per: Classic, Mantra, Draft, Superscudetto")
    print("Comandi: 'reset' per resettare, 'quit' per uscire")
    print("=" * 50)

    while True:
        try:
            user_input = input("\n💬 La tua domanda: ").strip()

            if user_input.lower() in ['quit', 'exit', 'esci']:
                print("👋 Buona fortuna con il fantacalcio!")
                break

            if user_input.lower() == 'reset':
                print(assistant.reset_conversation())
                continue

            if user_input.lower() == 'reset-db':
                print(assistant.reset_and_rebuild_database())
                continue

            if not user_input:
                continue

            # Example context - in a real app this would come from user profile/league settings
            context = {
                "timestamp": datetime.now().isoformat(),
                "session_type": "consultation"
            }

            print("\n🤔 Elaborando risposta...")
            response = assistant.get_response(user_input, context)
            print(f"\n🎯 {response}")

        except KeyboardInterrupt:
            print("\n\n👋 Sessione terminata. Buona fortuna!")
            break
        except Exception as e:
            print(f"\n❌ Errore: {str(e)}")

if __name__ == "__main__":
    main()