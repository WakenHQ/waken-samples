# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-voice[groq,gtts]",
# ]
# ///
"""A voice bot that echoes every message back — no LLM, no paid API key.

Drop a short voice memo in ./voice-inbox and get the same words back as
speech in ./voice-outbox. There's no Target adapter here, just a plain
`target_fn` handler — the smallest possible Source -> Target -> Output
wiring, handy for checking your voice plumbing works before wiring up a
real model (see voice_assistant.py).

Transcription goes through Groq's Whisper-backed API (free tier); Groq has
no TTS counterpart, so speech is synthesized via `gTTS`, which needs no API
key at all.

Setup:
    Grab a free key at https://console.groq.com/keys.
    export GROQ_API_KEY=...
    (or put it in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/echo_bot.py

Then, in another terminal, drop a short voice memo in:
    cp memo.m4a voice-inbox/

Watch ./voice-outbox for the spoken echo (and, if your platform has
`afplay` (macOS) or `paplay` (Linux) on PATH, hear it play automatically).
Swap the `echo` target for a real Target adapter (waken-groq, waken-gemini,
waken-claude, waken-ollama, ...) to turn this into an assistant, the way
voice_assistant.py does.
"""

from waken import Event, Response, Runtime, target_fn
from waken_voice import (
    GroqWhisperTranscriber,
    GTTSSynthesizer,
    VoiceOutput,
    VoiceSource,
)


@target_fn
async def echo(event: Event) -> Response:
    return Response(text=event.payload["prompt"])


runtime = Runtime()
runtime.target("echo", echo)
runtime.source(
    "voice",
    VoiceSource(
        watch="./voice-inbox", target="echo", transcriber=GroqWhisperTranscriber()
    ),
)
runtime.output(
    "voice", VoiceOutput(output_dir="./voice-outbox", synthesizer=GTTSSynthesizer())
)

runtime.run()
