
# Apify Integration Setup per Fantasy Football Assistant

## Overview

L'integrazione con Apify.com fornisce un modo professionale e affidabile per scrapare dati da Transfermarkt, superando le limitazioni dei metodi di scraping diretti.

## Vantaggi dell'integrazione Apify

- **Anti-bot bypass**: Gestione automatica delle protezioni Transfermarkt
- **Rate limiting professionale**: Infrastrutura cloud che rispetta i ToS
- **Affidabilità**: Uptime del 99.9% e gestione automatica degli errori
- **Scalabilità**: Possibilità di processare tutte le squadre Serie A in parallelo
- **Dati strutturati**: Output JSON consistente e pulito

## Setup

### 1. Registrazione Apify

1. Vai su [https://apify.com](https://apify.com)
2. Registra un account gratuito (include 10$ di crediti mensili)
3. Vai su [Account > Integrations](https://console.apify.com/account/integrations)
4. Copia il tuo **API Token**

### 2. Configurazione Replit

1. Vai su **Secrets** nel tuo Repl
2. Aggiungi una nuova secret:
   - **Key**: `APIFY_API_TOKEN`
   - **Value**: Il token copiato da Apify

### 3. Actor Transfermarkt

Devi trovare/configurare un actor Apify per Transfermarkt. Opzioni:

**Opzione A: Actor esistente**
- Cerca nel [Apify Store](https://apify.com/store) per "transfermarkt"
- Usa actor come `apify/transfermarkt-scraper` (esempio)

**Opzione B: Actor personalizzato**
- Crea un actor custom per le tue esigenze specifiche
- Configura per estrarre: giocatore, squadra origine/destinazione, fee, posizione

### 4. Configurazione ETL

Abilita Apify nel tuo ETL job:

```bash
# Nelle Secrets di Replit, aggiungi:
USE_APIFY_TRANSFERMARKT=1
APIFY_API_TOKEN=apify_api_xxxxxxxxxx

# Opzionale: personalizza rate limiting
REQUEST_DELAY=3.0
```

## Utilizzo

### Comando singola squadra

```bash
python apify_transfermarkt_scraper.py --team "Juventus" --season "2025-26" --write-roster --ingest
```

### Comando tutte le squadre Serie A

```bash
python apify_transfermarkt_scraper.py --all-serie-a --season "2025-26" --write-roster --ingest --delay 5
```

### Integrazione con ETL job esistente

Il job `etl_transfers_job.py` ora include automaticamente Apify se configurato:

```bash
python etl_transfers_job.py
```

Fonti utilizzate nell'ordine:
1. **Wikipedia** (gratuito, baseline)
2. **Transfermarkt diretto** (se `TRANSFERMARKT_FALLBACK=1`)
3. **Apify Transfermarkt** (se `USE_APIFY_TRANSFERMARKT=1`) ⭐ **Raccomandato**
4. **RSS ufficiali** (se configurati)

## Costi

### Piano Apify Free
- $10/mese di crediti gratuiti
- ~1000-2000 requests
- Sufficiente per aggiornamenti settimanali Serie A

### Costo stimato per Serie A completa
- ~20 squadre × 2 requests = 40 requests
- Costo: ~$0.20-0.50 per run completo
- Budget mensile free: 20-50 run completi

### Ottimizzazione costi
- Esegui solo 1-2 volte a settimana
- Usa `--arrivals-only` per ridurre il carico
- Filtra squadre non interessanti

## Monitoraggio

### Dashboard Apify
- [Console Apify](https://console.apify.com/) per monitorare runs
- Visualizza successi/fallimenti
- Analizza costi e performance

### Log applicazione
```bash
# I log mostrano status di ogni fonte
[ETL] (1/20) Juventus
[ETL] Nessun acquisto trovato per Cagliari (fonti: Wikipedia, TM (disabled), Apify Transfermarkt, RSS (none))
[ETL] Juventus: 3 acquisti aggiornati
```

## Troubleshooting

### Errore "APIFY_API_TOKEN richiesto"
- Verifica di aver aggiunto il token nelle Secrets
- Riavvia il Repl dopo aver aggiunto secrets

### Errore "Actor not found"
- Verifica l'ID dell'actor in `apify_config.json`
- Controlla che l'actor sia pubblico e attivo

### Rate limiting / timeout
- Aumenta `REQUEST_DELAY` a 5-10 secondi
- Riduci il numero di squadre processate in parallelo

### Costi elevati
- Usa `--arrivals-only` per ridurre i dati estratti
- Esegui meno frequentemente
- Considera upgrade a piano pagato per rate migliori

## Actor personalizzato (avanzato)

Se vuoi creare un actor specifico per le tue esigenze:

1. Vai su [Apify Console > Actors](https://console.apify.com/actors)
2. Crea nuovo actor
3. Usa il template "Web Scraper"
4. Configura per Transfermarkt con output JSON:

```javascript
// Esempio configurazione actor
{
  "startUrls": [{"url": "https://www.transfermarkt.it/..."}],
  "pageFunction": async function extractData(context) {
    // Il tuo codice di estrazione
    return {
      playerName: context.$('.player-name').text(),
      fromClub: context.$('.from-club').text(),
      transferType: 'arrival',
      fee: context.$('.fee').text()
    };
  }
}
```

## Conclusioni

L'integrazione Apify trasforma il tuo Fantasy Assistant da un tool hobbistico a una soluzione professionale, garantendo dati sempre aggiornati e affidabili per le tue analisi fantacalcio.
