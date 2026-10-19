# Claude handoff: integrate and finish AETHER

## Urgent deadline override: submission due in six hours

The user has a six-hour deadline. This overrides the open-ended execution schedule below, not scientific integrity or required gate rules. Start by recording the actual deadline and remaining time. Deliver a reviewable, runnable submission before it. Do not promise that the full registered experiment will finish within this window.

Prioritize a verified integrated prototype using the existing EMIT sample, complete provenance, a reproducible demo and an honest status/evidence package. Treat full scientific completion as a separate acceptance state. Preserve the accepted original demo as a recovery artifact throughout.

Suggested elapsed-time budget (adjust using actual progress):

- 0:00–0:30: inventory current branches/dirty changes and choose the integration base. Read existing diffs and authoritative evidence; avoid repeating the entire audit. Establish the submission run commands and blockers.
- 0:30–2:00: fix nullable retrieval time, integrate ingestion, generate/hash the pinned sample, wire base config, complete essential export lineage, and obtain the first actual data-backed run. If blocked, report the exact error immediately and work on independent delivery tasks.
- 2:00–3:00: integrate checker/orbit/UI changes, verify source identity and produce the data-backed demo/API display. Reuse valid cached geometry and existing scientific artifacts only when their identities match. Preserve capacity failures and the synthetic G4.5 failure explicitly.
- 3:00–4:30: run combined required checks and focused deterministic replay/export/API/browser acceptance; run a bounded integrated scientific pilot only if it will not jeopardize delivery. Measure runtime before starting larger matrices. Report incomplete checks as incomplete.
- 4:30–5:15: fix submission-blocking regressions, finish the requirements/evidence matrix and documentation. Prepare scope/scenario decisions with concrete evidence if required. Do not alter scientific parameters or thresholds to conceal failures.
- 5:15–6:00: freeze submission changes, package artifacts/checksums and a clean-checkout quickstart, perform a final smoke/reload check, and deliver with a time buffer. Avoid new nonessential features or long experiments during this buffer.

Do not launch the 360-reference, 900-development or full holdout matrices merely because they appear later in this prompt. Start them only if measured throughput, scientific prerequisites and remaining deadline justify them. Never bypass protocol freeze or human scientific decisions to fit the deadline. A small development pilot must be labelled as such and cannot replace calibration, all-family G4.5 or holdout acceptance.

Minimum submission package: runnable integrated code and exact revision; checked-in permitted pinned sample and manifest; one actual data-backed demonstration with explicit historical versus simulated provenance; verified input hashes and export reload; measured timing where available; exact check results; original failed-gate evidence; requirements-to-evidence matrix; and a clear list of pending science or acceptance criteria. If an integrated acceptance item cannot finish, deliver the best verified artifact and state its limitation prominently. Do not describe a failed or unrun gate as passed.

You are the lead integrator for AETHER. Fix the known implementation and integration gaps, produce a usable reproducible prototype using the already downloaded EMIT inputs, and carry the scientific workflow as far as its registered gates permit. Do the work; do not stop at another audit or plan. Preserve negative results and distinguish implementation completion from scientific acceptance.

## Authorization and working rules

The user authorizes local implementation fixes, integration of the existing lane work, local commits needed for a reviewable integration and scientific freeze, tests, development experiments, artifact generation, and documentation updates. Do not push, publish, send external messages, delete original downloaded inputs, rewrite Git history, or run holdout before a valid scientific freeze. Required scientific scenario decisions and final human sign-offs remain explicit decisions; prepare concrete evidence and options before asking.

Work autonomously on all independent authorized tasks while a scientific decision is pending. Do not repeatedly request permission for routine reversible work. Do not spawn agents unless the user or applicable instructions explicitly authorize delegation. Read applicable AGENTS.md/CLAUDE.md and skills before working in their scope. Treat this handoff as an integration assignment spanning the existing lanes; document that assignment in Work_Plan so old lane boundaries do not prevent necessary integration. Preserve each lane's authorship and independent verification evidence.

