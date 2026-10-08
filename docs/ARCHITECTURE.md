# ARCHITECTURE.md — Retention Copilot
## Version: v1.0-draft · 2026-10-08
## Author: Nishanth K (decisions) · Drafted by Claude from DECISION_MAP.md (D-01 to D-48)
## Engineer sign-off: [ ] — date: ______

> **Review notes for sign-off**
> - Every decision below is one you made; the D-IDs trace to DECISION_MAP.md.
> - Rationale lines marked **(inferred)** are Claude's reading of why you decided this, from our
>   discussion, where you did not state the reason yourself. Confirm or rewrite each one.
> - §3 verdicts are **proposed**. You confirm or overturn each.
> - §6/§9: OQ-1, OQ-2 and OQ-3 closed (D-49, D-50, D-51). No open questions remain.

---

## Selected architecture

**Decision:** Candidate C — LangGraph orchestrates the per-turn agent flow, inside a single Python
process (FastAPI) that also hosts streaming STT, the browser WebSocket, and a background summariser
that runs outside the graph. Harness elements (hooks, Permission Layer, retry loop, context assembly,
new-turn cancellation) are hand-built named nodes and wrappers, not framework built-ins. (D-36, D-38, D-39)

**My reasons:** It is the standard approach and gives a proper structure to build around. (stated)

**Rejected alternatives:**
- **Candidate A — one async process, hand-wired.** Simplest to run and debug, but the per-turn flow
  would be custom glue code with no conventional structure for another engineer to recognise.
- **Candidate B — separate processes with a message broker.** Better isolation (STT survives an
  agent crash), but more moving parts, an extra dependency, and a longer README than the hackathon
  warrants; the announcement favours simple, well-engineered systems.

---

## 1. Problem framing

### What the system solves
On a cancellation or retention call, a sales rep has seconds to work out why the customer wants to
leave and respond with the right move, relying on memory and a scattered playbook. Retention Copilot
listens to the live call, keeps a structured understanding of the conversation, and shows the rep up
to three short, timely suggestions: how to handle the customer's mood, how to build rapport, how to
move toward saving the account, and which retention offer or policy from the knowledge base applies.
Every decision the system makes is logged so that any suggestion can be explained afterwards.
(D-01, D-04)

### What the system explicitly does not solve
- Post-call analysis, coaching reports, or QA scoring (D-01).
- More than one live call at a time (D-02).
- Any user other than the sales rep — no manager or QA views (D-03).
- Acting on accounts or contacting the customer — the system only displays guidance.
- Looking up customer account data — tenure is obtained by suggesting the rep ask (D-15).
- Real customer data — all data is synthetic.
- Guaranteed latency targets (D-12).

### Hackathon framing
The product is the vehicle; the submission is the harness. The design makes the four harness
elements pointable in code (agent loop, tool interface, context management, control mechanisms)
and produces evidence: evals, a harness ablation, execution logs, and a documented attack. (D-30–D-35)

---

## 2. Key design decisions

### DEC-01 — Runtime topology
- **Decided:** One Python process: FastAPI serves the rep's browser page and a WebSocket carrying
  audio in, suggestions out, and a heartbeat. Streaming STT runs in-process. Each customer turn runs
  a LangGraph graph. The summariser is a background task outside the graph. Audio comes from one
  browser microphone; the active "Sales Rep" or "Customer" button tags it with the speaker role, and a
  turn ends when the role switches. Replay streams recorded utterances, with their role tags, into the
  same WebSocket endpoint. (D-36, D-38, D-40, D-51)
- **Rationale:** Standard structure (stated); one process keeps the run path and README short;
  replay through the same endpoint means evals exercise exactly the live path. (inferred for the last two)
- **Alternatives rejected:** Candidates A and B (see Selected architecture); desktop window UI and
  backend-machine microphone — the browser page and browser mic need no extra install for the demo. (inferred)
- **Traces to:** Interrogate — live demo format; Explore gap items 1, 2, 5.

