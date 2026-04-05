"""
FastAPI-server för tier-baserat AI-routing-system.
Exponerar /route, /chat och /health till n8n och Telegram-boten.

Kör: uvicorn api:app --host 0.0.0.0 --port 8000 --reload
"""

import json
import logging
import os
import re
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from main import chat

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI-Router API",
    description="Tier-baserat routing-system: Template → Hermes → Qwen/Kimi/Claude",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Keyword-filter (Tier 0 — 0 tokens)
# ---------------------------------------------------------------------------

KEYWORD_RULES = [
    {
        "model": "template",
        "task_type": "greeting",
        "keywords": ["hej", "hallå", "hejsan", "tjena", "god dag", "god morgon", "god kväll", "good morning", "good afternoon"],
    },
    {
        "model": "template",
        "task_type": "booking",
        "keywords": ["när kommer", "när kan ni", "boka tid", "bokning", "ledigt", "tillgänglig"],
    },
    {
        "model": "template",
        "task_type": "faq",
        "keywords": ["öppettider", "adress", "var ligger", "hur kontaktar", "telefon"],
    },
    {
        "model": "qwen",
        "task_type": "invoice",
        "keywords": ["faktura nr", "kvitto", "fakturanummer", "betalningsunderlag"],
    },
    {
        "model": "claude",
        "task_type": "quote",
        "keywords": ["rot-avdrag", "rut-avdrag", "rot avdrag", "rut avdrag", "ROT", "RUT"],
    },
    {
        "model": "kimi",
        "task_type": "code",
        "keywords": ["skriv kod", "debug", "n8n-node", "script", "python", "javascript"],
    },
]


def keyword_match(text: str) -> Optional[dict]:
    """Returnerar routing-beslut om ett nyckelord matchar, annars None."""
    lower = text.lower()
    for rule in KEYWORD_RULES:
        if any(kw in lower for kw in rule["keywords"]):
            return {
                "model": rule["model"],
                "task_type": rule["task_type"],
                "complexity": "low",
                "confidence": 1.0,
                "is_lead": False,
                "priority": "medium",
                "reason": "keyword-match",
                "suggested_response": None,
                "source": "keyword-filter",
            }
    return None


# ---------------------------------------------------------------------------
# Hermes routing-prompt (Tier 1)
# ---------------------------------------------------------------------------

HERMES_ROUTER_SYSTEM = """Du är ARIA (AI Router & Intent Analyzer) — master-router för ett AI-system som hjälper svenska småföretag (hantverkare, coacher, konsulter) att hantera kundkommunikation automatiskt.

## Din uppgift
Analysera inkommande meddelanden och besluta EXAKT vilken AI-modell som ska hantera dem. Ditt beslut styr kostnader, hastighet och kundnöjdhet.

## Modellval
| Modell   | Använd när                                                            |
|----------|-----------------------------------------------------------------------|
| template | FAQ, bokningstider, bekräftelser, hälsningar — uppenbart enkla svar  |
| hermes   | Enkelt svar du kan skriva direkt, max 3 meningar                      |
| qwen     | Strukturerad extraktion: fakturanr, belopp, datum ur text             |
| kimi     | Kod, skript, n8n-noder, teknisk konfiguration                         |
| claude   | ROT/RUT-offert, juridik, komplex analys, affärskritiska beslut        |

## Lead-definition (is_lead: true)
Sätt is_lead=true om meddelandet innehåller:
- Köpintention: "vill ha", "behöver", "söker", "intresserad av"
- Prisförfrågan: "vad kostar", "offert", "pris på"
- Specifikt projekt: "ska renovera", "bygga", "installera", "lägga"
- Tidsramar: "nästa månad", "till sommaren", "så snart som möjligt"

## Confidence-kalibrering
- 0.95–1.00 : Helt säker, uppenbart fall
- 0.85–0.94 : Säker bedömning
- 0.70–0.84 : Rimlig bedömning, viss tvetydighet
- 0.60–0.69 : Osäker, komplex input
- < 0.60    : Eskalera till claude

## Output — ENBART giltig JSON, noll förklaringar
Exempel 1 → {"model":"template","task_type":"faq","complexity":"low","confidence":0.98,"is_lead":false,"priority":"low","reason":"enkel FAQ öppettider","suggested_response":null}
Exempel 2 → {"model":"claude","task_type":"quote","complexity":"high","confidence":0.96,"is_lead":true,"priority":"high","reason":"ROT-offert kök 80h arbete","suggested_response":null}
Exempel 3 → {"model":"qwen","task_type":"invoice","complexity":"low","confidence":0.94,"is_lead":false,"priority":"medium","reason":"fakturaextraktion belopp datum","suggested_response":null}
Exempel 4 → {"model":"hermes","task_type":"lead","complexity":"medium","confidence":0.88,"is_lead":true,"priority":"high","reason":"allmän intresseförfrågan utan ROT","suggested_response":"Tack för ditt meddelande! Vi återkommer inom kort."}"""

