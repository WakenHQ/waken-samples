# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-openai",
#     "waken-voice",
# ]
# ///
"""A voice-in, voice-out assistant — drop an audio file, get an audio reply.

Watches ./voice-inbox for new .wav/.mp3/.m4a/.ogg files, transcribes each
with Whisper, routes the transcript to an OpenAI Target, and writes the
reply back as synthesized speech under ./voice-outbox — playing it locally
too, best-effort, via VoiceOutput's default `play=True`.

Both directions go through OpenAI's audio API (Whisper in, TTS out), so
this is the one sample in this repo that needs OPENAI_API_KEY specifically
— no free tier, but Whisper/TTS are inexpensive per request. Swap
OpenAIAdapter(model=...) for a smaller/cheaper chat model if you want to
keep costs down further; the voice plumbing doesn't change either way.

Setup:
    Grab a key at https://platform.openai.com/api-keys.
    export OPENAI_API_KEY=...
    (or put it in a .env file and run with `uv run --env-file .env`)

Run:
    uv run samples/voice_assistant.py

Then, in another terminal, drop a short voice memo in:
    cp memo.m4a voice-inbox/

Watch ./voice-outbox for the spoken reply (and, if your platform has
`afplay` (macOS) or `paplay` (Linux) on PATH, hear it play automatically —
best-effort, logged rather than raised if neither is available).
"""

from waken import Runtime
from waken_openai import OpenAIAdapter
from waken_voice import VoiceOutput, VoiceSource

runtime = Runtime()
runtime.target("assistant", OpenAIAdapter())
runtime.source("voice", VoiceSource(watch="./voice-inbox", target="assistant"))
runtime.output("voice", VoiceOutput(output_dir="./voice-outbox"))
runtime.run()