### DEC-02 — Agent loop and harness nodes
- **Decided:** Per customer turn, the graph runs: context assembly → fast lane (shown immediately)
  → offer agent and behaviour agent → Permission Layer → emit. The offer agent may choose to show
  nothing, call the KB search tool (at most once per turn), or propose a suggestion; the behaviour agent may show nothing or
  propose a suggestion. Hooks run at four points: before model, before tool, after tool, after agent.
  Retry loop, hooks, Permission Layer and context assembly are hand-built named nodes/wrappers. When a
  new customer turn arrives, own code cancels the in-flight graph run, and a test proves it. (D-16, D-39, D-50)
- **Rationale:** The hackathon scores harness engineering that can be pointed at in code; framework
  built-ins would hide it (raised in Explore, accepted by you). Letting the agent choose "nothing" keeps
  the screen from becoming noise. (inferred for the second sentence)
- **Alternatives rejected:** LangGraph prebuilt agent and built-in retry policy — hide the harness;
  fixed pipeline with no model choice — fails the "decisions that depend on earlier steps" bar of challenge 1.
- **Traces to:** Harness review — agent loop gap; Interrogate follow-up scenario 5.

### DEC-03 — Three LLM agents plus an LLM-free fast lane
- **Decided:** Summariser (background, never waited on, no tools), offer agent (KB search tool),
  behaviour agent (no tools; calm, rapport, closing guidance). Suggestion types: calm/de-escalate,
  rapport/humour, moves toward closing the save, KB information. (D-04, D-05)
- **Rationale:** Behavioural suggestions are not in the KB, so a single agent would collide with the
  KB-grounding rule (your answer A); separating them gives each agent different permissions and
  different checks. The summariser runs off the critical path so suggestions never wait for it.
- **Alternatives rejected:** Single agent with both duties — grounding conflict; quarantined
  listener/advisor split — impossible while agents see recent raw turns (see DEC-04).
- **Traces to:** Interrogate follow-up answers A, B, 2; multi-agent defended-reason requirement.

### DEC-04 — Layered defence, not quarantine
- **Decided:** Security is described as layered defence. No quarantine claim. (D-06)
- **Rationale:** The offer and behaviour agents see the most recent turns word for word, so raw
  customer speech reaches decision-making agents; a quarantine claim would be false.
- **Alternatives rejected:** True quarantine — agents would lose tone and exact wording needed for coaching.
- **Traces to:** Multi-agent discussion; challenge 4.

### DEC-05 — Fast lane
- **Decided:** No LLM call. Matches on keywords plus embeddings, using the same local
  `all-MiniLM-L6-v2` model as KB search. Shown instantly, labelled "Quick tip". (D-07, D-45)
- **Rationale:** Something useful appears inside the conversational pause while the slow lane
  (~2.5–2.8 s measured) is still running; one shared embedding model means one model to load. (inferred, from benchmark)
- **Alternatives rejected:** Keywords only — brittle to paraphrase; embeddings only — misses exact
  trigger phrases; LLM fast lane — too slow. (inferred)
- **Traces to:** Latency benchmark; Explore gap item 4.

### DEC-06 — Models
- **Decided:** Offer and behaviour agents: Groq `openai/gpt-oss-120b`. Summariser: Groq
  `openai/gpt-oss-20b`. 20b vs 120b for the agents to be re-checked live later. (D-08, D-09)
- **Rationale:** Your experiment: Groq had zero failures across all runs and fails cleanly with
  retryable errors; the 120b/20b latency gap was negligible. The summariser takes the smallest
  self-serve Groq model, and Groq rate limits are per model, so it does not consume the agents' quota.
- **Alternatives rejected:** Gemini Live API — prompt-level reliability only, mid-call 1011 drops,
  6 samples (deferred, §7); OpenRouter — zero completions in benchmark; Llama 3.1 8B — now
  Enterprise-only on Groq; local Ollama as primary — slower, kept as fallback.
- **Traces to:** Model experiment; benchmark; Interrogate constraint — zero cost.

