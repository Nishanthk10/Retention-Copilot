# Guarded conversation summariser

A reusable asynchronous summariser for **already-masked, untrusted** conversation turns. No import from the host app is required.

Install independently: `pip install ./summariser`. Dependencies: pydantic, jsonschema, PyYAML. From the host repo, run `python -m pytest summariser/tests -q`.

## Reuse

- Edit config.yaml to change the JSON Schema, enums, bounds and initial state. Pydantic Summary validates using this config, including x-max-words.
- Supply an async `complete(messages, schema) -> dict` to summarise(). Your provider should request structured JSON and must not log raw credentials.
- Supply a `log(step, **fields)` callback, a dictionary of approved KB records, a prior summary, and turns with integer turn_no.
- Optionally inject an async classifier(text) returning flags. Heuristics still run if it is unavailable.
- A successful call returns ValidationResult; a failure returns None and logs a rejection. Keep the prior summary on None.
- SummaryStore.write revalidates before persistence. BackgroundSummariser coalesces work per call, runs off the foreground path and supports cancellation.

Layers: L1 is the host's mandatory upstream PII boundary. L2 flags injection attempts without discarding speech. L3 delimits input and requests reported speech/schema output. L4 validates fields, word lengths, KB identifiers, prices and instruction wording. L5 retains the old summary on failure.

The customer_requests field must begin with Customer requested / Customer asked / Customer wanted. Improper demands should be summarized generically, for example, “Customer requested an unapproved discount,” with in_kb false. Storing the literal injected instruction is rejected.

The guardrail switch exists for controlled ablations; guardrails=False intentionally bypasses L2–L4 and must never disable upstream masking. It is not a production feature. Schema changes that remove the standard semantic fields also require adjusting the content-validator policy: configuration controls structure, while the retention-specific semantic checks explicitly reference offers_discussed and customer_requests.
