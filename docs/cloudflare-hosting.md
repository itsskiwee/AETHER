# Cloudflare and GitHub hosting

AETHER is deployed as the `aether-replay-hosted` Cloudflare Worker with Static Assets.
Workers Builds connects the Worker to the GitHub repository and deploys commits from
the configured production branch. The React console, globe, accepted replay data,
evidence exports, and read-only API snapshots ship together. The Worker does not run
the planner or simulator, and this deployment does not use Containers or a database.

Open the [hosted globe](https://aether-replay-hosted.ryan-rawal43.workers.dev/?view=globe).

## GitHub build settings

Connect the existing Worker from **Workers & Pages → aether-replay-hosted → Settings
→ Builds**. Select `itsskiwee/AETHER` and the `lane/REL-02-cloudflare-github` branch. Set:

| Setting | Value |
|---|---|
| Root directory | `/` |
| Build command | `npm run cloudflare:build` |
| Deploy command | `npm run deploy:cloudflare` |

Cloudflare's build environment installs the root Node dependencies. The build command
installs the frontend and backend build dependencies, refreshes public provider context
through the policy-checked script, builds the frontend, and exports read-only API
snapshots from `scripts.hosted_app`. If a public provider is unavailable, the offline
replay still builds and the context endpoint records the unavailable state.

## Data and refresh behavior

The console reads accepted replay artifacts from `data/fixtures/hosted_replay`. API
responses are generated from the same FastAPI read-only routes used for local hosting.
The Worker serves those snapshots as static assets; it does not recompute the
simulation, planner, or benchmark during a request. The globe view is available at
`/?view=globe` and uses its checked-in data file under `frontend/public/globe/`.

The satellite context is captured during each GitHub build. A push triggers a fresh
build and deployment; the public feeds do not refresh in the background. If a feed
fails during the build, the replay remains available and the context view labels the
provider state as unavailable. Satellite positions are estimates from published
orbital elements, not telemetry. Catalogue records are metadata, not real-time methane
measurements.

The public replay needs no runtime Cloudflare or Supabase secrets. Workers Builds uses
the GitHub and build credentials configured in the Cloudflare dashboard. The current
`workers.dev` address is shown in the Worker dashboard. Static assets use the Worker
Assets binding; no Durable Objects, Containers, or database bindings are configured.

## Build and deploy locally

Install the backend and frontend dependencies using the steps in the repository setup
guide. Then refresh provider context and publish:

```powershell
python scripts/live_context.py --output "$env:TEMP\aether-live-context.json"
$env:AETHER_LIVE_CONTEXT = "$env:TEMP\aether-live-context.json"
npm --prefix frontend ci
npm run build:cloudflare
npm run deploy:cloudflare
```

The public provider updater follows `aether.netpolicy`, validates public destinations,
and uses the configured network timeouts. No raw provider response is published by the
site; the API snapshot retains retrieval times, response hashes, and derived context.
