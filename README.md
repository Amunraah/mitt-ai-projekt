# Mitt AI Projekt

AI-projekt med OpenRouter - växla mellan olika AI-modeller (Hermes, Claude, Qwen, GPT-4).

## Kom igång

### 1. Installera beroenden

**Python:**
```bash
pip install -r requirements.txt
```

**Node.js:**
```bash
npm install
```

### 2. Konfigurera API-nyckel

Kopiera `.env.example` till `.env` och lägg till din OpenRouter API-nyckel:

```bash
cp .env.example .env
```

Hämta API-nyckel från: https://openrouter.ai/keys

### 3. Kör projektet

**Python:**
```bash
python main.py
```

**Node.js:**
```bash
npm start
```

## Tillgängliga modeller

| Modell | Nyckel | Beskrivning |
|--------|--------|-------------|
| Hermes 3 70B | `hermes` | Snabb, bra för coding (standard) |
| Claude 3.5 Sonnet | `claude` | Anthropic's bästa modell |
| Qwen 2.5 72B | `qwen` | Alibaba's modell |
| GPT-4o | `gpt4` | OpenAI's senaste |

## Exempel - Växla mellan modeller

### Python
```python
from main import chat

# Använd Hermes (standard)
response = chat("Skriv en Python-funktion", model="hermes")

# Växla till Claude
response = chat("Skriv en Python-funktion", model="claude")

# Växla till Qwen
response = chat("Skriv en Python-funktion", model="qwen")
```

### Node.js
```javascript
import { chat } from "./index.js";

// Använd Hermes (standard)
const response1 = await chat("Skriv en funktion", "hermes");

// Växla till Claude
const response2 = await chat("Skriv en funktion", "claude");

// Växla till Qwen
const response3 = await chat("Skriv en funktion", "qwen");
```

## Projektstruktur

```
mitt-ai-projekt/
├── .env              # Dina API-nycklar (ej i Git!)
├── .env.example      # Mall för teamet
├── .gitignore        # Ignorerar .env
├── main.py           # Python-exempel
├── index.js          # Node.js-exempel
├── requirements.txt  # Python-beroenden
├── package.json      # Node.js-beroenden
└── README.md         # Denna fil
```

## Säkerhet

⚠️ **Viktigt:** Commit aldrig `.env`-filen till Git! Den innehåller dina API-nycklar.

## Licens

MIT