HERMES_ROUTER_USER = """Meddelande: "{message}"
Kanal: "{channel}"
Historik: {history}"""

HERMES_EXPECTED_KEYS = {
    "model", "task_type", "complexity", "confidence", "is_lead", "priority", "reason"
}


# ---------------------------------------------------------------------------
# Template-hämtning
# ---------------------------------------------------------------------------

def _get_template_response(task_type: str) -> str:
    """Hämtar svar från templates.json baserat på task_type."""
    try:
        with open("templates.json", "r", encoding="utf-8") as f:
            templates = json.load(f)
        for t in templates:
            if t.get("name") == task_type or t.get("name") == f"{task_type}":
                return t.get("body", "Hej! Hur kan jag hjälpa dig?")
            # Fallback: matcha mot trigger-ord
            if task_type in t.get("trigger", []):
                return t.get("body", "Hej! Hur kan jag hjälpa dig?")
    except Exception as e:
        logger.warning(f"Kunde inte läsa templates.json: {e}")
    return "Hej! 👋 Välkommen till oss. Hur kan jag hjälpa dig idag?"


def call_hermes_router(message: str, channel: str, history: list) -> dict:
    """Anropar Hermes för routing-beslut. Returnerar parsed JSON-dict."""
    user_content = HERMES_ROUTER_USER.format(
        message=message,
        channel=channel,
        history=json.dumps(history[-3:], ensure_ascii=False) if history else "[]",
    )
    raw = chat(user_content, model="hermes", system_prompt=HERMES_ROUTER_SYSTEM)

    # Extrahera JSON ur svaret (Hermes kan ibland lägga till text)
    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        raise ValueError(f"Hermes returnerade ingen giltig JSON: {raw[:200]}")

    result = json.loads(json_match.group())

    # Säkerställ att alla nycklar finns
    result.setdefault("confidence", 0.5)
    result.setdefault("is_lead", False)
    result.setdefault("priority", "medium")
    result.setdefault("suggested_response", None)
    result.setdefault("source", "hermes-pass-1")
    return result


def call_hermes_router_retry(message: str, channel: str, history: list, first_result: dict) -> dict:
    """Andra chansen för Hermes med mer kontext om confidence var låg (0.60–0.84)."""
    retry_system = (
        HERMES_ROUTER_SYSTEM
        + f"\n\n## Retry-kontext\nFörra beslutet var osäkert "
        f"(confidence={first_result.get('confidence')}, model={first_result.get('model')}). "
        f"Analysera djupare och returnera ENBART giltig JSON."
    )
    user_content = HERMES_ROUTER_USER.format(
        message=message,
        channel=channel,
        history=json.dumps(history[-5:], ensure_ascii=False) if history else "[]",
    )
    raw = chat(user_content, model="hermes", system_prompt=retry_system)

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not json_match:
        return first_result  # Behåll första om retry misslyckas

    result = json.loads(json_match.group())
    result.setdefault("confidence", first_result.get("confidence", 0.5))
    result.setdefault("is_lead", first_result.get("is_lead", False))
    result.setdefault("priority", "medium")
    result.setdefault("suggested_response", None)
    result["source"] = "hermes-pass-2"
    return result


# ---------------------------------------------------------------------------
# Confidence-gate (kärnan i systemet)
# ---------------------------------------------------------------------------

def confidence_gate(message: str, channel: str, history: list) -> dict:
    """
    Tvåstegs confidence-gate:

    Pass 1 — Hermes analyserar
      confidence >= 0.85 → kör routing-beslut direkt
      confidence 0.60–0.84 → Hermes får andra chansen med mer kontext
      confidence < 0.60 → eskalera till Claude direkt

    Pass 2 (om behövs) — Hermes med retry-prompt
      confidence >= 0.70 → kör routing-beslut
      confidence < 0.70 → eskalera till Claude
    """

    # --- Pass 1 ---
    try:
        result = call_hermes_router(message, channel, history)
    except Exception as e:
        logger.warning(f"Hermes pass-1 misslyckades: {e} — eskalerar till Claude")
        return _escalate_to_claude(message)

    conf = float(result.get("confidence", 0.5))
    logger.info(f"[Pass-1] model={result.get('model')} confidence={conf:.2f} reason={result.get('reason')}")

    if conf >= 0.85:
        result["gate"] = "pass-1-high"
        return result

    if conf < 0.60:
        logger.info("[Pass-1] Confidence < 0.60 — eskalerar till Claude")
        return _escalate_to_claude(message)

    # --- Pass 2 (0.60–0.84) ---
    logger.info(f"[Pass-1] Confidence {conf:.2f} — startar pass-2 (retry)")
    try:
        result2 = call_hermes_router_retry(message, channel, history, result)
    except Exception as e:
        logger.warning(f"Hermes pass-2 misslyckades: {e} — använder pass-1-resultat")
        result["gate"] = "pass-1-fallback"
        return result

    conf2 = float(result2.get("confidence", 0.5))
    logger.info(f"[Pass-2] model={result2.get('model')} confidence={conf2:.2f}")

    if conf2 >= 0.70:
        result2["gate"] = "pass-2-ok"
        return result2

    logger.info("[Pass-2] Confidence < 0.70 — eskalerar till Claude")
    return _escalate_to_claude(message)