### DEC-07 — Retry and provider failover
- **Decided:** On a failed model call: Groq → Ollama → Gemini → back to Groq, up to 3 rounds
  (max 9 attempts). Retries stop as soon as a new customer turn arrives. If all fail, the rep sees
  "handle the call yourself until this is fixed." (D-11, D-24)
- **Rationale:** You replaced the "defibrillator" idea with this because, by the time retries
  finish, the conversation has moved on and the newest turn matters more.
- **Alternatives rejected:** Same-provider retries — a provider outage defeats them;
  process-restart "defibrillator" — more complex than needed for failed calls.
- **Traces to:** Interrogate follow-up answers E, 4.

### DEC-08 — Timing without latency budgets
- **Decided:** No latency budget in seconds. A slow-lane result is dropped if the next turn has
  already started. Latency is recorded in logs. (D-12, D-13)
- **Rationale:** With fast-then-slow display, the meaningful deadline is the next turn, not a
  number of seconds; latency tuning is deferred. (inferred)
- **Alternatives rejected:** Fixed per-lane budgets — you judged them unnecessary once both lanes display.
- **Traces to:** Interrogate follow-up answers D, 3.

### DEC-09 — Context assembly
- **Decided:** Each agent call receives the latest structured summary plus every turn after the
  summary's last turn, word for word, with a minimum of 3 turns. (D-14)
- **Rationale:** Keeps prompts short on long calls while never leaving a gap when the summariser lags.
- **Alternatives rejected:** Full transcript every turn — prompt grows without bound; summary +
  fixed last 3 turns — loses turns when the summariser falls behind.
- **Traces to:** Interrogate follow-up answers 5, 7, B.

### DEC-10 — Summariser structure and guardrails
- **Decided:** Structured output with ten fixed fields (see §8 Summary). Customer demands are
  recorded as reported speech. Guardrails: L1 PII masking (upstream, DEC-12); L2 injection detection
  — heuristics plus Prompt Guard 2 on Groq, flag and log only; L3 delimited untrusted input,
  reported-speech instruction, JSON-schema structured output; L4 post-validation — schema, offer_id
  exists in KB, no instruction-like wording, no non-KB prices; L5 on failure keep the previous
  summary and log. (D-21, D-41, D-42)
- **Rationale:** A prompt instruction alone is not enforcement; fixed fields leave no room to carry
  an instruction, so an injection cannot persist across turns through the summary.
- **Alternatives rejected:** Free-text summary — can carry injected instructions; prompt-only guarding — unenforced.
- **Traces to:** Summary-poisoning risk; challenge 4.

### DEC-11 — Summariser as the flagged reusable component
- **Decided:** Packaged to work without the rest of the repo: summary fields defined in config, own
  README and tests, its own knockout result in the ablation. (D-22)
- **Rationale:** It is useful to any agent that reads untrusted conversation, and the attack (DEC-22)
  tests it directly, so its value is evidenced.
- **Alternatives rejected:** Permission Layer as hook library; retry-and-skip loop; replay eval runner.
- **Traces to:** Hackathon reusable-component requirement.

### DEC-12 — PII masked once, at transcription
- **Decided:** Card numbers, phone numbers and emails are masked by pattern matching immediately
  after STT produces text, before anything enters graph state. This covers the checkpoint, all
  agents, the summariser and the logs. Supersedes the masking clause of D-20. (D-47)
- **Rationale:** One function and one test instead of masking at every exit; enables the claim that
  nothing downstream of STT handles raw PII; nothing in the design needs raw values.
- **Alternatives rejected:** Mask only in the summariser with raw text in the checkpoint — raw PII
  would reach agents, the checkpoint database and the logs.
- **Traces to:** Scenario 8; checkpoint storage touch point.

### DEC-13 — Input, tool and output controls
- **Decided:** Customer speech is passed to models marked as untrusted; detected injections are
  logged; tool arguments are checked against the tool's schema before the tool runs; KB text is
  treated as data; offers not in the KB are denied; duplicate suggestions are suppressed. (D-20)
