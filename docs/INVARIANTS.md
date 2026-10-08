# INVARIANTS.md — Retention Copilot
## Version: v1.0-draft · 2026-10-08 · Authorship mode: ASSISTED
## Engineer sign-off: [ ] — date: ______

> Structural and data invariants are CD-drafted for your confirmation. Domain invariants are your
> own rules, taken from decisions you stated (D-IDs shown) and worded by CD — sign-off means you
> stand behind the wording. Every invariant below passed the five challenge tests plus the
> complexity accumulation test; candidates that failed harm-and-detectability are in the
> Reclassified table and move into task prompts instead.
> Based on ARCHITECTURE.md v1.0-draft (including D-51 speaker role buttons) and UI_SURFACE.md v1.0-draft.

## Step 0 — Data touch point inventory
| Touch point | Where in the system | UI_SURFACE coverage |
|---|---|---|
| Capture | One browser mic on `/`; "Sales Rep" / "Customer" buttons tag audio with the speaker role over the WebSocket (D-51); replay streams recorded utterances with role tags the same way | Live Call Assist (Start call, role buttons) |
| Transformation — STT + masking | Streaming Whisper → turn segmentation by role → PII masker → Turn | Live Call Assist transcript panel |
| Storage — write | LangGraph checkpoint (SQLite), summary (SQLite), JSON-lines logs | Call Ended Card ("log saved") |
| Storage — read | Checkpoint on resume; latest summary per turn; logs in the viewer | Live Call Assist (reconnected), Call Log Viewer |
| Retrieval | Fast-lane keyword/embedding match; offer agent KB search (in-memory) | Suggestions panel; "Failed fetching docs" state |
| Transformation — models | Summariser (gpt-oss-20b), offer and behaviour agents (gpt-oss-120b), retry loop across providers | Suggestions panel; degraded states |
| Transmission — outbound | Prompts to Groq / Ollama / Gemini; Prompt Guard 2 calls | None (internal) — covered by INV-01, INV-03 |
| Rendering | Permission Layer → emit → WebSocket → suggestion panel, banner, mood, transcript | Live Call Assist, Call Ended Card, Call Log Viewer |
| Authentication | None (G-1 default: no login, local demo). API keys from environment only | N/A — covered by INV-03 |

### UI_SURFACE.md consistency check
- Touch points with no screen coverage: Transmission — outbound (internal only; covered by invariants). No gap.
- Screens with no touch point: none.

---

## GLOBAL invariants (go into Claude.md Section 2)

### INV-01: No unmasked PII exists anywhere downstream of transcription.
- Category: Domain (D-47, D-20, D-43)
- Scope: GLOBAL
- Authorship: Engineer-stated (D-47), CD-worded
- Why this matters: A card number spoken on a call would be sent to Groq, written to the checkpoint
  database and the logs, and shown in the log viewer, contradicting the threat model's central claim.
- Enforcement points: the single masking function applied to every STT output before a Turn is
  created; no other code path may create a Turn; ablation configs cannot disable masking (L1 always on).
- Failure Mode:
  - Violation: a card number, phone number or email in plain form in graph state, a prompt, the summary, the checkpoint DB, or a log line.
  - Detection: verification test that speaks or injects known PII patterns and greps checkpoint, logs and recorded prompts; otherwise invisible in normal use.
  - Blast radius: security exposure; threat-model claim false.

### INV-02: Every model call, tool call, Permission Layer decision and displayed item produces a log record carrying the call_id and turn number.
- Category: Structural (DEC-19)
- Scope: GLOBAL
- Authorship: CD-drafted (confirm)
- Why this matters: Challenge 2 requires a stranger to explain any suggestion from the logs; a missing
  record makes a bad suggestion unexplainable and invalidates eval and ablation evidence.
- Enforcement points: the logging wrapper around every node, the provider router, the KB tool, the Permission Layer and the emit step.
- Failure Mode:
  - Violation: a suggestion appears on screen with no matching log record, or a record lacks call_id / turn_no.
  - Detection: verification test that replays a call and checks one-to-one coverage of displayed suggestions to log records; otherwise only noticed during an investigation.
  - Blast radius: silent wrong answer in debugging; evidence for challenges 2–3 unusable.

### INV-03: API keys and credentials never appear in logs, checkpoints, prompts, the browser, or the repository.
- Category: Data
- Scope: GLOBAL
- Authorship: CD-drafted (confirm)
- Why this matters: Logs are shown on screen in the demo and the repo is submitted; a leaked key is public.
- Enforcement points: keys read only from environment variables; logger redacts key-like strings; `.env` git-ignored; nothing key-related sent over the WebSocket.
- Failure Mode:
  - Violation: a key string present in any log file, checkpoint, committed file or WebSocket message.
  - Detection: verification test grepping outputs and the repo for configured key values; otherwise invisible.
  - Blast radius: security exposure; account abuse.

---

## TASK-SCOPED invariants (embedded in the relevant task prompts in EXECUTION_PLAN.md)

### INV-04: No offer reaches the rep's screen unless its offer_id exists in the KB and the Permission Layer recorded Allow for it.
- Category: Domain (D-20, D-34)
- Scope: TASK-SCOPED (Permission Layer, emit, offer agent)
- Authorship: Engineer-stated, CD-worded
- Why this matters: A rep reading an invented offer to a customer makes a commitment the business never approved; this is the attack's success condition.
- Enforcement points: Permission Layer KB-grounding check; emit refuses any suggestion without a Permission decision record.
- Failure Mode:
  - Violation: a displayed offer whose offer_id is missing from the KB, or with no Allow record.
  - Detection: attack test (DEC-22) and log audit; on screen it looks like a normal suggestion.
  - Blast radius: financial loss; unauthorised commitment to a customer.

