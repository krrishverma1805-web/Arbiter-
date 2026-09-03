# Hosting the cockpit

## The public demo

**https://arbiter-cockpit.vercel.app** — the real Next.js cockpit serving a
frozen snapshot of one `arbiter run` (`f7e810ba`, 1,672 records, the
investigation agent pointed at `gpt-4o`). No backend: `src/app/api/v1/**`
route handlers read `src/lib/demo/*.json`, and `/api/v1/runs/{id}/stream`
replays the captured event sequence as SSE so `/live` animates the real
investigation. `POST /v1/runs` points every "reconcile" at the seeded run;
resolve is acknowledged but read-only.

Set `ARBITER_API_URL` on the deployment to point the cockpit at a real
backend instead — then the route handlers are bypassed (`next.config.mjs`)
and everything is live.

## Redeploying the demo

The Vercel project pulls `web/` from GitHub at build time (the repo's Vercel
GitHub app isn't linked, so a direct file deploy is used):

- install: `curl -sfL https://codeload.github.com/krrishverma1805-web/Arbiter-/tar.gz/refs/heads/main | tar xz --strip-components=2 Arbiter--main/web && pnpm install --frozen-lockfile`
- build: `pnpm build`

Push to `main`, then trigger a new production deploy. To make it automatic,
link the repo in the Vercel project's Git settings (root directory `web`).

## Refreshing the snapshot

`scripts/snapshot.sh` (against a live `arbiter-api`) regenerates
`web/src/lib/demo/*.json`. The current snapshot is run `f7e810ba` captured
2026-09-03 with the OpenAI provider.

## The full stack

`make up` from the repo root — FastAPI on `:8000`, cockpit on `:3000`.
Helm chart in `deploy/helm/arbiter/` for Kubernetes.