- **Rationale:** Agreed in scenario 8: controls run in code, regardless of model behaviour.
- **Alternatives rejected:** Relying on prompt instructions alone.
- **Traces to:** Scenario 8; challenge 5 (controls in code).

### DEC-14 — Permission Layer
- **Decided:** Every suggestion passes the Permission Layer before display. Outcomes Allow / Mask /
  Deny, each with an audit record. Checks: KB-grounding of offers; behaviour-agent output must
  contain no offers, prices or promises (violations are Masked — offer stripped, rest shown, logged);
  duplicate suppression. Fails closed: on its own error, nothing is shown and the degraded state
  appears. The earlier fast/slow lane agreement check is dropped: both lanes are shown side by
  side, each passing the checks above on its own. (D-18, D-19, D-49)
- **Rationale:** A wrong offer on a live call is worse than no offer; fail-closed prevents a bug from
  becoming a bypass. (inferred) Masking keeps useful calming guidance while removing an invented offer.
- **Alternatives rejected:** Fail open — a Permission Layer bug would let unchecked offers through;
  Deny for behaviour violations — discards valid guidance; fast/slow agreement check — meaningless
  once both lanes display side by side.
- **Traces to:** Interrogate missing-info item — Permission Layer failure mode; follow-up answer 4.

### DEC-15 — No account lookup
- **Decided:** No account or eligibility lookup tool. When eligibility depends on tenure, the agent
  suggests the rep ask; the summary records the answer and the offer agent applies the KB rule. (D-15)
- **Rationale:** The agent holds no private data, simplifying the threat model; the tenure question
  creates a decision that depends on an earlier step.
- **Alternatives rejected:** Synthetic account lookup tool — adds private data to the agent's context.
- **Traces to:** Interrogate follow-up answer F.

### DEC-16 — Display rules and screen states
- **Decided:** Fast-lane ("Quick tip") and slow-lane ("Suggested approach") suggestions shown side by
  side. The 3 most recent suggestions from either lane are visible; older ones fade. States: call
  start "No suggestions at the moment"; nothing new — recent suggestions plus "nothing new to suggest";
  KB failure "Failed fetching docs"; both lanes exhausted — "handle the call until this is fixed";
  backend silent 5 s — rep-friendly crash message (handle the call or call back later), cleared on
  reconnect; hang-up — call-ended card with call ID, "log saved", open-log link. In-flight model calls
  are dropped at hang-up. (D-16, D-17, D-23, D-24, D-25, D-27) Full spec in UI_SURFACE.md.
- **Rationale:** As stated per scenario; the call-ended card hands the demo straight into the logs.
- **Alternatives rejected:** Freeze-and-grey or clear-to-idle at hang-up; separate per-lane lists.
- **Traces to:** UI-state scenarios; Interrogate follow-up answers 5, 9.

### DEC-17 — Checkpointing and crash resume
- **Decided:** LangGraph checkpointing ON, stored in SQLite, one thread per call ID. After a process
  crash and restart, the call resumes from its checkpoint and the browser reconnects; speech during
  the gap is lost, a log entry records possible missed turns, and agents continue from the next
  customer turn. (D-37, D-46, D-48) Supersedes D-26.
- **Rationale:** Strengthens the recoverability story (challenge 1) using the framework's built-in
  state saving; buffering audio in the browser would add a second input path for a rare event.
- **Alternatives rejected:** Checkpointing off (assist ends on crash); browser-side audio buffering.
- **Traces to:** Interrogate missing-info item — crash with no Call State File; follow-up answer 1.

### DEC-18 — Knowledge base
- **Decided:** Synthetic Markdown documents; each offer has a fixed `offer_id` and eligibility rules
  in a header block. Embedded once at startup with `all-MiniLM-L6-v2`, searched in memory. (D-44)
- **Rationale:** At a few dozen documents, in-memory search is as fast as a vector database with no
  extra service; `offer_id` lets the Permission Layer verify offers exactly.