### INV-05: Behaviour-agent output never reaches the screen containing an offer, price or promise; such content is removed (Mask) and the removal is logged.
- Category: Domain (D-19)
- Scope: TASK-SCOPED (Permission Layer, behaviour agent)
- Authorship: Engineer-stated, CD-worded
- Why this matters: The behaviour agent has no KB access; any offer it states is invented by definition.
- Enforcement points: Permission Layer behaviour check.
- Failure Mode:
  - Violation: a "Suggested approach" from the behaviour agent containing a price, discount, waiver or promise.
  - Detection: Permission Layer unit tests with planted offers; on screen it reads as legitimate advice.
  - Blast radius: unauthorised commitment.

### INV-06: The Permission Layer fails closed — any error inside it results in nothing new displayed and the degraded state, never in an unchecked suggestion.
- Category: Structural (D-18)
- Scope: TASK-SCOPED (Permission Layer)
- Authorship: CD-drafted (confirm)
- Why this matters: A bug would otherwise become a bypass of every check above.
- Enforcement points: exception handling around the whole Permission Layer node.
- Failure Mode:
  - Violation: a suggestion displayed after the Permission Layer raised an error.
  - Detection: fault-injection test; otherwise invisible because the suggestion looks normal.
  - Blast radius: security exposure; INV-04/05 silently bypassed.

### INV-07: A summary is written to the store only after it passes schema and content validation (L4); on failure the previous summary is kept and the rejection logged.
- Category: Structural (D-42)
- Scope: TASK-SCOPED (summariser)
- Authorship: CD-drafted (confirm)
- Why this matters: The summary feeds every later turn; one poisoned summary persists an injection for the rest of the call.
- Enforcement points: summariser store-write function; nothing else writes the summary table.
- Failure Mode:
  - Violation: a stored summary with an instruction-like phrase, a non-KB offer_id, a value outside an enum, or an over-length field.
  - Detection: summariser guardrail tests and the attack test; agents would silently act on it.
  - Blast radius: silent wrong answer; attack succeeds across turns.

### INV-08: A slow-lane result is never displayed once the next customer turn has started; in-flight work for the old turn is cancelled.
- Category: Structural (D-13, D-11, DEC-02)
- Scope: TASK-SCOPED (graph runner, retry loop, emit)
- Authorship: CD-drafted (confirm)
- Why this matters: A late suggestion looks current, so the rep acts on advice about a moment that has passed.
- Enforcement points: turn-sequence check in emit; cancellation of the in-flight run and retries on new turn.
- Failure Mode:
  - Violation: a suggestion whose turn_no is lower than the latest customer turn appears after that turn began.
  - Detection: timing test in replay; rep cannot tell it is stale.
  - Blast radius: incorrect business decision on the call.

### INV-09: Cancelling an in-flight turn or resuming after a crash leaves the call's checkpoint consistent — the next turn runs from the last fully completed turn's state.
- Category: Data (D-37, D-46)
- Scope: TASK-SCOPED (graph build, checkpointing, resume)
- Authorship: CD-drafted (confirm)
- Why this matters: Half-written state would corrupt context for every later turn of the call.
- Enforcement points: checkpoint writes only at turn completion; cancellation and resume tests.
- Failure Mode:
  - Violation: after cancel or resume, state contains a partial turn, duplicated suggestions, or a summary pointer ahead of stored turns.
  - Detection: kill-mid-call and cancel-mid-turn tests; otherwise shows as subtly wrong suggestions.
  - Blast radius: silent wrong answer for the rest of the call.

### INV-10: Replayed calls enter through the same WebSocket path, with the same role-switch messages, as live audio.
- Category: Structural (D-40, D-51)
- Scope: TASK-SCOPED (replay runner, eval tasks)
- Authorship: CD-drafted (confirm)
- Why this matters: If replay bypasses STT or the WebSocket, every eval and ablation number measures a different system from the demo.
- Enforcement points: the replay script and the in-UI replay (web/replay.js) are both WebSocket clients using the same timing.json format; no in-process shortcut into the graph.
- Failure Mode:
  - Violation: replay code importing graph or STT modules directly.
  - Detection: test asserting replay runs against a live server only; otherwise results look normal.
  - Blast radius: invalid evaluation and ablation evidence.

---

## Reclassified as implementation guidance
| Candidate | Reason reclassified | Target task(s) |
|---|---|---|
| At most one KB search per turn (D-50) | Violation visible in logs; low harm | T5.2 |
| At most 3 suggestions visible; older fade (D-17) | Immediately visible on screen | T6.1 |
| Lane labels "Quick tip" / "Suggested approach" | Immediately visible | T6.1 |
| Retry order Groq → Ollama → Gemini, max 3 rounds (D-11) | Visible in logs (provider field); low harm | T5.1 |
| Summary fields per D-41 | Enforced by schema; covered by INV-07 for harm | T4.1 |
| Customer requests stored as reported speech | Covered by INV-07 validation | T4.2 |
| Duplicate suggestion suppression | Visible on screen | T5.3 |
| Turn closes on role switch (D-51) | Visible in transcript panel and logs | T2.2 |
| 5-second heartbeat banner (D-25) | Visible in demo; UI test covers it | T2.1, T6.1 |
| Ablation knockout disables L2–L4 only | Covered by INV-01 for PII; config visible | T7.3 |
