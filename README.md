# AICan

An on-device conversational exhibit: a local LLM picks an emotional gesture and a 96×96 software LED matrix plays it, while the character speaks back.

> 🇹🇷 **Türkçe özet:** AICan, Konya Bilim Merkezi için geliştirilen "Yapay zekânın duyguları var mı?" temalı bir sergi ünitesidir. Ziyaretçi konuşur ya da yazar; yerel bir dil modeli (Ollama / Qwen3 4B) uygun jesti seçer, 96×96 yazılım LED matrisi animasyonu oynatır ve karakter sesli yanıt verir. Tüm akış tek bir Flask sürecinde, internet olmadan da çalışabilecek şekilde tasarlanmıştır.

<p align="center">
  <img src="e2e_snapshots/selamlama__emoji__t1.0.png" width="140" alt="selamlama (greeting)">
  <img src="e2e_snapshots/mutluluk_yogun__emoji__t1.0.png" width="140" alt="mutluluk_yogun (joy)">
  <img src="e2e_snapshots/sevgi__emoji__t1.0.png" width="140" alt="sevgi (love)">
  <img src="e2e_snapshots/uzgun_derin__emoji__t1.0.png" width="140" alt="uzgun_derin (deep sadness)">
  <img src="e2e_snapshots/panik__emoji__t1.0.png" width="140" alt="panik (panic)">
</p>
<p align="center"><sub>Frames captured from the 96×96 matrix renderer (upscaled 8×). Emoji art: Google Noto Emoji, Apache 2.0 / OFL.</sub></p>

## Overview

AICan is a kiosk-style exhibit built for the Konya Science Center (Konya Bilim Merkezi), aimed at a mixed audience of children and adults. The exhibit theme is "Do AIs have feelings?". A visitor talks to the character or types a message. A small language model running locally on the exhibit PC chooses one of 32 predefined emotional gestures, the screen plays that gesture as an animation on a 96×96 pixel "LED panel", and the answer is spoken aloud with prosody matched to the emotion.

The same screen also hosts word games in which the AI reacts to winning and losing with the same gesture vocabulary.

There is no hardware to drive: the LED matrix is simulated in the browser. One Python process serves the exhibit screen (`/`) and an operator console (`/control`) to two browser tabs on the same machine.

## Features

- **Gesture-driven replies.** The LLM returns a short Turkish answer plus a gesture id and an intensity; 32 gestures (21 emotional states, 11 conversational responses) are defined in `ai/gestures.json`.
- **96×96 software LED matrix.** 26 gestures play pre-rendered Noto Emoji frames, 6 are generated procedurally; a separate idle "living eyes" animation runs when nobody is talking.
- **Speech in, speech out.** Whisper `large-v3-turbo` for speech-to-text on an NVIDIA GPU; edge-tts for emotion-shaped speech with an offline Piper fallback.
- **Four word games** (word chain, synonym/antonym, proverbs, true/false) driven by deterministic game logic rather than free LLM output.
- **Operator console.** Live status, last command, token and RAM statistics, a model switcher, test-mode toggle and a rolling event log.
- **Offline licensing and installer.** A signed-key licence gate, a demo mode, and a Windows installer built from a Nuitka standalone executable.

## Architecture

```
[Browser: exhibit tab "/"  +  operator tab "/control"]
        |  BroadcastChannel between tabs, fetch('/api/...') to the server
        v
[Flask server: orchestrator/web_server.py]  (single Python process)
        |
        |-- mic audio --> Whisper STT (faster-whisper, CUDA) --> text
        |
        |-- chat ------> LLM bridge --> Ollama / Qwen3 4B --> {reply, gesture, intensity}
        |                  guard layer: language, length, repetition, one retry
        |
        |-- games -----> game engine (deterministic) --> ai/*.json tables
        |                  word validity: local dictionary first, LLM as lenient fallback
        |
        |-- reply -----> gesture engine --> 96x96 matrix frames --> canvas renderer
        |
        `-- reply -----> TTS (edge-tts, Piper fallback, on-disk cache) --> spoken answer