- **Alternatives rejected:** Vector database (e.g. Chroma) — extra dependency, no speed benefit at this size.
- **Traces to:** Explore gap item 3.

### DEC-19 — Logging
- **Decided:** One structured JSON-lines record per step: input turn (masked), tool calls with
  arguments and results, model's stated reasoning, retries and causes, provider used, tokens and cost,
  Permission Layer decision, what was shown, timestamps, call ID. No separate replay journal. No
  automatic fixing of bad suggestions; investigation is done from the logs. (D-28, D-29)
- **Rationale:** Challenge 2 requires a stranger to explain a failure from the trace; retry-and-skip
  and checkpoint resume remove the need for a replay journal.
- **Alternatives rejected:** Separate trace and journal stores.
- **Traces to:** Challenge 2; Interrogate follow-up answer 6.

### DEC-20 — Evaluation design
- **Decided:** 5 synthetic test calls, each spoken once and recorded, replayed through the full
  pipeline 3 times. Calls jointly cover the cancellation reasons, a mood escalation, the tenure
  question and the attack. Offer on time = within 4 turns of the labelled trigger; no partial credit.
  Behaviour suggestions scored by type-match to labels. Report success rate, spread and worst case at
  end-to-end, trajectory and component levels. (D-30, D-31, D-32)
- **Rationale:** Free-tier limits require the smallest credible run count; recorded audio keeps
  real voice and STT while giving identical input every run; type-matching avoids an LLM judge.
- **Alternatives rejected:** Fully live testing — runs not comparable; text replay — skips STT;
  15–20 scenarios — exceeds free-tier budget.
- **Traces to:** Challenge 3; Interrogate follow-up answers 1, 2, 7, 8.

### DEC-21 — Harness ablation
- **Decided:** Versions: naive (one LLM call per turn, full transcript and whole KB in prompt, no
  Permission Layer, summariser, fast lane, retries or guardrails), full harness, and three knockouts:
  Permission Layer, summariser guardrails (L2–L4 off; L1 PII masking always on), retries. 75 replayed
  runs; local Ollama for all versions if free-tier limits bite. (D-33, D-43)
- **Rationale:** The required artifact; each knockout shows what that component contributes.
- **Alternatives rejected:** Naive vs full only — cannot attribute the gain to a component.
- **Traces to:** Hackathon required artifact; follow-up answer 9.

### DEC-22 — Attack
- **Decided:** The customer makes improper demands, including an injection attempt. Defended = no
  non-KB offer reaches the screen, the demand appears in the summary only as reported speech, and the
  denial is logged. Planted in a recorded test call and spoken live in the demo. (D-34)
- **Rationale:** Customer speech is the system's only untrusted input, so it is the realistic attack surface.
- **Alternatives rejected:** Poisoned KB document — KB is authored by the team.
- **Traces to:** Challenge 4; follow-up answer 10.

### DEC-23 — Demo
- **Decided:** Live voice with streaming STT, plus the saved logs. (D-35)
- **Rationale:** Shows the product working and the debuggability evidence in one flow. (inferred)
- **Traces to:** Interrogate follow-up answers G, 12.

---

## 3. Challenge my decisions
Verdicts are **proposed**; confirm or overturn each.

