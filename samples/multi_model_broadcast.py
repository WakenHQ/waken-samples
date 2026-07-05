# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "waken-gemini",
#     "waken-ollama",
# ]
# ///
"""Ask three different models the same question concurrently, compare answers.

`runtime.broadcast()` fans one prompt out to every registered Target and
waits for all of them — swapping providers is a one-line `runtime.target()`
change, nothing else here has to know. A Target that raises (e.g. Ollama
with no local daemon running) shows up as an error entry instead of taking
the whole broadcast down, which is the point of trying this with a target
you *haven't* set up: run it as-is to see that failure mode for free.

Setup:
    Grab free keys at https://console.groq.com/keys and
    https://aistudio.google.com/apikey.
    export GROQ_API_KEY=...  GEMINI_API_KEY=...
    (or put both in a .env file and run with `uv run --env-file .env`)

    Ollama is optional — if you have it running locally (`ollama serve` +
    `ollama pull llama3.2`) you'll get a third real answer; if not, you'll
    just see that target's entry come back with an error, which is fine.

Run:
    uv run samples/multi_model_broadcast.py
"""

import asyncio

from waken import Runtime
from waken_gemini import GeminiAdapter
from waken_groq import GroqAdapter
from waken_ollama import OllamaAdapter


async def main() -> None:
    runtime = Runtime()
    runtime.target("groq", GroqAdapter(model="llama-3.1-8b-instant"))
    runtime.target("gemini", GeminiAdapter())
    runtime.target("ollama", OllamaAdapter(model="llama3.2"))

    responses = await runtime.broadcast(
        prompt="In one sentence, what makes a good code review?"
    )
    for name, response in responses.items():
        print(f"{name}: {response.metadata.get('error') or response.text}")


if __name__ == "__main__":
    asyncio.run(main())
