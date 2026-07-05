<div align="center">

# waken-samples

Common, real-world use cases for [Waken](https://github.com/WakenHQ/waken) —
"nginx for AI agents." Every script is self-contained and runs with a single
`uv run` command: no clone, no venv, no `pip install` — `uv` resolves the
PEP 723 header at the top of the file and fetches everything it needs from
PyPI on the fly.

</div>

## Samples

| Script | Shows off | Needs |
|---|---|---|
| [`telegram_bot.py`](samples/telegram_bot.py) | Channel `Source`/`Output` (`waken-telegram`) + a Target adapter | `TELEGRAM_BOT_TOKEN`, `GROQ_API_KEY` |
| [`slack_bot.py`](samples/slack_bot.py) | Same shape, a different channel (`waken-slack`) and model | `SLACK_APP_TOKEN`, `SLACK_BOT_TOKEN`, `GEMINI_API_KEY` |
| [`file_drop_summarizer.py`](samples/file_drop_summarizer.py) | Built-in `FilesystemSource` + a custom `Target` that calls another `Target` | `GROQ_API_KEY` |
| [`github_issue_triage.py`](samples/github_issue_triage.py) | Built-in `WebhookSource`, routing a GitHub issue straight to an LLM | `GROQ_API_KEY` |
| [`scheduled_digest.py`](samples/scheduled_digest.py) | `runtime.cron`/`after`, fetch → summarize → deliver | `GROQ_API_KEY` |
| [`multi_model_broadcast.py`](samples/multi_model_broadcast.py) | `runtime.broadcast()` across three providers at once | `GROQ_API_KEY`, `GEMINI_API_KEY`, Ollama optional |
| [`voice_assistant.py`](samples/voice_assistant.py) | Voice `Source`/`Output` (`waken-voice`) — speech in, speech out | `OPENAI_API_KEY` |
| [`hey_assistant.py`](samples/hey_assistant.py) | Live push-to-talk mic + wake-word routing across several Targets | `OPENAI_API_KEY` or `GROQ_API_KEY` for voice I/O; `GEMINI_API_KEY` optional, ≥1 assistant needed |

The first six default to Groq, Gemini, and/or Ollama specifically because
those are free-tier (Groq, Gemini) or fully local/free (Ollama) and need
nothing beyond a Python package — no separate CLI or runtime install,
unlike `waken-claude` (wraps the Claude Agent SDK, which expects Node.js +
the `claude` CLI). Swap the adapter import for `waken-openai`,
`waken-claude`, `waken-mistral`, `waken-cohere`, `waken-bedrock`, or
`waken-copilot` and the rest of any script is unchanged — that one-line
swap is the whole point of a Waken `Target`. `voice_assistant.py` and
`hey_assistant.py` are the exception, since `waken-voice` wraps a speech
provider rather than a chat model. `voice_assistant.py` is hardwired to
OpenAI's audio API (Whisper in, TTS out), so it needs `OPENAI_API_KEY`
regardless of anything else. `hey_assistant.py` is more flexible:
`OPENAI_API_KEY` still gets you Whisper in/TTS out, but without it,
`GROQ_API_KEY` covers transcription instead (Groq's hosted Whisper) and
speech output falls back to free, no-key gTTS. `hey_assistant.py` also
skips any assistant whose key isn't set rather than crashing on startup —
set just `GROQ_API_KEY`, just `GEMINI_API_KEY` alongside one of the other
two, or any mix, as long as at least one assistant key is present and at
least one of `OPENAI_API_KEY`/`GROQ_API_KEY` is set for voice capture.

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) installed.
- Whichever API key(s) the sample you're running needs (see table above).
  Free tiers: [Groq](https://console.groq.com/keys), [Gemini](https://aistudio.google.com/apikey).
  [Ollama](https://ollama.com) needs no key at all — just a locally running daemon.
  `voice_assistant.py` needs an
  [OpenAI](https://platform.openai.com/api-keys) key (Whisper/TTS have no
  free tier, but are inexpensive per request); `hey_assistant.py` needs
  that same OpenAI key *or* a [Groq](https://console.groq.com/keys) key,
  since it can fall back to Groq transcription + free gTTS speech output.
- `hey_assistant.py` also needs a working microphone and PortAudio. On
  macOS/Windows the `sounddevice` wheel usually bundles PortAudio; on Linux
  install it separately first (e.g. `sudo apt-get install libportaudio2`
  on Debian/Ubuntu) — the PyPI wheel doesn't bundle it there.

## Running a sample

```bash
export GROQ_API_KEY=...
uv run samples/file_drop_summarizer.py
```

Or keep keys in a `.env` file (copy [`.env.example`](.env.example) as a
starting point — it lists every variable any sample uses) and pass it
explicitly:

```bash
cp .env.example .env   # fill in the keys you have
uv run --env-file .env samples/telegram_bot.py
```

Each script's own docstring has the exact setup steps and, where relevant,
a `curl` command to trigger it.

## What these are (and aren't)

These are **use cases**, not API tours — for a walkthrough of Waken's core
mechanics (scheduling primitives, `broadcast()`, webhook routing) with no
API keys required at all, see
[`examples/`](https://github.com/WakenHQ/waken/tree/main/examples) in the
main `waken` repo instead. Everything here is a small, complete program you
could actually run for yourself: a Telegram bot, a Slack assistant, a
file-drop summarizer, an issue triager, a morning digest, a model
comparison, a voice assistant, a "hey groq, ..." wake-word router.

CI here only lints and syntax-checks the scripts — it can't exercise them
end-to-end without live credentials for half a dozen providers, and several
of them (the bots, the scheduler) block forever waiting on a Source by
design. Running a sample for real, with your own keys, is the actual test.

## License

[MIT](LICENSE)
