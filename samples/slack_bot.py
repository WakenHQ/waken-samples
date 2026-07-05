# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-gemini",
#     "waken-slack",
# ]
# ///
"""An AI assistant living in a Slack channel, backed by Gemini.

Every message the bot sees becomes a Waken Event; replies land back in the
same channel/thread, so a thread reply resumes the same conversation. Uses
Socket Mode, so no public HTTP endpoint or reverse proxy needed.

Setup:
    1. Create a Slack app at https://api.slack.com/apps with Socket Mode
       enabled, an app-level token (`connections:write` scope) and a bot
       token, subscribed to the `message.channels` event.
    2. Grab a free key at https://aistudio.google.com/apikey.
    3. export SLACK_APP_TOKEN=xapp-...  SLACK_BOT_TOKEN=xoxb-...  GEMINI_API_KEY=...
       (or put all three in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/slack_bot.py

Then say something in a channel the bot's been invited to. Swap
GeminiAdapter for waken-groq/waken-openai/waken-claude/... to change the
model — the Slack wiring below doesn't change.
"""

from waken import Runtime
from waken_gemini import GeminiAdapter
from waken_slack import SlackOutput, SlackSource

runtime = Runtime()
runtime.target("assistant", GeminiAdapter())
runtime.source("slack", SlackSource(target="assistant"))
runtime.output("slack", SlackOutput())
runtime.run()
