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

## 2026-07-15 — workstation GPU/display architecture

- RX 580: PCI `0000:08:00.0`, ID `1002:67df`, kernel driver `amdgpu`, DRM `card0`. The 4K monitor is connected to its HDMI output. Xorg screen `AMDGPU(0)` uses this GPU, and `xrandr --listproviders` exposes only the RX 580.
- RTX 3090 Ti: PCI `0000:42:00.0`, ID `10de:2203`; audio function `0000:42:00.1`, ID `10de:1aef`; DRM `card1`. Firmware nevertheless marks the NVIDIA function `boot_vga=1` and AMD `boot_vga=0`.
- `/etc/X11/xorg.conf.d/20-amdgpu-only.conf` explicitly pins the Xorg screen to AMD `PCI:8:0:0` and disables `AutoAddGPU`, so rendering/display selection is correct.
- Ubuntu `gpu-manager` generates `/usr/share/X11/xorg.conf.d/11-nvidia-prime.conf`, whose NVIDIA OutputClass sets `PrimaryGPU=Yes`. At boot, systemd-logind gives Xorg an fd for both `card0` and NVIDIA `card1`; Xorg therefore keeps the NVIDIA DRM module busy even though it does not use the 3090 Ti as a screen/provider. Evidence: current `~/.local/share/xorg/Xorg.1.log` lines 58–68 and `fuser /dev/dri/card1`.
- Dynamic libvirt detachment deadlocks if NVIDIA user processes or Xorg's `card1` fd remain. Checking only `nvidia-smi --query-compute-apps` is insufficient because it omits DRM/graphics clients.
- Best-fit architecture is to keep AMD as seat0/display and assign NVIDIA DRM to a separate unused logind seat (for example with a persistent `loginctl attach`/udev seat rule). This preserves host CUDA availability while preventing Xorg from opening `card1`. Validate live seat reassignment before considering boot-time VFIO binding.
