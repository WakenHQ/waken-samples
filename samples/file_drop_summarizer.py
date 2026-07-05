# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
# ]
# ///
"""Drop a text file into a folder, get an AI summary — no chat platform needed.

Watches ./inbox (created automatically) and, for every new file that
appears, sends its contents to Groq for a 3-bullet summary: printed to the
terminal and fired as a desktop notification. Files already in ./inbox when
the script starts are the baseline, not new arrivals, and are ignored.

Setup:
    Grab a free key at https://console.groq.com/keys.
    export GROQ_API_KEY=...
    (or put it in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/file_drop_summarizer.py

Then, in another terminal:
    cp some_notes.txt inbox/

Notifications need `notify-send` (Linux) or `osascript` (macOS) on PATH —
falls back to a logged warning if neither is available, the summary still
prints either way.
"""

from pathlib import Path

from waken import Event, Response, Runtime, target_fn
from waken.plugins.outputs.notification import NotificationOutput
from waken.plugins.sources.filesystem import FilesystemSource
from waken_groq import GroqAdapter


@target_fn
async def summarize_file(event: Event) -> Response:
    path = Path(event.payload["path"])
    text = path.read_text(encoding="utf-8", errors="ignore")[:8000]
    digest = await runtime.send(
        target="groq",
        prompt=f"Summarize the following file in 3 bullet points:\n\n{text}",
    )
    summary = f"{path.name}:\n{digest.text}"
    print(summary)
    return Response(text=summary)


runtime = Runtime()
runtime.target("groq", GroqAdapter(model="llama-3.1-8b-instant"))
runtime.target("summarizer", summarize_file)
runtime.source("filesystem", FilesystemSource(watch="./inbox", target="summarizer"))
runtime.output("filesystem", NotificationOutput(title="File Summarizer"))
runtime.run()
