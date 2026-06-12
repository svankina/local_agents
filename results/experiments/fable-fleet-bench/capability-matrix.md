# Capability matrix — first-attempt pass rate per item

Built from every episodes*.json in this directory. 1.00 = always solves first try.

| model / condition | n | overall | fmt-viol | balanced-brack | camel-to-snake | chunk-list | flatten-nested | gcd | int-to-roman | merge-interval | run-length-enc | two-sum-indice | word-frequency |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| C1-gemma12b-nothink | 30 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C13-qwopus27b-think | 30 | 0.97 | 0.03 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 |
| C18-think (plan=medium) | 30 | 0.93 | 0.07 | 1.00 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C18-think (temp=0.0) | 30 | 0.93 | 0.07 | 1.00 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C7-qwen27b-q3 | 30 | 0.93 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.33 |
| C18-think (temp=0.2) | 30 | 0.90 | 0.10 | 1.00 | 0.33 | 1.00 | 1.00 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C18-think (temp=0.6) | 30 | 0.90 | 0.10 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C18-think (temp=1.0) | 30 | 0.90 | 0.10 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C8-nex-mini | 30 | 0.90 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| thinking-on | 30 | 0.90 | 0.10 | 0.67 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 |
| C18-think | 60 | 0.88 | 0.10 | 0.83 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 |
| C18-think (plan=detailed) | 30 | 0.80 | 0.17 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.67 | 0.33 |
| C4-gemma26b-nothink | 30 | 0.80 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| C6-gemma26b-cmoe-mtp-nothink | 30 | 0.80 | 0.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| diffusiongemma | 30 | 0.80 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 0.00 | 1.00 |
| C1-gemma12b | 30 | 0.73 | 0.27 | 1.00 | 0.00 | 1.00 | 1.00 | 0.67 | 0.67 | 0.33 | 0.67 | 1.00 | 1.00 |
| C12-byteshape | 30 | 0.67 | 0.30 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 0.67 | 1.00 | 0.00 | 0.33 | 1.00 |
| C12-byteshape-nothink | 30 | 0.67 | 0.30 | 1.00 | 0.67 | 1.00 | 1.00 | 0.00 | 0.67 | 1.00 | 0.00 | 0.33 | 1.00 |
| C13-qwopus27b | 30 | 0.60 | 0.23 | 1.00 | 0.33 | 1.00 | 0.33 | 0.33 | 1.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| C7-qwen27b-q3-think | 30 | 0.43 | 0.53 | 0.00 | 0.67 | 0.33 | 0.33 | 0.00 | 1.00 | 0.33 | 0.00 | 1.00 | 0.67 |
| thinking-off | 30 | 0.43 | 0.00 | 1.00 | 1.00 | 0.00 | 1.00 | 1.00 | 0.33 | 0.00 | 0.00 | 0.00 | 0.00 |
| C18-nothink | 60 | 0.40 | 0.00 | 1.00 | 0.83 | 0.00 | 1.00 | 1.00 | 0.17 | 0.00 | 0.00 | 0.00 | 0.00 |
| C18-nothink (fixloop) | 120 | 0.38 | 0.00 | 1.00 | 0.50 | 0.00 | 0.92 | 1.00 | 0.42 | 0.00 | 0.00 | 0.00 | 0.00 |
| C18-think (plan=terse) | 30 | 0.30 | 0.67 | 0.00 | 0.00 | 1.00 | 0.67 | 1.00 | 0.33 | 0.00 | 0.00 | 0.00 | 0.00 |
| C8-nex-mini-think | 30 | 0.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 | 0.00 |

## Per-model notes (auto-derived)

- **C1-gemma12b-nothink** (100% first-pass, 0% format violations): always solves: balanced-brackets, camel-to-snake, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: none.
- **C13-qwopus27b-think** (97% first-pass, 3% format violations): always solves: balanced-brackets, camel-to-snake, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices. struggles: none.
- **C18-think (plan=medium)** (93% first-pass, 7% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C18-think (temp=0.0)** (93% first-pass, 7% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C7-qwen27b-q3** (93% first-pass, 0% format violations): always solves: balanced-brackets, camel-to-snake, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices. struggles: word-frequency.
- **C18-think (temp=0.2)** (90% first-pass, 10% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C18-think (temp=0.6)** (90% first-pass, 10% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C18-think (temp=1.0)** (90% first-pass, 10% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C8-nex-mini** (90% first-pass, 0% format violations): always solves: balanced-brackets, camel-to-snake, chunk-list, flatten-nested, gcd, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: int-to-roman.
- **thinking-on** (90% first-pass, 10% format violations): always solves: chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency. struggles: camel-to-snake.
- **C18-think** (88% first-pass, 10% format violations): always solves: chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices. struggles: camel-to-snake.
- **C18-think (plan=detailed)** (80% first-pass, 17% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode. struggles: camel-to-snake, word-frequency.
- **C4-gemma26b-nothink** (80% first-pass, 0% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, word-frequency. struggles: camel-to-snake, two-sum-indices.
- **C6-gemma26b-cmoe-mtp-nothink** (80% first-pass, 0% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, word-frequency. struggles: camel-to-snake, two-sum-indices.
- **diffusiongemma** (80% first-pass, 100% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, word-frequency. struggles: camel-to-snake, two-sum-indices.
- **C1-gemma12b** (73% first-pass, 27% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, two-sum-indices, word-frequency. struggles: camel-to-snake, merge-intervals.
- **C12-byteshape** (67% first-pass, 30% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, merge-intervals, word-frequency. struggles: gcd, run-length-encode, two-sum-indices.
- **C12-byteshape-nothink** (67% first-pass, 30% format violations): always solves: balanced-brackets, chunk-list, flatten-nested, merge-intervals, word-frequency. struggles: gcd, run-length-encode, two-sum-indices.
- **C13-qwopus27b** (60% first-pass, 23% format violations): always solves: balanced-brackets, chunk-list, int-to-roman, run-length-encode, two-sum-indices. struggles: camel-to-snake, flatten-nested, gcd, merge-intervals, word-frequency.
- **C7-qwen27b-q3-think** (43% first-pass, 53% format violations): always solves: int-to-roman, two-sum-indices. struggles: balanced-brackets, chunk-list, flatten-nested, gcd, merge-intervals, run-length-encode.
- **thinking-off** (43% first-pass, 0% format violations): always solves: balanced-brackets, camel-to-snake, flatten-nested, gcd. struggles: chunk-list, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency.
- **C18-nothink** (40% first-pass, 0% format violations): always solves: balanced-brackets, flatten-nested, gcd. struggles: chunk-list, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency.
- **C18-nothink (fixloop)** (38% first-pass, 0% format violations): always solves: balanced-brackets, gcd. struggles: chunk-list, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency.
- **C18-think (plan=terse)** (30% first-pass, 67% format violations): always solves: chunk-list, gcd. struggles: balanced-brackets, camel-to-snake, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency.
- **C8-nex-mini-think** (0% first-pass, 100% format violations): always solves: none. struggles: balanced-brackets, camel-to-snake, chunk-list, flatten-nested, gcd, int-to-roman, merge-intervals, run-length-encode, two-sum-indices, word-frequency.
