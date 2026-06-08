# @efloud/tokens

Single source of truth for EFloud design tokens, shared across the monorepo's
front-end surfaces. Promoted from `u2algo-site/brand-kit/css/design-tokens.ts`
in PR #1.

## Exports

| Import | What |
|--------|------|
| `@efloud/tokens` | Raw JS-land constants: `colors`, `spacing`, `radius`, `typography`, `effects`, `tw`. Use for inline styles, canvas/chart theming, RN `StyleSheet`. |
| `@efloud/tokens/tailwind` | A **collision-safe** Tailwind preset (default export). Add to `presets: [...]` in a `tailwind.config.ts`. |

## Consumers

- **`frontend/`** (operator dashboard) — wired now. `tailwind.config.ts` adds the
  preset; `next.config.ts` lists the package under `transpilePackages` so the raw
  `.ts` source is transpiled by Next at build time. The Docker build
  (`Dockerfile` stage 1, "frontend-builder") installs the root npm workspace so the
  package resolves inside the image.
- **`u2algo-site/web`** — deferred to PR #6. `u2algo-site` is currently its own npm
  workspace root (`u2algo-site/package.json` → `workspaces: ["web"]`), and npm does
  not support nested workspaces. Folding it into the root workspace (or wiring a
  `file:` dependency) happens during the Next.js App Router migration in PR #6, where
  the `u2algo-site` deploy is reworked anyway. **Do not add `u2algo-site` to the root
  `workspaces` before then** — it would break the live Railway deploy.
- **`mobile/`** — deferred to PR #19 (NativeWind preset).

## Why no compiled `dist/`?

Consumers transpile the source directly (Next `transpilePackages`, jiti for the
Tailwind config, RN/Metro for mobile). If an external/published consumer ever needs
compiled output, add a `tsup`/`tsc` build step and point `main`/`types`/`exports` at
`dist/`. Until then, raw TS keeps the package zero-build.

## Invariant

The original `u2algo-site/brand-kit/css/design-tokens.ts` is retained until PR #6 so
the existing marketing assets keep resolving. This package is the canonical copy; the
brand-kit copy is removed when `u2algo-site/web` adopts `@efloud/tokens`.