def _escalate_to_claude(message: str) -> dict:
    return {
        "model": "claude",
        "task_type": "unknown",
        "complexity": "high",
        "confidence": 1.0,
        "is_lead": True,
        "priority": "high",
        "reason": "confidence-gate-escalation",
        "suggested_response": None,
        "source": "escalated-to-claude",
        "gate": "escalated",
    }


# ---------------------------------------------------------------------------
# Pydantic-modeller
# ---------------------------------------------------------------------------

class RouteRequest(BaseModel):
    message: str
    channel: str = "unknown"
    customer_id: Optional[str] = None
    history: Optional[list] = []


class ChatRequest(BaseModel):
    message: str
    model: str = "hermes"
    system_prompt: Optional[str] = None


class RouteResponse(BaseModel):
    model: str
    task_type: str
    complexity: str
    confidence: float
    is_lead: bool
    priority: str
    reason: str
    suggested_response: Optional[str]
    source: str
    gate: Optional[str] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/route", response_model=RouteResponse)
def route_message(req: RouteRequest):
    """
    Huvud-endpoint för routing.
    1. Keyword-filter (0 tokens)
    2. Confidence-gate med Hermes (2 pass om behövs)
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message får inte vara tom")

    # Steg 1 — Keyword-filter
    kw_result = keyword_match(req.message)
    if kw_result:
        logger.info(f"[keyword] → {kw_result['model']} ({kw_result['task_type']})")
        kw_result["gate"] = "keyword-filter"
        return kw_result

    # Steg 2 — Confidence-gate
    result = confidence_gate(req.message, req.channel, req.history or [])
    logger.info(
        f"[gate={result.get('gate')}] → {result['model']} "
        f"(conf={result['confidence']:.2f}, lead={result['is_lead']})"
    )
    return result


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    """Direkt chat-endpoint — kringgår routing, anropar valfri modell."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message får inte vara tom")
    try:
        response = chat(req.message, model=req.model, system_prompt=req.system_prompt)
        return {"response": response, "model": req.model}
    except Exception as e:
        logger.error(f"chat-fel: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate")
def generate_response(req: RouteRequest):
    """
    Kombinerad endpoint: router + generera svar i ett anrop.
    Returnerar routing-beslut + genererat svar.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="message får inte vara tom")

    # Routing
    kw_result = keyword_match(req.message)
    routing = kw_result if kw_result else confidence_gate(req.message, req.channel, req.history or [])

    chosen_model = routing["model"]
    suggested = routing.get("suggested_response")

    # Om template → hämta från templates.json
    if chosen_model == "template":
        task = routing.get("task_type", "")
        template_response = _get_template_response(task)
        return {
            "routing": routing,
            "response": template_response,
            "model_used": "template",
            "tokens_used": 0,
        }

    # Om Hermes redan föreslog ett svar → använd det
    if chosen_model == "hermes" and suggested:
        return {
            "routing": routing,
            "response": suggested,
            "model_used": "hermes",
            "tokens_used": None,
        }

    # Annars — anropa vald modell
    system_prompts = {
        "hermes": (
            "Du är ARIA — en professionell och varm AI-assistent för svenska småföretag. "
            "Svara alltid på svenska. Var konkret och affärsmässig. "
            "Håll svaret kort: max 3 meningar om inte kunden ber om mer."
        ),
        "qwen": (
            "Extrahera strukturerad data ur texten. "
            "Returnera ENBART valid JSON med fälten: invoice_no, amount, date, recipient. "
            "Sätt null för saknade fält. Inga förklaringar utanför JSON-objektet."
        ),
        "kimi": (
            "Du är en kodassistent specialiserad på n8n, Python och JavaScript. "
            "Returnera enbart kod i kodblock. Inga förklaringar utanför koden."
        ),
        "claude": (
            "Du är en offert- och affärsassistent för svenska hantverkare och coacher. "
            "ROT-avdrag: 30% av arbetskostnad, max 50 000 kr/person/år. "
            "RUT-avdrag: 50% av arbetskostnad, max 75 000 kr/person/år. "
            'Returnera ALLTID JSON: {"total": 0, "rot_reduction": 0, "rut_reduction": 0, '
            '"final_price": 0, "errors": [], "approved": true, "notes": ""}'
        ),
    }

    try:
        response = chat(
            req.message,
            model=chosen_model,
            system_prompt=system_prompts.get(chosen_model),
        )
        return {
            "routing": routing,
            "response": response,
            "model_used": chosen_model,
            "tokens_used": None,
        }
    except Exception as e:
        logger.error(f"generate-fel (model={chosen_model}): {e}")
        raise HTTPException(status_code=500, detail=str(e))
