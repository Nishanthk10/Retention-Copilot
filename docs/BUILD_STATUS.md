# Build and verification status

Build date: 2026-10-08. This is an implemented local prototype, not a completed live-audio benchmark or a published website.

## Verified here

| Check | Result | Scope |
|---|---|---|
| Python tests | 31 passed | Core and deterministic integration tests; provider/STT doubles where external inference is involved |
| Browser tests | 6 passed | Chromium; ready/mic-denied states, speaker role toggles, three-card cap, end dialog, logs, missing logs, HTML escaping, heartbeat timeout and reconnect |
| Seed validation | Passed | 12 unique synthetic policies; five labeled scenario scripts |
| Python compilation | Passed | Application, summariser, evaluation and utility modules |
| JavaScript syntax | Passed | Browser scripts, replay and AudioWorklet |
| Desktop/mobile inspection | Passed | Ready screen captured at 1440px and 390px; no page errors or horizontal overflow |
| PII boundary test | Passed | Planted card/email absent from captured prompts, audit trace and recovered checkpoint state |
| Completion-only recovery | Passed with deterministic adapters | Cancelled second turn did not replace first committed checkpoint; reconstruction restored the completed state |
| Wire-generation guard | Passed | An older buffered customer utterance cannot restart guidance after a newer customer turn begins |

The build ran on Python 3.12.14, FastAPI 0.142.4, LangGraph 1.2.14, langgraph-checkpoint-sqlite 3.1.1, Pydantic 2.13.5, and Playwright 1.51.0 / Chromium 134. The Node dev dependency is locked in package-lock.json. Normal model dependencies remain declared rather than falsely labeled tested.

## Implemented, awaiting external verification

| Area | Remaining requirement |
|---|---|
| Live Whisper recognition | Install full dependencies/models and speak into the user's microphone on the demo machine |
| Shared MiniLM embedding retrieval | Download model; measure actual semantic retrieval and CPU latency |
| Groq / Gemini adapters | Configure credentials locally, confirm account/model availability, run real requests |
| Ollama fallback | Install/run the configured local model and measure behavior |
| Prompt Guard classifier | Optional configured preview-model request; verify availability and response format |
| S1–S5 audio replay | Engineer must record the included scripts; all five currently fail the recording-readiness check because audio is absent |
| Evaluation and ablation | Run the 75 recorded calls; no success rates, component deltas or latency claims are reported yet |
| Recorded attack evidence | Run S5 and inspect the reported-speech summary, permission record and displayed offers |
| Real process crash experiment | Run evals/crash_resume.py against the recorded corpus; deterministic reconstruction tests do not substitute for this evidence |

## Deliverables

- Complete source tree, tests, seeded KB and scenario scripts.
- Original planning documents retained unchanged under docs/.
- README with Windows and macOS/Linux setup and demo steps.
- Standalone summariser package and reuse guide.
- Replay, scorer, ablation, attack and crash-resume command-line tools.
- Desktop/mobile screenshots in docs/ui-desktop.png and docs/ui-mobile.png (explicit test-mode UI).

## Important implementation differences

- Incremental four-second Whisper windows plus role-boundary finalization are implemented; full VAD-triggered adaptive streaming segmentation is not.
- Checkpoint copying plus an atomic committed-ID pointer enforces the completed-turn recovery rule; blindly resuming the latest intermediate framework checkpoint would not.
- Permission checks render canonical policy terms and enforce explicit tenure, strengthening ID-only validation.
- Pattern-based behavioural masking and PII redaction have known language-coverage limits. Tests prove the included cases, not universal safety.
- No audio fixture was supplied. Replay deliberately remains disabled until real files pass validation; no text bypass or fabricated evaluation corpus was added.
- Token/cost values remain unavailable where the provider gives no reliable value.

Next on the demo machine: configure one provider, install/download the local models, run one live conversation, record S1–S5, then execute the evidence matrix. Do not label the hackathon submission fully evaluated until those results exist.
