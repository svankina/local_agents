# M1 "A Box I Can Orbit" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A shaded 4×3×5 prism with crisp black edges standing on a grid, orbitable at 60fps — built through the real kernel pipeline (profile → extrude → half-edge B-rep → validateSolid → tessellate → RenderData → three.js), not a hardcoded mesh.

**Architecture:** Layered `app → doc → kernel` per the approved spec (`docs/superpowers/specs/2026-06-11-cad-engine-design.md`); M1 builds the kernel's lines-only slice (num, vec, profile, brep, extrude, tess) plus the viewport shell, validating the kernel→three.js seam before any sketching exists. three.js may be imported only inside `src/app/viewport/` (CI-greped).

**Tech Stack:** TypeScript (strict + noUncheckedIndexedAccess), Vite vanilla-ts, vitest, three.js (display only).

**Note on `earClip`:** Task 7 exports `earClip` from `src/kernel/tess.ts` as a sanctioned exception to the contract's public-API list — it is an internal testing seam, marked as such, not for use by `doc/` or `app/`.

---

### Task 1: Project scaffold

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `vite.config.ts`
- Create: `index.html`
- Create: `src/main.ts`
- Create: `src/kernel/.gitkeep`, `src/doc/.gitkeep`, `src/app/viewport/.gitkeep`, `test/.gitkeep`
- Create: `scripts/check-three-imports.sh`
- Create: `.gitignore`

This is infrastructure — no TDD. Steps are: write files, install, verify the import-guard script actually catches violations, run the full `check` gate, commit.

- [ ] **Step 1: Write the project config files** (all paths relative to the repo root `/home/svankina/src/custom_cad`)

`package.json`:

```json
{
  "name": "custom-cad",
  "private": true,
  "version": "0.0.1",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run --passWithNoTests",
    "check": "tsc --noEmit && vitest run --passWithNoTests && bash scripts/check-three-imports.sh"
  },
  "dependencies": {
    "three": "^0.184.0",
    "@types/three": "^0.184.0"
  },
  "devDependencies": {
    "typescript": "^6.0.3",
    "vite": "^8.0.16",
    "vitest": "^4.1.8"
  }
}
```

`tsconfig.json` (strict + `noUncheckedIndexedAccess` as required by project conventions):

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "module": "ESNext",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "moduleResolution": "bundler",
    "verbatimModuleSyntax": true,
    "noEmit": true,
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true
  },
  "include": ["src", "test", "vite.config.ts"]
}
```

`vite.config.ts` (note: imported from `vitest/config`, not `vite`, so the `test` block typechecks):

```ts
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['test/**/*.test.ts'],
    environment: 'node',
  },
});
```

`index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>custom_cad</title>
    <style>
      html, body { margin: 0; height: 100%; }
      #app { width: 100%; height: 100%; }
    </style>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

`src/main.ts` (placeholder; the viewport task replaces this):

```ts
console.log('custom_cad scaffold ok');
```

`.gitignore`:

```
node_modules/
dist/
.worktrees/
```

Create the layer directories with `.gitkeep` placeholders (git does not track empty dirs):

```bash
mkdir -p src/kernel src/doc src/app/viewport test scripts
touch src/kernel/.gitkeep src/doc/.gitkeep src/app/viewport/.gitkeep test/.gitkeep
```

- [ ] **Step 2: Write the three.js import guard script**

`scripts/check-three-imports.sh`:

```bash
#!/usr/bin/env bash
# Enforce the architecture rule: three.js may be imported ONLY inside src/app/viewport/.
# Catches `from 'three'`, `from "three"`, and subpath imports like `from 'three/addons/...'`.
set -u

violations=$(grep -rn -E "from ['\"]three[/'\"]" src/ --include='*.ts' | grep -v "^src/app/viewport/" || true)

if [ -n "$violations" ]; then
  echo "ERROR: three.js imported outside src/app/viewport/:" >&2
  echo "$violations" >&2
  exit 1
fi
exit 0
```

Make it executable:

```bash
chmod +x scripts/check-three-imports.sh
```

- [ ] **Step 3: Install dependencies**

```bash
npm install
```

Expected: completes without errors; `node_modules/` and `package-lock.json` appear. Verify the resolved versions:

```bash
npm ls three typescript vite vitest
```

Expected output lists `three@0.184.x`, `typescript@6.0.x`, `vite@8.0.x`, `vitest@4.1.x` with no `UNMET DEPENDENCY` lines.

- [ ] **Step 4: Verify the guard script catches a violation (negative test), then passes clean**

The guard is the one piece of logic here, so prove it works before trusting it. Plant a violation:

```bash
echo "import * as THREE from 'three';" > src/kernel/_guardcheck.ts
bash scripts/check-three-imports.sh; echo "exit=$?"
```

Expected output:

```
ERROR: three.js imported outside src/app/viewport/:
src/kernel/_guardcheck.ts:1:import * as THREE from 'three';
exit=1
```

Also verify the double-quote form is caught:

```bash
echo 'import * as THREE from "three";' > src/kernel/_guardcheck.ts
bash scripts/check-three-imports.sh; echo "exit=$?"
```

Expected: same ERROR block (with the double-quoted line shown) and `exit=1`.

Now verify viewport files are exempt and the clean tree passes:

```bash
rm src/kernel/_guardcheck.ts
echo "import * as THREE from 'three'; console.log(THREE.REVISION);" > src/app/viewport/_guardcheck.ts
bash scripts/check-three-imports.sh; echo "exit=$?"
```

Expected output: no ERROR lines, just `exit=0`. Clean up the probe file:

```bash
rm src/app/viewport/_guardcheck.ts
```

- [ ] **Step 5: Run the full check gate**

```bash
npm run check
```

Expected:
1. `tsc --noEmit` produces no output (zero type errors).
2. `vitest run --passWithNoTests` prints a line like `No test files found, exiting with code 0` (the `--passWithNoTests` flag makes zero tests a pass — kernel tests arrive in the next task).
3. `bash scripts/check-three-imports.sh` produces no output.
4. Overall exit code 0 (the command returns to the prompt with no `npm error` lines).

Also sanity-check the dev server starts:

```bash
npm run dev
```

Expected: Vite prints `Local: http://localhost:5173/` within a couple of seconds. Open it; the page is blank and the browser console shows `custom_cad scaffold ok`. Ctrl-C to stop.

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json tsconfig.json vite.config.ts index.html .gitignore src/main.ts src/kernel/.gitkeep src/doc/.gitkeep src/app/viewport/.gitkeep test/.gitkeep scripts/check-three-imports.sh
git commit -m "chore: scaffold Vite vanilla-ts project with vitest and three.js import guard

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Numeric tolerance primitives (`num.ts`)

**Files:**
- Create: `src/kernel/num.ts`
- Test: `test/kernel/num.test.ts`

All float comparisons in the kernel must go through this module — no inline `Math.abs(a-b) < something` anywhere else. The contract is one absolute tolerance, `EPS_L = 1e-6` model units, with comparisons **inclusive** (`<=`) so a difference of exactly `EPS_L` counts as equal.

- [ ] **Step 1: Write the failing test**

Create `test/kernel/num.test.ts` with the following exact contents:

```ts
import { describe, it, expect } from 'vitest';
import { EPS_L, eq, isZero } from '../../src/kernel/num';

describe('EPS_L', () => {
  it('is 1e-6', () => {
    expect(EPS_L).toBe(1e-6);
  });
});

describe('eq', () => {
  it('returns true for identical values', () => {
    expect(eq(1, 1)).toBe(true);
    expect(eq(0, 0)).toBe(true);
    expect(eq(-3.5, -3.5)).toBe(true);
  });

  it('absorbs ordinary float roundoff (0.1 + 0.2 vs 0.3)', () => {
    // 0.1 + 0.2 === 0.30000000000000004; difference ~5.6e-17, far inside EPS_L
    expect(0.1 + 0.2 === 0.3).toBe(false); // sanity: plain === would fail
    expect(eq(0.1 + 0.2, 0.3)).toBe(true);
  });

  it('returns true for differences within EPS_L, inclusive of the boundary', () => {
    expect(eq(0, 5e-7)).toBe(true);        // |diff| = 5e-7 <  1e-6
    expect(eq(-1, -1 - 5e-7)).toBe(true);  // works on negatives
    expect(eq(0, 1e-6)).toBe(true);        // |diff| = 1e-6 <= 1e-6 -> inclusive
  });

  it('returns false for differences beyond EPS_L', () => {
    expect(eq(0, 2e-6)).toBe(false);   // |diff| = 2e-6 > 1e-6
    expect(eq(1, 1.001)).toBe(false);  // |diff| ~ 1e-3
    expect(eq(5, -5)).toBe(false);
  });

  it('honors a custom eps, inclusive of the boundary', () => {
    expect(eq(1, 1.4, 0.5)).toBe(true);   // |diff| = 0.4 <= 0.5
    expect(eq(1, 1.5, 0.5)).toBe(true);   // |diff| = 0.5 <= 0.5 (0.5 and 1.5 are exact doubles)
    expect(eq(1, 1.6, 0.5)).toBe(false);  // |diff| = 0.6 > 0.5
    expect(eq(0, 2e-6, 1e-9)).toBe(false); // tighter eps than default rejects
  });
});

describe('isZero', () => {
  it('returns true for zero and values within EPS_L of zero', () => {
    expect(isZero(0)).toBe(true);
    expect(isZero(5e-7)).toBe(true);
    expect(isZero(-5e-7)).toBe(true);  // uses absolute value
    expect(isZero(1e-6)).toBe(true);   // inclusive boundary
  });

  it('returns false for values beyond EPS_L', () => {
    expect(isZero(2e-6)).toBe(false);
    expect(isZero(-2e-6)).toBe(false);
    expect(isZero(1)).toBe(false);
  });

  it('honors a custom eps', () => {
    expect(isZero(0.4, 0.5)).toBe(true);
    expect(isZero(0.6, 0.5)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run test/kernel/num.test.ts
```

Expected: the suite errors before any assertion runs, with a module-resolution failure like:

```
FAIL  test/kernel/num.test.ts
Error: Failed to resolve import "../../src/kernel/num" from "test/kernel/num.test.ts". Does the file exist?
```

(Exact wording varies by Vite version; the key signal is a failed import of `src/kernel/num`, not an assertion failure.)

- [ ] **Step 3: Write minimal implementation**

Create `src/kernel/num.ts` with the following exact contents:

```ts
/**
 * Numeric tolerance primitives. ALL float comparisons in the kernel go
 * through this module. One absolute tolerance, inclusive comparisons.
 * Valid model range is roughly 1e-3 .. 1e4 units; geometry finer than
 * ~10 * EPS_L is unsupported.
 */

/** Absolute length tolerance in model units. */
export const EPS_L = 1e-6;

/** True iff |a - b| <= eps (inclusive). */
export function eq(a: number, b: number, eps: number = EPS_L): boolean {
  return Math.abs(a - b) <= eps;
}

/** True iff |x| <= eps (inclusive). */
export function isZero(x: number, eps: number = EPS_L): boolean {
  return Math.abs(x) <= eps;
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run test/kernel/num.test.ts
```

Expected output ends with all tests green:

```
 ✓ test/kernel/num.test.ts (9 tests)

 Test Files  1 passed (1)
      Tests  9 passed (9)
```

Also confirm strict-mode typechecking is clean:

```bash
npx tsc --noEmit
```

Expected: no output, exit code 0.

- [ ] **Step 5: Remove the bootstrap-only `--passWithNoTests` flag**

Tests exist now, so the scaffold-time escape hatch must go (a misconfigured `include` pattern should fail loudly from here on). In `package.json`, change the two scripts to exactly:

```json
    "test": "vitest run",
    "check": "tsc --noEmit && vitest run && bash scripts/check-three-imports.sh"
```

Run: `npm run check`
Expected: typecheck silent, `Tests  9 passed (9)`, import guard silent, exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/kernel/num.ts test/kernel/num.test.ts package.json
git commit -m "feat(kernel): add numeric tolerance primitives EPS_L/eq/isZero

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Vector math module (`src/kernel/vec.ts`)

**Files:**
- Create: `src/kernel/vec.ts`
- Test: `test/kernel/vec.test.ts`

**Prerequisite:** `src/kernel/num.ts` exists and exports `isZero` per the shared contract (built in the preceding num.ts task). Nothing else is needed.

This module is the linear-algebra floor everything else stands on: `Vec2`/`Vec3` value types (plain objects, no classes), the handful of 3D ops the kernel uses, and `PlaneCS` — an orthonormal coordinate frame (`z = x cross y`) used as the sketch-plane representation throughout the spec (§3, §5). All functions are pure and return fresh objects; nothing mutates its inputs.

- [ ] **Step 1: Write the failing test**

Create `test/kernel/vec.test.ts` with the full suite. Every expected value below was computed by hand; integer/exact results use `toBe`/`toEqual`, division results use `toBeCloseTo` with 12 digits.

```ts
import { describe, it, expect } from 'vitest';
import {
  v2, v3,
  add3, sub3, scale3, dot3, cross3, len3, normalize3,
  sub2, cross2,
  XY_PLANE, planePointToWorld,
  type PlaneCS,
} from '../../src/kernel/vec';

describe('constructors', () => {
  it('v2 builds a plain {x,y} object', () => {
    expect(v2(1.5, -2)).toEqual({ x: 1.5, y: -2 });
  });

  it('v3 builds a plain {x,y,z} object', () => {
    expect(v3(1, 2, 3)).toEqual({ x: 1, y: 2, z: 3 });
  });
});

describe('Vec3 arithmetic', () => {
  it('add3: (1,2,3)+(4,5,6) = (5,7,9)', () => {
    expect(add3(v3(1, 2, 3), v3(4, 5, 6))).toEqual({ x: 5, y: 7, z: 9 });
  });

  it('sub3: (4,5,6)-(1,2,3) = (3,3,3)', () => {
    expect(sub3(v3(4, 5, 6), v3(1, 2, 3))).toEqual({ x: 3, y: 3, z: 3 });
  });

  it('scale3: 2*(1,-2,3) = (2,-4,6)', () => {
    expect(scale3(v3(1, -2, 3), 2)).toEqual({ x: 2, y: -4, z: 6 });
  });

  it('dot3: (1,2,3).(4,-5,6) = 4 - 10 + 18 = 12', () => {
    expect(dot3(v3(1, 2, 3), v3(4, -5, 6))).toBe(12);
  });

  it('does not mutate inputs', () => {
    const a = v3(1, 2, 3);
    const b = v3(4, 5, 6);
    add3(a, b);
    sub3(a, b);
    scale3(a, 2);
    expect(a).toEqual({ x: 1, y: 2, z: 3 });
    expect(b).toEqual({ x: 4, y: 5, z: 6 });
  });
});

describe('cross3 right-handedness', () => {
  it('x cross y = z', () => {
    expect(cross3(v3(1, 0, 0), v3(0, 1, 0))).toEqual({ x: 0, y: 0, z: 1 });
  });

  it('y cross z = x', () => {
    expect(cross3(v3(0, 1, 0), v3(0, 0, 1))).toEqual({ x: 1, y: 0, z: 0 });
  });

  it('general case: (1,2,3) x (4,5,6) = (-3,6,-3)', () => {
    // x = 2*6 - 3*5 = -3; y = 3*4 - 1*6 = 6; z = 1*5 - 2*4 = -3
    expect(cross3(v3(1, 2, 3), v3(4, 5, 6))).toEqual({ x: -3, y: 6, z: -3 });
  });
});

describe('len3 / normalize3', () => {
  it('len3 of (3,4,0) = 5 and (1,2,2) = 3', () => {
    expect(len3(v3(3, 4, 0))).toBe(5);
    expect(len3(v3(1, 2, 2))).toBe(3);
  });

  it('normalize3 of (3,4,0) = (0.6, 0.8, 0)', () => {
    const n = normalize3(v3(3, 4, 0));
    expect(n.x).toBeCloseTo(0.6, 12);
    expect(n.y).toBeCloseTo(0.8, 12);
    expect(n.z).toBe(0);
  });

  it('normalize3 result has unit length', () => {
    expect(len3(normalize3(v3(1, 2, 3)))).toBeCloseTo(1, 12);
  });

  it('normalize3 throws on the zero vector', () => {
    expect(() => normalize3(v3(0, 0, 0))).toThrow();
  });

  it('normalize3 throws on a near-zero vector (below EPS_L = 1e-6)', () => {
    expect(() => normalize3(v3(1e-9, 1e-9, 0))).toThrow();
  });
});

describe('Vec2 ops', () => {
  it('sub2: (3,5)-(1,2) = (2,3)', () => {
    expect(sub2(v2(3, 5), v2(1, 2))).toEqual({ x: 2, y: 3 });
  });

  it('cross2 sign: CCW positive, CW negative', () => {
    expect(cross2(v2(1, 0), v2(0, 1))).toBe(1);   // x then y: CCW turn
    expect(cross2(v2(0, 1), v2(1, 0))).toBe(-1);  // y then x: CW turn
    expect(cross2(v2(2, 3), v2(4, 5))).toBe(-2);  // 2*5 - 3*4 = -2
  });
});

describe('PlaneCS', () => {
  it('XY_PLANE fields', () => {
    expect(XY_PLANE.origin).toEqual({ x: 0, y: 0, z: 0 });
    expect(XY_PLANE.x).toEqual({ x: 1, y: 0, z: 0 });
    expect(XY_PLANE.y).toEqual({ x: 0, y: 1, z: 0 });
    expect(XY_PLANE.z).toEqual({ x: 0, y: 0, z: 1 });
  });

  it('planePointToWorld on XY_PLANE: uv (2,3) -> world (2,3,0)', () => {
    expect(planePointToWorld(XY_PLANE, v2(2, 3))).toEqual({ x: 2, y: 3, z: 0 });
  });

  it('planePointToWorld on a translated+rotated plane', () => {
    // YZ-style plane: u runs along world Y, v runs along world Z, normal +X,
    // origin at (5,0,0). z = x cross y = (0,1,0) x (0,0,1) = (1,0,0): orthonormal RH frame.
    const p: PlaneCS = {
      origin: v3(5, 0, 0),
      x: v3(0, 1, 0),
      y: v3(0, 0, 1),
      z: v3(1, 0, 0),
    };
    // (5,0,0) + 2*(0,1,0) + 3*(0,0,1) = (5,2,3)
    expect(planePointToWorld(p, v2(2, 3))).toEqual({ x: 5, y: 2, z: 3 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npx vitest run test/kernel/vec.test.ts
```

