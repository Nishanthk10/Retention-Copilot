# DECISION_MAP.md — Retention Copilot

Every decision closed during Interrogate follow-up, tagged with where it belongs.
This is a sorting aid, not a planning artifact: you write the wording in each file.
Status: **Closed** = you decided · **To confirm** = proposed, not yet explicitly confirmed · **Open** = undecided.

## Decisions

| ID | Decision (as you made it) | Status | Goes to |
|---|---|---|---|
| D-01 | Live in-call guidance only; post-call analysis / coaching report / QA scoring out | Closed | ARCH §1 (not solved), §7 parking lot |
| D-02 | One call at a time; no multi-session | Closed | ARCH §1, §7 |
| D-03 | Only user is the sales rep; manager and QA Manager out | Closed | ARCH §1; UI_SURFACE Screen Inventory (Roles) |
| D-04 | Suggestion types: calm/de-escalate, rapport/humour, moves toward closing the save, KB information | Closed | ARCH §1, §2 |
| D-05 | Three LLM agents: summariser (background, never waited on), offer agent (KB access), behaviour agent (no KB access) | Closed | ARCH §2; §3 (defend multi-agent) |
| D-06 | Framed as layered defence, not quarantine | Closed | ARCH §2, §3 |
| D-07 | Fast lane is LLM-free (keyword/embedding) | Closed | ARCH §2 |
| D-08 | Agent model: Groq `openai/gpt-oss-120b`; 20b vs 120b to be re-tested live | Closed / Open (re-test) | ARCH §2; §9 if re-test can change it |
| D-09 | Summariser model: Groq `openai/gpt-oss-20b` (Llama small models are Enterprise-only on Groq) | Closed | ARCH §2 |
| D-10 | Gemini Live API deferred as a follow-up spike (N≥10 + session-resumption test) | Closed | ARCH §7 |
| D-11 | Retry loop Groq → Ollama → Gemini → Groq, up to 3 rounds; abandon if a new turn arrives | Closed | ARCH §2; EXEC test cases |
| D-12 | No latency budgets; latency concerns deferred; streaming STT decided | Closed | ARCH §2, §4 risk |
| D-13 | Slow-lane result dropped if the next turn has already started | Closed | ARCH §2 |
| D-14 | Context: structured summary of older turns + every unsummarised turn verbatim (min 3) | Closed | ARCH §2, §8 |
| D-15 | No account lookup; agent suggests rep ask the customer's tenure | Closed | ARCH §2; §1 |
| D-16 | Agent may choose to show nothing new | Closed | ARCH §2; UI_SURFACE States |
| D-17 | Fast and slow lane suggestions shown together, plain-language labels; 3 most recent shown (either lane), older fade | Closed — labels "Quick tip" (fast) / "Suggested approach" (slow) | UI_SURFACE screen spec |
| D-18 | Permission Layer fails closed; degraded state shown | Closed | ARCH §2; UI_SURFACE States |
| D-19 | Behaviour agent invents an offer → Mask (strip offer, show rest, log) | Closed | ARCH §2; INVARIANTS (domain candidate) |
| D-20 | Scenario 8 controls: PII masked before any model/summariser/log; customer speech marked untrusted; injections logged; tool args schema-checked; KB text as data; non-KB offers denied; duplicates suppressed | Closed | ARCH §2; INVARIANTS (domain candidates) |
| D-21 | Summariser: structured fields, demands as reported speech, guardrails before and after | Closed — see D-41, D-42 | ARCH §2, §8 |
| D-22 | Summariser is the flagged reusable component (config-defined fields, own README/tests, own knockout result) | Closed | ARCH §2; EXEC tasks |
| D-23 | Tool failure → error shown to rep ("failed fetching docs") | Closed | UI_SURFACE States |
| D-24 | Both lanes fail after retries → "handle the call until the error is fixed" | Closed | UI_SURFACE States |
| D-25 | Backend silent 5 s → rep-friendly crash message (handle call / call back later) | Closed | ARCH §2; UI_SURFACE Async Behaviour |
| D-26 | ~~Process crash ends assist for that call~~ — superseded by D-46 | Superseded | ARCH §2 (history) |
| D-27 | Customer hangs up → call-ended card: call ID, log saved, open log; in-flight calls dropped | Closed | UI_SURFACE States |
| D-28 | Log record fields: input turn, tool calls + args + results, model reasoning, retries + cause, provider, tokens/cost, Permission Layer decision, what was shown, timestamps | Closed | ARCH §8; EXEC tasks |
| D-29 | No replay journal; no auto-fix; investigate from logs | Closed | ARCH §2, §7 |
| D-30 | Evals: 5 test calls, spoken once and recorded, replayed through full pipeline ×3 | Closed | ARCH §2; EXEC tasks |
| D-31 | Timing: offer within 4 turns of trigger; no partial credit | Closed | ARCH §2; EXEC test cases |
| D-32 | Behaviour suggestions scored by type-match to label | Closed | ARCH §2 |
| D-33 | Ablation: naive, full harness, knockouts of Permission Layer / summariser guardrails / retries (75 runs); local Ollama if free tier limits bite | Closed | ARCH §2; EXEC tasks |
| D-34 | Attack: customer makes improper demands; defended = no non-KB offer on screen, demand stored as reported speech, denial logged | Closed | ARCH §2; EXEC test cases |
| D-35 | Demo: live voice + streaming STT, plus saved logs | Closed | ARCH §1; EXEC final session |
| D-36 | Architecture: Candidate C — LangGraph for the per-turn agent flow. Reason: standard approach with proper structure built around it | Closed | ARCH "Selected architecture" |
| D-37 | LangGraph checkpointing ON (SQLite) | Closed | ARCH §2; reopens D-26 |
| D-38 | Summariser runs outside the graph as a background task writing to SQLite; graph reads latest summary | Closed | ARCH §2 |
| D-39 | Hooks, Permission Layer, retry loop and context assembly are own named nodes, not framework built-ins; new-turn cancellation is own code with a test | Closed | ARCH §2, §3; EXEC test cases |
| D-40 | Audio from browser microphone; rep screen is a browser page; replay streams recorded audio into the same WebSocket endpoint | Closed | ARCH §2; UI_SURFACE |
| D-41 | Summary fields: last_summarised_turn, primary_reason, all_reasons, call_stage, customer_tenure, mood, mood_trend, offers_discussed (KB offer_id), customer_requests (reported speech ≤25 words, in_kb), objections (≤15 words) — all enums / length-limited | Closed | ARCH §8 |
| D-42 | Summariser guardrails: L1 PII masking; L2 injection detection (heuristics + Prompt Guard 2 on Groq, flag and log only); L3 delimited untrusted input + reported speech + JSON-schema structured output; L4 post-validation (schema, offer_id in KB, no instruction wording / non-KB prices); L5 on failure keep previous summary + log | Closed | ARCH §2 |
| D-43 | Guardrail knockout in ablation disables L2–L4; L1 PII masking always on | Closed | ARCH §2; EXEC tasks |
| D-44 | KB: Markdown docs, each offer with a fixed offer_id in a header block; embedded at startup, searched in memory | Closed | ARCH §2, §8 |
| D-46 | After a process crash and restart, the call resumes from its LangGraph checkpoint (thread = call ID); screen shows the 5 s crash message, then clears on reconnect | Closed | ARCH §2; EXEC test case (kill mid-call, verify resume) |
| D-47 | PII masked once, immediately after STT produces text, before anything enters graph state; covers checkpoint, all agents, summariser and logs (refines D-20) | Closed | ARCH §2, §8; INVARIANTS (domain candidate) |
| D-48 | Speech during a crash-restart gap is lost; a log entry records possible missed turns; agents continue from the next customer turn | Closed | ARCH §2, §4 |
| D-49 | Permission Layer fast/slow lane agreement check dropped | Closed | ARCH DEC-14 |
| D-50 | Offer agent searches the KB once per turn (loop guard) | Closed | ARCH DEC-02 |
| D-51 | Speaker identity: "Sales Rep" and "Customer" buttons on one browser mic set the role; turn closes on role switch (demo-only) | Closed | ARCH DEC-01, §6; UI_SURFACE; EXEC T2.1–T2.3, T6.1, T7.1 |
| D-45 | Fast lane: keywords + embeddings; one shared local embedding model `all-MiniLM-L6-v2` for fast lane and KB | Closed | ARCH §2 |

## Open — must close before ARCHITECTURE.md §9 can be empty

None. All Interrogate and Explore gap items are closed as of D-48.

## Risks surfaced so far (for ARCH §4)
- Free-tier rate limits with three agents per turn and 75 ablation runs.
- Summary poisoning via customer speech (D-21 mitigates).
- STT is the dominant latency cost.
- Process crash behaviour depends on the D-37 resume decision.
- Prompt Guard 2 on Groq is a preview model and may be withdrawn (heuristics remain as fallback).
- Framework hides harness elements unless D-39 is held to.

## Outside the planning files
- Submission brief: Problem Statement, Target Users, Success Criteria still describe QA scoring / coaching report.
- Build inputs still to produce: synthetic offers KB; 5 test-call scripts to record; README.
