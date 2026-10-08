# Implementation notes and deviations

Original planning documents have not been rewritten or marked signed off. The user's instruction to execute supplied the authorization to build.

## Checkpoint semantics

LangGraph's exit durability can persist on error as well as success; it alone is not a completion-only guarantee. The working graph therefore runs without a saver. Only after it completes is its state copied through aupdate_state to a LangGraph graph backed by AsyncSqliteSaver. The returned checkpoint config is atomically committed in calls.db. Recovery uses that explicit checkpoint ID, not whichever snapshot is newest. If cancellation interrupts copying, an orphan snapshot is harmless. This was exercised by deterministic integration tests. No claim is made that the recorded audio SIGKILL experiment has run.

A restored transcript contains only turns from the last completed customer graph. Subsequent in-flight speech may be lost. Previously used turn numbers are not reused: the masked audit trace determines the next sequence number. Summaries newer than the restored frontier are not fed into that recovery snapshot. New accepted turns remain in memory until a later graph commits them.

Framework reference consulted: https://reference.langchain.com/python/langgraph/checkpoints and https://reference.langchain.com/python/langgraph/types/Durability .

## Offer and behaviour controls

A valid offer_id alone does not prove generated offer text is grounded. Approved offers are rendered using the canonical display_text from the KB, and minimum tenure is checked from explicit customer wording rather than trusting model-generated summary facts. Unknown tenure denies the tenure-dependent offer; the offer agent can ask a question instead. Additional conditions remain explicit in canonical text, e.g. a verified outage is required for a credit review.

Behavioural content uses conservative phrase and commercial-term detection, removes unsafe clauses, and logs Mask/Deny. This is a bounded heuristic, not a general semantic proof against all paraphrases. Use synthetic calls and extend tests before deployment. The system is layered defence, not quarantine: recent raw-but-masked speech still reaches the agents.

## Audio

Browser AudioWorklet converts native sample rate to 16 kHz PCM16. Role messages pass through the worklet, flushing accumulated samples before a switch so buffered old-role audio is not tagged as the new speaker. Server windows are bounded to four seconds, transcribed with Whisper's VAD, and combined until the role changes. VAD filters recognition windows; it is not a separate adaptive end-of-utterance streaming decoder. Final transcripts appear at role boundaries. Live performance and the target-machine latency need measurement.

Replay uses the same wire protocol and schema. Python replay waits for role acknowledgements; browser replay preserves WebSocket ordering. Neither replay imports graph or STT code. Recordings have intentionally not been fabricated. The --dry-transcript flag still requires real audio; no bundled spoken fixture was present in the supplied inputs.

## Provider/logging behavior

The router uses HTTP calls with explicit retries instead of SDK retries. Every attempt/result/failure is correlated. Raw error response bodies and request URLs are not logged. Provider costs remain null because no trustworthy per-call cost was supplied; token usage is recorded when returned. Structured model rationales are brief decision summaries, not hidden chain-of-thought.

Groq structured output reference: https://console.groq.com/docs/structured-outputs . Gemini reference: https://ai.google.dev/gemini-api/docs/structured-output . These informed the adapters; no authenticated live call was made during the build.

## Evaluation boundaries

Unsafe ablations are possible only in a separate EVAL_MODE process; they produce explicit permission_bypassed records. The full-mode “every offer must be allowed” invariant is deliberately removed only in that experiment. PII masking stays mandatory in every variant.

The recorded attack runner requires all three evidence elements: no unapproved offer, reported-speech demand, and a Mask/Deny record. A model that safely chooses nothing may produce no denial record; the runner reports incomplete evidence instead of manufacturing a denial. The no-permission knockout does not guarantee a breach on every run.

## Remaining limitations

- No real recorded calls or configured providers were supplied; no voice quality, live offer quality, ablation improvement or cost result is claimed.
- Regex masking covers tested email, digit and spoken-digit patterns, not arbitrary personal data or every STT rendering.
- Local-only authentication assumptions; logs are available to whoever can reach the local server.
- Large embeddings/STT dependencies and model downloads are required for normal mode.
- The UI has no post-call score, manager view, real account lookup or automatic diarization, consistent with the scope.
