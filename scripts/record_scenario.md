# Record the five evaluation calls

The engineer records each scripted utterance once. Do not use real customer details. Scripts and labels are in evals/scenarios/S1.yaml through S5.yaml.

1. Use a recorder capable of exporting WAV (for example, an audio editor), select the microphone, and set the project rate to **16000 Hz, mono**.
2. Speak one numbered utterance at a time, exactly as scripted. Export each as **signed 16-bit PCM WAV**. Do not export MP3 or a WAV container holding compressed audio.
3. Create evals/recordings/S1/ and name the utterances 01_rep.wav, 02_customer.wav, 03_rep.wav, and so on. Preserve the roles and order in the script.
4. Create timing.json in the same folder. Measure the intended pause before each utterance; the pause provides normal thinking/speaking time for the system.

Example format (include every utterance, not just these two):

```json
{
  "utterances": [
    {"file": "01_rep.wav", "role": "rep", "gap_before_s": 0},
    {"file": "02_customer.wav", "role": "customer", "gap_before_s": 1.0}
  ]
}
```

5. Repeat for S2–S5. Validate from the project root with `python -m evals.check_recordings`.
6. Start the normal application and replay each once to confirm transcription quality and turn segmentation. Do not change recordings between ablation variants.

Both browser replay and the Python runner send role messages and PCM audio through /ws/audio. A role switch finalizes the previous utterance. Do not inject text directly into a model to produce the submitted audio evaluation numbers.
