# Offline demo rehearsal audit

Rehearsed on 17 October 2026 against the packaged `runs/demo/` artifacts. No simulations were regenerated and no application source or scientific assumptions were changed.

## Commands and results

```bash
sha256sum -c artifacts/aether-offline-demo-seed1000.tar.gz.sha256
backend/.venv/bin/python scripts/verify_demo.py runs/demo
AETHER_API_PORT=8002 AETHER_CONSOLE_PORT=4174 bash scripts/serve-demo.sh
node /tmp/aether-rehearsal-browser.mjs
```

The archive checksum passed:

```text
81c0800bdcf72b1c94d064030af19b077d0b661ad11b476665027b1823f09431  artifacts/aether-offline-demo-seed1000.tar.gz
```

The packaged and current `runs/demo/acceptance.json` files had the same SHA-256 after verification (`3cb839f9b2633482f30ef273f5e5abe8e1a81943fd2b333a57f1d0a519fc6676`). The verifier loaded both policy archives, reconstructed their beliefs, validated exported ZIP records and replay equality, and reported:

| Policy | Plans / validations | Checker violations | Acquisitions | Forecast revision | Selection change |
| --- | ---: | ---: | ---: | ---: | --- |
| `largest_first` | 40 / 40 | 0 | 35 | 10 | No |
| `adaptive_eig` | 52 / 52 | 0 | 47 | 11 | Yes |

The launcher reloaded both records with independent schedule validations and completed the production frontend build. It served the API on `127.0.0.1:8002` and the console on `127.0.0.1:4174`.

Browser verification used installed Chromium (`/usr/bin/chromium`) through the local Playwright library, with no API mocks. The live console showed **SIMULATED MISSION** and loaded both seed-1000 policy records. For each policy, the Windows table rendered; Planner showed the selected `forecast_revision` plan and `0 violations`; the recorded forecast table showed the injected `FORECAST_REVISED` event; and the selected source's Beliefs evidence table rendered without `NaN`. The visible forecast revisions were 10 (`largest_first`, unchanged selections) and 11 (`adaptive_eig`, changed selections). The Comparison screen displayed **INSUFFICIENT SAMPLES** and **PRELIMINARY**; its actual evaluator report contained two seeds and marked `insufficient_samples: true`. Chromium reported no page errors. A comparison screenshot was saved outside the repository at `/tmp/aether-rehearsal-comparison.png`.

## Blockers and deviations

- The default API port 8000 and console port 4173 were already occupied; port 8001 was also occupied. The launcher ran successfully on the documented alternate-port mechanism at 8002 and 4174.
- The CUA browser provider was unavailable in this session. I used the installed headless Chromium browser directly through Playwright for the actual UI walkthrough.
- The repository's opt-in `playwright test` runner did not start a worker or Chromium and produced no test output for about 45 seconds, so I stopped that runner. The direct Playwright browser walkthrough then completed successfully against the same live console and API. Its first comparison assertion matched several visible “INSUFFICIENT SAMPLES” labels; I narrowed the locator and reran the complete walkthrough successfully.

I stopped the launcher with Ctrl-C. Ports 8002 and 4174 were closed afterward; the pre-existing services on 8000, 8001, and 4173 remained running and untouched.