## Read first and establish current state

- `docs/completion-audit-2026-10-18.md` in `/home/itsskiweee/Projects/AETHER-codex1`.
- `AGENTS.md`, `CLAUDE.md`, `Implementation/Work_Plan.md`, `Implementation/Parameter_Register.md`, `Implementation/PRD_Amendments.md`, the completion prompt and applicable PRD acceptance requirements.
- Latest completion reports in each worktree, `docs/dataset-interface.md`, validation report, protocol and model cards. Do not trust copied status reports over newer source/results.
- Use `git worktree list`, branch ancestry, status and diffs to choose the current integration base. At audit time `AETHER-wt/claude-1` main was `302d0b0`; do not reset or overwrite it if it has advanced.

Known worktrees under `/home/itsskiweee/Projects`:

| Path | Role and audit-time state |
|---|---|
| `AETHER` | Preserved original offline demo, `ee87199` |
| `AETHER-wt/claude-1` | Main integration, `302d0b0`; dataset wiring, timing/cache, scientific drivers |
| `AETHER-codex1` | Ingestion parser/inventory/pinned loader/preparer; uncommitted changes and staged bulk raw removals |
| `AETHER-codex2` | Orbit capacity utility/tests, reports and candidate windows; uncommitted |
| `AETHER-codex3` | Independent checker hardening, tests and witness utility; uncommitted |
| `AETHER-codex6` | Combined UI/API work; uncommitted. `completion-codex-4.md` is newer than `completion-codex-6.md` |
| `AETHER-c2` | Science branch `886336e`, including C2-06 failed synthetic pilot not yet on main at audit time |
| `AETHER-c2b` | Timing aggregation `1c3e89f`, already represented on main at audit time |

Capture a concise initial integration inventory and preserve dirty work before transferring it. Do not blindly merge whole old worktrees, duplicate already merged commits, commit dependency symlinks, or overwrite concurrent edits. Use reviewed commits or carefully scoped patches, reconcile conflicts, and retain the original accepted demo as historical evidence.

## 1. Fix the actual ingestion blocker and prepare the dataset

The raw data are present. The blocker is a metadata schema incompatibility, not a finding that the files are corrupt or scientifically rejected:

`backend/aether/contracts/models.py::DataSource.retrieved_at_utc` currently requires an aware datetime. `ingestion/prepare_pinned.py` correctly passes None because the actual download timestamp was not retained, then deliberately stops when the contract rejects it.

1. Implement the previously requested nullable retrieval time (`UtcDatetime | None`, preserving strict UTC validation for non-null values). Update relevant schema/contract round-trip coverage and consumers; do not invent a timestamp from filenames, mtimes or the Git commit date. Keep the field explicit in serialized provenance.
2. Integrate actual-schema parsing, inventory, pinned loader and preparer from codex1. Confirm observed field aliases, kg/hr-to-kg/h identity, nullable rates, raw identity/geometry and conservative UNKNOWN uncertainty semantics.
3. Locate the raw directory, reported as `data/raw/EMITL2BCH4PLM_002-20261018_042728/`. Verify local paths and inventory rather than downloading again. Reported counts are 1,686 JSON/TIFF pairs; 155 regional records, 73 numeric and 82 missing rates. Reconcile discrepancies rather than forcing these counts.
4. Generate the deterministic 20-record Permian sample (10 quantified/10 missing), normalized `PlumeObservation` array, selected raw pairs and `data/manifests/emit_permian.json`. Verify expected inventory hash and all raw/normalized hashes, sizes, identities, duplicates, regional bounds and cluster counts. Record missing retrieval evidence as PARTIAL/unknown.
5. Keep original raw inputs untouched. Keep bulk downloads ignored; retain the permitted selected sample pairs as tracked reproducible inputs so a fresh checkout can run the demo. Review staged bulk removals carefully: removing files from the Git index must not delete local originals. No history rewrite.

Acceptance: final loader succeeds offline on the selected dataset, malformed/tampered inputs fail clearly, null-rate/null-retrieval records validate honestly, and a clean checkout contains everything required for the pinned sample.

