
import openai
import os
import sys
import json
from datetime import datetime
from knowledge_manager import KnowledgeManager
from corrections_manager import CorrectionsManager

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
        # Initialize knowledge manager for RAG
        self.knowledge_manager = KnowledgeManager()
        
        # Initialize corrections manager for persistent corrections
        self.corrections_manager = CorrectionsManager()
        
        # Load training data if available
        try:
            self.knowledge_manager.load_from_jsonl("training_data.jsonl")
        except Exception as e:
            print(f"⚠️ Could not load training_data.jsonl: {e}")
            
        # Try loading extended training data as fallback
        try:
            self.knowledge_manager.load_from_jsonl("extended_training_data.jsonl")
        except Exception as e:
            print(f"⚠️ Could not load extended_training_data.jsonl: {e}")
            print("ℹ️ Running with limited knowledge base - responses will be based on general principles")
        
        # Response cache with TTL (Time To Live)
        self.response_cache = {}
        self.cache_ttl = {}
        self.cache_max_size = 100
        self.cache_duration = 300  # 5 minutes
        self.cache_stats = {'hits': 0, 'misses': 0}
        
        self.system_prompt = """
        Sei un assistente virtuale ESPERTO per fantacalcio Serie A. Il tuo nome è Fantacalcio AI.
        
        REGOLE FONDAMENTALI:
        1. USA SOLO dati reali dal database - NON inventare mai statistiche, prezzi o informazioni
        2. Se non hai dati specifici, dillo chiaramente: "Non ho dati aggiornati su..."
        3. Basati sempre sui dati della stagione 2024-25 (la più recente disponibile)
        4. Risposte CONCISE e PRATICHE - max 300 parole
        5. SEMPRE prezzi reali quando suggerisci giocatori
        
        COMPETENZE:
        - Consigli su aste e costruzione rosa per tutte le modalità (Classic, Mantra, Draft, Superscudetto)
        - Formazioni specifiche con nomi reali e prezzi corretti
        - Strategie budget e distribuzione crediti
        - Analisi giocatori basata su: fantamedia, presenze, bonus, rigori, assist, gol
        
        STILE RISPOSTA:
        - Competente e diretto
        - Sempre nomi specifici quando disponibili
        - Prezzi esatti dai dati
        - Giustifica le scelte con statistiche reali
        - Se mancano dati: ammettilo e suggerisci alternative
        
        IMPORTANTE: Ogni risposta deve essere verificabile coi dati reali disponibili.
        """
        
        self.conversation_history = []
    
    def get_response(self, user_message, context=None):
        """Get AI response for fantasy football queries with RAG"""
        
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
        
        # Get relevant knowledge from vector database (limit to prevent slow responses)
        try:
            relevant_context = self.knowledge_manager.get_context_for_query(user_message, max_results=3)
            if relevant_context:
                messages.append({"role": "system", "content": relevant_context})
        except Exception as e:
            print(f"Warning: Knowledge retrieval failed: {e}")
        
        # Add context if provided (league info, budget, etc.)
        if context:
            context_msg = f"Contesto: {json.dumps(context, ensure_ascii=False)}"
            messages.append({"role": "system", "content": context_msg})
        
        # Add conversation history (last 4 messages only for speed)
        messages.extend(self.conversation_history[-4:])
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        try:
            # Use gpt-4o-mini for fastest responses
            model = "gpt-4o-mini"
            
            response = openai.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.2,  # Lower temperature for speed
                max_tokens=250,   # Reduced tokens for faster responses
                timeout=25,       # 25 second timeout
                stream=False
            )
            
            ai_response = response.choices[0].message.content
            
            # Apply persistent corrections to response
            try:
                ai_response = self.corrections_manager.apply_corrections(ai_response, "chat_response")
            except Exception as e:
                print(f"Warning: Corrections failed: {e}")
            
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
            
            # Update conversation history (keep it short)
            self.conversation_history.append({"role": "user", "content": user_message})
            self.conversation_history.append({"role": "assistant", "content": ai_response})
            
            # Keep conversation history manageable
            if len(self.conversation_history) > 8:
                self.conversation_history = self.conversation_history[-8:]
            
            return ai_response
            
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower():
                return "⏰ Richiesta troppo lenta. Prova con una domanda più specifica."
            return f"❌ Errore temporaneo. Riprova: {error_msg[:100]}"
    
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
    
    def get_corrections_summary(self):
        """Get corrections system summary"""
        return self.corrections_manager.get_corrections_summary()

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
