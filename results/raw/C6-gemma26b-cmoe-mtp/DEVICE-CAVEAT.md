# C6 device caveat (2026-06-12)

Vulkan device enumeration flipped between the two partial runs that make up the
merged `results/C6-gemma26b-cmoe-mtp.json`:

- **throughput + toolcall** (phase-1 run, ~01:13–01:42, `server.phase1.log`):
  Vulkan0 = AMD RX 580, Vulkan1 = RTX 3090 Ti → `-dev Vulkan1` correctly placed
  dense layers + MTP drafter on the **3090 Ti** (vram_loaded 3375 MiB).
- **agentic re-run** (~05:40, `server.log`): enumeration flipped (Vulkan0 = 3090 Ti,
  Vulkan1 = RX 580) → dense layers + drafter landed on the **RX 580**; NVIDIA
  vram_loaded read 58 MiB.

Impact: agentic 5/5 is a quality result and stands regardless of device. Decode
during agentic (~18–20 t/s) is consistent with the NVIDIA phase-1 numbers because
-cmoe decode is dominated by CPU expert streaming. Do not cite C6 agentic-phase
throughput as a 3090 Ti number.

Same flip caused the C7 first-attempt failure (27B dense pinned to the 8GB card,
0.83 t/s, run aborted and retried on the correct device). Runner should resolve
the device by name, not index, before Phase 3.