## 2. Complete integration and lineage

1. Configure base/family inputs to select the final manifest and expected SHA-256. Keep explicit documented synthetic-only operation. An explicitly selected missing/invalid dataset must fail, never silently fall back.
2. Verify windows, simulate and the default benchmark all use the same source-resolution path. Ensure each comparison uses policy-independent regional deduplication/clustering and seeded fill. Historical observations provide locations/context only: they never initialize truth flux, present-day activity or unreviewed fitted priors.
3. Check `RunRecord.input_dataset`, DATA_READY events, counts and exported evidence agree with actual sources. Preserve separate REAL_OBSERVATION, MODEL_INFERENCE, SIMULATED_OBSERVATION and SIMULATED_GROUND_TRUTH semantics.
4. Fix CLI `_dataset_inputs`: at audit time it returned only the manifest. Enumerate and hash the manifest, normalized input and selected raw files in export `input_sha256`, with transformation/config/code identities. Validate input lineage at the appropriate export boundary; reject missing or altered required evidence. Ensure paths are portable and no arbitrary manifest path escapes the repository.
5. Add the promised benchmark synthetic-only switch or explicitly reconcile the interface with a documented supported equivalent; avoid misleading flags that do not reach the runner.
6. Integrate performance and UI consumers using the actual final schemas. Keep deterministic RunRecord bytes independent of timing. Never show zero as measured solver time; distinguish whole-run, window-generation and policy-planning measurements.
7. Resolve the outstanding `greedy_insert(now_utc=...)` handoff: inspect every production/reference/test caller. Remove the silent historical-source-cap bug without breaking completed-commitment resource accounting.

Acceptance: fresh pinned-data development runs, identical-source policy comparisons, explicit synthetic-only runs, missing/tamper failures, byte-identical replay and successful export reload with complete hashes.

## 3. Establish capacity on the actual integrated scenario

1. Integrate orbit candidate generation and independent checker changes without weakening checker independence or importing production solver/policy logic into the checker.
2. Reconcile candidate source IDs and coordinates with the final normalized source construction. Regenerate windows if inputs differ. Review/publish the named golden-window artifact through independent verification; do not promote it solely because generation succeeded.
3. Measure G1-F: at least five qualifying passes/72 h and at least four feasible acquisitions/pass under the registered definition. Report qualifying versus all window groups and all individual pass capacities. Distinguish candidate option counts, checker-valid witnesses and proven optimal per-pass capacities.
4. Preserve the existing historical-location result: seven passes, one with only two acquisitions, failing the registered per-pass threshold. Verify whether it applies unchanged to the final source scenario. Do not substitute the passing synthetic candidate or average away the failing pass.
5. Do not add independent per-pass capacities into a mission throughput claim without cross-pass resource carryover analysis.
6. If final G1-F fails, prepare the smallest defensible scenario/scope options with evidence and scientific implications. Obtain the required decision before changing registered parameters or acceptance thresholds. Continue independent integration and verification work while waiting.

## 4. Complete development science and handle failed gates honestly

1. Integrate C2-06 and retain its authoritative synthetic m0 pilot artifact: `AETHER-c2/experiments/results/g45-pilot-synthetic-m0/gate.json`. It used 30 development seeds, no pinned dataset, and zero reference checker violations. Gap = 0.0047610338; paired SD = 0.0220548674; threshold = 0.0441097347; verdict FAIL. This is useful negative evidence, not final real-data acceptance.
2. Fix stale report contradictions: distinguish old demo comparisons, the completed failed synthetic pilot, and the still-pending wired all-family gate. Inspect any h168 diagnostic output; do not assume it completed or passed.
3. Resolve D9 family scope explicitly; the proposed rule is all six protocol families on all 30 development seeds. Preserve SD, not standard error, in the registered gate. Label the oracle as an oracle-informed greedy reference, not a proven upper bound.
4. Run an integrated pilot first. Measure machine/worker throughput, cold/warm geometry cache behavior, policy costs and resource use; estimate the remaining experiment cost before launching the full matrices.
5. Complete SCI-10 multi-seed m0 calibration using meaningful reliability and flux-coverage evidence and seed-cluster uncertainty. Having a calibration script or passing unit tests is not the acceptance result.
6. Run the approved pinned-data G4.5 scope. Report per-family paired gaps/SD, reference feasibility, capacity/demand and pass measures. If it fails, preserve the failure and prepare scenario choices for human review. Do not tune the planner, change the metric/reference or switch SD to SE just to pass.
7. After gate/scenario decisions, run the development competitor matrix and calculate required holdout count from adaptive-minus-largest paired SD per family, using 0.01 absolute Brier points and 80% power. Do not substitute oracle-minus-random variance or silently cap the result at 100. Resolve budget requirements above 100 before lock.

