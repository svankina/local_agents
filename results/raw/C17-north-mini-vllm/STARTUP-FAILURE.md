# C17 startup failure: compressed-tensors MoE quant rejected

C17 did not reach the mandatory coherence gate. vLLM failed during model
initialization before `/health` became available, so no throughput, toolcall, or
agentic suites were run.

Config attempted:

- model: `cyankiwi/North-Mini-Code-1.0-AWQ-INT4`
- revision: `69f25e86d2b35d04837388514bec4eff729d1b30`
- quantization flag: `--quantization compressed-tensors`
- tool parser: `cohere_command4`
- reasoning parser: `cohere_command4`
- `--max-model-len 16384`
- `--max-num-seqs 8`
- `--gpu-memory-utilization 0.90`

The raw server log contains the root failure:

```text
AssertionError: Only symmetric quantization is supported for MoE
```

This happened in vLLM 0.22.1 while constructing the compressed-tensors
WNA16 Marlin MoE method. The selected public INT4 AWQ repo is a
compressed-tensors pack-quantized model, but this vLLM MoE path requires
symmetric quantization. The duplicate `FenomAI/North-Mini-Code-1.0-AWQ-INT4`
repo has identical shard sizes and metadata, so it is not a useful fallback.

Because the server never became healthy, the coherence probes were not sent.
