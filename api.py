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

HERMES_ROUTER_SYSTEM = """<|im_start|>system
Du är master-router för ett AI-assistentsystem för småföretag.
Analysera meddelandet och returnera ett routing-beslut som giltig JSON.

Regler:
- template : uppenbar FAQ, bokningstid, bekräftelse, standardsvar
- hermes   : enkelt svar som kan genereras direkt av dig
- qwen     : strukturerad data-extraktion från text, bild eller PDF
- kimi     : kod, skript, n8n-konfiguration, teknisk setup
- claude   : offert med ROT/RUT-beräkning, komplex analys, churn, juridik

Returnera ENBART giltig JSON — inget annat, ingen förklaring.
<|im_end|>"""

HERMES_ROUTER_USER = """<|im_start|>user
Meddelande: "{message}"
Kanal: "{channel}"
Historik: {history}
<|im_end|>
<|im_start|>assistant
"""

HERMES_EXPECTED_KEYS = {
    "model", "task_type", "complexity", "confidence", "is_lead", "priority", "reason"
}


def call_hermes_router(message: str, channel: str, history: list) -> dict:
    """Anropar Hermes för routing-beslut. Returnerar parsed JSON-dict."""
    user_block = HERMES_ROUTER_USER.format(
        message=message,
        channel=channel,
        history=json.dumps(history[-3:], ensure_ascii=False) if history else "[]",
    )
    prompt = HERMES_ROUTER_SYSTEM + "\n" + user_block
    raw = chat(prompt, model="hermes")

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
    retry_system = HERMES_ROUTER_SYSTEM.replace(
        "Returnera ENBART giltig JSON",
        f"Förra beslutet var osäkert (confidence={first_result.get('confidence')}, "
        f"model={first_result.get('model')}). Analysera djupare och returnera ENBART giltig JSON",
    )
    user_block = HERMES_ROUTER_USER.format(
        message=message,
        channel=channel,
        history=json.dumps(history[-5:], ensure_ascii=False) if history else "[]",
    )
    prompt = retry_system + "\n" + user_block
    raw = chat(prompt, model="hermes")

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

    # Om template → returnera direkt utan AI-anrop
    if chosen_model == "template":
        return {
            "routing": routing,
            "response": suggested or "[MALL: fyll i från templates.json]",
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
        "hermes": "Du är en hjälpsam AI-assistent för småföretag. Svara kort och professionellt på svenska.",
        "qwen": "Extrahera strukturerad data från texten. Returnera JSON only.",
        "kimi": "Du är en kodassistent. Returnera bara kod, inga förklaringar.",
        "claude": (
            "Du är en offert- och affärsassistent för småföretag i Sverige. "
            "Vid ROT-avdrag: 30% av arbetskostnad, max 50 000 kr/person/år. "
            "Returnera alltid JSON med fälten: total, rot_reduction, final_price, errors, approved."
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