Expected failure: the suite cannot even load because the module under test does not exist yet — vitest reports an unresolved import, e.g. `Error: Failed to resolve import "../../src/kernel/vec" from "test/kernel/vec.test.ts". Does the file exist?` (exact wording varies by Vite version; the point is a module-resolution failure, zero tests run).

- [ ] **Step 3: Write the implementation**

Create `src/kernel/vec.ts` (full file contents):

```ts
import { isZero } from './num';

export type Vec2 = { x: number; y: number };
export type Vec3 = { x: number; y: number; z: number };

export function v2(x: number, y: number): Vec2 {
  return { x, y };
}

export function v3(x: number, y: number, z: number): Vec3 {
  return { x, y, z };
}

export function add3(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

export function sub3(a: Vec3, b: Vec3): Vec3 {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

export function scale3(a: Vec3, s: number): Vec3 {
  return { x: a.x * s, y: a.y * s, z: a.z * s };
}

export function dot3(a: Vec3, b: Vec3): number {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

export function cross3(a: Vec3, b: Vec3): Vec3 {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

export function len3(a: Vec3): number {
  return Math.sqrt(a.x * a.x + a.y * a.y + a.z * a.z);
}

/** Returns a unit-length copy of `a`. Throws if `len3(a)` is within EPS_L of zero
 *  (an invariant violation per spec §8 — callers must never pass degenerate vectors). */
export function normalize3(a: Vec3): Vec3 {
  const l = len3(a);
  if (isZero(l)) {
    throw new Error(`normalize3: near-zero length vector (len=${l})`);
  }
  return { x: a.x / l, y: a.y / l, z: a.z / l };
}

export function sub2(a: Vec2, b: Vec2): Vec2 {
  return { x: a.x - b.x, y: a.y - b.y };
}

/** 2D cross product (z-component of the 3D cross). Positive = `b` is a CCW turn from `a`. */
export function cross2(a: Vec2, b: Vec2): number {
  return a.x * b.y - a.y * b.x;
}

/** Orthonormal right-handed coordinate frame: x, y, z unit vectors with z = x cross y. */
export type PlaneCS = { origin: Vec3; x: Vec3; y: Vec3; z: Vec3 };

export const XY_PLANE: PlaneCS = {
  origin: v3(0, 0, 0),
  x: v3(1, 0, 0),
  y: v3(0, 1, 0),
  z: v3(0, 0, 1),
};

/** Maps plane-local uv coordinates to world space: origin + u*x + v*y. */
export function planePointToWorld(p: PlaneCS, uv: Vec2): Vec3 {
  return add3(p.origin, add3(scale3(p.x, uv.x), scale3(p.y, uv.y)));
}
```

- [ ] **Step 4: Run test to verify it passes**

```
npx vitest run test/kernel/vec.test.ts
```

Expected: `Test Files  1 passed (1)` with all 20 tests passing, e.g. `Tests  20 passed (20)`.

Also confirm strict-mode type cleanliness:

```
npx tsc --noEmit
```

Expected: exits silently with status 0.

- [ ] **Step 5: Commit**

```
git add src/kernel/vec.ts test/kernel/vec.test.ts
git commit -m "feat(kernel): add vec module (Vec2/Vec3 ops, PlaneCS, planePointToWorld)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `Result` type + profile types, `signedArea`, `rectProfile`

**Files:**
- Create: `src/kernel/result.ts`, `src/kernel/profile.ts`
- Test: `test/kernel/result.test.ts`, `test/kernel/profile.test.ts`

**Prerequisite:** `src/kernel/vec.ts` (from the shared contracts) already exists and exports `Vec2`, `v2`, `cross2`, `PlaneCS`, `XY_PLANE`. Nothing else is needed.

- [ ] **Step 1: Write the failing test for `result.ts`**

Create `test/kernel/result.test.ts`:

```ts
import { describe, it, expect } from 'vitest';
import { ok, err, type Result } from '../../src/kernel/result';

describe('ok', () => {
  it('wraps a value with ok: true', () => {
    expect(ok(42)).toEqual({ ok: true, value: 42 });
  });

  it('narrows via the ok discriminant', () => {
    const r: Result<string> = ok('hello');
    if (r.ok) {
      expect(r.value).toBe('hello');
    } else {
      throw new Error('expected ok result');
    }
  });
});