```

The chat path and the game path are separate: games never go through the chat system prompt, so a game cannot be derailed by free-form model output. Each gesture carries valence and arousal values, which the TTS layer converts into speaking rate, pitch and pauses.

## Tech stack

| Area | Technology |
|---|---|
| Server | Python, Flask (threaded) |
| Language model | Ollama, `qwen3:4b-instruct-2507-q4_K_M`, optional baked system prompt via `ollama create` |
| Speech-to-text | faster-whisper (`large-v3-turbo`, CUDA, int8_float16), VAD, optional noise reduction |
| Text-to-speech | edge-tts (primary), Piper (offline fallback), optional ElevenLabs engine, WAV cache |
| Front end | Plain HTML/JS, Canvas 2D (`web/led-panel.js`), `BroadcastChannel` |
| Rendering | Pillow, hand-drawn and parametric patterns on a fixed 96×96 grid |
| Licensing | Ed25519 signatures, AES-GCM content pack, HMAC-bound activation, pywebview licence window |
| Packaging | Nuitka (standalone), Inno Setup installer |
| Tests | pytest |

## Engineering highlights

- **Choosing the model with a benchmark, not by feel.** `logs/` holds the evaluation runs on a fixed 50-example set scoring whether the chosen gesture is acceptable. Gesture accuracy for Qwen3 4B went from 74% with the first prompt to 80% and then 90% across successive prompt revisions; an A/B run of Gemma3 4B on the same 50 examples scored 66% (`logs/baseline_qwen3-4b.json`, `after_faz123_qwen3-4b.json`, `after_prompt_v3_qwen3-4b.json`, `ab_gemma3-4b.json`). Qwen3 4B was kept because Gemma's Turkish is fluent but it follows the gesture rules less reliably.
- **Guarding a small model.** Replies pass a guard layer (maximum words and sentences, Turkish-language check, repetition-loop detection) with a single feedback retry. When Ollama is down, `/api/send` still returns HTTP 200 with a polite fallback line and `meta.degraded: true`, so the kiosk never shows an error box.
- **Offline-first speech.** The Whisper CT2 model and a Piper voice ship inside the installer, and the build refuses to finish without them. Before this, the first launch downloaded the model for roughly 12 minutes during which transcription returned 503. If the network drops, TTS falls back to Piper instead of going silent.
- **Deterministic games on a probabilistic core.** Game flow, scoring and the AI's emotional reactions are plain code; the LLM is only consulted to validate or propose words, with a short timeout and a lenient failure mode so a visitor is never penalised for the model's weakness.
- **Licensing without a server.** Activation is bound to a machine fingerprint (2 of 3 of motherboard, disk and MAC) with HMAC, and demo keys lock if the system clock is rolled back. The `web/` and `ai/` content is shipped as an encrypted `web.pak` decrypted only in memory after the licence check. The documentation also lists the limits of this scheme honestly (obfuscation is a deterrent, not a barrier).
- **A demo licence is a locked test mode.** Demo forces `test_mode` on: two games only, chat disabled (the server answers with a fixed line and never calls the LLM), a visible watermark, model-management endpoints return 403, and the Ollama warm-up thread is never started.
- **Build verification as tests.** `build.py` scans the distribution before producing the installer and stops if it finds an activation file, key material, raw `web/`/`ai/`, a filled ElevenLabs key in the seed config, or a missing Whisper/Piper bundle. Those rules, the licence code and the demo lock are covered by pytest; the last recorded run collected 277 tests, 276 passing plus one known-failing legacy test.
- **Kiosk robustness.** `/api/health` reports Ollama, TTS state and uptime for a watchdog; oversize input is rejected; sessions and game outcomes are written to a structured session log with a per-session summary.

## Project status

Version 0.9.0, pre-delivery. The licence pipeline, standalone Nuitka build and Inno Setup installer have been produced and are locked by tests. The remaining step recorded in the hand-off notes is a manual acceptance test of the full microphone, Whisper and TTS loop on the target machine. The legacy Tkinter interface (`orchestrator/main.py`) is kept in the repository but is unused and excluded from the build. GPU-less machines are untested; the installer targets Windows with an NVIDIA GPU.

## Repository layout

| Path | Purpose |
|---|---|
| `run_web.py` | Entry point: starts the Flask server and opens the two tabs |
| `orchestrator/web_server.py` | Flask app, `/api/*` endpoints, licence gate, demo lock, watermark |
| `orchestrator/llm_bridge.py`, `word_llm.py` | Ollama bridge with guard layer; word-game LLM helper |
| `orchestrator/game_engine.py` | Deterministic word and quiz games |
| `orchestrator/gesture_engine.py` | 96×96 pattern dispatcher and emoji frame playback |
| `orchestrator/tts/` | TTS engines (edge, Piper, ElevenLabs), emotion-to-prosody map, cache |
| `ai/` | `gestures.json`, `system_prompt.txt`, game data tables |
| `web/` | Exhibit screen, control panel, LED renderer |
| `lisans*.py`, `parmak_izi.py`, `web_paket.py` | Licensing, fingerprint, encrypted content pack |
| `build.py`, `installer/Aican.iss` | Nuitka build and Inno Setup installer |
| `tests/`, `orchestrator/test_*.py` | pytest suites (licence, build, demo lock, TTS, quiz) |
| `docs/` | Install guide, delivery checklist, design plans and specs |
| `JESTLER.md` | Generated gesture catalogue (`orchestrator/build_jest_rehberi.py`) |

## Running locally

Requires Python 3.10+, an NVIDIA GPU for speech recognition, and [Ollama](https://ollama.com) with the model pulled.

```bash
ollama pull qwen3:4b-instruct-2507-q4_K_M
pip install -r orchestrator/requirements.txt
python run_web.py        # opens the exhibit tab (/) and the control panel (/control)
python -m pytest -q      # run the test suite
```

Running from source skips the licence gate; the installer build enforces it.

Full setup, calibration and kiosk operation (Turkish): [docs/INSTALL.md](docs/INSTALL.md). Installer guide for end users: [docs/KURULUM.md](docs/KURULUM.md). Gesture catalogue: [JESTLER.md](JESTLER.md).

## Acknowledgements

The idle "living eyes" animation (`EyeSystem` in `web/led-panel.js`) was re-implemented for the 96×96 canvas pipeline, taking behavioural ideas (blinking, idling, curiosity states) from [FluxGarage/RoboEyes](https://github.com/FluxGarage/RoboEyes) (MIT) and [sidikalamini/eyes-animation](https://github.com/sidikalamini/eyes-animation). No code was copied.
