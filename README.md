# 🌬️ Monitor Qualità dell'Aria – Raspberry Pi 3B+ + Sensirion SPS30

Monitor completo per la qualità dell'aria basato su **Raspberry Pi 3B+** e sensore **Sensirion SPS30** in modalità I2C. Raccoglie dati di particolato (PM1.0, PM2.5, PM4.0, PM10), li archivia in SQLite, li espone via API REST FastAPI e li visualizza su una dashboard web in tempo reale.

---

## 📋 Funzionalità

- **Raccolta continua** ogni 60 secondi (configurabile) tramite `collector/scheduler.py`
- **Archiviazione SQLite** locale in `data/air_quality.db`
- **API REST** FastAPI con endpoint per dati in tempo reale, storici e statistiche
- **Dashboard web** responsive con grafico temporale, badge AQI e tema dark/light
- **Alert Telegram** configurabili per PM2.5 e PM10 con cooldown anti-spam
- **Servizi systemd** per avvio automatico al boot

---

## 🔧 Hardware richiesto

| Componente           | Specifiche                        |
|----------------------|-----------------------------------|
| Raspberry Pi 3B+     | Raspberry Pi OS (Bullseye/Bookworm) |
| Sensirion SPS30      | Interfaccia I2C (SEL pin a GND)   |
| Cavi Dupont F-F      | 4 cavi per connessione I2C        |

### Schema di collegamento SPS30 → Raspberry Pi (I2C)

| Pin SPS30 | Colore consigliato | GPIO RPi         |
|-----------|--------------------|------------------|
| 1 – VDD   | Rosso              | Pin 2 (5V)       |
| 2 – SDA   | Blu                | Pin 3 (GPIO 2)   |
| 3 – SCL   | Giallo             | Pin 5 (GPIO 3)   |
| 4 – SEL   | Arancione          | GND (I2C mode)   |
| 5 – GND   | Nero               | Pin 6 (GND)      |

> **Nota:** Il pin SEL collegato a GND seleziona la modalità I2C. L'indirizzo I2C sarà `0x69`.

---

## 🚀 Installazione rapida

### 1. Clona il repository

```bash
git clone https://github.com/YOUR_USERNAME/rpi-sps30-air-quality.git
cd rpi-sps30-air-quality
```

### 2. Esegui lo script di setup

```bash
bash setup.sh
```

Lo script esegue automaticamente:
- Installazione dipendenze di sistema (`python3-venv`, `i2c-tools`, ecc.)
- Abilitazione I2C in `/boot/config.txt` se necessario
- Creazione del virtual environment Python (`.venv/`)
- Installazione dei pacchetti Python da `requirements.txt`
- Creazione della directory `data/`
- Copia di `.env.example` in `.env`
- Installazione e avvio dei servizi systemd

### 3. Configura le variabili d'ambiente

```bash
nano .env
```

```env
COLLECTION_INTERVAL=900      # secondi tra una lettura (900 = 15 minuti)
SENSOR_WARMUP=5              # secondi di riscaldamento del sensore
CAP=20121                    # CAP della tua città per qualità aria esterna accurata
PM25_ALERT_THRESHOLD=25.0    # soglia alert PM2.5 (µg/m³)
PM10_ALERT_THRESHOLD=50.0    # soglia alert PM10 (µg/m³)
TELEGRAM_BOT_TOKEN=          # opzionale: token bot Telegram
TELEGRAM_CHAT_ID=            # opzionale: ID chat Telegram
```

### 4. Verifica il sensore

```bash
i2cdetect -y 1
# Deve apparire "69" nella griglia
```

---

## 🖥️ Utilizzo

### Dashboard web

Apri il browser su:

```
http://<IP-DEL-RASPBERRY>:8000
```

### API REST

| Endpoint          | Descrizione                              |
|-------------------|------------------------------------------|
| `GET /api/health` | Liveness check + conteggio letture       |
| `GET /api/latest` | Ultima lettura disponibile               |
| `GET /api/outdoor` | Qualità aria esterna locale (auto via IP) |
| `GET /api/data?range=day\|week\|month` | Dati storici (aggregati) |
| `GET /api/stats?range=day\|week\|month` | Statistiche min/avg/max |
| `GET /docs`       | Documentazione Swagger interattiva       |

