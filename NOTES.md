# Local model research

## 2026-07-15 — strongest uncensored multimodal model for RTX 3090 Ti

Recommendation: `llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF`, using the `Q4_K_M` language-model GGUF plus its BF16 `mmproj` in llama.cpp. Qwen3.6 is a native image/video/text MoE (35B total, 3B active, 262k native context). The community variant uses Heretic v1.3.0 + MPOA and preserves native MTP weights.

Evidence and constraints:

- Official Qwen model card: Qwen3.6-35B-A3B is a causal LM with vision encoder. Reported vision results include MMMU 81.7, MMMU-Pro 75.3, RealWorldQA 85.3, OmniDocBench 89.9, and VideoMMMU 83.7. Source: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- Uncensored source card reports refusals reduced from 83/100 to 10/100, KL divergence 0.0015, and MMLU 83.39% vs 83.71% original. It is strongly decensored, not literally refusal-free. Source: https://huggingface.co/llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved
- Standard GGUF repository provides Q4_K_M at 21,780,313,248 bytes (~20.28 GiB) and BF16 mmproj at 902,822,112 bytes (~0.84 GiB), leaving roughly 2.9 GiB of a 24 GiB GPU before runtime/KV allocation. Source: https://huggingface.co/llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF
- Local benchmark of the same base architecture at IQ4_XS and 32k context loaded in 19,583 MiB under CUDA, delivered 143.4 tok/s p1k with MTP, 100% strict tool-call score, and 5/5 agentic on the Vulkan run. This proves the architecture/backend works on this RTX 3090 Ti; the uncensored Q4_K_M + mmproj itself has not yet been locally smoke-tested. See `RESULTS.md` C12/C14.
- Start at 16k context with q8 KV cache. The APEX I-Quality pack plus mmproj consumes ~22.74 GiB in files alone and leaves too little predictable runtime margin for a clean full-GPU recommendation. APEX quality claims are also third-party and benchmarked on Qwen3.5, not this exact 3.6 build.

Suggested llama.cpp flags: `-ngl 99 --jinja -fa on -c 16384 --cache-type-k q8_0 --cache-type-v q8_0 --spec-type draft-mtp --spec-draft-n-max 2 --no-spec-draft-backend-sampling --mmproj <mmproj.gguf>`.