describe('err', () => {
  it('builds a KernelError with explicit entity ids', () => {
    expect(err<number>('openLoop', 'profile is not closed', ['rect.s0'])).toEqual({
      ok: false,
      error: { code: 'openLoop', msg: 'profile is not closed', entityIds: ['rect.s0'] },
    });
  });

  it('defaults entityIds to an empty array', () => {
    expect(err<number>('degenerate', 'zero extrude distance')).toEqual({
      ok: false,
      error: { code: 'degenerate', msg: 'zero extrude distance', entityIds: [] },
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```
npx vitest run test/kernel/result.test.ts
```

Expected: the run fails with a module-resolution error, e.g. `Error: Failed to resolve import "../../src/kernel/result" from "test/kernel/result.test.ts". Does the file exist?` (0 tests run).

- [ ] **Step 3: Write minimal implementation**

Create `src/kernel/result.ts` (full file):

```ts
export type KernelError = {
  code: 'openLoop' | 'selfIntersect' | 'degenerate';
  msg: string;
  entityIds: string[];
};

export type Result<T> = { ok: true; value: T } | { ok: false; error: KernelError };

export function ok<T>(value: T): Result<T> {
  return { ok: true, value };
}

export function err<T>(code: KernelError['code'], msg: string, entityIds: string[] = []): Result<T> {
  return { ok: false, error: { code, msg, entityIds } };
}
```

- [ ] **Step 4: Run test to verify it passes**

```
npx vitest run test/kernel/result.test.ts
```

Expected: `Test Files  1 passed (1)`, `Tests  4 passed (4)`.

- [ ] **Step 5: Commit**

```
git add src/kernel/result.ts test/kernel/result.test.ts && git commit -m "feat(kernel): add Result type with ok/err helpers

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

- [ ] **Step 6: Write the failing test for `signedArea`**

Create `test/kernel/profile.test.ts`. The `loopOf` helper builds a closed loop where consecutive segments share the *same* `Vec2` corner objects — that is the closure convention used everywhere in this kernel (closure by construction, never by numeric comparison).

```ts
import { describe, it, expect } from 'vitest';
import { signedArea, type Loop, type Seg } from '../../src/kernel/profile';
import { v2, type Vec2 } from '../../src/kernel/vec';

/** Closed loop over the given corners; consecutive segs share corner objects by reference. */
function loopOf(pts: Vec2[]): Loop {
  const segs: Seg[] = pts.map((p, i) => ({
    id: `t.s${i}`,
    a: p,
    b: pts[(i + 1) % pts.length]!,
  }));
  return { segs };
}

describe('signedArea', () => {
  it('CCW unit square -> +1', () => {
    const loop = loopOf([v2(0, 0), v2(1, 0), v2(1, 1), v2(0, 1)]);
    expect(signedArea(loop)).toBe(1);
  });

  it('reversed (CW) unit square -> -1', () => {
    const loop = loopOf([v2(0, 0), v2(0, 1), v2(1, 1), v2(1, 0)]);
    expect(signedArea(loop)).toBe(-1);
  });

  it('CCW 3-4-5 right triangle -> +6', () => {
    // (0,0) -> (4,0) -> (0,3): area = 4*3/2 = 6, CCW so positive.
    const loop = loopOf([v2(0, 0), v2(4, 0), v2(0, 3)]);
    expect(signedArea(loop)).toBe(6);
  });

  it('square away from the origin -> area independent of translation', () => {
    // 3x3 square with min corner (2,1): area 9.
    // Shoelace terms (a.x*b.y - a.y*b.x): -3 + 15 + 12 - 6 = 18; half = 9.
    const loop = loopOf([v2(2, 1), v2(5, 1), v2(5, 4), v2(2, 4)]);
    expect(signedArea(loop)).toBe(9);
  });
});
```

- [ ] **Step 7: Run test to verify it fails**

```
npx vitest run test/kernel/profile.test.ts
```

Expected: module-resolution failure, e.g. `Error: Failed to resolve import "../../src/kernel/profile" from "test/kernel/profile.test.ts". Does the file exist?` (0 tests run).

- [ ] **Step 8: Write minimal implementation (types + `signedArea` only)**

Create `src/kernel/profile.ts` (full file; `rectProfile` is deliberately absent — next round):

```ts
import { cross2, type PlaneCS, type Vec2 } from './vec';

// M1 profiles: line segments only, single outer loop, no holes.

export type SketchEntId = string;

export type Seg = { id: SketchEntId; a: Vec2; b: Vec2 };

/**
 * Closed loop: segs[i].b is EXACTLY the same object as segs[(i+1)%n].a.
 * Closure is shared-by-construction; it is never tested numerically.
 */
export type Loop = { segs: Seg[] };

export type Profile = { plane: PlaneCS; outer: Loop };

/** Shoelace signed area in uv coordinates; positive = CCW. */
export function signedArea(loop: Loop): number {
  let sum = 0;
  for (const seg of loop.segs) {
    sum += cross2(seg.a, seg.b);
  }
  return sum / 2;
}
```

- [ ] **Step 9: Run test to verify it passes**

```
npx vitest run test/kernel/profile.test.ts
```

Expected: `Test Files  1 passed (1)`, `Tests  4 passed (4)`.

- [ ] **Step 10: Write the failing test for `rectProfile`**

Append this `describe` block to the end of `test/kernel/profile.test.ts`, and extend the existing profile import line to:

```ts
import { signedArea, rectProfile, type Loop, type Seg } from '../../src/kernel/profile';
```

and the vec import line to:

```ts
import { v2, XY_PLANE, type Vec2 } from '../../src/kernel/vec';
```

Appended block:

```ts
describe('rectProfile', () => {
  const p = rectProfile(XY_PLANE, 3, 2);

  it('has 4 segments with ids rect.s0..rect.s3', () => {
    expect(p.outer.segs.map((s) => s.id)).toEqual(['rect.s0', 'rect.s1', 'rect.s2', 'rect.s3']);
  });

  it('starts corners at (0,0),(w,0),(w,h),(0,h) — CCW order', () => {
    expect(p.outer.segs.map((s) => s.a)).toEqual([
      { x: 0, y: 0 },
      { x: 3, y: 0 },
      { x: 3, y: 2 },
      { x: 0, y: 2 },
    ]);
  });

  it('closes by reference: segs[i].b is the SAME object as segs[(i+1)%4].a', () => {
    for (let i = 0; i < 4; i++) {
      expect(p.outer.segs[i]!.b).toBe(p.outer.segs[(i + 1) % 4]!.a);
    }
  });

  it('signedArea(outer) === w*h (CCW)', () => {
    expect(signedArea(p.outer)).toBe(6);
  });

  it('carries the plane it was given', () => {
    expect(p.plane).toBe(XY_PLANE);
  });
});
```

- [ ] **Step 11: Run test to verify it fails**

```
npx vitest run test/kernel/profile.test.ts
```

Expected: the file fails to load with `SyntaxError: The requested module '../../src/kernel/profile' does not provide an export named 'rectProfile'` (the 4 signedArea tests do not run because the import fails).

- [ ] **Step 12: Implement `rectProfile`**

Replace `src/kernel/profile.ts` with the full final file:

```ts
import { cross2, v2, type PlaneCS, type Vec2 } from './vec';

// M1 profiles: line segments only, single outer loop, no holes.

export type SketchEntId = string;

export type Seg = { id: SketchEntId; a: Vec2; b: Vec2 };

/**
 * Closed loop: segs[i].b is EXACTLY the same object as segs[(i+1)%n].a.
 * Closure is shared-by-construction; it is never tested numerically.
 */
export type Loop = { segs: Seg[] };

export type Profile = { plane: PlaneCS; outer: Loop };

/** Shoelace signed area in uv coordinates; positive = CCW. */
export function signedArea(loop: Loop): number {
  let sum = 0;
  for (const seg of loop.segs) {
    sum += cross2(seg.a, seg.b);
  }
  return sum / 2;
}

/**
 * Axis-aligned w x h rectangle in the plane's uv space.
 * Corners (0,0),(w,0),(w,h),(0,h), CCW; seg ids 'rect.s0'..'rect.s3'.
 * Adjacent segments share the same corner Vec2 objects (closure by construction).
 */
export function rectProfile(plane: PlaneCS, w: number, h: number): Profile {
  const c0 = v2(0, 0);
  const c1 = v2(w, 0);
  const c2 = v2(w, h);
  const c3 = v2(0, h);
  const outer: Loop = {
    segs: [
      { id: 'rect.s0', a: c0, b: c1 },
      { id: 'rect.s1', a: c1, b: c2 },
      { id: 'rect.s2', a: c2, b: c3 },
      { id: 'rect.s3', a: c3, b: c0 },
    ],
  };
  return { plane, outer };
}
```

- [ ] **Step 13: Run all tests and the type check**

```
npx vitest run test/kernel/profile.test.ts
```

Expected: `Test Files  1 passed (1)`, `Tests  9 passed (9)`. Then:

```
npx tsc --noEmit
```

Expected: no output, exit code 0.

- [ ] **Step 14: Commit**

```
git add src/kernel/profile.ts test/kernel/profile.test.ts && git commit -m "feat(kernel): add profile types, signedArea, and rectProfile

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: B-rep half-edge types and `validateSolid`

**Files:**
- Create: `src/kernel/brep.ts`
- Test: `test/kernel/brep.test.ts`
- Depends on (must already exist): `src/kernel/vec.ts` (for `v3`, `dot3`, `sub3`, `PlaneCS`, `Vec3`), `src/kernel/profile.ts` (for the `SketchEntId` type)

This task builds the boundary-representation data structure (Mäntylä-style half-edge tables, spec §3) and the structural validator that every kernel op runs in dev builds. `validateSolid` returns human-readable problem strings; `[]` means valid. It checks: twin involution, `next`-cycle/loop consistency, edge usage, Euler–Poincaré, and a winding-vs-normal sample. It does **not** check geometric degeneracy — the green-path test exploits that deliberately.

- [ ] **Step 1: Write the failing test** — create `test/kernel/brep.test.ts` with the full contents below. The `makeSheet()` helper hand-wires the smallest topologically valid solid: two triangular faces glued back to back over the same three vertices. It has zero volume (geometrically degenerate) but is a closed topological manifold — exactly what `validateSolid` inspects, so it is a legitimate green-path fixture.

```ts
import { describe, expect, it } from 'vitest';
import { v3 } from '../../src/kernel/vec';
import type { PlaneCS } from '../../src/kernel/vec';
import { validateSolid } from '../../src/kernel/brep';
import type {
  BLoop,
  Edge,
  Face,
  HalfEdge,
  Solid,
  TopoId,
  Vertex,
} from '../../src/kernel/brep';

/**
 * Minimal topologically-valid solid: two triangular faces glued back to back
 * over the same three vertices (a "sheet"). V=3, E=3, F=2, 6 half-edges;
 * Euler-Poincare: 3 - 3 + 2 = 2. It is geometrically DEGENERATE (zero volume)
 * but topologically a closed manifold, which is all validateSolid checks --
 * fine for these tests.
 *
 * Id map:
 *   Vertices:   A=1 (0,0,0)   B=2 (1,0,0)   C=3 (0,1,0)
 *   Edges:      AB=10   BC=11   CA=12
 *   Half-edges, "up" face loop 30:   20 (A->B)  21 (B->C)  22 (C->A)
 *   Half-edges, "down" face loop 31: 23 (A->C)  24 (C->B)  25 (B->A)
 *   Twins: 20<->25, 21<->24, 22<->23
 *   Face 40 ("up"):   surface normal +z; loop A->B->C is CCW seen from +z.
 *   Face 41 ("down"): surface normal -z (y negated so z = x cross y);
 *                     loop A->C->B is CCW seen from -z.
 */
function makeSheet(): Solid {
  const planeUp: PlaneCS = {
    origin: v3(0, 0, 0), x: v3(1, 0, 0), y: v3(0, 1, 0), z: v3(0, 0, 1),
  };
  const planeDown: PlaneCS = {
    origin: v3(0, 0, 0), x: v3(1, 0, 0), y: v3(0, -1, 0), z: v3(0, 0, -1),
  };

  const A = v3(0, 0, 0);
  const B = v3(1, 0, 0);
  const C = v3(0, 1, 0);

  const vertices = new Map<TopoId, Vertex>([
    [1, { id: 1, p: A }],
    [2, { id: 2, p: B }],
    [3, { id: 3, p: C }],
  ]);

  const halfEdges = new Map<TopoId, HalfEdge>([
    // up-face cycle: 20 -> 21 -> 22 -> 20   (A -> B -> C -> A)
    [20, { id: 20, start: 1, twin: 25, next: 21, loop: 30, edge: 10 }],
    [21, { id: 21, start: 2, twin: 24, next: 22, loop: 30, edge: 11 }],
    [22, { id: 22, start: 3, twin: 23, next: 20, loop: 30, edge: 12 }],
    // down-face cycle: 23 -> 24 -> 25 -> 23  (A -> C -> B -> A)
    [23, { id: 23, start: 1, twin: 22, next: 24, loop: 31, edge: 12 }],
    [24, { id: 24, start: 3, twin: 21, next: 25, loop: 31, edge: 11 }],
    [25, { id: 25, start: 2, twin: 20, next: 23, loop: 31, edge: 10 }],
  ]);

  // gen tags here are arbitrary-but-valid EdgeGen/FaceGen values; validateSolid
  // never reads them, but the types require them.
  const edges = new Map<TopoId, Edge>([
    [10, { id: 10, curve: { kind: 'line', a: A, b: B }, gen: { role: 'capEdge', end: 'end', curve: 't.s0' }, he: 20 }],
    [11, { id: 11, curve: { kind: 'line', a: B, b: C }, gen: { role: 'capEdge', end: 'end', curve: 't.s1' }, he: 21 }],
    [12, { id: 12, curve: { kind: 'line', a: C, b: A }, gen: { role: 'capEdge', end: 'end', curve: 't.s2' }, he: 22 }],
  ]);

  const loops = new Map<TopoId, BLoop>([
    [30, { id: 30, face: 40, he: 20 }],
    [31, { id: 31, face: 41, he: 23 }],
  ]);

  const faces = new Map<TopoId, Face>([
    [40, { id: 40, loop: 30, surface: { kind: 'plane', cs: planeUp }, gen: { role: 'cap', end: 'end' } }],
    [41, { id: 41, loop: 31, surface: { kind: 'plane', cs: planeDown }, gen: { role: 'cap', end: 'start' } }],
  ]);

  return { vertices, halfEdges, edges, loops, faces };
}

describe('validateSolid', () => {
  it('returns [] for a minimal topologically valid solid (back-to-back triangle sheet)', () => {
    expect(validateSolid(makeSheet())).toEqual([]);
  });

  it('reports broken twin involution', () => {
    const s = makeSheet();
    // 20's twin should be 25; point it at 21 instead. 21.twin is 24, so
    // twin(twin(20)) === 20 fails; 25 still claims twin 20, so it fails too.
    s.halfEdges.get(20)!.twin = 21;
    const errs = validateSolid(s);
    expect(errs).toContain('half-edge 20: twin involution broken (twin 21.twin = 24)');
    expect(errs).toContain('half-edge 25: twin involution broken (twin 20.twin = 21)');
    expect(errs).toHaveLength(2);
  });

  it('reports an Euler-Poincare violation when a face is removed', () => {
    const s = makeSheet();
    s.faces.delete(41); // V=3, E=3, F=1  ->  3 - 3 + 1 = 1 !== 2
    expect(validateSolid(s)).toEqual([
      'Euler-Poincare violated: V=3 E=3 F=1, V-E+F=1 != 2',
    ]);
  });

  it('reports CW winding when a loop is reversed relative to its surface normal', () => {
    const s = makeSheet();
    // Flip face 40's surface frame so its normal points -z while its loop
    // still runs A->B->C. That is equivalent to reversing the loop relative
    // to the normal, but leaves all pointer topology intact, so ONLY the
    // winding check fires. Projected uv (u = dot(p-origin, x), v = dot(p-origin, y)):
    //   A=(0,0), B=(1,0), C=(0,-1)
    // shoelace 2*area = (0*0 - 1*0) + (1*(-1) - 0*0) + (0*0 - 0*(-1)) = -1
    // -> signed area -0.5.
    s.faces.get(40)!.surface = {
      kind: 'plane',
      cs: { origin: v3(0, 0, 0), x: v3(1, 0, 0), y: v3(0, -1, 0), z: v3(0, 0, -1) },
    };
    expect(validateSolid(s)).toEqual([
      'face 40: loop winding is CW in surface uv (signed area -0.5)',
    ]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails** — run:

```
npx vitest run test/kernel/brep.test.ts
```

Expected failure: the suite errors before any test runs with `Failed to resolve import "../../src/kernel/brep" from "test/kernel/brep.test.ts". Does the file exist?` (module not created yet). All 4 tests show as failed/not run.

- [ ] **Step 3: Write the implementation** — create `src/kernel/brep.ts` with the full contents below.

```ts
import { dot3, sub3 } from './vec';
import type { PlaneCS, Vec3 } from './vec';
import type { SketchEntId } from './profile';

export type TopoId = number;

export type FaceGen =
  | { role: 'side'; curve: SketchEntId }
  | { role: 'cap'; end: 'start' | 'end' };

export type EdgeGen =
  | { role: 'capEdge'; end: 'start' | 'end'; curve: SketchEntId }
  | { role: 'sideEdge'; vertex: SketchEntId }; // vertex tag = seg.id + ':a'

export type Surface = { kind: 'plane'; cs: PlaneCS };
export type Curve3 = { kind: 'line'; a: Vec3; b: Vec3 };

export type Vertex = { id: TopoId; p: Vec3 };

export type HalfEdge = {
  id: TopoId;
  start: TopoId; // vertex id this half-edge leaves from
  twin: TopoId;  // opposite half-edge on the same edge
  next: TopoId;  // next half-edge around the loop
  loop: TopoId;
  edge: TopoId;
};

export type Edge = { id: TopoId; curve: Curve3; gen: EdgeGen; he: TopoId };
export type BLoop = { id: TopoId; face: TopoId; he: TopoId }; // he = entry half-edge of the cycle
export type Face = { id: TopoId; loop: TopoId; surface: Surface; gen: FaceGen }; // single loop per face in M1

export type Solid = {
  vertices: Map<TopoId, Vertex>;
  halfEdges: Map<TopoId, HalfEdge>;
  edges: Map<TopoId, Edge>;
  loops: Map<TopoId, BLoop>;
  faces: Map<TopoId, Face>;
};

/**
 * Structural validation of a manifold half-edge solid (spec section 3).
 * Returns human-readable problem strings; [] means valid.
 *
 * Checks:
 *  1. twin involution: twin exists, twin !== self, twin.twin === self,
 *     twins share one edge and traverse it in opposite directions;
 *  2. `next` forms closed cycles, one per loop, that partition all half-edges,
 *     and every half-edge's `loop` field matches the cycle it sits in;
 *  3. every edge is referenced by exactly two half-edges
 *     (opposite traversal of those two is enforced via check 1's twin pairing);
 *  4. Euler-Poincare for a genus-0 single shell: V - E + F === 2;
 *  5. winding sample: each planar face's loop, projected into surface uv
 *     (u = dot(p - origin, cs.x), v = dot(p - origin, cs.y)), has positive
 *     shoelace area, i.e. is CCW as seen from the +cs.z side.
 *
 * Geometric degeneracy (zero area / zero volume) is intentionally NOT checked.
 * In dev builds the kernel runs this after every op and throws on non-empty
 * results (invariant bug, not a user error).
 */
export function validateSolid(s: Solid): string[] {
  const errors: string[] = [];

  // Destination vertex of a half-edge = start vertex of its `next`.
  const dest = (he: HalfEdge): TopoId | undefined => s.halfEdges.get(he.next)?.start;

  // --- 1. Twin involution -------------------------------------------------
  for (const he of s.halfEdges.values()) {
    const t = s.halfEdges.get(he.twin);
    if (t === undefined) {
      errors.push(`half-edge ${he.id}: twin ${he.twin} missing`);
      continue;
    }
    if (t.id === he.id) {
      errors.push(`half-edge ${he.id} is its own twin`);
      continue;
    }
    if (t.twin !== he.id) {
      errors.push(`half-edge ${he.id}: twin involution broken (twin ${t.id}.twin = ${t.twin})`);
      continue;
    }
    if (t.edge !== he.edge) {
      errors.push(`half-edge ${he.id} and twin ${t.id} reference different edges (${he.edge} vs ${t.edge})`);
    }
    if (he.start !== dest(t) || t.start !== dest(he)) {
      errors.push(`half-edge ${he.id} and twin ${t.id} do not traverse opposite directions`);
    }
  }

  // --- 2. next-cycles partition halfEdges; loop fields consistent ----------
  const visited = new Set<TopoId>();
  for (const loop of s.loops.values()) {
    const entry = s.halfEdges.get(loop.he);
    if (entry === undefined) {
      errors.push(`loop ${loop.id}: entry half-edge ${loop.he} missing`);
      continue;
    }
    const cycle: HalfEdge[] = [entry];
    let closed = false;
    let cur = entry;
    while (cycle.length <= s.halfEdges.size) {
      const nxt = s.halfEdges.get(cur.next);
      if (nxt === undefined) {
        errors.push(`half-edge ${cur.id}: next ${cur.next} missing`);
        break;
      }
      if (nxt.id === entry.id) {
        closed = true;
        break;
      }
      cycle.push(nxt);
      cur = nxt;
    }
    if (!closed) {
      errors.push(`loop ${loop.id}: next-cycle from half-edge ${entry.id} does not close back to entry`);
    }
    for (const he of cycle) {
      if (he.loop !== loop.id) {
        errors.push(`half-edge ${he.id} is in the cycle of loop ${loop.id} but has loop field ${he.loop}`);
      }
      if (visited.has(he.id)) {
        errors.push(`half-edge ${he.id} appears in more than one loop cycle`);
      }
      visited.add(he.id);
    }
  }
  for (const he of s.halfEdges.values()) {
    if (!visited.has(he.id)) {
      errors.push(`half-edge ${he.id} not reachable from any loop's next-cycle`);
    }
  }

  // --- 3. Each edge referenced by exactly two half-edges -------------------
  const edgeRefs = new Map<TopoId, number>();
  for (const he of s.halfEdges.values()) {
    edgeRefs.set(he.edge, (edgeRefs.get(he.edge) ?? 0) + 1);
  }
  for (const e of s.edges.values()) {
    const n = edgeRefs.get(e.id) ?? 0;
    if (n !== 2) {
      errors.push(`edge ${e.id} referenced by ${n} half-edges (expected 2)`);
    }
    if (!s.halfEdges.has(e.he)) {
      errors.push(`edge ${e.id}: representative half-edge ${e.he} missing`);
    }
  }
  for (const [edgeId, n] of edgeRefs) {
    if (!s.edges.has(edgeId)) {
      errors.push(`half-edges reference unknown edge ${edgeId} (${n} refs)`);
    }
  }

  // --- 4. Euler-Poincare ----------------------------------------------------
  const V = s.vertices.size;
  const E = s.edges.size;
  const F = s.faces.size;
  if (V - E + F !== 2) {
    errors.push(`Euler-Poincare violated: V=${V} E=${E} F=${F}, V-E+F=${V - E + F} != 2`);
  }

  // --- 5. Winding sample: loop CCW as seen from +surface.cs.z --------------
  for (const face of s.faces.values()) {
    const loop = s.loops.get(face.loop);
    if (loop === undefined) {
      errors.push(`face ${face.id}: loop ${face.loop} missing`);
      continue;
    }
    const entry = s.halfEdges.get(loop.he);
    if (entry === undefined) continue; // already reported by check 2
    const cs = face.surface.cs;
    const pts: { u: number; v: number }[] = [];
    let cur = entry;
    let walkOk = true;
    for (let i = 0; i <= s.halfEdges.size; i++) {
      const vert = s.vertices.get(cur.start);
      if (vert === undefined) {
        errors.push(`half-edge ${cur.id}: start vertex ${cur.start} missing`);
        walkOk = false;
        break;
      }
      const rel = sub3(vert.p, cs.origin);
      pts.push({ u: dot3(rel, cs.x), v: dot3(rel, cs.y) });
      const nxt = s.halfEdges.get(cur.next);
      if (nxt === undefined) {
        walkOk = false; // already reported by check 2
        break;
      }
      if (nxt.id === entry.id) break;
      cur = nxt;
    }
    if (!walkOk || pts.length < 3) continue;
    let area2 = 0; // shoelace: 2 * signed area, positive = CCW in uv
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i]!;
      const b = pts[(i + 1) % pts.length]!;
      area2 += a.u * b.v - b.u * a.v;
    }
    if (area2 <= 0) {
      errors.push(`face ${face.id}: loop winding is CW in surface uv (signed area ${area2 / 2})`);
    }
  }

  return errors;
}
```

- [ ] **Step 4: Run test to verify it passes** — run:

```
npx vitest run test/kernel/brep.test.ts
```

Expected: `Test Files  1 passed (1)` and `Tests  4 passed (4)`. Then run the typecheck to confirm strict-mode cleanliness:

```
npx tsc --noEmit
```

Expected: exits silently with status 0 (no diagnostics).

- [ ] **Step 5: Commit**

```
git add src/kernel/brep.ts test/kernel/brep.test.ts
git commit -m "feat(kernel): half-edge B-rep types and validateSolid

Adds the Solid half-edge tables (Vertex/HalfEdge/Edge/BLoop/Face with
structured gen tags) and validateSolid covering twin involution,
next-cycle partition, edge usage, Euler-Poincare, and a winding-vs-normal
sample. Tested against a hand-wired back-to-back triangle sheet
(topologically valid, geometrically degenerate) plus three broken-solid
red paths.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: `extrude()` — profile → half-edge prism solid

**Files:**
- Create: `src/kernel/extrude.ts`
- Test: `test/kernel/extrude.test.ts`

This task builds the M1 centerpiece: turning a closed CCW `Profile` (line segments on a plane) into a watertight half-edge prism `Solid`, with every face/edge carrying its structured `gen` tag. All topology is wired by **index arithmetic** over the segment list — no numeric coincidence matching anywhere (spec §3). Depends on `num.ts`, `vec.ts`, `result.ts`, `profile.ts`, `brep.ts` (with `validateSolid`) already existing per the shared contracts.

Hand-checked expected values used below: `rectProfile(XY_PLANE, 4, 3)` has shoelace area `(0 + 4·3 + 4·3 + 0)/2 = 12` (CCW); reversing it gives `-12`. A 4-segment prism has `V=2n=8`, `E=3n=12`, `F=n+2=6`, `halfEdges=6n=24`, `loops=n+2=6`, and Euler–Poincaré `8−12+6=2`. The 3-segment triangle `(0,0),(2,0),(0,2)` has area `4/2 = 2` (CCW) and prism counts `V=6, E=9, F=5, halfEdges=18`, Euler `6−9+5=2`.

- [ ] **Step 1: Write the failing test**

Create `test/kernel/extrude.test.ts` with the complete contents below. Note the CW-identity test: `extrude` reorients CW input by *reversing the segment array and swapping each seg's endpoints (keeping ids)* — that operation is an involution, so a manually reversed rectangle must produce a solid **deeply identical** to the CCW one (same TopoIds, same gens, same coordinates).

```ts
import { describe, expect, it } from 'vitest';
import { v2, XY_PLANE } from '../../src/kernel/vec';
import type { Result } from '../../src/kernel/result';
import { rectProfile, signedArea, type Profile } from '../../src/kernel/profile';
import { validateSolid } from '../../src/kernel/brep';
import { extrude } from '../../src/kernel/extrude';

function unwrap<T>(r: Result<T>): T {
  if (!r.ok) throw new Error(`expected ok, got ${r.error.code}: ${r.error.msg}`);
  return r.value;
}

const rect = () => rectProfile(XY_PLANE, 4, 3);

describe('extrude rejections', () => {
  it('rejects dist = 0 as degenerate', () => {
    const r = extrude(rect(), { dist: 0 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe('degenerate');
  });

  it('rejects negative dist as degenerate', () => {
    const r = extrude(rect(), { dist: -2 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe('degenerate');
  });

  it('rejects a 2-segment loop as degenerate, naming the segments', () => {
    const a = v2(0, 0);
    const b = v2(1, 0);
    const p: Profile = {
      plane: XY_PLANE,
      outer: { segs: [{ id: 'x.s0', a, b }, { id: 'x.s1', a: b, b: a }] },
    };
    const r = extrude(p, { dist: 5 });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe('degenerate');
      expect(r.error.entityIds).toEqual(['x.s0', 'x.s1']);
    }
  });

  it('rejects a zero-area (collinear) loop as degenerate', () => {
    const a = v2(0, 0);
    const b = v2(1, 0);
    const c = v2(2, 0);
    const p: Profile = {
      plane: XY_PLANE,
      outer: {
        segs: [
          { id: 'z.s0', a, b },
          { id: 'z.s1', a: b, b: c },
          { id: 'z.s2', a: c, b: a },
        ],
      },
    };
    const r = extrude(p, { dist: 5 });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe('degenerate');
  });
});

describe('extrude rect 4x3 by 5', () => {
  const solid = () => unwrap(extrude(rect(), { dist: 5 }));

  it('has prism counts V=8 E=12 F=6 halfEdges=24 loops=6 and validates clean', () => {
    const s = solid();
    expect(s.vertices.size).toBe(8);
    expect(s.edges.size).toBe(12);
    expect(s.faces.size).toBe(6);
    expect(s.halfEdges.size).toBe(24);
    expect(s.loops.size).toBe(6);
    expect(validateSolid(s)).toEqual([]);
  });

  it('places the 8 corner vertices exactly', () => {
    const pts = [...solid().vertices.values()]
      .map((v) => v.p)
      .sort((p, q) => p.z - q.z || p.y - q.y || p.x - q.x);
    expect(pts).toEqual([
      { x: 0, y: 0, z: 0 }, { x: 4, y: 0, z: 0 }, { x: 0, y: 3, z: 0 }, { x: 4, y: 3, z: 0 },
      { x: 0, y: 0, z: 5 }, { x: 4, y: 0, z: 5 }, { x: 0, y: 3, z: 5 }, { x: 4, y: 3, z: 5 },
    ]);
  });

  it('tags every face: one side per seg plus start/end caps', () => {
    const gens = [...solid().faces.values()].map((f) => f.gen);
    expect(gens).toHaveLength(6);
    expect(gens).toContainEqual({ role: 'cap', end: 'start' });
    expect(gens).toContainEqual({ role: 'cap', end: 'end' });
    for (const id of ['rect.s0', 'rect.s1', 'rect.s2', 'rect.s3']) {
      expect(gens).toContainEqual({ role: 'side', curve: id });
    }
  });

  it('tags every edge and carries exact analytic line curves', () => {
    const s = solid();
    const gens = [...s.edges.values()].map((e) => e.gen);
    expect(gens).toHaveLength(12);
    for (const id of ['rect.s0', 'rect.s1', 'rect.s2', 'rect.s3']) {
      expect(gens).toContainEqual({ role: 'capEdge', end: 'start', curve: id });
      expect(gens).toContainEqual({ role: 'capEdge', end: 'end', curve: id });
      expect(gens).toContainEqual({ role: 'sideEdge', vertex: `${id}:a` });
    }
    const vert = [...s.edges.values()].find(
      (e) => e.gen.role === 'sideEdge' && e.gen.vertex === 'rect.s0:a',
    );
    expect(vert?.curve).toEqual({
      kind: 'line', a: { x: 0, y: 0, z: 0 }, b: { x: 0, y: 0, z: 5 },
    });
    const capE = [...s.edges.values()].find(
      (e) => e.gen.role === 'capEdge' && e.gen.end === 'start' && e.gen.curve === 'rect.s0',
    );
    expect(capE?.curve).toEqual({
      kind: 'line', a: { x: 0, y: 0, z: 0 }, b: { x: 4, y: 0, z: 0 },
    });
  });
});

describe('extrude CW reorientation', () => {
  it('a CW outer loop produces a solid identical to the CCW one', () => {
    const ccw = rect();
    // Manually reverse: reverse seg order AND swap each seg's endpoints, keep ids.
    // Endpoint sharing is preserved: reversed segs still chain by object identity.
    const cw: Profile = {
      plane: ccw.plane,
      outer: { segs: [...ccw.outer.segs].reverse().map((s) => ({ id: s.id, a: s.b, b: s.a })) },
    };
    expect(signedArea(ccw.outer)).toBe(12);
    expect(signedArea(cw.outer)).toBe(-12);
    const sCcw = unwrap(extrude(ccw, { dist: 5 }));
    const sCw = unwrap(extrude(cw, { dist: 5 }));
    expect(validateSolid(sCw)).toEqual([]);
    // extrude's internal reversal is the exact involution of the manual one above,
    // so the two solids must be deeply equal -- TopoIds, gens, coordinates, wiring.
    expect(sCw).toEqual(sCcw);
  });
});

describe('extrude triangle prism', () => {
  it('hand-built 3-seg loop -> V=6 E=9 F=5 halfEdges=18, validates clean', () => {
    const p0 = v2(0, 0);
    const p1 = v2(2, 0);
    const p2 = v2(0, 2);
    const tri: Profile = {
      plane: XY_PLANE,
      outer: {
        segs: [
          { id: 'tri.s0', a: p0, b: p1 },
          { id: 'tri.s1', a: p1, b: p2 },
          { id: 'tri.s2', a: p2, b: p0 },
        ],
      },
    };
    const s = unwrap(extrude(tri, { dist: 1 }));
    expect(s.vertices.size).toBe(6);
    expect(s.edges.size).toBe(9);
    expect(s.faces.size).toBe(5);
    expect(s.halfEdges.size).toBe(18);
    expect(validateSolid(s)).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run test/kernel/extrude.test.ts
```

Expected: the whole file errors with a module-resolution failure, e.g. `Error: Failed to resolve import "../../src/kernel/extrude" from "test/kernel/extrude.test.ts". Does the file exist?` (0 tests run). This confirms the tests are wired to the not-yet-existing implementation.

- [ ] **Step 3: Write minimal implementation**

Create `src/kernel/extrude.ts` with the complete contents below. The construction algorithm, concretely:

1. **Guards:** reject `dist <= 0 || isZero(dist)`; reject `< 3` segments; reject any zero-length segment; reject `isZero(signedArea)`. All return `err('degenerate', ...)` — the kernel never throws for control flow.
2. **Orientation:** if `signedArea < 0` (CW), reorient to CCW via `reverseLoop` — reverse the seg array and swap each seg's `a`/`b`, keeping ids. This is an involution and preserves endpoint sharing by object identity. (Documented choice: reorient, don't reject.)
3. **Vertices (2n):** bottom ring `B[i] = planePointToWorld(plane, segs[i].a)`; top ring `T[i] = B[i] + scale3(plane.z, dist)`.
4. **Pre-mint every TopoId** into index-parallel arrays, then wire twins/nexts purely by index arithmetic (the wiring table is in the file header comment).
5. **Faces (n+2):** one planar quad per seg (`B[i]→B[i+1]→T[i+1]→T[i]`, outward normal `dir × plane.z`); bottom cap traversing the ring **backwards** (CW in uv ⇒ CCW seen from its outward normal `−plane.z`); top cap traversing **forwards** (CCW in uv, normal `+plane.z`).
6. **Edges (3n):** `n` bottom-cap, `n` top-cap, `n` vertical, with the exact `gen` tags from the contract.

```ts
// src/kernel/extrude.ts
//
// Linear extrusion of a planar profile (M1: line segments only, outer loop only,
// no holes) into a manifold half-edge prism. Construction is deterministic index
// arithmetic over the segment list -- coincidence is declared, never discovered
// numerically (spec section 3).
//
// A CW outer loop is REORIENTED to CCW internally (reverse seg order + swap each
// seg's a/b, keeping ids) rather than rejected. That reversal is an involution,
// so extruding a reversed loop yields a solid identical to the CCW original.
//
// Topology for an n-segment CCW loop (V=2n, E=3n, F=n+2, halfEdges=6n):
//
//   Vertices  B[i] = planePointToWorld(plane, segs[i].a); T[i] = B[i] + dist*plane.z
//   Faces     side[i]: quad B[i] -> B[i+1] -> T[i+1] -> T[i], gen {role:'side', curve:segs[i].id},
//                      surface PlaneCS {origin:B[i], x:dir(i), y:plane.z, z:dir(i) x plane.z}
//             bottom cap: ring traversed BACKWARDS (CW in uv => CCW viewed from -plane.z),
//                      gen {role:'cap', end:'start'}, cs {x:plane.y, y:plane.x, z:-plane.z}
//             top cap: ring traversed FORWARDS (CCW in uv), gen {role:'cap', end:'end'},
//                      cs = plane translated by dist*plane.z
//   Edges     eBot[i]:  B[i]--B[i+1]  gen {role:'capEdge', end:'start', curve:segs[i].id}
//             eTop[i]:  T[i]--T[i+1]  gen {role:'capEdge', end:'end',   curve:segs[i].id}
//             eVert[i]: B[i]--T[i]    gen {role:'sideEdge', vertex:segs[i].id+':a'}
//
// Half-edge wiring table (j = (i+1)%n, k = (i-1+n)%n):
//
//   half-edge      start  next           twin           edge
//   sideBottom[i]  B[i]   sideRight[i]   capBot[i]      eBot[i]
//   sideRight[i]   B[j]   sideTop[i]     sideLeft[j]    eVert[j]
//   sideTop[i]     T[j]   sideLeft[i]    capTop[i]      eTop[i]
//   sideLeft[i]    T[i]   sideBottom[i]  sideRight[k]   eVert[i]
//   capBot[i]      B[j]   capBot[k]      sideBottom[i]  eBot[i]
//   capTop[i]      T[i]   capTop[j]      sideTop[i]     eTop[i]

import { isZero } from './num';
import {
  add3, cross3, normalize3, planePointToWorld, scale3, sub2, sub3,
  type PlaneCS,
} from './vec';
import { err, ok, type Result } from './result';
import { signedArea, type Loop, type Profile, type Seg } from './profile';
import type { Curve3, Solid, Surface, TopoId, Vertex } from './brep';

/** Reverse a loop's orientation. Involution; preserves seg ids and shared endpoint objects. */
function reverseLoop(loop: Loop): Loop {
  const segs: Seg[] = [];
  for (let i = loop.segs.length - 1; i >= 0; i--) {
    const s = loop.segs[i]!;
    segs.push({ id: s.id, a: s.b, b: s.a });
  }
  return { segs };
}

export function extrude(profile: Profile, opts: { dist: number }): Result<Solid> {
  const { dist } = opts;
  if (dist <= 0 || isZero(dist)) {
    return err('degenerate', `extrude distance must be positive, got ${dist}`);
  }

  let loop = profile.outer;
  const segIds = loop.segs.map((s) => s.id);
  const n = loop.segs.length;
  if (n < 3) {
    return err('degenerate', `outer loop needs at least 3 segments, got ${n}`, segIds);
  }
  for (const s of loop.segs) {
    const d = sub2(s.b, s.a);
    if (isZero(Math.hypot(d.x, d.y))) {
      return err('degenerate', `zero-length segment ${s.id}`, [s.id]);
    }
  }
  const area = signedArea(loop);
  if (isZero(area)) {
    return err('degenerate', 'outer loop encloses near-zero area', segIds);
  }
  if (area < 0) loop = reverseLoop(loop); // CW input -> reorient to CCW (see header)

  const plane = profile.plane;
  const lift = scale3(plane.z, dist);

  const solid: Solid = {
    vertices: new Map(),
    halfEdges: new Map(),
    edges: new Map(),
    loops: new Map(),
    faces: new Map(),
  };
  let nextId: TopoId = 1;
  const mint = (): TopoId => nextId++;

  // --- 1. mint 2n vertices: bottom ring at segs[i].a, top ring lifted by dist*plane.z ---
  const botV: Vertex[] = [];
  const topV: Vertex[] = [];
  for (let i = 0; i < n; i++) {
    const p = planePointToWorld(plane, loop.segs[i]!.a);
    const bv: Vertex = { id: mint(), p };
    const tv: Vertex = { id: mint(), p: add3(p, lift) };
    solid.vertices.set(bv.id, bv);
    solid.vertices.set(tv.id, tv);
    botV.push(bv);
    topV.push(tv);
  }

  // --- 2. pre-mint all remaining TopoIds so wiring is pure index arithmetic ---
  const sideBottom: TopoId[] = [];
  const sideRight: TopoId[] = [];
  const sideTop: TopoId[] = [];
  const sideLeft: TopoId[] = [];
  const capBot: TopoId[] = [];
  const capTop: TopoId[] = [];
  const sideFace: TopoId[] = [];
  const sideLoop: TopoId[] = [];
  const eBot: TopoId[] = [];
  const eTop: TopoId[] = [];
  const eVert: TopoId[] = [];
  for (let i = 0; i < n; i++) {
    sideBottom.push(mint());
    sideRight.push(mint());
    sideTop.push(mint());
    sideLeft.push(mint());
    capBot.push(mint());
    capTop.push(mint());
    sideFace.push(mint());
    sideLoop.push(mint());
    eBot.push(mint());
    eTop.push(mint());
    eVert.push(mint());
  }
  const botFaceId = mint();
  const botLoopId = mint();
  const topFaceId = mint();
  const topLoopId = mint();

  // --- 3. per-seg: side face (planar quad), 6 half-edges, 3 edges ---
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    const k = (i - 1 + n) % n;
    const seg = loop.segs[i]!;
    const B = botV[i]!;
    const Bn = botV[j]!;
    const T = topV[i]!;
    const Tn = topV[j]!;

    // Side face i: quad B[i] -> B[i+1] -> T[i+1] -> T[i]; outward normal dir x plane.z.
    const dir = normalize3(sub3(Bn.p, B.p)); // safe: zero-length segs rejected above
    const sideSurf: Surface = {
      kind: 'plane',
      cs: { origin: B.p, x: dir, y: plane.z, z: cross3(dir, plane.z) },
    };
    solid.faces.set(sideFace[i]!, {
      id: sideFace[i]!, loop: sideLoop[i]!, surface: sideSurf,
      gen: { role: 'side', curve: seg.id },
    });
    solid.loops.set(sideLoop[i]!, { id: sideLoop[i]!, face: sideFace[i]!, he: sideBottom[i]! });

    // Side half-edges (see wiring table in header).
    solid.halfEdges.set(sideBottom[i]!, {
      id: sideBottom[i]!, start: B.id, twin: capBot[i]!, next: sideRight[i]!,
      loop: sideLoop[i]!, edge: eBot[i]!,
    });
    solid.halfEdges.set(sideRight[i]!, {
      id: sideRight[i]!, start: Bn.id, twin: sideLeft[j]!, next: sideTop[i]!,
      loop: sideLoop[i]!, edge: eVert[j]!,
    });
    solid.halfEdges.set(sideTop[i]!, {
      id: sideTop[i]!, start: Tn.id, twin: capTop[i]!, next: sideLeft[i]!,
      loop: sideLoop[i]!, edge: eTop[i]!,
    });
    solid.halfEdges.set(sideLeft[i]!, {
      id: sideLeft[i]!, start: T.id, twin: sideRight[k]!, next: sideBottom[i]!,
      loop: sideLoop[i]!, edge: eVert[i]!,
    });

    // Cap half-edges: bottom ring runs backwards (next steps i -> i-1), top runs forwards.
    solid.halfEdges.set(capBot[i]!, {
      id: capBot[i]!, start: Bn.id, twin: sideBottom[i]!, next: capBot[k]!,
      loop: botLoopId, edge: eBot[i]!,
    });
    solid.halfEdges.set(capTop[i]!, {
      id: capTop[i]!, start: T.id, twin: sideTop[i]!, next: capTop[j]!,
      loop: topLoopId, edge: eTop[i]!,
    });

    // Edges with analytic line curves and gen tags.
    const botCurve: Curve3 = { kind: 'line', a: B.p, b: Bn.p };
    const topCurve: Curve3 = { kind: 'line', a: T.p, b: Tn.p };
    const vertCurve: Curve3 = { kind: 'line', a: B.p, b: T.p };
    solid.edges.set(eBot[i]!, {
      id: eBot[i]!, curve: botCurve,
      gen: { role: 'capEdge', end: 'start', curve: seg.id }, he: sideBottom[i]!,
    });
    solid.edges.set(eTop[i]!, {
      id: eTop[i]!, curve: topCurve,
      gen: { role: 'capEdge', end: 'end', curve: seg.id }, he: sideTop[i]!,
    });
    solid.edges.set(eVert[i]!, {
      id: eVert[i]!, curve: vertCurve,
      gen: { role: 'sideEdge', vertex: seg.id + ':a' }, he: sideLeft[i]!,
    });
  }

  // --- 4. caps ---
  // Bottom: outward normal is -plane.z; swapping x/y gives z = x cross y = plane.y x plane.x = -plane.z.
  const botCs: PlaneCS = { origin: plane.origin, x: plane.y, y: plane.x, z: scale3(plane.z, -1) };
  // Top: the profile plane translated along +plane.z by dist.
  const topCs: PlaneCS = { origin: add3(plane.origin, lift), x: plane.x, y: plane.y, z: plane.z };

  solid.faces.set(botFaceId, {
    id: botFaceId, loop: botLoopId, surface: { kind: 'plane', cs: botCs },
    gen: { role: 'cap', end: 'start' },
  });
  solid.loops.set(botLoopId, { id: botLoopId, face: botFaceId, he: capBot[0]! });
  solid.faces.set(topFaceId, {
    id: topFaceId, loop: topLoopId, surface: { kind: 'plane', cs: topCs },
    gen: { role: 'cap', end: 'end' },
  });
  solid.loops.set(topLoopId, { id: topLoopId, face: topFaceId, he: capTop[0]! });

  return ok(solid);
}
```

Why the wiring is twin-consistent (sanity check, no action needed): `sideBottom[i]` runs `B[i]→B[i+1]` while its twin `capBot[i]` runs `B[i+1]→B[i]` (opposite direction, same edge `eBot[i]`); `sideRight[i]` runs `B[i+1]→T[i+1]` while `sideLeft[i+1]` runs `T[i+1]→B[i+1]` (same edge `eVert[i+1]`); `sideTop[i]` runs `T[i+1]→T[i]` while `capTop[i]` runs `T[i]→T[i+1]` (same edge `eTop[i]`). Every edge is referenced by exactly two half-edges, and each face loop is CCW seen from `+surface.cs.z`.

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run test/kernel/extrude.test.ts
```

Expected: `Test Files  1 passed (1)` and `Tests  10 passed (10)` — 4 rejection tests, 4 rect tests, the CW-identity test, and the triangle prism test all green.

- [ ] **Step 5: Typecheck and run the full suite**

```bash
npx tsc --noEmit && npx vitest run
```

Expected: `tsc` exits silently (no type errors) and all existing kernel test files pass alongside the new one (no regressions).

- [ ] **Step 6: Commit**

```bash
git add src/kernel/extrude.ts test/kernel/extrude.test.ts
git commit -m "feat(kernel): extrude profile to half-edge prism with gen tags

Deterministic index-arithmetic construction: 2n vertices, n side quads,
2 caps, 3n tagged edges; CW outer loops reoriented to CCW (involution).
Rejects non-positive distance, <3 segs, zero-length segs, zero area.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Tessellation — `Solid` → `RenderData` (ear clipping, analytic normals, edge polylines)

**Files:**
- Create: `/home/svankina/src/custom_cad/src/kernel/tess.ts`
- Test: `/home/svankina/src/custom_cad/test/kernel/tess.test.ts`
- Depends on (must already exist from earlier tasks): `src/kernel/num.ts`, `src/kernel/vec.ts`, `src/kernel/profile.ts`, `src/kernel/brep.ts`, `src/kernel/extrude.ts`

This task turns a B-rep `Solid` into the flat typed-array `RenderData` contract (spec §3) that the viewport consumes. Key decisions you implement here, exactly as specified:

- **Per-face vertex duplication.** Positions are NOT shared across faces. Each face emits its own copies of its loop vertices, each carrying the face's analytic normal `surface.cs.z` (flat shading; normals are never averaged).
- **`faceSpans.start`/`count` are measured in `triIndex` ENTRIES** (so always multiples of 3; a quad face = 2 triangles = `count: 6`).
- **`edgeSpans.start`/`count` are measured in VERTEX entries** of `edges.positions` (a line edge = `count: 2`, occupying 6 floats).
- **Ear clipping** is a plain O(n²) clipper for simple CCW polygons, no holes (M1). It is exported from `tess.ts` so it can be unit-tested directly, but it is an internal kernel helper — nothing outside the kernel/tests may import it.
- `chordTol` is accepted but unused in M1 (lines only — nothing to discretize). It stays in the signature so the call sites don't churn when arcs land at M4.
- Faces' loops are guaranteed CCW when projected into their own `surface.cs` (u,v) frame — that is exactly the winding invariant `validateSolid` enforces — so the tessellator never re-orients anything.

---

- [ ] **Step 1: Write the failing ear-clip test**

Create `/home/svankina/src/custom_cad/test/kernel/tess.test.ts` with exactly this content (tessellate tests come in a later step):

```ts
import { describe, it, expect } from 'vitest';
import { earClip } from '../../src/kernel/tess';
import { cross2, sub2 } from '../../src/kernel/vec';
import type { Vec2 } from '../../src/kernel/vec';

// 2 * signed area of triangle (a,b,c); positive = CCW
function twiceArea(a: Vec2, b: Vec2, c: Vec2): number {
  return cross2(sub2(b, a), sub2(c, a));
}

describe('earClip', () => {
  it('triangulates a CCW 4x3 rectangle into 2 CCW triangles, area 12', () => {
    const pts: Vec2[] = [
      { x: 0, y: 0 },
      { x: 4, y: 0 },
      { x: 4, y: 3 },
      { x: 0, y: 3 },
    ];
    const tris = earClip(pts);
    expect(tris.length).toBe(6); // (4 - 2) triangles * 3 indices
    let total = 0;
    for (let t = 0; t < tris.length; t += 3) {
      const ta = twiceArea(pts[tris[t]!]!, pts[tris[t + 1]!]!, pts[tris[t + 2]!]!);
      expect(ta).toBeGreaterThan(0); // every output triangle stays CCW
      total += ta / 2;
    }
    expect(total).toBeCloseTo(12, 10);
  });

  it('triangulates a concave L-shaped hexagon into 4 CCW triangles, area 3', () => {
    // 2x2 square with the top-right 1x1 corner removed. CCW. Reflex vertex at (1,1).
    const pts: Vec2[] = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 1 },
      { x: 1, y: 1 },
      { x: 1, y: 2 },
      { x: 0, y: 2 },
    ];
    const tris = earClip(pts);
    expect(tris.length).toBe(12); // (6 - 2) triangles * 3 indices
    let total = 0;
    for (let t = 0; t < tris.length; t += 3) {
      const ta = twiceArea(pts[tris[t]!]!, pts[tris[t + 1]!]!, pts[tris[t + 2]!]!);
      expect(ta).toBeGreaterThan(0);
      total += ta / 2;
    }
    expect(total).toBeCloseTo(3, 10); // 2*2 - 1*1
  });
});
```

Why these expected values: shoelace area of the L-hexagon is `(0·0−2·0)+(2·1−2·0)+(2·1−1·1)+(1·2−1·1)+(1·2−0·2)+(0·0−0·2) = 0+2+1+1+2+0 = 6`, so area `= 6/2 = 3` and the polygon is CCW. Any correct triangulation of an n-gon has n−2 triangles.

- [ ] **Step 2: Run test to verify it fails**

```bash
npx vitest run test/kernel/tess.test.ts
```

Expected failure: the suite fails to load with a module-resolution error like `Error: Failed to resolve import "../../src/kernel/tess" from "test/kernel/tess.test.ts"` (wording varies slightly by Vite version) — `src/kernel/tess.ts` does not exist yet.

- [ ] **Step 3: Implement `earClip`**

Create `/home/svankina/src/custom_cad/src/kernel/tess.ts`:

```ts
// Tessellation: Solid -> RenderData (flat typed arrays for the viewport).
// M1 scope: planar faces, line edges. Normals are analytic from the face
// surface (cs.z), emitted per face vertex; positions are NOT shared across
// faces (flat shading, no normal averaging).

import { EPS_L } from './num';
import { cross2, sub2 } from './vec';
import type { Vec2 } from './vec';

/**
 * Ear-clipping triangulation of a simple CCW polygon (no holes).
 * Returns local indices into `pts`, 3 per triangle, length 3*(n-2).
 * Internal kernel helper -- exported only so tests can hit it directly.
 * O(n^2): for each candidate corner, ear = convex corner AND no other
 * remaining vertex inside (or on the boundary of) the corner triangle.
 *
 * NOTE: cross2 here is an area-scale quantity; using EPS_L as its threshold
 * is fine at M1 model scales (~1e-3..1e4 units, spec section 3).
 */
export function earClip(pts: Vec2[]): number[] {
  const n = pts.length;
  if (n < 3) return [];
  const idx: number[] = [];
  for (let i = 0; i < n; i++) idx.push(i);
  const out: number[] = [];
  while (idx.length > 3) {
    let clipped = false;
    for (let i = 0; i < idx.length; i++) {
      const i0 = idx[(i + idx.length - 1) % idx.length]!; // `!`: noUncheckedIndexedAccess
      const i1 = idx[i]!;
      const i2 = idx[(i + 1) % idx.length]!;
      if (isEar(pts, idx, i0, i1, i2)) {
        out.push(i0, i1, i2);
        idx.splice(i, 1); // remove the ear tip
        clipped = true;
        break;
      }
    }
    if (!clipped) {
      // A simple polygon always has >= 2 ears (two-ears theorem); reaching
      // here means degenerate or non-simple input -- a kernel bug upstream.
      throw new Error('earClip: no ear found (degenerate or non-simple polygon)');
    }
  }
  out.push(idx[0]!, idx[1]!, idx[2]!);
  return out;
}

function isEar(pts: Vec2[], idx: number[], i0: number, i1: number, i2: number): boolean {
  const a = pts[i0]!;
  const b = pts[i1]!;
  const c = pts[i2]!;
  // Convex corner of a CCW polygon: cross of (b-a) x (c-b) > 0.
  // Reflex or collinear corners are never ears.
  const cr = cross2(sub2(b, a), sub2(c, b));
  if (cr <= EPS_L) return false;
  // No other remaining vertex inside the candidate triangle. Boundary counts
  // as inside (>= -EPS_L): clipping an ear whose edge passes through another
  // vertex would create a T-junction.
  for (const j of idx) {
    if (j === i0 || j === i1 || j === i2) continue;
    if (pointInTriInclusive(pts[j]!, a, b, c)) return false;
  }
  return true;
}

function pointInTriInclusive(p: Vec2, a: Vec2, b: Vec2, c: Vec2): boolean {
  const d0 = cross2(sub2(b, a), sub2(p, a));
  const d1 = cross2(sub2(c, b), sub2(p, b));
  const d2 = cross2(sub2(a, c), sub2(p, c));
  return d0 >= -EPS_L && d1 >= -EPS_L && d2 >= -EPS_L;
}
```

The boundary-inclusive point-in-triangle test is load-bearing for the L-shape: the corner at `(0,0)` with neighbors `(0,2)` and `(2,0)` is convex, but the reflex vertex `(1,1)` lies exactly on its diagonal (`x+y=2`), so that ear must be rejected — otherwise you emit a triangle whose edge passes through a polygon vertex.

- [ ] **Step 4: Run test to verify it passes**

```bash
npx vitest run test/kernel/tess.test.ts
```

Expected: `2 passed` (both `earClip` tests), exit code 0.

- [ ] **Step 5: Write the failing `tessellate` tests**

Replace the ENTIRE contents of `/home/svankina/src/custom_cad/test/kernel/tess.test.ts` with:

```ts
import { describe, it, expect } from 'vitest';
import { earClip, tessellate } from '../../src/kernel/tess';
import type { RenderData } from '../../src/kernel/tess';
import { rectProfile } from '../../src/kernel/profile';
import { extrude } from '../../src/kernel/extrude';
import { XY_PLANE, cross2, sub2 } from '../../src/kernel/vec';
import type { Vec2, Vec3 } from '../../src/kernel/vec';

// 2 * signed area of triangle (a,b,c); positive = CCW
function twiceArea(a: Vec2, b: Vec2, c: Vec2): number {
  return cross2(sub2(b, a), sub2(c, a));
}

describe('earClip', () => {
  it('triangulates a CCW 4x3 rectangle into 2 CCW triangles, area 12', () => {
    const pts: Vec2[] = [
      { x: 0, y: 0 },
      { x: 4, y: 0 },
      { x: 4, y: 3 },
      { x: 0, y: 3 },
    ];
    const tris = earClip(pts);
    expect(tris.length).toBe(6); // (4 - 2) triangles * 3 indices
    let total = 0;
    for (let t = 0; t < tris.length; t += 3) {
      const ta = twiceArea(pts[tris[t]!]!, pts[tris[t + 1]!]!, pts[tris[t + 2]!]!);
      expect(ta).toBeGreaterThan(0); // every output triangle stays CCW
      total += ta / 2;
    }
    expect(total).toBeCloseTo(12, 10);
  });

  it('triangulates a concave L-shaped hexagon into 4 CCW triangles, area 3', () => {
    // 2x2 square with the top-right 1x1 corner removed. CCW. Reflex vertex at (1,1).
    const pts: Vec2[] = [
      { x: 0, y: 0 },
      { x: 2, y: 0 },
      { x: 2, y: 1 },
      { x: 1, y: 1 },
      { x: 1, y: 2 },
      { x: 0, y: 2 },
    ];
    const tris = earClip(pts);
    expect(tris.length).toBe(12); // (6 - 2) triangles * 3 indices
    let total = 0;
    for (let t = 0; t < tris.length; t += 3) {
      const ta = twiceArea(pts[tris[t]!]!, pts[tris[t + 1]!]!, pts[tris[t + 2]!]!);
      expect(ta).toBeGreaterThan(0);
      total += ta / 2;
    }
    expect(total).toBeCloseTo(3, 10); // 2*2 - 1*1
  });
});

// ---------------------------------------------------------------------------
// tessellate() on the canonical M1 solid: rectProfile(XY_PLANE, 4, 3)
// extruded by 5. A 4 x 3 x 5 box: 6 quad faces, 12 edges, 8 corners.
// ---------------------------------------------------------------------------

function makeBox(): RenderData {
  const res = extrude(rectProfile(XY_PLANE, 4, 3), { dist: 5 });
  if (!res.ok) throw new Error(`extrude failed: ${res.error.code}: ${res.error.msg}`);
  return tessellate(res.value, 0.1); // chordTol unused for lines-only
}

// Round a vertex position to a dedup key (1e-6 grid, matches EPS_L).
function posKey(positions: Float32Array, vi: number): string {
  const r = (t: number) => Math.round(t * 1e6);
  return `${r(positions[3 * vi]!)},${r(positions[3 * vi + 1]!)},${r(positions[3 * vi + 2]!)}`;
}

function expectSpanNormal(rd: RenderData, span: { start: number; count: number }, n: Vec3): void {
  for (let i = span.start; i < span.start + span.count; i++) {
    const vi = rd.mesh.triIndex[i]!;
    expect(rd.mesh.normals[3 * vi]).toBeCloseTo(n.x, 6);
    expect(rd.mesh.normals[3 * vi + 1]).toBeCloseTo(n.y, 6);
    expect(rd.mesh.normals[3 * vi + 2]).toBeCloseTo(n.z, 6);
  }
}

describe('tessellate (4x3x5 box)', () => {
  it('emits 6 quad faces as 36 triIndex entries with contiguous non-overlapping spans', () => {
    const rd = makeBox();
    // 6 faces, each a quad with its own 4 vertices (no sharing across faces)
    expect(rd.mesh.positions.length).toBe(6 * 4 * 3); // 72 floats
    expect(rd.mesh.normals.length).toBe(72);
    expect(rd.mesh.triIndex.length).toBe(36); // 6 faces * 2 tris * 3
    expect(rd.mesh.faceSpans.length).toBe(6);
    const spans = [...rd.mesh.faceSpans].sort((a, b) => a.start - b.start);
    let cursor = 0;
    for (const s of spans) {
      expect(s.start).toBe(cursor); // contiguous, no gaps/overlap
      expect(s.count).toBe(6); // quad = 2 tris = 6 triIndex ENTRIES
      cursor += s.count;
    }
    expect(cursor).toBe(36); // spans exactly cover triIndex
  });

  it('emits analytic per-face normals: caps +/-z, side rect.s0 faces -y', () => {
    const rd = makeBox();
    const top = rd.mesh.faceSpans.find((s) => s.gen.role === 'cap' && s.gen.end === 'end');
    const bottom = rd.mesh.faceSpans.find((s) => s.gen.role === 'cap' && s.gen.end === 'start');
    const side0 = rd.mesh.faceSpans.find((s) => s.gen.role === 'side' && s.gen.curve === 'rect.s0');
    expect(top).toBeDefined();
    expect(bottom).toBeDefined();
    expect(side0).toBeDefined();
    expectSpanNormal(rd, top!, { x: 0, y: 0, z: 1 });
    expectSpanNormal(rd, bottom!, { x: 0, y: 0, z: -1 });
    // rect.s0 runs (0,0)->(4,0) in a CCW outer loop; the interior is at y > 0,
    // so the outward side-face normal is (0,-1,0).
    expectSpanNormal(rd, side0!, { x: 0, y: -1, z: 0 });
  });

  it('is watertight on a positions-dedup basis (every undirected tri edge used exactly twice)', () => {
    const rd = makeBox();
    const { positions, triIndex } = rd.mesh;
    // 8 distinct corner positions even though faces do not share vertex entries
    const uniq = new Set<string>();
    for (let vi = 0; vi < positions.length / 3; vi++) uniq.add(posKey(positions, vi));
    expect(uniq.size).toBe(8);
    const edgeUse = new Map<string, number>();
    for (let t = 0; t < triIndex.length; t += 3) {
      const k = [
        posKey(positions, triIndex[t]!),
        posKey(positions, triIndex[t + 1]!),
        posKey(positions, triIndex[t + 2]!),
      ];
      for (let e = 0; e < 3; e++) {
        const a = k[e]!;
        const b = k[(e + 1) % 3]!;
        const ek = a < b ? `${a}|${b}` : `${b}|${a}`;
        edgeUse.set(ek, (edgeUse.get(ek) ?? 0) + 1);
      }
    }
    // 12 topological box edges + 6 quad diagonals = 18 undirected mesh edges
    expect(edgeUse.size).toBe(18);
    for (const [ek, uses] of edgeUse) {
      expect(uses, `undirected edge ${ek}`).toBe(2);
    }
  });

  it('emits one 2-vertex span per B-rep edge (12 spans, vertex-entry units)', () => {
    const rd = makeBox();
    expect(rd.edges.edgeSpans.length).toBe(12); // prism: E = 3n = 12
    expect(rd.edges.positions.length).toBe(12 * 2 * 3); // 72 floats
    const spans = [...rd.edges.edgeSpans].sort((a, b) => a.start - b.start);
    let cursor = 0;
    for (const s of spans) {
      expect(s.start).toBe(cursor); // start in VERTEX entries
      expect(s.count).toBe(2); // a line = 2 vertex entries
      cursor += s.count;
    }
    expect(cursor).toBe(24); // 24 vertex entries total
  });
});
```

Where the expected numbers come from (verify against the extrude contract): n = 4 segments ⇒ F = n+2 = 6 faces, E = 3n = 12, V = 2n = 8. Each face is a planar quad ⇒ 2 triangles ⇒ 6 `triIndex` entries per face, 36 total. Each face emits 4 private vertices ⇒ 24 vertices ⇒ 72 position/normal floats. Watertightness counts: each of the 12 box edges is bordered by exactly 2 faces (used once per face), and each quad's internal diagonal is shared by exactly the 2 triangles of that quad — 12 + 6 = 18 undirected edges, every one used exactly twice.

- [ ] **Step 6: Run test to verify the new tests fail**

```bash
npx vitest run test/kernel/tess.test.ts
```

Expected failure: the suite errors before running, with something like `SyntaxError: The requested module '/src/kernel/tess.ts' does not provide an export named 'tessellate'` (exact wording varies by Vite version). The two `earClip` tests may not even get to run — that's fine.

- [ ] **Step 7: Implement `tessellate`**

Replace the ENTIRE contents of `/home/svankina/src/custom_cad/src/kernel/tess.ts` with:

```ts
// Tessellation: Solid -> RenderData (flat typed arrays for the viewport).
// M1 scope: planar faces, line edges. Normals are analytic from the face
// surface (cs.z), emitted per face vertex; positions are NOT shared across
// faces (flat shading, no normal averaging).
//
// Span units (the render contract, locked in M1):
//   faceSpans.start/count are measured in triIndex ENTRIES (multiples of 3).
//   edgeSpans.start/count are measured in VERTEX entries of edges.positions
//     (a line edge has count === 2, occupying 6 floats).

import { EPS_L } from './num';
import { cross2, sub2, dot3, sub3 } from './vec';
import type { Vec2, Vec3 } from './vec';
import type { Solid, TopoId, FaceGen, EdgeGen } from './brep';

export type RenderData = {
  mesh: {
    positions: Float32Array;
    normals: Float32Array;
    triIndex: Uint32Array;
    faceSpans: { faceId: TopoId; gen: FaceGen; start: number; count: number }[];
  };
  edges: {
    positions: Float32Array;
    edgeSpans: { edgeId: TopoId; gen: EdgeGen; start: number; count: number }[];
  };
};

/**
 * Ear-clipping triangulation of a simple CCW polygon (no holes).
 * Returns local indices into `pts`, 3 per triangle, length 3*(n-2).
 * Internal kernel helper -- exported only so tests can hit it directly.
 * O(n^2): for each candidate corner, ear = convex corner AND no other
 * remaining vertex inside (or on the boundary of) the corner triangle.
 *
 * NOTE: cross2 here is an area-scale quantity; using EPS_L as its threshold
 * is fine at M1 model scales (~1e-3..1e4 units, spec section 3).
 */
export function earClip(pts: Vec2[]): number[] {
  const n = pts.length;
  if (n < 3) return [];
  const idx: number[] = [];
  for (let i = 0; i < n; i++) idx.push(i);
  const out: number[] = [];
  while (idx.length > 3) {
    let clipped = false;
    for (let i = 0; i < idx.length; i++) {
      const i0 = idx[(i + idx.length - 1) % idx.length]!; // `!`: noUncheckedIndexedAccess
      const i1 = idx[i]!;
      const i2 = idx[(i + 1) % idx.length]!;
      if (isEar(pts, idx, i0, i1, i2)) {
        out.push(i0, i1, i2);
        idx.splice(i, 1); // remove the ear tip
        clipped = true;
        break;
      }
    }
    if (!clipped) {
      // A simple polygon always has >= 2 ears (two-ears theorem); reaching
      // here means degenerate or non-simple input -- a kernel bug upstream.
      throw new Error('earClip: no ear found (degenerate or non-simple polygon)');
    }
  }
  out.push(idx[0]!, idx[1]!, idx[2]!);
  return out;
}

function isEar(pts: Vec2[], idx: number[], i0: number, i1: number, i2: number): boolean {
  const a = pts[i0]!;
  const b = pts[i1]!;
  const c = pts[i2]!;
  // Convex corner of a CCW polygon: cross of (b-a) x (c-b) > 0.
  // Reflex or collinear corners are never ears.
  const cr = cross2(sub2(b, a), sub2(c, b));
  if (cr <= EPS_L) return false;
  // No other remaining vertex inside the candidate triangle. Boundary counts
  // as inside (>= -EPS_L): clipping an ear whose edge passes through another
  // vertex would create a T-junction.
  for (const j of idx) {
    if (j === i0 || j === i1 || j === i2) continue;
    if (pointInTriInclusive(pts[j]!, a, b, c)) return false;
  }
  return true;
}

function pointInTriInclusive(p: Vec2, a: Vec2, b: Vec2, c: Vec2): boolean {
  const d0 = cross2(sub2(b, a), sub2(p, a));
  const d1 = cross2(sub2(c, b), sub2(p, b));
  const d2 = cross2(sub2(a, c), sub2(p, c));
  return d0 >= -EPS_L && d1 >= -EPS_L && d2 >= -EPS_L;
}

/** Walk a loop's half-edge cycle via `next`, collecting start-vertex positions in order. */
function loopVertices(solid: Solid, loopId: TopoId): Vec3[] {
  const loop = solid.loops.get(loopId);
  if (!loop) throw new Error(`tessellate: missing loop ${loopId}`);
  const out: Vec3[] = [];
  let heId = loop.he;
  const max = solid.halfEdges.size + 1; // runaway guard
  for (let i = 0; i < max; i++) {
    const he = solid.halfEdges.get(heId);
    if (!he) throw new Error(`tessellate: missing halfEdge ${heId}`);
    const v = solid.vertices.get(he.start);
    if (!v) throw new Error(`tessellate: missing vertex ${he.start}`);
    out.push(v.p);
    heId = he.next;
    if (heId === loop.he) return out;
  }
  throw new Error(`tessellate: loop ${loopId} half-edge cycle does not close`);
}

export function tessellate(solid: Solid, _chordTol: number): RenderData {
  // _chordTol: unused in M1 (lines only); kept in the signature for arcs (M4).
  const positions: number[] = [];
  const normals: number[] = [];
  const triIndex: number[] = [];
  const faceSpans: RenderData['mesh']['faceSpans'] = [];

  for (const face of solid.faces.values()) {
    const cs = face.surface.cs;
    const pts3 = loopVertices(solid, face.loop);
    // Project into the face's own (u,v) frame: u = (p-origin).x_axis, etc.
    // validateSolid's winding invariant guarantees this polygon is CCW.
    const uv: Vec2[] = pts3.map((p) => {
      const q = sub3(p, cs.origin);
      return { x: dot3(q, cs.x), y: dot3(q, cs.y) };
    });
    const base = positions.length / 3; // global index of this face's first vertex
    for (const p of pts3) positions.push(p.x, p.y, p.z);
    for (let i = 0; i < pts3.length; i++) normals.push(cs.z.x, cs.z.y, cs.z.z);
    const local = earClip(uv);
    const start = triIndex.length; // span units: triIndex ENTRIES
    for (const li of local) triIndex.push(base + li);
    faceSpans.push({ faceId: face.id, gen: face.gen, start, count: local.length });
  }

  const edgePositions: number[] = [];
  const edgeSpans: RenderData['edges']['edgeSpans'] = [];
  for (const edge of solid.edges.values()) {
    const start = edgePositions.length / 3; // span units: VERTEX entries
    const { a, b } = edge.curve; // M1: kind 'line' only
    edgePositions.push(a.x, a.y, a.z, b.x, b.y, b.z);
    edgeSpans.push({ edgeId: edge.id, gen: edge.gen, start, count: 2 });
  }

  return {
    mesh: {
      positions: Float32Array.from(positions),
      normals: Float32Array.from(normals),
      triIndex: Uint32Array.from(triIndex),
      faceSpans,
    },
    edges: {
      positions: Float32Array.from(edgePositions),
      edgeSpans,
    },
  };
}
```

Notes for the implementer:
- The parameter is named `_chordTol` (underscore-prefixed) purely to satisfy `noUnusedParameters` under strict TS; the runtime signature matches the contract.
- `Map.values()` iterates in insertion order, so spans come out deterministic and back-to-back; the bookkeeping (`base`, `start`) is pure index arithmetic — no numeric matching anywhere.
- Kernel rule reminder: this file imports only from `./num`, `./vec`, `./brep` — never from `doc/` or `app/`, and never three.js.

- [ ] **Step 8: Run test to verify it passes**

```bash
npx vitest run test/kernel/tess.test.ts
```

Expected: `Test Files  1 passed`, `Tests  6 passed` (2 earClip + 4 tessellate), exit code 0.

- [ ] **Step 9: Typecheck and run the full suite**

```bash
npx tsc --noEmit && npx vitest run
```

Expected: tsc emits nothing (exit 0) and all test files from this and prior tasks pass. If tsc complains about `import type` vs value imports, the fix is to keep types (`Vec2`, `Vec3`, `Solid`, `TopoId`, `FaceGen`, `EdgeGen`, `RenderData`) on `import type` lines and values (`EPS_L`, `cross2`, `sub2`, `dot3`, `sub3`, `XY_PLANE`, `rectProfile`, `extrude`, `earClip`, `tessellate`) on plain `import` lines, exactly as written above.

- [ ] **Step 10: Commit**

```bash
git add src/kernel/tess.ts test/kernel/tess.test.ts
git commit -m "feat(kernel): tessellate solids to RenderData via ear clipping

Planar-face ear-clip triangulation with analytic per-face normals (no
averaging, positions private per face), faceSpans in triIndex entries,
edgeSpans in vertex entries; watertightness verified on the 4x3x5 box.

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Viewport shell — `CameraState`, `Viewport`, and app entry point

**Files:**
- Create: `src/app/viewport/cameraState.ts`
- Create: `src/app/viewport/renderer.ts`
- Create: `src/style.css`
- Modify: `index.html` (full replacement)
- Modify: `src/main.ts` (full replacement of the Vite placeholder)
- Test: none (three.js DOM/WebGL objects — manual verification instead; `npm run check` still gates)

This task builds the viewport shell from spec section 6 / milestone M1 (section 10): an orthographic, z-up camera wrapped behind the `CameraState` facade, a `Viewport` that owns the WebGL renderer, grid, and lights, and render-on-demand (a frame is drawn only on `requestRender()` / camera change / resize — never a free-running loop). No model is added yet; that lands in the `sceneSync` task. `src/app/viewport/*.ts` are the only files allowed to import three.js — `src/main.ts` must import only `Viewport`, never `three`.

- [ ] **Step 1: Install three.js and its types (skip pieces already present)**

  ```bash
  cd /home/svankina/src/custom_cad
  npm ls three || npm install three
  npm ls @types/three || npm install -D @types/three
  ```

  Expected: both `npm ls` lines eventually print a resolved version (e.g. `three@0.1xx.x`). We need three **>= 0.151** because `OrbitControls.zoomToCursor` was added in r151.

- [ ] **Step 2: Verify the OrbitControls import path against the installed three version**

  Modern three maps `three/addons/*` to `examples/jsm/*` via package exports. Confirm before writing any import:

  ```bash
  cd /home/svankina/src/custom_cad
  node -p "require('three/package.json').version"
  grep -n '"./addons/\*"' node_modules/three/package.json
  ls node_modules/three/examples/jsm/controls/OrbitControls.js
  ```

  Expected: version >= `0.151.0`; the grep prints a line like `"./addons/*": "./examples/jsm/*",`; the `ls` succeeds. If (and only if) the grep finds nothing, the installed three is too old for the `addons` alias — run `npm install three@latest` and re-verify rather than falling back to the legacy `three/examples/jsm/...` path.

- [ ] **Step 3: Write `src/app/viewport/cameraState.ts`**

  Full file contents:

  ```ts
  import * as THREE from 'three';
  import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

  /** Model units visible vertically at zoom = 1. */
  const FRUSTUM_HEIGHT = 20;
  const FAR = 1000;

  /**
   * Facade over THREE.OrthographicCamera + OrbitControls (spec sec 6: camera
   * math is not this project's curriculum; the facade keeps a hand-rolled
   * swap cheap if OrbitControls fights us later).
   *
   * Conventions: CAD z-up (camera.up = +z), orthographic only, no damping
   * (CAD wants crisp stops), zoom toward cursor, screen-space panning.
   */
  export class CameraState {
    readonly camera: THREE.OrthographicCamera;
    private controls: OrbitControls;
    private listeners: Array<() => void> = [];

    constructor(canvas: HTMLCanvasElement) {
      const aspect = canvas.clientWidth / Math.max(1, canvas.clientHeight);
      const halfH = FRUSTUM_HEIGHT / 2;
      const halfW = halfH * aspect;
      this.camera = new THREE.OrthographicCamera(-halfW, halfW, halfH, -halfH, -FAR, FAR);
      this.camera.up.set(0, 0, 1); // CAD convention: z-up
      this.camera.position.set(10, -10, 7); // isometric-ish start
      this.camera.lookAt(0, 0, 0);

      this.controls = new OrbitControls(this.camera, canvas);
      this.controls.enableDamping = false; // crisp stops
      this.controls.zoomToCursor = true;
      this.controls.screenSpacePanning = true;
      this.controls.target.set(0, 0, 0);
      this.controls.update();
      this.controls.addEventListener('change', () => {
        for (const cb of this.listeners) cb();
      });
    }

    /** Register a callback fired whenever the user moves the camera. */
    onChange(cb: () => void): void {
      this.listeners.push(cb);
    }

    /** Recompute the ortho frustum for a new canvas size (keeps vertical extent, adjusts width by aspect). */
    resize(w: number, h: number): void {
      const aspect = w / Math.max(1, h);
      const halfH = FRUSTUM_HEIGHT / 2;
      this.camera.left = -halfH * aspect;
      this.camera.right = halfH * aspect;
      this.camera.top = halfH;
      this.camera.bottom = -halfH;
      this.camera.updateProjectionMatrix();
    }

    dispose(): void {
      this.controls.dispose();
      this.listeners.length = 0;
    }
  }
  ```

- [ ] **Step 4: Write `src/app/viewport/renderer.ts`**

  Full file contents:

  ```ts
  import * as THREE from 'three';
  import { CameraState } from './cameraState';

  /**
   * Owns the WebGLRenderer, Scene, ground grid, and lights. Render-on-demand:
   * a frame is drawn only when requestRender() is called (coalesced via a
   * requestAnimationFrame flag), on camera change, or on container resize.
   * There is intentionally NO free-running render loop.
   */
  export class Viewport {
    readonly cameraState: CameraState;
    private renderer: THREE.WebGLRenderer;
    private scene: THREE.Scene;
    private resizeObserver: ResizeObserver;
    private renderQueued = false;
    private disposed = false;

    constructor(container: HTMLElement) {
      this.renderer = new THREE.WebGLRenderer({ antialias: true });
      this.renderer.setPixelRatio(window.devicePixelRatio);
      this.renderer.setSize(container.clientWidth, container.clientHeight);
      container.appendChild(this.renderer.domElement);

      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color(0xf0f0f0);

      // GridHelper lies in the XZ plane by default; rotate into XY so the
      // ground plane matches our z-up convention.
      const grid = new THREE.GridHelper(40, 40, 0x888888, 0xcccccc);
      grid.rotateX(Math.PI / 2);
      this.scene.add(grid);

      // Hemisphere "sky" direction is its position vector; point it up +z.
      const hemi = new THREE.HemisphereLight(0xffffff, 0x665544, 1.0);
      hemi.position.set(0, 0, 1);
      this.scene.add(hemi);

      const dir = new THREE.DirectionalLight(0xffffff, 1.5);
      dir.position.set(5, -8, 12);
      this.scene.add(dir);

      this.cameraState = new CameraState(this.renderer.domElement);
      this.cameraState.onChange(() => this.requestRender());

      this.resizeObserver = new ResizeObserver(() => {
        const w = container.clientWidth;
        const h = container.clientHeight;
        if (w === 0 || h === 0) return;
        this.renderer.setSize(w, h);
        this.cameraState.resize(w, h);
        this.requestRender();
      });
      this.resizeObserver.observe(container);

      this.requestRender();
    }

    add(obj: THREE.Object3D): void {
      this.scene.add(obj);
      this.requestRender();
    }

    /** Coalesces multiple calls in one frame into a single render. */
    requestRender(): void {
      if (this.renderQueued || this.disposed) return;
      this.renderQueued = true;
      requestAnimationFrame(() => {
        this.renderQueued = false;
        if (this.disposed) return;
        this.renderer.render(this.scene, this.cameraState.camera);
      });
    }

    dispose(): void {
      this.disposed = true;
      this.resizeObserver.disconnect();
      this.cameraState.dispose();
      this.renderer.dispose();
      this.renderer.domElement.remove();
      this.overlay.remove();
    }
  }
  ```

- [ ] **Step 4b: Add the 2D overlay canvas stub** (spec §6: all text/glyphs/rubber bands render on an HTML canvas layered over WebGL — M2+ draws on it; M1 only establishes the layer so the seam exists)

  Add to `Viewport` (the `dispose()` body above already includes `this.overlay.remove()`):

  ```ts
    /** 2D overlay for future sketch glyphs/dimension text. Transparent, never intercepts input. */
    readonly overlay: HTMLCanvasElement;
  ```

  In the constructor, after `container.appendChild(this.renderer.domElement);`:

  ```ts
      this.overlay = document.createElement('canvas');
      this.overlay.style.position = 'absolute';
      this.overlay.style.inset = '0';
      this.overlay.style.pointerEvents = 'none';
      container.style.position = 'relative';
      container.appendChild(this.overlay);
  ```

  And inside the `ResizeObserver` callback, after `this.cameraState.resize(w, h);`:

  ```ts
        this.overlay.width = w * window.devicePixelRatio;
        this.overlay.height = h * window.devicePixelRatio;
  ```

  Run: `npx tsc --noEmit` — expected: silent, exit 0.

- [ ] **Step 5: Replace the Vite placeholder — `index.html`, `src/style.css`, `src/main.ts`**

  `index.html` (full replacement at repo root):

  ```html
  <!doctype html>
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>custom-cad</title>
    </head>
    <body>
      <div id="app"></div>
      <script type="module" src="/src/main.ts"></script>
    </body>
  </html>
  ```

  `src/style.css` (full file — full-viewport canvas, no margins, no scrollbars):

  ```css
  html,
  body {
    margin: 0;
    padding: 0;
    width: 100%;
    height: 100%;
    overflow: hidden;
  }

  #app {
    width: 100vw;
    height: 100vh;
  }

  #app canvas {
    display: block;
  }
  ```

  `src/main.ts` (full replacement — note: imports `Viewport` only, never `three`; the import-boundary check in `npm run check` enforces this):

  ```ts
  import './style.css';
  import { Viewport } from './app/viewport/renderer';

  const container = document.querySelector<HTMLDivElement>('#app');
  if (!container) {
    throw new Error('missing #app container in index.html');
  }

  new Viewport(container);
  ```

  Remove leftover Vite template files if they exist (they reference DOM the new `index.html` no longer has):

  ```bash
  cd /home/svankina/src/custom_cad
  rm -f src/counter.ts src/typescript.svg public/vite.svg
  ```

- [ ] **Step 6: Type-check**

  ```bash
  cd /home/svankina/src/custom_cad && npx tsc --noEmit
  ```

  Expected: exits 0 with no output. If it complains about `zoomToCursor` not existing on `OrbitControls`, your `@types/three` is older than your `three` — fix with `npm install -D @types/three@latest` and re-run.

- [ ] **Step 7: Manual verification in the browser**

  ```bash
  cd /home/svankina/src/custom_cad && npm run dev
  ```

  Open http://localhost:5173 and verify ALL of the following:

  1. A light-grey page filling the entire window — no white margin strip, no scrollbars.
  2. A 40x40 grid visible as the **ground plane**, seen from an oblique angle above (camera at (10,-10,7) looking at the origin). If the grid appears as a vertical wall, the `rotateX(Math.PI / 2)` is missing.
  3. **Left-drag** orbits around the origin; the horizon tilts but the view never rolls sideways (z stays up).
  4. **Right-drag** pans the view (grid translates with the cursor, screen-space).
  5. **Mouse wheel** zooms, and zooming-in moves **toward the cursor position** (put the cursor over a grid corner away from screen center, scroll in — that corner should stay roughly under the cursor, not slide toward center). No perspective distortion at any zoom (orthographic).
  6. Releasing the mouse stops motion **instantly** — no coast/glide (damping is off).
  7. Resize the browser window: the canvas refills the window and the grid squares stay square (no stretching) — `ResizeObserver` -> `cameraState.resize` working.
  8. Open devtools console: no errors. (Optional sanity check on render-on-demand: in the Performance tab, record a few seconds while NOT touching the mouse — there should be no per-frame GPU/render activity; activity appears only while orbiting.)

  Stop the dev server with Ctrl-C when done.

- [ ] **Step 8: Run the full check (including the three.js import boundary)**

  ```bash
  cd /home/svankina/src/custom_cad && npm run check
  ```

  Expected: `tsc --noEmit` passes, vitest reports all existing kernel tests passing, and `scripts/check-three-imports.sh` finds no violations (the only `from 'three...'` imports live in `src/app/viewport/cameraState.ts` and `src/app/viewport/renderer.ts`). Exit code 0.

- [ ] **Step 9: Commit**

  ```bash
  cd /home/svankina/src/custom_cad
  git add src/app/viewport/cameraState.ts src/app/viewport/renderer.ts src/main.ts src/style.css index.html package.json package-lock.json
  git rm --ignore-unmatch src/counter.ts src/typescript.svg public/vite.svg
  git commit -m "feat(viewport): ortho z-up viewport shell with OrbitControls facade and render-on-demand

  Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
  ```

---

### Task 9: Scene sync + M1 box demo (`sceneSync.ts`, `main.ts`, kernel acceptance test)

**Files:**
- Create: `src/app/viewport/sceneSync.ts`
- Create: `test/integration/m1.test.ts`
- Modify: `src/main.ts`

This task closes M1: the kernel pipeline (`rectProfile → extrude → tessellate`) gets one end-to-end acceptance test, and its `RenderData` output gets converted to three.js objects and drawn in the viewport. `renderDataToObjects` itself needs a DOM/WebGL context, so it is **not** unit-tested; the pure-data half of the pipeline is tested exhaustively instead, and the three.js half is verified manually.

- [ ] **Step 1: Write the M1 kernel acceptance test** — the full pipeline on the exact M1 demo geometry: a 4×3 rectangle on `XY_PLANE` extruded 5 units. Span-unit conventions used below (per the render contract): `faceSpans` `start`/`count` are measured in **entries of `triIndex`** (always multiples of 3); `edgeSpans` `start`/`count` are measured in **vertex indices** into `edges.positions` (count = 2 for a line). Create `test/integration/m1.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { XY_PLANE } from '../../src/kernel/vec';
import { rectProfile } from '../../src/kernel/profile';
import { extrude } from '../../src/kernel/extrude';
import { validateSolid, type FaceGen } from '../../src/kernel/brep';
import { tessellate, type RenderData } from '../../src/kernel/tess';

type Mesh = RenderData['mesh'];

function vtx(positions: Float32Array, vi: number): [number, number, number] {
  // `!` for noUncheckedIndexedAccess; `+ 0` normalizes -0 (Float32Array preserves -0,
  // and vitest's toEqual uses Object.is, where -0 !== 0).
  return [positions[3 * vi]! + 0, positions[3 * vi + 1]! + 0, positions[3 * vi + 2]! + 0];
}

/**
 * Watertightness check: per-face vertex duplication is expected (analytic normals
 * differ per face), so merge vertices by EXACT position key (box coords 0,3,4,5 are
 * exact in f32 -- vertices are shared by construction upstream, never re-derived),
 * then require every undirected triangle edge to be used by exactly 2 triangles.
 */
function checkWatertight(mesh: Mesh): { mergedVerts: number; uniqueEdges: number } {
  const canon = new Map<string, number>();
  const canonOf = (vi: number): number => {
    const [x, y, z] = vtx(mesh.positions, vi);
    const key = `${x},${y},${z}`;
    let c = canon.get(key);
    if (c === undefined) {
      c = canon.size;
      canon.set(key, c);
    }
    return c;
  };
  const edgeUse = new Map<string, number>();
  for (let t = 0; t < mesh.triIndex.length; t += 3) {
    const tri = [
      canonOf(mesh.triIndex[t]!),
      canonOf(mesh.triIndex[t + 1]!),
      canonOf(mesh.triIndex[t + 2]!),
    ];
    for (let i = 0; i < 3; i++) {
      const a = tri[i]!;
      const b = tri[(i + 1) % 3]!;
      expect(a, 'degenerate triangle edge (repeated vertex)').not.toBe(b);
      const key = a < b ? `${a}|${b}` : `${b}|${a}`;
      edgeUse.set(key, (edgeUse.get(key) ?? 0) + 1);
    }
  }
  for (const [key, uses] of edgeUse) {
    expect(uses, `mesh edge ${key} must be shared by exactly 2 triangles`).toBe(2);
  }
  return { mergedVerts: canon.size, uniqueEdges: edgeUse.size };
}

/** Outward unit normal expected for each face of the 4x3x5 box, keyed by gen tag.
 * Sides: CCW loop + extrusion along +z gives outward = segDir x z. */
function expectedFaceNormal(gen: FaceGen): [number, number, number] {
  if (gen.role === 'cap') return gen.end === 'start' ? [0, 0, -1] : [0, 0, 1];
  switch (gen.curve) {
    case 'rect.s0': return [0, -1, 0]; // (0,0)->(4,0), dir +x
    case 'rect.s1': return [1, 0, 0];  // (4,0)->(4,3), dir +y
    case 'rect.s2': return [0, 1, 0];  // (4,3)->(0,3), dir -x
    case 'rect.s3': return [-1, 0, 0]; // (0,3)->(0,0), dir -y
    default: throw new Error(`unexpected side curve ${gen.curve}`);
  }
}

describe('M1 acceptance: rectProfile -> extrude -> validateSolid -> tessellate', () => {
  const profile = rectProfile(XY_PLANE, 4, 3);
  const result = extrude(profile, { dist: 5 });

  it('extrudes to a valid solid with prism table sizes (n=4)', () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const solid = result.value;
    expect(validateSolid(solid)).toEqual([]);
    expect(solid.vertices.size).toBe(8);   // 2n
    expect(solid.edges.size).toBe(12);     // 3n
    expect(solid.faces.size).toBe(6);      // n+2
    expect(solid.loops.size).toBe(6);      // one loop per face in M1
    expect(solid.halfEdges.size).toBe(24); // 6n
  });

  it('tessellates: 12 tris, 6 contiguous face spans, correct bbox and gen tags', () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const rd = tessellate(result.value, 0.1);

    // 6 quad faces x 2 tris = 12 triangles = 36 triIndex entries.
    expect(rd.mesh.triIndex.length).toBe(36);
    // 6 faces x 4 loop vertices, duplicated per face for analytic normals.
    expect(rd.mesh.positions.length).toBe(72);
    expect(rd.mesh.normals.length).toBe(72);

    // Face spans partition triIndex contiguously (units: triIndex entries).
    expect(rd.mesh.faceSpans.length).toBe(6);
    const starts = rd.mesh.faceSpans.map((s) => s.start).sort((a, b) => a - b);
    expect(starts).toEqual([0, 6, 12, 18, 24, 30]);
    for (const span of rd.mesh.faceSpans) expect(span.count).toBe(6);

    // Gen tags: exactly one start cap, one end cap, four sides covering s0..s3.
    const caps = rd.mesh.faceSpans.filter((s) => s.gen.role === 'cap');
    const sides = rd.mesh.faceSpans.filter((s) => s.gen.role === 'side');
    expect(caps.map((s) => (s.gen.role === 'cap' ? s.gen.end : '')).sort()).toEqual(['end', 'start']);
    expect(sides.map((s) => (s.gen.role === 'side' ? s.gen.curve : '')).sort()).toEqual([
      'rect.s0', 'rect.s1', 'rect.s2', 'rect.s3',
    ]);

    // Bounding box of the mesh: [0,4] x [0,3] x [0,5].
    const min = [Infinity, Infinity, Infinity];
    const max = [-Infinity, -Infinity, -Infinity];
    for (let i = 0; i < rd.mesh.positions.length; i += 3) {
      for (let k = 0; k < 3; k++) {
        min[k] = Math.min(min[k]!, rd.mesh.positions[i + k]!);
        max[k] = Math.max(max[k]!, rd.mesh.positions[i + k]!);
      }
    }
    expect(min).toEqual([0, 0, 0]);
    expect(max).toEqual([4, 3, 5]);
  });

  it('has analytic outward normals per face and CCW triangle winding vs normal', () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const rd = tessellate(result.value, 0.1);
    for (const span of rd.mesh.faceSpans) {
      const [nx, ny, nz] = expectedFaceNormal(span.gen);
      for (let i = span.start; i < span.start + span.count; i++) {
        const vi = rd.mesh.triIndex[i]!;
        expect(vtx(rd.mesh.normals, vi)).toEqual([nx, ny, nz]);
      }
      // Geometric winding agrees with the supplied normal for every triangle.
      for (let t = span.start; t < span.start + span.count; t += 3) {
        const p0 = vtx(rd.mesh.positions, rd.mesh.triIndex[t]!);
        const p1 = vtx(rd.mesh.positions, rd.mesh.triIndex[t + 1]!);
        const p2 = vtx(rd.mesh.positions, rd.mesh.triIndex[t + 2]!);
        const e1: [number, number, number] = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]];
        const e2: [number, number, number] = [p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]];
        const gn: [number, number, number] = [
          e1[1] * e2[2] - e1[2] * e2[1],
          e1[2] * e2[0] - e1[0] * e2[2],
          e1[0] * e2[1] - e1[1] * e2[0],
        ];
        expect(gn[0] * nx + gn[1] * ny + gn[2] * nz).toBeGreaterThan(0);
      }
    }
  });

  it('is watertight: merged box has 8 vertices, 18 edges, every edge shared by 2 tris', () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const rd = tessellate(result.value, 0.1);
    const { mergedVerts, uniqueEdges } = checkWatertight(rd.mesh);
    expect(mergedVerts).toBe(8);
    expect(uniqueEdges).toBe(18); // closed triangulated surface: E = 3F/2 = 3*12/2
    // Euler-Poincare on the merged mesh: V - E + F = 8 - 18 + 12 = 2.
    expect(mergedVerts - uniqueEdges + 12).toBe(2);
  });

  it('emits 12 edge segments with correct gen tags and lengths', () => {
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    const rd = tessellate(result.value, 0.1);
    expect(rd.edges.edgeSpans.length).toBe(12);
    expect(rd.edges.positions.length).toBe(72); // 12 segments x 2 verts x 3 floats
    const starts = rd.edges.edgeSpans.map((s) => s.start).sort((a, b) => a - b);
    expect(starts).toEqual([0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]);
    for (const span of rd.edges.edgeSpans) expect(span.count).toBe(2);

    const capLen: Record<string, number> = {
      'rect.s0': 4, 'rect.s1': 3, 'rect.s2': 4, 'rect.s3': 3,
    };
    let capStart = 0;
    let capEnd = 0;
    let side = 0;
    const sideVerts: string[] = [];
    for (const span of rd.edges.edgeSpans) {
      const a = vtx(rd.edges.positions, span.start);
      const b = vtx(rd.edges.positions, span.start + 1);
      const d: [number, number, number] = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const len = Math.hypot(d[0], d[1], d[2]);
      if (span.gen.role === 'capEdge') {
        if (span.gen.end === 'start') capStart++;
        else capEnd++;
        expect(len).toBeCloseTo(capLen[span.gen.curve]!, 12);
        // cap edges are horizontal
        expect(d[2]).toBe(0);
      } else {
        side++;
        sideVerts.push(span.gen.vertex);
        // vertical edges: pure z, length 5
        expect(d[0]).toBe(0);
        expect(d[1]).toBe(0);
        expect(Math.abs(d[2])).toBe(5);
      }
    }
    expect(capStart).toBe(4);
    expect(capEnd).toBe(4);
    expect(side).toBe(4);
    expect(sideVerts.sort()).toEqual(['rect.s0:a', 'rect.s1:a', 'rect.s2:a', 'rect.s3:a']);
  });
});
```

- [ ] **Step 2: Run the acceptance test** — `npx vitest run test/integration/m1.test.ts`. This test exercises only already-implemented kernel code, so the expected result is **PASS** (`Test Files  1 passed (1)`, `Tests  5 passed (5)`). It is an acceptance gate, not a red-green driver: **if any assertion fails, the bug is in the kernel module that owns that assertion** (`extrude.ts`, `tess.ts`, `profile.ts`) — fix it there and re-run; do not change the expected values in this file (they are computed by hand for a 4×3×5 box).

- [ ] **Step 3: Create `src/app/viewport/sceneSync.ts`** — converts `RenderData` typed arrays into three.js objects. This is one of the only three files allowed to import three.js. Full file contents:

```ts
import * as THREE from 'three';
import type { RenderData } from '../../kernel/tess';