Esempio:

```bash
curl http://localhost:8000/api/latest | python3 -m json.tool
```

```json
{
  "id": 1440,
  "timestamp": "2024-11-01T11:00:00+00:00",
  "pm1p0": 3.21,
  "pm2p5": 5.67,
  "pm4p0": 6.12,
  "pm10p0": 6.45,
  "nc0p5": 412.3,
  "nc1p0": 89.2,
  "nc2p5": 12.1,
  "nc4p0": 2.3,
  "nc10p0": 0.8,
  "typical_size": 0.52
}
```

---

## ⚙️ Gestione servizi systemd

```bash
# Stato dei servizi
sudo systemctl status air-collector
sudo systemctl status air-api

# Log in tempo reale
journalctl -fu air-collector
journalctl -fu air-api

# Riavvio
sudo systemctl restart air-collector
sudo systemctl restart air-api

# Stop
sudo systemctl stop air-collector air-api
```

---

## 🔔 Alert Telegram (opzionale)

1. Crea un bot con **@BotFather** su Telegram → ottieni il token
2. Scrivi un messaggio al tuo bot, poi visita:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```
   Per trovare il tuo `chat_id`
3. Inserisci `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` nel file `.env`
4. Riavvia il collector: `sudo systemctl restart air-collector`

Gli alert vengono inviati con cooldown di 30 minuti per evitare spam.

---

## 📁 Struttura del progetto

```
rpi-sps30-air-quality/
├── collector/
│   ├── __init__.py
│   ├── sensor.py        # Driver SPS30 via libreria sps30
│   ├── db.py            # Accesso SQLite
│   └── scheduler.py     # Loop di raccolta dati
├── api/
│   ├── __init__.py
│   └── main.py          # FastAPI REST API
├── web/
│   └── index.html       # Dashboard SPA (Chart.js)
├── alerts/
│   ├── __init__.py
│   └── telegram_bot.py  # Alerter Telegram
├── systemd/
│   ├── air-collector.service
│   └── air-api.service
├── data/                # (gitignored) SQLite DB + log
├── .venv/               # (gitignored) Virtual environment
├── requirements.txt
├── setup.sh
├── .env.example
├── .gitignore
└── README.md
```

---

## 📊 Categorie AQI (WHO 2021 – PM2.5)

| Categoria                     | PM2.5 (µg/m³) | Colore   |
|-------------------------------|---------------|----------|
| Buona                         | < 15          | 🟢 Verde  |
| Moderata                      | 15 – 25       | 🟡 Giallo |
| Non salutare per sensibili    | 25 – 50       | 🟠 Arancione |
| Non salutare                  | 50 – 75       | 🔴 Rosso  |
| Molto pericolosa              | > 75          | 🟣 Viola  |

---

## 🛠️ Sviluppo locale (senza sensore)

Per sviluppare o testare l'API senza il Raspberry Pi / sensore fisico, è possibile inserire dati di test nel database:

```python
# test_insert.py
from collector.db import Database
from collector.sensor import AirQualityReading
import random, time

db = Database()
for i in range(100):
    r = AirQualityReading(
        pm1p0=round(random.uniform(1, 10), 2),
        pm2p5=round(random.uniform(2, 20), 2),
        pm4p0=round(random.uniform(3, 22), 2),
        pm10p0=round(random.uniform(4, 25), 2),
        nc0p5=round(random.uniform(100, 500), 2),
        nc1p0=round(random.uniform(50, 200), 2),
        nc2p5=round(random.uniform(5, 30), 2),
        nc4p0=round(random.uniform(1, 5), 2),
        nc10p0=round(random.uniform(0.1, 1), 2),
        typical_size=round(random.uniform(0.3, 1.0), 2),
    )
    db.insert(r)
print(f"Inserted {db.count()} readings")
```

Poi avvia solo l'API:

```bash
source .venv/bin/activate
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📄 Licenza

MIT License – libero utilizzo, modifica e distribuzione con attribuzione.

---

*Progetto realizzato con Raspberry Pi 3B+ · Sensirion SPS30 · Python 3.11 · FastAPI · Chart.js*

