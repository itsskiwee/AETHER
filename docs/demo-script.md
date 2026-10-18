# AETHER three-minute demo script

This walkthrough uses the saved seed-1000 run records in `runs/demo/`. It is a simulated mission replay. Have the console running before recording so the three-minute presentation does not include installation or generation time.

## Timed walkthrough

| Time | Exact navigation | Presenter notes |
|---|---|---|
| 0:00–0:20 | Open `http://127.0.0.1:4173`. In the run selector, choose `largest_first` with seed `1000`. | “AETHER is a simulated methane-observation planner. This console replays saved, seeded simulation records; it does not task real spacecraft.” Point out **SIMULATED MISSION**, **OFFLINE ARTIFACTS**, and **REPLAY**. |
| 0:20–0:40 | In the run selector, choose `adaptive_eig` with seed `1000`. | “Here is the second policy on the same demo scenario and seed. Each run records 20 synthetic source hypotheses and 1,483 generated windows.” |
| 0:40–1:00 | Press `3` for **Windows**. Inspect the spacecraft-window view and feasible-options table; toggle rejected windows to show rejection reasons. | “The planner has to work with constrained observation opportunities. A rejected or unavailable opportunity is not evidence that a source was inactive.” |
| 1:00–1:18 | Press `5` for **Planner**. In the run selector choose `largest_first`; select forecast revision `10`. | “The scripted forecast refresh is recorded at simulation hour 20. In this run, revision 10 retains the same selections.” |
| 1:18–1:52 | In the run selector choose `adaptive_eig`. In **Planner**, select forecast revision `11`; expand **Recorded forecast events** and compare its option IDs with the preceding revision. | “This adaptive run changes selections after the refreshed forecast: 11 option IDs leave and 9 enter, with the same 16 candidate windows. The refresh advances forecast issuance from hour 18 to hour 20 and updates estimates for other sources. The event targets `source-001`, which has no feasible window during hours 20–32, so this does not demonstrate avoiding that source's scripted cloud interval.” |
| 1:52–2:12 | Press `4` for **Beliefs**. In the source selector choose `source-005`, which has three acquisitions in this run; open its values and evidence ledger. | “The adaptive run has 47 acquisitions: 10 detections, 23 valid non-detections, and 14 invalid acquisitions. Valid non-detections are evidence; invalid acquisitions are kept distinct.” |
| 2:12–2:37 | Press `6` for **Comparison**. Show the policy rows, sample counts, paired differences, and preliminary / insufficient-samples label. | “This view reads the separate base-config comparison: three policies across two development seeds, six runs total. Two seeds are insufficient to establish which policy is better, so these results remain preliminary.” |
| 2:37–2:55 | Press `7` for **Method**. Show the configuration and code identity, provenance, and limitations. | “The saved records preserve how the run was configured and what evidence is simulated. The demo uses synthetic inputs and does not represent real satellite operations or measured emission reductions.” |
| 2:55–3:00 | Return to the overview if desired. | “AETHER makes the planning choices and their evidence inspectable; larger, locked, held-out evaluation remains future work.” |

## Recording checklist

- Install the backend and frontend dependencies and confirm `data/ephemeris/de421.bsp` is present. Installation may need package-registry access; the prepared demo generation and replay run offline.
- Confirm `runs/demo/acceptance.json` exists and names `configs/demo.yaml`, seed 1000, both policies, and successful replay and export reload. The expected counts are 40 plans / 35 acquisitions for `largest_first` and 52 plans / 47 acquisitions for `adaptive_eig`; both have zero checker violations.
- If the known-good artifacts are missing, generate them from the repository root with `bash scripts/demo.sh`. This also runs the separate base-config comparison; that comparison alone took 631.763 seconds in the recorded delivery, so allow additional time for simulation and replay generation.
- Start the console from the repository root with `bash scripts/serve-demo.sh`, then open `http://127.0.0.1:4173`. The launcher starts the read-only API on port 8000 and the console on port 4173. If needed, set alternate ports, for example: `AETHER_API_PORT=8001 AETHER_CONSOLE_PORT=4174 bash scripts/serve-demo.sh`.
- Rehearse the navigation and keep the **SIMULATED MISSION**, **OFFLINE ARTIFACTS**, and **REPLAY** labels visible when introducing the console.
- Check microphone and screen capture levels, silence notifications, and confirm the browser is showing the local console. Keep `runs/` output and the recording outside Git.
- Keep a copy of the run archive and checksum available for the backup replay below.

## Backup replay instructions

Package the known-good artifact directory outside Git and record its checksum:

```bash
mkdir -p artifacts
tar -czf artifacts/aether-offline-demo-seed1000.tar.gz -C runs demo
sha256sum artifacts/aether-offline-demo-seed1000.tar.gz > artifacts/aether-offline-demo-seed1000.tar.gz.sha256
```

Copy the archive and `.sha256` file to the backup installation. Install the repository dependencies there and ensure the pinned ephemeris file is present. From the repository root, extract, verify, and serve the saved records:

```bash
mkdir -p runs
tar -xzf artifacts/aether-offline-demo-seed1000.tar.gz -C runs
sha256sum -c artifacts/aether-offline-demo-seed1000.tar.gz.sha256
backend/.venv/bin/python scripts/verify_demo.py runs/demo
bash scripts/serve-demo.sh runs/demo
```

Open `http://127.0.0.1:4173`. This replays the packaged records; it does not require rerunning the simulation or comparison. Dependencies must already be installed. If the backup machine uses different local ports, set `AETHER_API_PORT` and `AETHER_CONSOLE_PORT` on the launcher command.
