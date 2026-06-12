# C15 tool-call failure root cause: corrupted generation, not parser or template (2026-06-12)

The C15 toolcall (0.167 = no-tool cases only) and agentic (0/5) scores were initially
attributed to tool-call parser/template plumbing. Manual diagnosis shows the real cause:
**the server generates gibberish for every prompt**, so no suite that reads model output
could ever pass. Throughput numbers (130.6 single / 360.3 x4 aggregate) measure token
mechanics only and remain valid as a continuous-batching demonstration, but C15 is NOT a
usable serving config.

Evidence (manual probes against the exact C15 container config):

- `temperature 0`, prompt "Say hello and name three colors." →
  `'\\� finanz videog\n\nControlItemyer Waks� finanzت instﬁ凤ったs ...'`
- tools probe (read_file/list_dir) → finish_reason `length`, no tool_calls, content
  is multi-script token salad (`ったったsったsったs7...تFG...`).

Ruled out:

1. **Tool parser** (`qwen3_coder` vs `qwen3_xml`): both fail identically; the model
   never produces parseable output of any kind.
2. **Chat template**: the AWQ repo's standalone `chat_template.jinja` fully supports
   tools (qwen3_coder XML style). Passing it explicitly via `--chat-template` changed
   nothing.
3. **mrope config loss**: startup warned `Unrecognized keys in rope_parameters for
   rope_type='default': {mrope_section, mrope_interleaved}` (the official Qwen repo
   declares the identical block, so the quantizer is not at fault). Re-injecting the
   full rope block via `--hf-overrides '{"text_config": {"rope_parameters": {...}}}'`
   made the warning disappear but output is still gibberish.

Remaining suspects (untested, GPU time yielded to C16):

- vLLM 0.22.1's `awq_marlin` MoE path for `Qwen3_5MoeForConditionalGeneration`
  (this VL-architecture MoE may be broken under quantized expert layouts).
- `--language-model-only` extraction path for this arch.
- The community AWQ quant itself (`mattbucci/Qwen3.6-35B-A3B-AWQ` rev 7525d0f) —
  unknown quantizer; weights could be mis-packed. No other <20 GiB AWQ/GPTQ exists
  to cross-check on a 24 GB card.

Next steps if revisited: try a vLLM nightly image; or serve a model with first-class
vLLM support for the parallel-pool arm (e.g. Cohere north-mini-code 30B-A3B, which has
official vLLM tool-calling docs); or wait for an official Qwen-blessed 4-bit quant.
