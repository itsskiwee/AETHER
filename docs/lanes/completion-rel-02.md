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
