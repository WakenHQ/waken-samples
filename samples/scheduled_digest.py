# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "httpx",
# ]
# ///
"""A recurring "morning digest" job: fetch, summarize with an LLM, deliver.

Pulls the current top 5 Hacker News stories, asks Groq for a 3-bullet
digest, and prints it. `@runtime.cron(...)` sets the real once-a-day
cadence; `@runtime.after(seconds=2)` fires the same logic once, immediately,
so you see output right away instead of waiting until tomorrow morning.

Setup:
    Grab a free key at https://console.groq.com/keys.
    export GROQ_API_KEY=...
    (or put it in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/scheduled_digest.py

Watch the terminal — the digest prints within a couple of seconds, then
again every morning at 08:00 (server-local time) for as long as this stays
running.
"""

import httpx
from waken import Runtime
from waken_groq import GroqAdapter

HN_TOP_STORIES = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM = "https://hacker-news.firebaseio.com/v0/item/{item_id}.json"


async def fetch_top_titles(count: int = 5) -> list[str]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        top_ids = (await client.get(HN_TOP_STORIES)).json()[:count]
        items = [(await client.get(HN_ITEM.format(item_id=i))).json() for i in top_ids]
    return [item.get("title", "(untitled)") for item in items]


async def send_digest() -> None:
    titles = await fetch_top_titles()
    listing = "\n".join(f"- {title}" for title in titles)
    response = await runtime.send(
        target="digest",
        prompt=f"Summarize today's top Hacker News stories in 3 bullets:\n\n{listing}",
    )
    print(response.text)


runtime = Runtime()
runtime.target("digest", GroqAdapter(model="llama-3.1-8b-instant"))


@runtime.cron("0 8 * * *")
async def morning_digest() -> None:
    await send_digest()


@runtime.after(seconds=2)
async def morning_digest_demo() -> None:
    await send_digest()


runtime.run()
