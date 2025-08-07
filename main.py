import openai
import os
import sys
import json
import logging
from datetime import datetime
from knowledge_manager import KnowledgeManager

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
            # Initialize knowledge manager for RAG with proper error handling
            print("🔄 Initializing knowledge manager...")
            self.knowledge_manager = KnowledgeManager()
            
            # Comprehensive embedding recovery system
            if self.knowledge_manager.embedding_disabled:
                print("🔧 Attempting comprehensive embedding recovery...")
                
                # Step 1: Reset embedding system completely
                self.knowledge_manager.embedding_disabled = False
                self.knowledge_manager.embedding_model = None
                
                recovery_successful = False
                
                # Step 2: Try to reinitialize embedding model
                try:
                    import torch
                    from sentence_transformers import SentenceTransformer
                    
                    # Clear all torch settings
                    if hasattr(torch, '_default_device'):
                        torch._default_device = None
                    if hasattr(torch, 'cuda') and torch.cuda.is_available():
                        torch.cuda.empty_cache()
                    
                    # Multiple initialization attempts
                    init_methods = [
                        lambda: SentenceTransformer('all-MiniLM-L6-v2', device='cpu'),
                        lambda: SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', device='cpu'),
                        lambda: SentenceTransformer('all-MiniLM-L6-v2')
                    ]
                    
                    for i, method in enumerate(init_methods):
                        try:
                            print(f"   Recovery attempt {i+1}/3...")
                            self.knowledge_manager.embedding_model = method()
                            test_embed = self.knowledge_manager.embedding_model.encode("test recovery", show_progress_bar=False)
                            if len(test_embed) > 0:
                                print(f"✅ Embedding model recovered with method {i+1}")
                                recovery_successful = True
                                break
                        except Exception as method_error:
                            print(f"   Method {i+1} failed: {method_error}")
                            continue
                    
                    if not recovery_successful:
                        raise Exception("All embedding recovery methods failed")
                        
                except Exception as embed_error:
                    print(f"⚠️ Embedding model recovery failed: {embed_error}")
                
                # Step 3: Fix collection if embedding model is working
                if recovery_successful:
                    try:
                        import time
                        recovery_name = f"fantacalcio_recovered_{int(time.time())}"
                        
                        # Reset database and create fresh collection
                        print("🔄 Creating fresh database...")
                        self.knowledge_manager.client.reset()
                        
                        self.knowledge_manager.collection = self.knowledge_manager.client.create_collection(
                            name=recovery_name,
                            metadata={"description": "Fantacalcio knowledge base for RAG - Recovered"}
                        )
                        self.knowledge_manager.collection_name = recovery_name
                        self.knowledge_manager.collection_is_empty = True
                        
                        # Test the complete system
                        test_doc_id = self.knowledge_manager.add_knowledge(
                            "Test recovery document - Lautaro Martinez fantamedia test",
                            {"type": "recovery_test"}
                        )
                        
                        # Verify search works
                        test_results = self.knowledge_manager.search_knowledge("Lautaro Martinez", n_results=1)
                        
                        if test_results and len(test_results) > 0:
                            print("✅ Complete embedding system recovery successful!")
                            print(f"   Collection: {recovery_name}")
                            print(f"   Test search returned {len(test_results)} results")
                        else:
                            raise Exception("Search test failed")
                            
                    except Exception as collection_error:
                        print(f"❌ Collection recovery failed: {collection_error}")
                        self.knowledge_manager.embedding_disabled = True
                else:
                    print("❌ Embedding recovery failed - disabling embeddings")
                    self.knowledge_manager.embedding_disabled = True
            
            print("✅ Knowledge manager initialized")

            # Initialize corrections manager (using ChromaDB)
            print("🔄 Initializing corrections manager...")
            from corrections_manager import CorrectionsManager
            self.corrections_manager = CorrectionsManager(self.knowledge_manager)
            print("✅ Corrections manager initialized")
        except Exception as e:
            print(f"❌ Failed to initialize managers: {e}")
            print("🔄 Running in degraded mode without vector search")
            # Create minimal fallback managers
            self.knowledge_manager = None
            from corrections_manager import CorrectionsManager
            self.corrections_manager = CorrectionsManager(None)

        # Load training data once at startup
        self._load_training_data()
        
        # Update knowledge base with current Serie A data
        self._update_serie_a_data()
        
        # Skip model verification in production for faster startup
        
        # Response cache with TTL (Time To Live)
        self.response_cache = {}
        self.cache_ttl = {}
        self.cache_max_size = 50
        self.cache_duration = 180
        self.cache_stats = {'hits': 0, 'misses': 0}

        self.system_prompt = """
        Sei un assistente virtuale ESPERTO per fantacalcio Serie A 2024-25. Il tuo nome è Fantacalcio AI.
        
        REGOLE CRITICHE PER ACCURATEZZA:
        1. USA SOLO dati verificati dal database quando disponibili - sono SEMPRE corretti e aggiornati
        2. Se NON hai dati dal database, dillo chiaramente e fornisci consigli strategici generali
        3. NON inventare MAI statistiche specifiche, prezzi o fantamedie se non nel database
        4. Per giocatori come Handanovic e Donnarumma che non giocano più in Serie A, specificalo
        5. I dati del database sono per la stagione 2024-25 ATTUALE

        DATI VERIFICATI STAGIONE 2024-25:
        - Lautaro Martinez (Inter): fantamedia 8.1, 44 crediti - MIGLIOR ATTACCANTE
        - Mike Maignan (Milan): fantamedia 6.8, 24 crediti - MIGLIOR PORTIERE
        - Yann Sommer (Inter): fantamedia 6.6, 20 crediti - AFFIDABILE
        - Nicolo Barella (Inter): fantamedia 7.5, 32 crediti - TOP CENTROCAMPISTA

        GIOCATORI NON PIÙ IN SERIE A 2024-25:
        - Samir Handanovic: RITIRATO
        - Gianluigi Donnarumma: PSG (Francia)
          - Victor Osimhen Galatasaray   (Turchia))

        PRIORITÀ CONSIGLI:
        1. Usa i dati verificati per consigli precisi
        2. Per budget 150 crediti attaccanti: cerca giocatori 35-40 crediti
        3. Portieri: Maignan (24) o Sommer (20) sono le scelte top
        4. Sempre considera continuità presenze oltre alla fantamedia

        STILE: Preciso, basato su dati reali, pratico per vincere al fantacalcio.
        """

        self.conversation_history = []

    def _load_training_data(self):
        """Load training data once at startup"""
        if not self.knowledge_manager:
            print("⚠️ Knowledge manager not available, skipping training data load")
            return
            
        # Check if embeddings are working
        if self.knowledge_manager.embedding_disabled:
            print("⚠️ Embeddings disabled, cannot load training data")
            return
            
        training_loaded = False

        # Try loading main training data
        try:
            print("🔄 Loading main training data...")
            self.knowledge_manager.load_from_jsonl("training_data.jsonl")
            training_loaded = True
            print("✅ Main training data loaded")
            
            # Verify data was actually loaded
            if self.knowledge_manager.collection:
                count = self.knowledge_manager.collection.count()
                print(f"📊 Collection now has {count} documents")
                if count == 0:
                    print("⚠️ No documents in collection after loading")
                    
        except Exception as e:
            print(f"⚠️ Could not load training_data.jsonl: {e}")

        # Try loading extended training data as fallback
        try:
            print("🔄 Loading extended training data...")
            self.knowledge_manager.load_from_jsonl("extended_training_data.jsonl")
            print("✅ Extended training data loaded")
            
            if self.knowledge_manager.collection:
                count = self.knowledge_manager.collection.count()
                print(f"📊 Collection now has {count} total documents")
                
        except Exception as e:
            print(f"⚠️ Could not load extended_training_data.jsonl: {e}")
            if not training_loaded:
                print("⚠️ Running with limited knowledge base")
                
        # Final verification
        if self.knowledge_manager.collection:
            final_count = self.knowledge_manager.collection.count()
            if final_count > 0:
                print(f"✅ Knowledge base loaded successfully with {final_count} documents")
                self.knowledge_manager.collection_is_empty = False
            else:
                print("❌ Knowledge base is empty after loading attempts")

    def _update_serie_a_data(self):
        """Update knowledge base with current Serie A data"""
        try:
            from serie_a_data_collector import SerieADataCollector
            collector = SerieADataCollector()
            # This will add current season data to the knowledge manager
            collector.update_knowledge_base()
            print("✅ Serie A data updated with real player information")
            
            # Also load additional real player data
            self._load_real_player_data()
        except Exception as e:
            print(f"⚠️ Could not update Serie A data: {e}")
            # Load minimal real data as fallback
            self._load_minimal_real_data()
    
    def _load_real_player_data(self):
        """Load comprehensive real player data into knowledge base"""
        real_players_data = [
            "Lautaro Martinez dell'Inter ha fantamedia 8.1 nella stagione 2024-25, costa 44 crediti ed è il miglior attaccante per affidabilità",
            "Victor Osimhen del Napoli ha fantamedia 8.2 nella stagione 2024-25, costa 45 crediti ma è a rischio trasferimento",
            "Dusan Vlahovic della Juventus ha fantamedia 7.8 nella stagione 2024-25, costa 42 crediti ed è il rigorista titolare",
            "Khvicha Kvaratskhelia del Napoli ha fantamedia 7.9 nella stagione 2024-25, costa 41 crediti ed è molto decisivo",
            "Rafael Leao del Milan ha fantamedia 7.6 nella stagione 2024-25, costa 40 crediti ma è discontinuo",
            "Nicolo Barella dell'Inter ha fantamedia 7.5 nella stagione 2024-25, costa 32 crediti ed è il miglior centrocampista",
            "Hakan Calhanoglu dell'Inter ha fantamedia 7.1 nella stagione 2024-25, costa 29 crediti ed è rigorista e punizioni",
            "Theo Hernandez del Milan ha fantamedia 7.2 nella stagione 2024-25, costa 32 crediti ed è il miglior terzino",
            "Alessandro Bastoni dell'Inter ha fantamedia 7.0 nella stagione 2024-25, costa 30 crediti e fa assist da difensore",
            "Mike Maignan del Milan ha fantamedia 6.8 nella stagione 2024-25, costa 24 crediti ed è il portiere più affidabile"
        ]
        
        if self.knowledge_manager:
            for player_info in real_players_data:
                try:
                    self.knowledge_manager.add_knowledge(player_info, {
                        "type": "real_player_2024_25",
                        "season": "2024-25",
                        "source": "current_data"
                    })
                except Exception as e:
                    print(f"⚠️ Failed to add player data: {e}")
    
    def _load_minimal_real_data(self):
        """Load minimal real data as fallback when full update fails"""
        minimal_data = [
            "Lautaro Martinez è il miglior attaccante della Serie A 2024-25 con fantamedia 8.1, costa 44 crediti",
            "Victor Osimhen del Napoli ha la fantamedia più alta tra gli attaccanti: 8.2, costa 45 crediti",
            "Dusan Vlahovic della Juventus ha fantamedia 7.8, costa 42 crediti ed è il rigorista",
            "Khvicha Kvaratskhelia del Napoli ha fantamedia 7.9, costa 41 crediti",
            "Rafael Leao del Milan ha fantamedia 7.6, costa 40 crediti ma è discontinuo",
            "Nicolo Barella dell'Inter è il centrocampista più affidabile con fantamedia 7.5, costa 32 crediti",
            "Hakan Calhanoglu dell'Inter ha fantamedia 7.1, costa 29 crediti ed è rigorista",
            "Theo Hernandez del Milan ha fantamedia 7.2, costa 32 crediti, miglior terzino",
            "Mike Maignan del Milan è il portiere consigliato con fantamedia 6.8, costa 24 crediti",
            "Yann Sommer dell'Inter ha fantamedia 6.6, costa 20 crediti ed è molto affidabile"
        ]
        
        # Store as static fallback regardless of knowledge manager status
        self.static_fallback_data = minimal_data
        
        if self.knowledge_manager:
            for data in minimal_data:
                try:
                    self.knowledge_manager.add_knowledge(data, {
                        "type": "minimal_real_data",
                        "season": "2024-25"
                    })
                except Exception as e:
                    print(f"⚠️ Failed to add minimal data: {e}")
        else:
            print("📋 Knowledge manager disabled, using static fallback data")

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
        if self.knowledge_manager and not self.knowledge_manager.embedding_disabled:
            try:
                relevant_context = self.knowledge_manager.get_context_for_query(user_message)
            except Exception as e:
                print(f"⚠️ Knowledge search failed: {e}")
                relevant_context = None
        
        # If no relevant context from database, use static fallback data
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
        elif hasattr(self, 'static_fallback_data'):
            # Use static fallback data when database is unavailable
            fallback_context = f"""
            DATI FANTACALCIO SERIE A 2024-25 (da database statico):
            {chr(10).join(self.static_fallback_data)}
            
            ISTRUZIONI: Usa questi dati verificati per fornire consigli specifici sui giocatori.
            Fornisci sempre nomi concreti, prezzi e fantamedie quando richiesto.
            Sii preciso e pratico nelle tue risposte.
            """
            messages.append({"role": "system", "content": fallback_context})
            print("📋 Using static fallback data for response")
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