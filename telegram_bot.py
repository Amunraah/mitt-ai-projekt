"""
Telegram Bot — kopplad till /generate (tier-baserad routing + confidence-gate).
Loggar varje konversation till Supabase leads-tabell.

Kör: python telegram_bot.py
"""

import logging
import os

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

TOKEN        = os.getenv("TELEGRAM_BOT_TOKEN")
API_URL      = os.getenv("API_BASE_URL", "http://localhost:8000")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_ANON_KEY")

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Supabase-loggning
# ---------------------------------------------------------------------------

def log_to_supabase(customer_id: str, text: str, response: str, routing: dict) -> None:
    """Skriver ett lead/meddelande till Supabase leads-tabellen."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.warning("Supabase ej konfigurerat — hoppar over loggning")
        return

    payload = {
        "customer_id": customer_id,
        "channel":     "telegram",
        "intent":      routing.get("task_type", "unknown"),
        "model_used":  routing.get("model", "unknown"),
        "text":        text,
        "response":    response,
        "status":      "qualified" if routing.get("is_lead") else "new",
        "confidence":  routing.get("confidence"),
        "gate":        routing.get("gate"),
        "is_lead":     routing.get("is_lead", False),
        "priority":    routing.get("priority", "medium"),
        "metadata": {
            "complexity": routing.get("complexity"),
            "reason":     routing.get("reason"),
            "source":     routing.get("source"),
        },
    }

    try:
        with httpx.Client(timeout=5) as client:
            r = client.post(
                f"{SUPABASE_URL}/rest/v1/leads",
                json=payload,
                headers={
                    "apikey":        SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type":  "application/json",
                    "Prefer":        "return=minimal",
                },
            )
            if r.status_code not in (200, 201):
                logger.error(f"Supabase-fel {r.status_code}: {r.text}")
            else:
                logger.info(
                    f"Supabase: loggat (model={routing.get('model')}, "
                    f"lead={routing.get('is_lead')}, gate={routing.get('gate')})"
                )
    except Exception as e:
        logger.error(f"Supabase-anslutningsfel: {e}")


# ---------------------------------------------------------------------------
# /generate-anrop mot api.py
# ---------------------------------------------------------------------------

def call_chat(message: str, model: str = "hermes") -> str:
    """Anropar /chat direkt — kringgår routing."""
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{API_URL}/chat",
            json={"message": message, "model": model},
        )
        r.raise_for_status()
        return r.json().get("response", "Inget svar.")


def call_generate(message: str, customer_id: str, history: list) -> dict:
    """Anropar /generate och returnerar routing-beslut + svar."""
    with httpx.Client(timeout=30) as client:
        r = client.post(
            f"{API_URL}/generate",
            json={
                "message":     message,
                "channel":     "telegram",
                "customer_id": customer_id,
                "history":     history,
            },
        )
        r.raise_for_status()
        return r.json()


# ---------------------------------------------------------------------------
# Konversationshistorik (per chat_id, max 10 par)
# ---------------------------------------------------------------------------

_history: dict[str, list] = {}


def get_history(chat_id: str) -> list:
    return _history.get(chat_id, [])


def push_history(chat_id: str, role: str, content: str) -> None:
    h = _history.setdefault(chat_id, [])
    h.append({"role": role, "content": content})
    if len(h) > 10:
        h.pop(0)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Hej! 👋 Jag är din AI-assistent med smart routing.\n\n"
        "Kommandon:\n"
        "/status  — Visa system-info\n"
        "/clear   — Rensa konversationshistorik\n"
        "/hermes  — Skriv direkt till Hermes-4 (ingen routing)\n\n"
        "Skriv ett meddelande så hjälper jag dig!"
    )


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    h = get_history(chat_id)
    await update.message.reply_text(
        f"Router:    {API_URL}/generate\n"
        f"Supabase:  {'KOPPLAD' if SUPABASE_URL else 'EJ KONFIGURERAT'}\n"
        f"Historik:  {len(h)} meddelanden i minnet"
    )


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = str(update.effective_chat.id)
    _history[chat_id] = []
    await update.message.reply_text("Historik rensad. Ny konversation startad.")


async def hermes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Skriver direkt till Hermes-4, kringgår routing."""
    text = " ".join(context.args)
    if not text:
        await update.message.reply_text(
            "Användning: /hermes <din fråga>\n"
            "Exempel: /hermes Vad är skillnaden på ROT och RUT?"
        )
        return
    await update.message.chat.send_action(action="typing")
    try:
        response = call_chat(text, model="hermes")
        if len(response) > 4000:
            response = response[:3997] + "..."
        await update.message.reply_text(response + "\n\n[hermes-4 | direkt]")
    except httpx.ConnectError:
        await update.message.reply_text("API-servern svarar inte. Kör: uvicorn api:app --port 8000")
    except Exception as e:
        await update.message.reply_text(f"Något gick fel: {str(e)[:200]}")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id     = str(update.effective_chat.id)
    user_text   = update.message.text
    customer_id = f"telegram_{chat_id}"

    await update.message.chat.send_action(action="typing")

    history = get_history(chat_id)
    push_history(chat_id, "user", user_text)

    try:
        result   = call_generate(user_text, customer_id, history)
        routing  = result.get("routing", {})
        response = result.get("response", "Kunde inte generera svar.")

        if len(response) > 4000:
            response = response[:3997] + "..."

        push_history(chat_id, "assistant", response)

        # Logga till Supabase
        log_to_supabase(customer_id, user_text, response, routing)

        # Routing-footer (ta bort parse_mode i produktion om du vill slippa footern)
        model = routing.get("model", "?")
        gate  = routing.get("gate", "?")
        conf  = float(routing.get("confidence") or 0)
        footer = f"\n\n[{model} | {conf:.2f} | {gate}]"

        await update.message.reply_text(response + footer)

    except httpx.ConnectError:
        await update.message.reply_text(
            "API-servern svarar inte.\n"
            "Starta den med:\n"
            "uvicorn api:app --host 0.0.0.0 --port 8000"
        )
    except Exception as e:
        logger.error(f"handle_message-fel: {e}")
        await update.message.reply_text(f"Något gick fel: {str(e)[:200]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN saknas i .env!")
        return

    print(
        f"Bot startad\n"
        f"  API:      {API_URL}\n"
        f"  Supabase: {'KOPPLAD' if SUPABASE_URL else 'EJ KONFIGURERAT'}"
    )

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",  start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("clear",  clear_cmd))
    app.add_handler(CommandHandler("hermes", hermes_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    app.run_polling()


if __name__ == "__main__":
    main()
