# REL-02 — recorded product and hosting handoff

User scope: public repository submission, probable hosted website, local product and
evidence package. Branch `lane/REL-02-hosted-replay`; base int-b `ed1f7fd`.

## Delivered

- `scripts/hosted_app.py`: production console and existing read-only API on one origin;
  validates pinned inputs and recorded schedule acceptance before serving; `/healthz`.
- `scripts/prepare_hosted_replay.py`: hash/acceptance-checked extraction of the small
  two-policy demo sample, with overwrite protection.
- `data/fixtures/hosted_replay`: both accepted run records, manifests, genuine timing,
  acceptance and per-file hashes. No caches, hidden truth dump or unfinished benchmark.
- `Dockerfile`, `.dockerignore`, `docs/hosted-replay.md`: container deployment path;
  excludes credentials, dependencies, caches and bulk raw inputs from build context.
- README starts with recorded replay, avoiding a simulation wait for reviewers.

## Checks actually completed

- Existing production API (8011): both runs, their manifests and pinned historical
  context returned successfully; 20 seeded sources / 0 fill, 1,494 windows and 46 inputs.
- New single-origin server (4321): `/healthz`, `/api/runs`,
  `/api/project/historical-context`, `/` and both referenced JS/CSS assets returned 200.
  It used the actual repository sample, existing production frontend build and API.
- Ruff check/fix and format completed for the two delivery scripts.
- Separate portable ZIP was built under `AETHER-deliverables`, with exact committed
  int-b source, accepted demo records and exports. Extracted file hashes/sizes matched;
  both exports passed `aether.cli verify-export` against extracted source, 46 inputs each.

## Limits and integration

### User-requested current-data extension

Connected public CelesTrak GP and NASA CMR endpoints through the existing URL/DNS
policy and timeout constants. `scripts/live_context.py` saves original response
bytes and hashes locally, stops after provider errors, caches upstream refreshes
for 2 h and preserves original timestamps. No Carbon Mapper or authenticated
granule download is attempted. `scripts/serve_hosted.sh` enables the refresh
worker only with AETHER_ENABLE_LIVE=1. The scientific aether package is unchanged.

`/?view=live` shows actual Landsat 8/9 provider epochs, SGP4/Skyfield subpoints,
NASA catalogue observation/update times, URLs and response hashes. A schematic
coordinate plot has an equivalent table. UI distinguishes modelled positions,
published metadata and simulated planning. The newest EMIT observation returned
was 2025-09-22; a fresh query does not make that observation current.

Actual provider requests succeeded and both positions propagated without errors.
Production TypeScript/Vite build succeeded. React review: hooks are unconditional,
initial request is abortable, failed/stale/unavailable states are explicit, values
render as text and the plot has a table alternative. No new visual browser/Axe
result is claimed.

Docker CLI is installed, but access to the daemon socket is denied. The image build
has not been run; native execution verifies the shared ASGI path, not Docker layers.
No new browser/Axe result is claimed because no browser surface was available.
No remote publication, repository visibility change or hosting account mutation occurred.
The recorded comparison is intentionally unavailable until completed evaluator artifacts
are supplied. No scientific gate is bypassed and no adaptive superiority is claimed.

Changes are isolated from Claude's active work. Integrate this branch's delivery commit
into the final submission branch; reconcile the Work_Plan note rather than replacing
newer scientific or governance edits. Rebuild the portable bundle from the final revision
after all accepted integration commits land. The earlier bundle is a fixed demo snapshot.