Planning sizes: six families × 30 seeds × two references = 360 gate runs; six × 30 × five competitors = 900 development runs; holdout = 30N competitor runs. Reuse only records whose complete identities match. Do not claim these are all required additional runs if valid reusable records already exist.

## 5. Implement and enforce a scientific freeze before holdout

Current `verify_git_lock` verifies the protocol file and a containing Git tag; it does not enforce matching current scientific inputs. Matrix cache hashes alone do not provide this freeze.

1. Define a committed scientific identity manifest binding protocol, family/base configs, dataset manifest/normalized/raw inputs, transformations, tuning/holdout seed lists, relevant code and result-affecting pinned ephemeris/EOP and package environment.
2. Make holdout entry verify the reviewed freeze identity and reject result-affecting drift or dirty scientific inputs. Avoid self-referential commit hashes; define code/file identity and tag relationships precisely. Test changes to configs, code, data and seeds against the guard.
3. Prepare the concrete protocol, gate/calibration evidence, power calculation and compute budget for the required scientific decision. Then commit/tag the approved lock before any holdout execution. No retrospective lock.
4. Run holdout only after these conditions are met. Report all six registered families, five competitors, primary adaptive-versus-largest and equally prominent adaptive-versus-greedy comparisons, paired CIs, multiplicity adjustment, denominators, censoring, seed counts, feasibility and genuine timing. Negative registered results are valid completed experiments.

## 6. Finish UI, combined verification and delivery

1. Integrate the combined UI/API patch, using the newer codex4 handoff as local evidence and preserving later corrections. Keep old runs explicitly unpinned/synthetic-only; never attach the current project dataset to historical runs.
2. Rehearse actual new pinned-data artifacts through production API/browser without route mocks. Show historical dates/provenance, lineage, null flux/reasons, UNKNOWN uncertainty, seeded/fill counts, simulated acquisition labels, authoritative CIs/coverage/lock state and measured/unavailable timing.
3. Run required checks on the same final integrated revision: backend offline suite, Ruff check/format, truth isolation, security/import guards, checker/oracle/geometry regressions, frontend TypeScript/build, browser and accessibility, fresh-checkout sample usability, deterministic replay and verified export reload. Report exact commands, revision, results and artifact paths. Do not combine unrelated lane pass counts into a release claim.
4. Produce a P0 requirement-to-evidence matrix with every criterion marked passed, failed, pending or explicitly reviewed out of scope. Update model cards, validation report, walkthroughs, comparison limitations and completion reports. Include negative results and unverified domain assumptions.
5. Package the evidence and checksums; request required final human G5/G6 sign-off against concrete artifacts. Inspect repository security settings only if available/authorized; otherwise report that operational item accurately. No unsolicited deployment or publication.

## Required final handoff

Return the integrated branch/commit and changed files, final sample paths/counts/hashes, each gate verdict and evidence, calibration/power/holdout status, exact combined check results, requirements matrix and artifact/archive paths. List genuine remaining decisions or blockers with the next action. Give measured compute estimates where possible and label planning estimates. Never say “complete” if implementation is done but required experiments or acceptance remain pending.