/**
 * Convert kernel RenderData into three.js renderables.
 * - mesh: indexed BufferGeometry built directly from the kernel's typed arrays
 *   (no copies); normals are the kernel's analytic per-face normals, so no
 *   computeVertexNormals and no flatShading.
 * - polygonOffset pushes face fragments slightly back in depth so the
 *   coincident hairline edges win the depth test at all angles (no z-fighting).
 * - edges: non-indexed LineSegments, two vertices per kernel Edge.
 */
export function renderDataToObjects(rd: RenderData): {
  mesh: THREE.Mesh;
  edges: THREE.LineSegments;
} {
  const meshGeo = new THREE.BufferGeometry();
  meshGeo.setAttribute('position', new THREE.BufferAttribute(rd.mesh.positions, 3));
  meshGeo.setAttribute('normal', new THREE.BufferAttribute(rd.mesh.normals, 3));
  meshGeo.setIndex(new THREE.BufferAttribute(rd.mesh.triIndex, 1));

  const meshMat = new THREE.MeshLambertMaterial({
    color: 0xb0b8c4,
    polygonOffset: true,
    polygonOffsetFactor: 1,
    polygonOffsetUnits: 1,
  });
  const mesh = new THREE.Mesh(meshGeo, meshMat);

  const edgeGeo = new THREE.BufferGeometry();
  edgeGeo.setAttribute('position', new THREE.BufferAttribute(rd.edges.positions, 3));
  const edgeMat = new THREE.LineBasicMaterial({ color: 0x111111 });
  const edges = new THREE.LineSegments(edgeGeo, edgeMat);

  return { mesh, edges };
}
```

- [ ] **Step 4: Verify typecheck and the three.js import guard** — run `npx tsc --noEmit && bash scripts/check-three-imports.sh`. Expected: both succeed (exit 0, no violations reported) — `sceneSync.ts` lives under `src/app/viewport/`, which is the allowed location.

- [ ] **Step 5: Extend `src/main.ts`** — build the demo solid and put it in the viewport. Replace the file with the contents below.

```ts
import './style.css';
import { Viewport } from './app/viewport/renderer';
import { renderDataToObjects } from './app/viewport/sceneSync';
import { XY_PLANE } from './kernel/vec';
import { rectProfile } from './kernel/profile';
import { extrude } from './kernel/extrude';
import { tessellate } from './kernel/tess';

