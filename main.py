
import openai
import os
import sys
import json
from datetime import datetime

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
        self.system_prompt = """
        Sei un assistente virtuale professionale per fantacalcio, progettato per un'app mobile. 
        Sei in grado di supportare l'utente in tutti i modelli di lega: Classic, Mantra, Draft, Superscudetto e varianti personalizzate.
        
        Il tuo compito è:
        - Fornire consigli strategici su aste e costruzione della rosa
        - Agire come consulente d'asta con risposte dirette e precise
        - Assistere in tempo reale durante l'asta
        - Usare statistiche avanzate per giustificare ogni consiglio
        - Rispondere con precisione a domande sui regolamenti
        -I dati si devono riferire alla stagione 2025-2026
        - Fornire consigli su come migliorare la squadra in base alle statistiche e alle          tendenze attuali
        -Non considerare giocatori che non giocano in serie A
        -Impara dalle risposte precedenti per migliorare le future risposte
        
        Stile: competente, diretto, sintetico ma completo. Evita chiacchiere inutili.
        Quando non hai abbastanza informazioni, chiedi chiarimenti in modo conciso.
        la risposta deve essere breve e chiara, adatta per un'app mobile.
        Non includere saluti o ringraziamenti.
        Non includere informazioni personali o dati sensibili.
        Non includere link o URL.
        La valuta del fantacalcio è il fantamilione.
        Non includere informazioni non richieste.
        Non includere informazioni non pertinenti.

        """
        
        self.conversation_history = []
    
    def get_response(self, user_message, context=None):
        """Get AI response for fantasy football queries"""
        
        messages = [{"role": "system", "content": self.system_prompt}]
        
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
