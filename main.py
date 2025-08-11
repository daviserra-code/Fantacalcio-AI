# main.py (shim)
from fantacalcio_assistant import FantacalcioAssistant

# opzionale: piccolo smoke test quando lanci direttamente main.py
if __name__ == "__main__":
    import os
    print("[main] Shim attivo. OPENAI_MODEL:", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))