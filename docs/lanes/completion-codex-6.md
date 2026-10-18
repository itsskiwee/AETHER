# Codex 6 / L9 completion handoff — 18 October 2026

Assignment: original Codex-6 L9 interface maps to the completion prompt's Codex-4
console/API/documentation role. Branch `lane/UI-08-completion`, worktree
`/home/itsskiweee/Projects/AETHER-codex6`, based on main's C1-01 ownership/interface commit.

## Work in progress, not acceptance evidence

Added read-only run manifest, run-pinned historical context, and separate measured
whole-run/comparison timing routes; console source lineage, historical context,
manifest inspection and measured timing panels; API and browser regression tests.
Current changes touch `backend/aether/api/__init__.py`,
`backend/tests/unit/test_api.py`, `frontend/src/{App,ArtifactEvidence}.tsx`,
`frontend/src/types.ts`, `frontend/e2e/console.spec.ts`, and
`frontend/playwright.config.ts`.

Another session edited the same API, ArtifactEvidence and types files concurrently.
Its changes include a project historical-context route, explicit synthetic-only
responses and stricter display validation. These changes were preserved. Source
ownership needs resolving before a final commit; the user was asked through the
text clarification tool. No merge, push, publication, or shared-contract edit occurred.

## Checks and remaining concrete issues

- Focused API/truth-isolation/security tests passed on the first implementation.
  That result predates the concurrent API/component changes and does not certify
  the current combined files.
- Initial production build passed before the concurrent edits.
- Current scoped Ruff check and `git diff --check` pass.
- Full offline pytest and Playwright suites were launched; results were not final
  when concurrent edits were discovered. Neither is recorded as a passing gate.
- The existing unpinned-context test expects 404; the concurrent implementation
  now returns an explicit 200 synthetic-only object. Reconcile the test with that
  documented interface rather than showing the project's dataset for an old run.
- New historical browser fixture and selectors describe the first implementation;
  update them to the combined component's `status: pinned`, full InputDatasetRef,
  native ID/source fields, table caption and summary copy before rerunning.
- Confirm the API's project dataset reference works with the final ingestion and
  DATA-02 contract. The proposal remains in `docs/dataset-interface.md`.
- Add explicit family/competitor coverage checks against authoritative protocol
  and evaluator artifacts; avoid client-side scientific replacements.
- `AETHER_TEST_PORT` is available to isolate browser verification from other
  sessions; default remains 4173. `frontend/node_modules` is an untracked symlink
  to the original checkout's installed dependencies; do not commit it.

## Dependencies and finish criteria

Actual pinned-data replay awaits ingestion's normalized dataset/manifest and
Claude-1's additive input_dataset contract/runner wiring. Final claims, all-family
results, timing schema and lock/holdout status await their scientific/integration
owners. No real plume evidence, scientific acceptance or holdout completion is
claimed here. Existing demo artifacts remain untouched.

After ownership is resolved, estimate 1–2 hours for reconciling this small UI/API
patch and focused verification, plus a separate integrated data-backed browser
rehearsal once the owning lanes deliver their artifacts. No estimate is given
for the scientific experiment itself.