function main(): void {
  const container = document.getElementById('app');
  if (!container) {
    console.error('main: #app container not found in index.html');
    return;
  }
  const viewport = new Viewport(container);

  // M1 demo: hardcoded 4x3 rectangle on the XY plane, extruded 5 units up.
  const profile = rectProfile(XY_PLANE, 4, 3);
  const result = extrude(profile, { dist: 5 });
  if (!result.ok) {
    console.error(
      `extrude failed [${result.error.code}]: ${result.error.msg}`,
      result.error.entityIds,
    );
    return;
  }

  const renderData = tessellate(result.value, 0.1);
  const { mesh, edges } = renderDataToObjects(renderData);
  viewport.add(mesh);
  viewport.add(edges);
  viewport.requestRender();
}

main();
```

- [ ] **Step 6: Manual verification — THE M1 exit** — run `npm run dev`, open the printed URL (e.g. `http://localhost:5173/`), and verify ALL of the following:
  1. A **shaded grey prism** (color is a light blue-grey, `0xb0b8c4`) is visible: 4 units along model X, 3 along model Y, 5 along model Z. The 4×3 face is the base on the grid plane. Note: model "up" is +Z; if the prism appears lying sideways relative to the grid, the `GridHelper` orientation in `renderer.ts` doesn't match model +Z (three's GridHelper defaults to the XZ plane) — fix it in `renderer.ts` (e.g. `grid.rotation.x = Math.PI / 2` to put it in XY), not in this task's files.
  2. **Crisp black hairline edges** on all 12 edges of the box, including the silhouette and the edges crossing in front of faces.
  3. **No z-fighting**: orbit slowly through many angles, especially grazing angles where an edge lies almost in a face plane — edges must stay solid black lines, never a flickering stipple of grey/black pixels. If they stipple, the `polygonOffset` settings on the mesh material are not taking effect.
  4. **Orbit / pan / zoom feel**: left-drag orbits, zoom goes to the cursor, panning is screen-space; motion is smooth with no visible stutter (effectively 60fps for a 12-triangle scene).
  5. **Render-on-demand**: when the mouse is idle, the dev-tools Performance tab (or a glance at GPU/CPU usage) shows no continuous re-render; frames are produced only during interaction.
  6. The browser **console shows no errors** (in particular, no `extrude failed` message).

