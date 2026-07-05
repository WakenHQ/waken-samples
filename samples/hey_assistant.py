# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "waken",
#     "waken-groq",
#     "waken-gemini",
#     "waken-openai",
#     "waken-voice[groq,gtts]==0.2.0",
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
    - OPENAI_API_KEY (recommended — Whisper in, TTS out, and doubles as the
      "openai" assistant: https://platform.openai.com/api-keys)
    - GROQ_API_KEY (unlocks "hey groq, ...": https://console.groq.com/keys.
      Also covers voice input when OPENAI_API_KEY isn't set — Groq
      transcribes via Whisper too, just without the OpenAI key)
    - GEMINI_API_KEY (optional — unlocks "hey gemini, ...": https://aistudio.google.com/apikey)
    (or put whichever of these in a .env file and run with `uv run --env-file .env`)

    An assistant whose key isn't set is skipped rather than crashing the
    script — you just won't be able to say "hey <that one>, ...". At least
    one assistant key is needed.

    Voice I/O needs OPENAI_API_KEY or GROQ_API_KEY. With OPENAI_API_KEY,
    both directions go through OpenAI (Whisper in, TTS out). Without it,
    GROQ_API_KEY is used for transcription instead, and speech output
    falls back to gTTS — free, no key, but it calls Google Translate's
    public TTS endpoint, so treat it as best-effort rather than an SLA'd
    service.

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
    uv run samples/hey_assistant.py path/to/request.m4a

Say "hey <name>, ..." for whichever assistants you configured. A transcript
that doesn't match gets a spoken nudge back instead of being silently
dropped. NAME_ALIASES corrects known transcription slips (Whisper hears
"grok", you said "groq") — add to it if you hit others.
"""

import argparse
import asyncio
import os
import re
import shutil
import time
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd
from waken import Event, Output, Response, Runtime, target_fn
from waken_gemini import GeminiAdapter
from waken_groq import GroqAdapter
from waken_openai import OpenAIAdapter
from waken_voice import GroqWhisperTranscriber, GTTSSynthesizer, VoiceOutput, VoiceSource

SAMPLE_RATE = 16_000
VOICE_INBOX = Path("./voice-inbox")
WAKE_PATTERN = re.compile(r"^\s*hey[,]?\s+(\w+)[,:]?\s*(.*)$", re.IGNORECASE)
NAME_ALIASES = {
    "grok": "groq",  # Whisper knows the chatbot everyone talks about, not the chip startup
}
PROCESSING_DONE: asyncio.Event | None = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "audio_file",
        nargs="?",
        type=Path,
        help="Transcribe and route this existing audio file instead of recording from the mic.",
    )
    parser.add_argument(
        "--offline-timeout",
        type=float,
        default=120.0,
        help="Seconds to wait for one-shot audio file processing before exiting.",
    )
    return parser.parse_args()


def mark_processing_done() -> None:
    if PROCESSING_DONE is not None:
        PROCESSING_DONE.set()


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

if os.environ.get("OPENAI_API_KEY"):
    transcriber, synthesizer = None, None  # VoiceSource/VoiceOutput defaults: OpenAI Whisper + TTS
elif os.environ.get("GROQ_API_KEY"):
    transcriber, synthesizer = GroqWhisperTranscriber(), GTTSSynthesizer()
    print("OPENAI_API_KEY not set — transcribing with Groq Whisper, speaking with gTTS.")
else:
    raise SystemExit(
        "Voice I/O needs OPENAI_API_KEY or GROQ_API_KEY (for transcription) — set one of these."
    )

runtime = Runtime()
for name, adapter in ASSISTANTS.items():
    runtime.target(name, adapter)


def log_exchange(route: str, reply: str) -> None:
    print(f"🧭 Routing to: {route}")
    print(f"💬 Model response: {reply}")


@target_fn
async def wake_word_router(event: Event) -> Response:
    transcript = event.payload["prompt"]
    # Leading newline: this runs concurrently with record_clip()'s `input()`
    # prompt, which leaves the cursor sitting mid-line with no trailing "\n".
    print(f"\n📝 Transcription: {transcript}")
    match = WAKE_PATTERN.match(transcript)
    if match is None:
        example = next(iter(ASSISTANTS))
        response = Response(text=f"I didn't catch a wake word — try 'hey {example}, ...'.")
        log_exchange("none — no wake word matched", response.text)
        return response

    name, request = match.group(1).lower(), match.group(2).strip()
    name = NAME_ALIASES.get(name, name)
    if name not in ASSISTANTS or not request:
        names = ", ".join(ASSISTANTS)
        response = Response(text=f"Say 'hey <name>, ...' with name one of: {names}.")
        log_exchange("none — unknown assistant or empty request", response.text)
        return response

    response = await runtime.send(target=name, prompt=request)
    log_exchange(name, response.text)
    return response


class DoneSignalingOutput:
    """Wraps an Output; marks offline processing done only once delivery
    (TTS synthesis + playback) actually finishes. Signaling from inside
    wake_word_router itself fires too early — the router returns before
    the runtime hands its Response to this Output, so `source.stop()`
    could cancel synthesis/playback still in flight.
    """

    def __init__(self, wrapped: Output) -> None:
        self._wrapped = wrapped

    async def deliver(self, event: Event, response: Response) -> None:
        await self._wrapped.deliver(event, response)
        mark_processing_done()


runtime.target("router", wake_word_router)
runtime.output(
    "voice",
    DoneSignalingOutput(VoiceOutput(output_dir="./voice-outbox", synthesizer=synthesizer)),
)


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


def queue_audio_file(path: Path) -> Path:
    if not path.is_file():
        raise SystemExit(f"Audio file not found: {path}")

    suffix = path.suffix or ".audio"
    queued_path = VOICE_INBOX / f"offline-{int(time.time() * 1000)}{suffix}"
    shutil.copy2(path, queued_path)
    print(f"📥 Queued {path} as {queued_path.name} — transcribing and routing...")
    return queued_path


async def process_audio_file(path: Path, timeout: float) -> None:
    global PROCESSING_DONE

    PROCESSING_DONE = asyncio.Event()
    queued_path = queue_audio_file(path)
    try:
        await asyncio.wait_for(PROCESSING_DONE.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        print(
            f"⏳ Timed out after {timeout:g}s waiting for {queued_path.name}. "
            "Increase --offline-timeout if the model or transcription is still running."
        )


async def main(audio_file: Path | None, offline_timeout: float) -> None:
    VOICE_INBOX.mkdir(exist_ok=True)
    source = VoiceSource(watch=str(VOICE_INBOX), target="router", transcriber=transcriber)
    runtime.source("voice", source)
    await source.start(runtime)
    try:
        if audio_file is not None:
            await process_audio_file(audio_file, offline_timeout)
            return

        while True:
            await record_clip()
    finally:
        await source.stop()


if __name__ == "__main__":
    try:
        args = parse_args()
        asyncio.run(main(args.audio_file, args.offline_timeout))
    except KeyboardInterrupt:
        pass
