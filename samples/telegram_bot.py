# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "waken-telegram",
# ]
# ///
"""A Telegram chatbot backed by Groq — the lowest-friction way to try Waken.

Message the bot registered under TELEGRAM_BOT_TOKEN and it replies through
the same chat, powered by Groq's fast inference API. Groq's free tier and
Telegram's @BotFather signup are both a couple of minutes of setup, no
credit card — good first sample if you have neither key yet.

Setup:
    1. Message @BotFather on Telegram, run /newbot, copy the token.
    2. Grab a free key at https://console.groq.com/keys.
    3. export TELEGRAM_BOT_TOKEN=...  GROQ_API_KEY=...
       (or put both in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/telegram_bot.py

Then message your bot on Telegram. Swap GroqAdapter for any other Target
adapter (waken-gemini, waken-openai, waken-claude, waken-ollama, ...) to
change the model — the Telegram wiring below doesn't change.
"""

from waken import Runtime
from waken_groq import GroqAdapter
from waken_telegram import TelegramOutput, TelegramSource

runtime = Runtime()
runtime.target("assistant", GroqAdapter(model="llama-3.1-8b-instant"))
runtime.source("telegram", TelegramSource(target="assistant"))
runtime.output("telegram", TelegramOutput())
runtime.run()
