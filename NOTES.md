# Local model research

## 2026-07-15 — strongest uncensored multimodal model for RTX 3090 Ti

Recommendation: `llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF`. For a 128k multimodal window, use the `Q3_K_L` language-model GGUF plus its BF16 `mmproj`; reserve `Q4_K_M` for shorter-context maximum-quality use. Qwen3.6 is a native image/video/text MoE (35B total, 3B active, 262k native context). The community variant uses Heretic v1.3.0 + MPOA and preserves native MTP weights.

Evidence and constraints:

- Official Qwen model card: Qwen3.6-35B-A3B is a causal LM with vision encoder. Reported vision results include MMMU 81.7, MMMU-Pro 75.3, RealWorldQA 85.3, OmniDocBench 89.9, and VideoMMMU 83.7. Source: https://huggingface.co/Qwen/Qwen3.6-35B-A3B
- Uncensored source card reports refusals reduced from 83/100 to 10/100, KL divergence 0.0015, and MMLU 83.39% vs 83.71% original. It is strongly decensored, not literally refusal-free. Source: https://huggingface.co/llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved
- Standard GGUF sizes: Q3_K_M 17,267,455,136 bytes (~16.08 GiB), Q3_K_L 18,652,886,176 bytes (~17.37 GiB), Q4_K_M 21,780,313,248 bytes (~20.28 GiB), and BF16 mmproj 902,822,112 bytes (~0.84 GiB). Q3_K_L plus vision leaves ~5.8 GiB of a 24 GiB GPU before runtime/KV allocation; Q4_K_M leaves only ~2.9 GiB. Source: https://huggingface.co/llmfan46/Qwen3.6-35B-A3B-uncensored-heretic-Native-MTP-Preserved-GGUF
- A published RTX 3090 setup runs the same uncensored Qwen3.6-35B-A3B with Q3_K_M, BF16 mmproj, `-c 131072`, Flash Attention, and 83.7% GPU utilization for the main process. Source: https://gnu.support/large-language-models-llm/Private-Local-AI-Setup-with-Qwen3-6-35B-and-RTX-3090-124779.html
- Community reports corroborate the long-context behavior: Qwen3.6-27B IQ4_NL plus 4-bit TurboQuant fits 256k on a 3090, while Qwen3.5-27B Q4_K_M reportedly ran 262,144 with q4 K/V cache. Another Qwen3.6-27B Q4_K_M report reached ~91k with the default cache. Source: https://news.ycombinator.com/item?id=47863217
- Upstream llama.cpp supports q8/q4 KV cache, but TurboQuant remains an open feature request as of 2026-07-15; do not rely on a TurboQuant-only recipe with the repository's pinned llama.cpp build. The feature thread reports, for Qwen3.5-35B-A3B, roughly 2× cache compression from f16 to q8 and 3.6× from f16 to q4. Source: https://github.com/ggml-org/llama.cpp/issues/20977
- Local benchmark of the same base architecture at IQ4_XS and 32k context loaded in 19,583 MiB under CUDA, delivered 143.4 tok/s p1k with MTP, 100% strict tool-call score, and 5/5 agentic on the Vulkan run. This proves the architecture/backend works on this RTX 3090 Ti; the uncensored long-context build itself has not yet been locally smoke-tested. See `RESULTS.md` C12/C14.
- Decision: 128k is demonstrated on an RTX 3090 with Q3_K_M. Q3_K_L at 128k with q8 KV is the conservative highest-quality standard quant likely to fit. A 262k trial is plausible with Q3_K_M and q4 KV, but is not yet demonstrated for this exact MTP-preserved artifact and should not replace the 128k default until a local NIAH/long-context quality check passes.

Suggested 128k llama.cpp flags: `-ngl 99 --jinja -fa on -c 131072 --cache-type-k q8_0 --cache-type-v q8_0 --spec-type draft-mtp --spec-draft-n-max 2 --no-spec-draft-backend-sampling --mmproj <mmproj.gguf>`.

## 2026-07-24 — VM memory and host crash root causes

- The guest's `503 loading model` cycle came from its Linux OOM killer. llama.cpp had about 14.48 GiB anonymous RSS in a 16 GiB VM, and a nearly full 131k conversation triggered a 1.57 GiB automatic prompt-cache save. Keep the VM at 32 GiB and use llama.cpp `--cache-ram 0`.
- The host crashes were separate and were not host OOMs. At `2026-07-24 07:41:39`, `virsh start` asked libvirt to detach the managed RTX 3090 Ti while the proprietary NVIDIA DRM stack was loaded. One second later, kernel `7.0.11-76070011-generic` logged a NULL pointer dereference in `nv_audio_dynamic_power [nvidia]`. The call trace runs through `nvidia_modeset`, `nv_drm_dev_unload`, `nvidia_modeset_remove`, and `nv_pci_remove`; the crashing task was `rpc-libvirtd`.
- Stopping CUDA consumers and moving NVIDIA DRM off `seat0` did not make live driver removal safe. The unsafe design was libvirt `managed='yes'` plus start/stop scripts that dynamically detached and reloaded NVIDIA. Repeated VM launch attempts repeatedly exercised that kernel-driver removal path.
- Correct architecture: bind both NVIDIA PCI functions to `vfio-pci` during boot, keep libvirt host devices `managed='no'`, and refuse VM startup unless both functions already use `vfio-pci`. Returning the card to host NVIDIA use also requires a boot-mode change and reboot; never hot-rebind this card.
