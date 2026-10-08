# Global invariants

Read docs/INVARIANTS.md and AGENTS.md.

- INV-01: Mask card, phone and email patterns at the sole transcription boundary before Turn creation; downstream state, prompts, summaries, checkpoints and logs receive only masked text. PII masking cannot be disabled in ablations.
- INV-02: Log every model/tool call, permission decision and displayed item with call_id and turn_no. Never emit if the required audit record fails.
- INV-03: Credentials are environment-only and must never reach prompts, the browser, logs, checkpoints or source control. Redact configured keys and key-like strings.

Do not claim live-model or recorded-audio evidence from deterministic test doubles.