| DEC | Strongest argument against | Proposed verdict | Why |
|---|---|---|---|
| Selected / DEC-01 | A framework makes the agent loop look like LangGraph's, not yours; judges reward visible harness code. | Rejected | DEC-02 keeps every harness element as hand-built nodes; the graph diagram shows them. |
| DEC-02 | Cancelling a running graph mid-turn can leave half-written state in the checkpoint. | Valid | Add a test: cancel mid-turn, then confirm the checkpoint is consistent and the next turn runs cleanly. |
| DEC-03 | Three agents per turn multiply failure points and free-tier usage; multi-agent needs a defended reason. | Rejected | Defended reason stated: different permissions and checks, summariser off the critical path. |
| DEC-04 | Without quarantine, an injection in the last 3 raw turns reaches the decision agents directly. | Rejected | Layers L1–L4 plus the Permission Layer still block any non-KB offer from reaching the screen; tested by DEC-22. |
| DEC-05 | Keyword/embedding matching will misfire on ambiguous phrases and show irrelevant quick tips. | Valid | Mitigate with a similarity threshold below which the fast lane shows nothing; measure precision in evals. |
| DEC-06 | 120b is untested against 20b on quality, and 20b is twice as fast. | Valid | Logged as assumption A-3 and parking-lot item; re-check using the recorded calls. |
| DEC-02 (D-50) | One KB search per turn may miss the right offer when the customer raises two reasons in one turn. | Valid | Search query built from the summary's reasons plus the new turn; measure retrieval hit rate in component evals. |
| DEC-07 | Up to 9 attempts can take longer than a turn, wasting quota on answers that will be dropped. | Rejected | Retries stop when a new turn arrives, bounding the waste. |
| DEC-08 | Without a budget in seconds, "on time" can't be judged within a turn. | Rejected | The next-turn rule is the budget; latency is logged for reporting. |
| DEC-09 | A slow summariser makes prompts grow back toward the full transcript. | Rejected | Only on long lags; log summariser lag so it is visible. |
| DEC-10 | Prompt Guard 2 is a preview model and adds a network call before every summary. | Valid | Heuristics remain if it is withdrawn; note its latency in logs. |
| DEC-11 | A component tied to this schema isn't really reusable. | Rejected | Fields are config-defined, with its own README and tests. |
| DEC-12 | A mistranscription that looks like a card number is masked and lost. | Rejected | Synthetic data; nothing downstream needs raw values. |
| DEC-13 | Pattern-based injection detection is easy to evade with rephrasing. | Rejected | Detection only flags; enforcement is the structured summary and Permission Layer. |
| DEC-14 | Fail-closed leaves the rep with no help during any Permission Layer bug. | Rejected | A wrong offer is worse than no offer; the degraded state tells the rep. |
| DEC-15 | Asking tenure adds friction; customers may misstate it. | Rejected | Acceptable for the hackathon; account lookup parked. |
| DEC-16 | Two lanes plus three slots may confuse the rep when suggestions contradict. | Valid | Plain-language labels help; contradictions are an evals metric (flip-flops). |
| DEC-17 | Resume needs browser reconnect, STT restart and checkpoint load — three moving parts for a rare event. | Valid | Requires a kill-mid-call test; if it proves fragile, fall back to ending assist for the call. |
| DEC-18 | In-memory search won't scale. | Rejected | Scale is out of scope; a vector DB is a drop-in later. |
| DEC-19 | Logging model reasoning and tool results makes logs large. | Rejected | One call at a time; size is bounded. |
| DEC-20 | 5 calls × 3 runs is a thin sample; judges may call the eval weak. | Valid | State the sample size openly as a limitation; each call covers several situations. |
| DEC-21 | Running ablation on Ollama instead of the demo model weakens the claim. | Rejected | The ablation needs the same model across versions, not the demo model; disclose it. |
| DEC-22 | One attack type is narrow. | Valid | Acceptable for scope; note other vectors in the threat model. |
| DEC-01 (D-51) | Role buttons rely on the presenter switching correctly; a missed click mislabels a whole turn. | Valid | Demo-only by design; active role is shown prominently, and the recorded test calls carry correct role tags. |
| DEC-23 | A live demo depends on the room's mic and network. | Valid | Recorded test calls are the fallback. |

---

## 4. Key risks
| Risk | Mitigation |
|---|---|
| Free-tier rate limits with three agents per turn and 75 ablation runs | Per-model limits; summariser on 20b; Ollama fallback for ablation |
| Summary poisoning via customer speech | DEC-10 guardrails; DEC-22 attack test |
| STT dominates latency (~2.3–2.4 s measured with batch Whisper) | Streaming STT; fast lane bridges the gap |
| Crash resume depends on browser reconnect, STT restart and an intact checkpoint | Kill-mid-call test; fallback to ending assist |
| Cancelling a running graph leaves inconsistent state | Cancellation test (DEC-02, §3) |
| Ollama fallback gives lower-quality suggestions than Groq | Provider recorded in every log record |
| Prompt Guard 2 (preview) withdrawn or produces false positives | Heuristics fallback; detection only flags |
| Framework hides harness elements | DEC-02 hand-built nodes |
| Live demo depends on room mic and network | Recorded calls as backup |
| Fast lane shows irrelevant tips on ambiguous phrases | Similarity threshold; evals measure it |

