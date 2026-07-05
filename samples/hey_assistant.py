# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "waken-gemini",
#     "waken-openai",
#     "waken-voice",
#     "sounddevice",
#     "numpy",
# ]
# ///
"""Push-to-talk, multi-assistant voice routing: "hey <name>, <request>".

Press Enter, say something starting with a wake phrase — "hey groq, what's
the capital of France?" or "hey gemini, ..." — press Enter again to stop.
The clip is transcribed (Whisper), the wake phrase picks which registered
Target answers it, and the reply is spoken back (TTS) automatically. No
polling directory to babysit and no separate recorder process: the mic
loop and the transcribe/route/speak pipeline run concurrently in this one
script/one `uv run`.

Setup:
    - OPENAI_API_KEY (required — Whisper in, TTS out, and doubles as the
      "openai" assistant: https://platform.openai.com/api-keys)
    - GROQ_API_KEY (optional — unlocks "hey groq, ...": https://console.groq.com/keys)
    - GEMINI_API_KEY (optional — unlocks "hey gemini, ...": https://aistudio.google.com/apikey)
    (or put whichever of these in a .env file and run with `uv run --env-file .env`)

    An assistant whose key isn't set is skipped rather than crashing the
    script — you just won't be able to say "hey <that one>, ...". At least
    one assistant key is needed; OPENAI_API_KEY already has to be set for
    voice I/O, so "openai" is always available whenever the script runs at
    all.

    Microphone capture needs PortAudio. macOS/Windows: the `sounddevice`
    wheel usually bundles it, nothing extra to do. Linux: install your
    distro's PortAudio package first, e.g. `sudo apt-get install
    libportaudio2` on Debian/Ubuntu — the PyPI wheel doesn't bundle it
    there, and `sounddevice` fails to import without it.

    WSL: PortAudio's ALSA backend defaults to a "default"/"sysdefault"
    device with no real hardware behind it, which fails to even start
    (a "Wait timed out"/PaErrorCode -9987 ALSA thread error) rather than
    just being silent — your actual microphone is bridged in over
    PulseAudio (WSLg), not raw ALSA. If that happens, this script prints
    the available input devices; pick the one with "pulse" in its name
    and rerun with `WAKEN_MIC_DEVICE=<index or name>` set.

Run:
    uv run samples/hey_assistant.py

Say "hey <name>, ..." for whichever assistants you configured. A transcript
that doesn't match gets a spoken nudge back instead of being silently
dropped.
"""

import asyncio
import os
import re
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from waken import Event, Response, Runtime, target_fn
from waken_gemini import GeminiAdapter
from waken_groq import GroqAdapter
from waken_openai import OpenAIAdapter
from waken_voice import VoiceOutput, VoiceSource

SAMPLE_RATE = 16_000
VOICE_INBOX = Path("./voice-inbox")
WAKE_PATTERN = re.compile(r"^\s*hey[,]?\s+(\w+)[,:]?\s*(.*)$", re.IGNORECASE)


def _resolve_device(value: str | None) -> int | str | None:
    if value is None:
        return None
    return int(value) if value.isdigit() else value


MIC_DEVICE = _resolve_device(os.environ.get("WAKEN_MIC_DEVICE"))

ASSISTANTS = {}
if os.environ.get("GROQ_API_KEY"):
    ASSISTANTS["groq"] = GroqAdapter(model="llama-3.1-8b-instant")
if os.environ.get("GEMINI_API_KEY"):
    ASSISTANTS["gemini"] = GeminiAdapter()
if os.environ.get("OPENAI_API_KEY"):
    ASSISTANTS["openai"] = OpenAIAdapter()

if not ASSISTANTS:
    raise SystemExit(
        "No assistant API keys found — set at least one of GROQ_API_KEY, "
        "GEMINI_API_KEY, OPENAI_API_KEY."
    )
print(f"Assistants available: {', '.join(ASSISTANTS)}")

runtime = Runtime()
for name, adapter in ASSISTANTS.items():
    runtime.target(name, adapter)


@target_fn
async def wake_word_router(event: Event) -> Response:
    transcript = event.payload["prompt"]
    match = WAKE_PATTERN.match(transcript)
    if match is None:
        example = next(iter(ASSISTANTS))
        return Response(text=f"I didn't catch a wake word — try 'hey {example}, ...'.")

    name, request = match.group(1).lower(), match.group(2).strip()
    if name not in ASSISTANTS or not request:
        names = ", ".join(ASSISTANTS)
        return Response(text=f"Say 'hey <name>, ...' with name one of: {names}.")

    return await runtime.send(target=name, prompt=request)


runtime.target("router", wake_word_router)
runtime.output("voice", VoiceOutput(output_dir="./voice-outbox"))


async def wait_for_enter(prompt: str) -> None:
    await asyncio.get_running_loop().run_in_executor(None, input, prompt)


async def record_clip() -> None:
    await wait_for_enter("\nPress Enter to start talking...")
    print("Recording — press Enter again to stop.")
    frames: list[np.ndarray] = []
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="int16",
            device=MIC_DEVICE,
            callback=lambda indata, *_: frames.append(indata.copy()),
        ):
            await wait_for_enter("")
    except sd.PortAudioError as error:
        print(f"\nCouldn't start the microphone stream: {error}")
        print(
            "On WSL this is almost always ALSA opening a device with no real\n"
            "hardware behind it — the actual mic is bridged in over PulseAudio\n"
            "(WSLg), not raw ALSA. Available input devices:"
        )
        for index, info in enumerate(sd.query_devices()):
            if info["max_input_channels"] > 0:
                print(f"  [{index}] {info['name']}")
        print(
            "Pick one whose name contains 'pulse', then rerun with:\n"
            "  WAKEN_MIC_DEVICE=<index or name> uv run samples/hey_assistant.py"
        )
        raise SystemExit(1) from error

    if not frames:
        print("(nothing recorded)")
        return

    audio = np.concatenate(frames, axis=0)
    path = VOICE_INBOX / f"clip-{int(time.time() * 1000)}.wav"
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)  # int16
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(audio.tobytes())
    print(f"Saved {path.name} — transcribing and routing...")


async def main() -> None:
    VOICE_INBOX.mkdir(exist_ok=True)
    source = VoiceSource(watch=str(VOICE_INBOX), target="router")
    runtime.source("voice", source)
    await source.start(runtime)
    try:
        while True:
            await record_clip()
    finally:
        await source.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