- [ ] **Step 7: Full gate** — run `npm run check`. Expected: `tsc --noEmit` clean, all vitest suites pass (including `test/integration/m1.test.ts`), and `scripts/check-three-imports.sh` reports no violations.

- [ ] **Step 8: Commit**
  ```bash
  git add src/app/viewport/sceneSync.ts src/main.ts test/integration/m1.test.ts
  git commit -m "feat(app): wire kernel RenderData into three.js scene, complete M1 box demo

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
  ```

- [ ] **Step 9: M1 exit checklist** — confirm each exit criterion from spec §10 (M1 — "A box I can orbit") against where it was verified:
  - **Shaded prism with hairline edges** → Step 6, items 1–2 (visual), backed by Step 3's polygonOffset material + black `LineBasicMaterial`.
  - **60fps orbit** → Step 6, item 4 (smooth orbit), item 5 (render-on-demand, no busy loop).
  - **`validateSolid` green** → `test/integration/m1.test.ts`, first `it` block: `expect(validateSolid(solid)).toEqual([])`, plus prism table sizes V=8/E=12/F=6/HE=24.
  - **Render contract locked** → `test/integration/m1.test.ts` asserts the full `RenderData` shape end-to-end (faceSpans in triIndex entries with starts `[0,6,...,30]`, edgeSpans in vertex indices with count 2, analytic normals, watertightness 8/18/2-shared), and `sceneSync.ts` consumes that exact shape unreshaped.
  - **`gen` tags present** → `test/integration/m1.test.ts` asserts cap `start`/`end`, side curves `rect.s0..s3`, capEdge × 8, and sideEdge vertices `rect.s0:a..rect.s3:a`.
  - **Real extrude + real ear-clip tessellator on a hardcoded rectangle through `sceneSync`** → `src/main.ts` (Step 5) calls `rectProfile → extrude → tessellate → renderDataToObjects` with no mock layers.