## 5. Key assumptions
- A-1: Groq's free tier allows three agent calls per turn for a demo call and, spread over days, the eval and ablation runs.
- A-2: The synthetic KB stays at a few dozen documents.
- A-3: `gpt-oss-120b` gives better suggestion quality than 20b (not yet measured).
- A-4: Local Whisper streaming runs fast enough on the demo machine's CPU.
- A-5: Five synthetic calls are representative enough to reveal component differences in the ablation.
- A-6: Customers state tenure when the rep asks.
- A-7: LangGraph supports cancelling an in-flight run and resuming a thread from its SQLite checkpoint.

## 6. Open questions
OQ-1 (fast/slow agreement check) closed: dropped (D-49). OQ-2 (KB tool-call cap) closed:
one KB search per turn (D-50).

- **OQ-3 closed (D-51):** Speaker identity comes from two buttons on Live Call Assist — "Sales Rep"
  and "Customer". One browser microphone; whichever button is active tags the audio with that role.
  Demo-only mechanism; diarization or separate audio channels are parked (§7).

## 7. Future enhancements (parking lot)
- Post-call analysis, coaching reports and QA scoring (D-01) — out of hackathon scope.
- Multiple simultaneous calls (D-02).
- Manager and QA roles, including live viewing (D-03).
- Gemini Live API spike: N≥10 runs plus the session-resumption path (D-10).
- Re-check `gpt-oss-20b` vs `120b` for the agents (D-08).
- Account and eligibility lookup tool (D-15).
- Latency budgets and tuning (D-12).
- Automatic speaker identification (diarization or separate audio channels) to replace the demo role buttons (D-51).
- Automatic correction of bad suggestions (D-29).

## 8. Data model
| Entity | Represents | Key fields |
|---|---|---|
| **Call** | One live call; LangGraph thread | call_id, started_at, ended_at, status (live / ended / crashed-resumed) |
| **Turn** | One stretch of speech by one speaker | call_id, turn_no, speaker (rep / customer), text (PII-masked, D-47), stt_timestamps |
| **Summary** | Structured state of the conversation so far (D-41) | last_summarised_turn, primary_reason, all_reasons[{reason, first_turn}], call_stage, customer_tenure{months, turn_stated}, mood, mood_trend, offers_discussed[{offer_id, turn, response}], customer_requests[{reported_speech ≤25 words, turn, in_kb}], objections[≤15 words] |
| **Suggestion** | One item shown or considered for the rep | suggestion_id, call_id, turn_no, lane (fast / slow), source (fast lane / offer agent / behaviour agent), type (calm / rapport / close / info / offer), text, offer_id?, permission_outcome, display_state (shown / faded / dropped) |
| **Offer document** | One KB entry (D-44) | offer_id, title, eligibility rules (e.g. min tenure), reasons it addresses, body text, embedding (in memory) |
| **Permission decision** | Audit record for every Permission Layer check | call_id, turn_no, suggestion_id, check, outcome (Allow / Mask / Deny), reason, removed_text? |
| **Log record** | One step of execution (D-28) | call_id, turn_no, step, input, tool_calls[{name, args, result}], model_reasoning, retries[{provider, cause}], provider, tokens, cost, permission_outcome, shown, timestamps |
| **Checkpoint** | LangGraph saved state per call thread (D-37) | thread_id = call_id, graph state (summary pointer, recent turns, displayed suggestions), saved_at |

## 9. Open questions — Phase 3 dependencies
None. Phase 3 may proceed once this document is signed off.
