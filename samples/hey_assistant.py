# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "waken-gemini",
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
    - OPENAI_API_KEY (Whisper in, TTS out — https://platform.openai.com/api-keys)
    - GROQ_API_KEY (https://console.groq.com/keys)
    - GEMINI_API_KEY (https://aistudio.google.com/apikey)
    (or put all three in a .env file and run with `uv run --env-file .env`)

    Microphone capture needs PortAudio. macOS/Windows: the `sounddevice`
    wheel usually bundles it, nothing extra to do. Linux: install your
    distro's PortAudio package first, e.g. `sudo apt-get install
    libportaudio2` on Debian/Ubuntu — the PyPI wheel doesn't bundle it
    there, and `sounddevice` fails to import without it.

Run:
    uv run samples/hey_assistant.py

Say "hey groq, ..." or "hey gemini, ...". A transcript that isn't one of
those gets a spoken nudge back instead of being silently dropped.
"""

import asyncio
import re
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from waken import Event, Response, Runtime, target_fn
from waken_gemini import GeminiAdapter
from waken_groq import GroqAdapter
from waken_voice import VoiceOutput, VoiceSource

SAMPLE_RATE = 16_000
VOICE_INBOX = Path("./voice-inbox")
WAKE_PATTERN = re.compile(r"^\s*hey[,]?\s+(\w+)[,:]?\s*(.*)$", re.IGNORECASE)

ASSISTANTS = {
    "groq": GroqAdapter(model="llama-3.1-8b-instant"),
    "gemini": GeminiAdapter(),
}

runtime = Runtime()
for name, adapter in ASSISTANTS.items():
    runtime.target(name, adapter)


@target_fn
async def wake_word_router(event: Event) -> Response:
    transcript = event.payload["prompt"]
    match = WAKE_PATTERN.match(transcript)
    if match is None:
        return Response(text="I didn't catch a wake word — try 'hey groq, ...'.")

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
    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        callback=lambda indata, *_: frames.append(indata.copy()),
    ):
        await wait_for_enter("")

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
