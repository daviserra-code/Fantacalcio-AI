
import openai
import os
import sys
import json
from datetime import datetime
from knowledge_manager import KnowledgeManager

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
        
        self.system_prompt = """
        Sei un assistente virtuale professionale per fantacalcio Serie A, progettato per un'app mobile. 
        Il tuo nome è Fantacalcio AI.
        Il tuo scopo è aiutare gli utenti a gestire la loro rosa di fantacalcio per la Serie A italiana in modo efficace e strategico.
        Sei in grado di supportare l'utente in tutti i modelli di lega: Classic, Mantra, Draft, Superscudetto e varianti personalizzate.
        
        Il tuo compito è:
        - Fornire consigli strategici su aste e costruzione della rosa
        - Suggerire formazioni specifiche con nomi di giocatori
        - Agire come consulente d'asta con raccomandazioni precise
        - Assistere con regole e meccaniche del fantacalcio italiano
        - Fornire consigli su gestione budget e distribuzione crediti
        - Suggerire strategie per diverse modalità di gioco
        - Dare consigli su ruoli, formazioni e tattiche specifiche
        - Spiegare criteri di valutazione dei giocatori (fantamedia, bonus, rigori, etc.)
        - Consigliare giocatori specifici per ogni ruolo basandoti sui dati disponibili
        
        HAI ACCESSO A UN DATABASE COMPLETO con informazioni sui giocatori di Serie A. 
        Quando ti vengono fornite informazioni rilevanti dal database, usale per dare consigli specifici e dettagliati.
        Puoi e devi suggerire formazioni complete con nomi di giocatori specifici, prezzi e strategie di acquisto.
        
        Rispondi sempre con informazioni concrete e pratiche. Se hai dati sui giocatori, usali confidentemente.
        
        Stile: competente, diretto, specifico. Fornisci sempre nomi di giocatori quando richiesti e disponibili nei dati.
        """
        
        self.conversation_history = []
    
    def get_response(self, user_message, context=None):
        """Get AI response for fantasy football queries with RAG"""
        
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Get relevant knowledge from vector database
        relevant_context = self.knowledge_manager.get_context_for_query(user_message)
        if relevant_context:
            messages.append({"role": "system", "content": relevant_context})
        
        # Add context if provided (league info, budget, etc.)
        if context:
            context_msg = f"Contesto attuale: {json.dumps(context, ensure_ascii=False)}"
            messages.append({"role": "system", "content": context_msg})
        
        # Add conversation history (last 5 messages to manage token usage)
        messages.extend(self.conversation_history[-10:])
        
        # Add current user message
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = openai.chat.completions.create(
                model="gpt-4",
                messages=messages,
                temperature=0.3,  # Lower temperature for more consistent advice
                max_tokens=500    # Optimized for mobile responses
            )
            
            ai_response = response.choices[0].message.content
            
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
