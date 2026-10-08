# Retention Copilot

A local, single-call assistant for retention conversations. It listens to role-tagged browser audio, shows immediate tips plus model-guided suggestions, and records an auditable trace. It never changes an account or contacts a customer.

**Implementation is included. Live model/STT performance and the recorded-call evaluation are not yet validated.** See [BUILD_STATUS.md](docs/BUILD_STATUS.md) for precisely what was tested and what remains.

## Start on Windows (PowerShell)

Install Python 3.11 or 3.12, extract this folder, then open a terminal here:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
```

Set `GROQ_API_KEY` in `.env`, or run a local Ollama model and set `OLLAMA_MODEL` to its installed name. Gemini is an optional fallback. Keep credentials on your machine; do not put them in a chat, recording, or source control.

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** in Chrome or Edge. Keep the terminal running. Initial startup downloads `small.en` and `all-MiniLM-L6-v2`; this needs internet access and disk space. The page shows “Starting up…” until both are ready. Later, `MODEL_OFFLINE=true` uses cached models only.

## Start on macOS / Linux

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env with your provider configuration.
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

No provider credentials are bundled. No paid service was called during this build. Provider availability, quotas, pricing and your machine's model capacity must be checked before the hackathon; this project does not guarantee zero-cost hosted inference. Ollama runs locally if you install a suitable model.

## Give the demo

1. Click **Start call** and allow the microphone. It begins paused.
2. Click **Sales Rep** or **Customer** before that person speaks. Switching the role, or clicking the active role again, closes the previous turn. One physical microphone is shared; there is no automatic speaker identification.
3. After a customer turn closes, look for **Quick tip** and **Suggested approach** cards. At most three remain visible. Suggestions are advisory and the offers are fictional.
4. For tenure-dependent offers, have the customer explicitly state tenure (for example, “Seven months”). The permission check enforces the synthetic rule before rendering the catalog's exact wording.
5. Click **End call**, then **Open log** to inspect model attempts, tool results, permission decisions, and displayed items. Logs contain brief decision rationales, not requests for hidden chain-of-thought.
6. Follow [the recording guide](scripts/record_scenario.md), then choose **Replay test call**. Until WAVs exist, replay is visibly unavailable.

The app binds to localhost, uses no login, and processes synthetic data. Do not expose it to a public network as-is. Microphone permission requires localhost or HTTPS. A call resumes after a backend restart or a browser refresh; speech during the gap is lost and you must choose a speaker again. Reconnect does not replay missed speech. The checkpoint restores only the last completed customer graph; uncommitted turns may be lost and are recorded as possible missed turns.

## What is implemented

- FastAPI, two WebSockets, mono PCM16 audio at 16 kHz, AudioWorklet resampling and role-boundary flushing.
- Faster Whisper CPU/int8 processing of incremental four-second windows with VAD; accumulated transcript is finalized on role switch. This is **chunked recognition**, not token-by-token streaming or a guarantee of low latency.
- Shared MiniLM embeddings for in-memory KB retrieval and LLM-free keyword/embedding tips.
- Explicit LangGraph context, fast-lane, agent, permission and emit nodes; offer and behaviour agents run concurrently.
- One optional KB search per offer-agent turn. Behaviour agent has no tools.
- Groq → Ollama → Gemini, up to three rounds, with task cancellation on a new customer turn or hang-up. Missing providers are logged and fall through. Model names are configurable where needed.
- A standalone background summariser: ten configured fields, injection flags, delimited input, schema/content validation, previous-summary preservation, and SQLite storage.
- Allow/Mask/Deny checks, canonical offer wording, tenure checks, duplicate suppression, and fail-closed output.
- Completion-only LangGraph SQLite snapshots with an atomically committed snapshot pointer. Intermediate graph steps cannot become the recovery state.
- A live transcript, mood, connection recovery, call-ended dialog, and readable log timeline with raw JSON expansion.
- Twelve synthetic policies, five labeled scripts, WebSocket audio replay, scoring, five ablation variants, attack and crash-resume runners.

## Verify the implementation

For checks without downloading speech/embedding models, install the lighter development dependencies:

```bash
python -m pip install -r requirements-core.txt
python -m pytest -q
python scripts/validate_seed.py
```

`TEST_MODE=true` starts the web/API shell without model downloads. It uses lexical KB search and disables speech recognition. It is explicitly labeled and **is not a live AI demo, audio replay substitute, or valid evaluation mode**. Integration tests inject provider/STT doubles only inside tests; there is no production text-input shortcut.

Browser tests:

```bash
npm install
npx playwright install chromium
npm run test:ui
```

The Playwright config starts a dedicated local test server. Stop any server already using port 8000 first. `ui_tests/` contains role, state, log, and error checks; see build status for which were actually run here.

## Run real audio evidence

Record all five scripts once before evaluating. Synthetic TTS is not silently substituted for the engineer's recordings.

```bash
python -m evals.check_recordings
# With a normal, non-test-mode server running:
python -m evals.replay --scenario S1 --dry-transcript
python -m evals.attack
# Stop other eval servers. This manages its own server on 8011:
python -m evals.ablation --runs 3
# Optional single-provider comparison:
python -m evals.ablation --runs 3 --model-provider ollama
# Dedicated recorded-audio crash experiment on 8012:
python -m evals.crash_resume --scenario S5 --kill-at-turn 6
```

The full matrix is 5 scenarios × 3 repeats × 5 variants = 75 runs. Run reports are written only from actual audio WebSocket results. No benchmark scores or attack-success claims have been fabricated.

Scoring includes offer-within-four-turns, non-KB IDs, turns to first offer, offer flip-flops, suggestions per turn, word error rate, summary reason accuracy, KB retrieval hits and behavior type-match. The accompanying JSON retains per-run component data. Compare matched scenarios and providers across variants. A timeout is an incomplete run, not a successful evaluation. Exact-ID scoring alone is not a general semantic safety proof.

The `naive` and knockout modes deliberately remove protections for local evaluation. They require `EVAL_MODE=true`; PII masking cannot be disabled. Normal live use always starts with `EVAL_CONFIG=full`. Run unsafe variants with synthetic inputs only and separate output directories.

## Reusable component and architecture notes

See [summariser/README.md](summariser/README.md). It imports nothing from `app/`, takes injected providers/loggers and can be installed separately with `pip install ./summariser`.

Original planning files are preserved in `docs/`. [IMPLEMENTATION_NOTES.md](docs/IMPLEMENTATION_NOTES.md) explains checkpoint commit semantics, controls, implementation differences and known limitations. Tests cannot establish general prompt-injection immunity or complete PII detection.

## Troubleshooting

- **Starting up / Setup needed:** install the full requirements, ensure model downloads are available, and restart. If working offline, first populate the model cache.
- **No slow suggestions:** inspect the call log's `model_retry` records. Configure a provider or start Ollama with the configured model. Keys are never sent to the browser.
- **Microphone denied:** allow microphone access for localhost in browser settings, then try again. Audio is sent only while a role is active.
- **409 when starting:** the single allowed call is already live. Reload the page to reconnect and end it.
- **Replay disabled:** record WAVs and timing.json, run the recording checker, then reload.
- **Slow CPU:** model inference may dominate latency. Test on the hackathon machine before presenting; no live latency benchmark is claimed.
- **Permission denied / no new card:** inspect the permission decision. Missing tenure, unknown offers, commercial behaviour text and duplicates are suppressed.
- **Missing token/cost values:** a provider did not supply a comparable usage field or cost. The log leaves them unavailable rather than inventing prices.
