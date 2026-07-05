# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
# ]
# ///
"""Route an inbound GitHub issue webhook through an LLM for a priority call.

A repo (or a "New issue" GitHub Action step, via `curl`) POSTs the issue
payload to /webhook/github; the title+body get turned into a triage prompt
and routed straight to Groq, whose one-line verdict gets printed by the
built-in TerminalOutput.

Setup:
    Grab a free key at https://console.groq.com/keys.
    export GROQ_API_KEY=...
    (or put it in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/github_issue_triage.py   # in one terminal

    curl -X POST http://localhost:8080/webhook/github \\
         -H 'Content-Type: application/json' \\
         -d '{"issue": {"title": "Crash on startup", "body": "Segfaults on launch."}}'

Watch the terminal for the priority call.
"""

from typing import Any

from waken import Event, Runtime
from waken.plugins.outputs.terminal import TerminalOutput
from waken.plugins.sources.webhook import WebhookSource
from waken_groq import GroqAdapter

TRIAGE_PROMPT = """You are triaging an inbound GitHub issue.
Respond with exactly one line: `<priority P0|P1|P2|P3> - <one-sentence reason>`.

Title: {title}
Body: {body}"""


def parse_github_issue(body: dict[str, Any]) -> Event:
    issue = body.get("issue", {})
    prompt = TRIAGE_PROMPT.format(
        title=issue.get("title", "(no title)"), body=issue.get("body", "(no body)")
    )
    return Event(source="webhook", target="triage", payload={"prompt": prompt})


runtime = Runtime()
runtime.target("triage", GroqAdapter(model="llama-3.1-8b-instant"))
runtime.source("github", WebhookSource("github", parse_github_issue))
runtime.output("webhook", TerminalOutput())
runtime.run()
